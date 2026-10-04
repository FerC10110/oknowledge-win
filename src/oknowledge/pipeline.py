"""From a URL to a note. The orchestrator, and the keeper of one rule:
whatever fails, the link stays saved.

Everything here is arranged around that rule. The page can be unreadable,
every engine can be down, the cover can refuse to download, the indexes can
fail to rebuild: each of those costs the user part of the note's content, and
never the note itself. What cannot be finished now is left in the queue with a
status a later `retry` picks up.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from .ai import AllEnginesFailed, analyze_with_chain
from .ai.base import DEFAULT_LIMIT, UNCATEGORIZED
from .config import Config
from .extract import Unreadable, detect_type, extract
from .model import Extracted, Note, QueueEntry
from .net import fetch
from .queue import Locked, Queue
from .urls import link_id, normalize
from .vault import categories, find_note, rebuild_indexes, write_note

PARTIAL_SUMMARY = {
    "es": "Guardado sin analizar: la página no se pudo leer o el análisis falló. "
          "Usá `oknowledge retry` para completarlo.",
    "en": "Saved without analysis: the page could not be read or the analysis failed. "
          "Run `oknowledge retry` to finish it.",
}
TRUNCATED = {
    "es": "\n\n(La página era más larga de lo que entra en el modelo: "
          "el resumen se hizo sobre su primera parte, pero el contenido está entero más abajo.)",
    "en": "\n\n(The page was longer than the model takes: the summary covers its "
          "first part only, but the full content is kept below.)",
}
# A cover is only saved if what came back really is an image we know: a default
# extension would file an HTML error page away as cover.jpg.
EXTENSIONS = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
COVER_TIMEOUT = 15.0
COVER_MAX_BYTES = 5 * 1024 * 1024


@dataclass
class Result:
    """What one add() did, as the CLI and the web report it."""

    id: str
    url: str
    path: Path | None
    status: str
    engine: str | None = None
    error: str | None = None
    skipped: bool = False
    # What went wrong around the note without costing it: an index whose name
    # another file holds, a reindex that failed outright. Reported, not
    # swallowed, because an index nobody mentions stays stale forever.
    warnings: list[str] = field(default_factory=list)


def _today() -> str:
    return dt.datetime.now(dt.timezone.utc).date().isoformat()


def _uncategorized(cfg: Config) -> str:
    return UNCATEGORIZED.get(cfg.language, UNCATEGORIZED["en"])


def _reason(error: BaseException) -> str:
    """The failure as the queue records it.

    Unreadable already reads as a sentence about the page, so it speaks for
    itself. Anything else is a surprise -- a bug in an extractor, a library or
    in us -- and keeps its type name, so it is not passed off to the user as
    "the page could not be read".
    """
    detail = str(error)
    if isinstance(error, Unreadable):
        return detail or type(error).__name__
    return f"{type(error).__name__}: {detail}" if detail else type(error).__name__


def _host(url: str) -> str:
    """The source of a note nothing could be extracted from."""
    try:
        host = urlsplit(url).hostname
    except ValueError:                       # a malformed IPv6 literal
        host = None
    return host or url or "unknown"


def download_cover(cfg: Config, url: str | None, link: str) -> str | None:
    """Save the page's cover image beside the note, or return None.

    Catches everything on purpose. The cover is decoration and it is fetched
    *after* the analysis succeeded, so a full disk or a surprise from httpx
    here would otherwise throw away a note that was ready to be written.
    """
    if not url:
        return None
    try:
        got = fetch(url, timeout=COVER_TIMEOUT, max_bytes=COVER_MAX_BYTES)
        suffix = EXTENSIONS.get(got.content_type.split(";")[0].strip().lower())
        if suffix is None:
            return None                      # not an image: an error page, most likely
        cfg.attachments_dir.mkdir(parents=True, exist_ok=True)
        (cfg.attachments_dir / f"{link}{suffix}").write_bytes(got.content)
    except Exception:
        return None
    return f"../attachments/{link}{suffix}"


def _partial_note(cfg: Config, link: str, url: str, content: str,
                  page: Extracted | None) -> Note:
    """The note that can always be written: the URL, plus whatever did arrive."""
    return Note(
        id=link,
        url=url,
        title=(page.title if page else url),
        category=_uncategorized(cfg),
        tags=[],
        type=(page.type if page else detect_type(url)),
        source=(page.source if page else _host(url)),
        saved=_today(),
        summary=PARTIAL_SUMMARY.get(cfg.language, PARTIAL_SUMMARY["en"]),
        points=[],
        status="partial",
        content=content,
        author=(page.author if page else None),
        published=(page.published if page else None),
        body=(page.text if page and content == "full" else None),
    )


def add(cfg: Config, url: str, content: str | None = None, engine: str | None = None,
        reprocess: bool = False, queue: Queue | None = None) -> Result:
    """Save one link, and say what happened to it."""
    q = queue or Queue()
    clean = normalize(url)
    link = link_id(clean)
    mode = content or cfg.default_content

    existing = find_note(cfg, link)
    if existing and not reprocess:
        path, note = existing
        return Result(id=link, url=clean, path=path, status=note.status, skipped=True)
    # Reprocessing rewrites the note already on disk, whatever the new title
    # would have named it: a second file carrying the same id is the duplicate
    # link that find_note() exists to prevent.
    target = existing[0] if existing else None

    try:
        # The lock first, the queue only inside it. enqueue() overwrites, so
        # queueing a link another process holds would reset its entry to
        # pending and throw away the title and error it had recorded.
        with q.lock(link):
            q.enqueue(link, clean, mode)
            return _process(cfg, q, link, clean, mode, engine, target)
    except Locked as error:
        # Expected, not a failure: somebody else has this link. The queue was
        # left exactly as it was, and a later retry will finish it.
        return Result(id=link, url=clean, path=None, status="pending", error=str(error))


def _process(cfg: Config, q: Queue, link: str, url: str, mode: str,
             engine: str | None, target: Path | None) -> Result:
    try:
        page = extract(url)
    except Exception as error:
        # extract() promises to raise only Unreadable, and the rule that a link
        # is never lost must not rest on that promise: a bug in trafilatura,
        # pypdf, yt-dlp or in our own dispatcher would otherwise cost the user
        # the link. _reason() keeps the type name so a real bug stays legible.
        # BaseException -- Ctrl-C, SystemExit -- passes through untouched.
        note = _partial_note(cfg, link, url, mode, None)
        return _save(cfg, q, link, url, note, "partial", _reason(error), None, target)

    try:
        analysis, used = analyze_with_chain(
            cfg, page.text, {"url": url, "title": page.title},
            list(categories(cfg)), engine=engine,
        )
    except AllEnginesFailed as error:
        # The text is already out of the page: keep it, so a retry only has to
        # ask a model again instead of fetching the page again.
        note = _partial_note(cfg, link, url, mode, page)
        return _save(cfg, q, link, url, note, "partial", str(error), None, target)

    summary = analysis.summary
    if len(page.text) > DEFAULT_LIMIT:
        summary += TRUNCATED.get(cfg.language, TRUNCATED["en"])

    note = Note(
        id=link,
        url=url,
        title=analysis.title or page.title,
        category=analysis.category or _uncategorized(cfg),
        tags=analysis.tags,
        type=page.type,
        source=page.source,
        saved=_today(),
        summary=summary,
        points=analysis.points,
        status="ok",
        content=mode,
        author=page.author,
        published=page.published,
        cover=download_cover(cfg, page.cover_url, link),
        body=page.text if mode == "full" else None,
    )
    return _save(cfg, q, link, url, note, "ok", "", used, target)


def _save(cfg: Config, q: Queue, link: str, url: str, note: Note, status: str,
          error: str, engine: str | None, target: Path | None) -> Result:
    """Write the note, record its status, then rebuild the indexes.

    The order is the point. The queue is what a retry reads and the indexes are
    derived data, so reindexing before the status would let a full disk leave a
    finished note on disk with its entry still saying pending.
    """
    path = write_note(cfg, note, cfg.language, path=target)
    q.set_status(link, status, error=error, title=note.title)
    return Result(id=link, url=url, path=path, status=status, engine=engine,
                  error=error or None, warnings=_reindex(cfg))


def _reindex(cfg: Config) -> list[str]:
    """Rebuild every index, reporting what it could not write.

    Runs with the note and its status already safe, so nothing in here can
    lose anything. rebuild_indexes() does not raise over one blocked index, but
    it does write files, so a full disk can still stop it altogether: that is a
    warning too, not a lost note.
    """
    try:
        done = rebuild_indexes(cfg, cfg.language)
    except Exception as error:
        return [f"the indexes could not be rebuilt: {_reason(error)}"]
    return [f"the index {path.name} was left as it is: another file holds that name"
            for path in done.blocked]


def retry(cfg: Config, queue: Queue | None = None) -> list[Result]:
    """Finish every link the queue still owes.

    unfinished() is partial and failed only. A process that died between
    enqueue and its final set_status leaves its entry pending, and no retry
    would ever look at it again -- the link would be lost, which is the one
    thing this module does not allow. orphaned() is exactly those abandoned
    entries, so both lists are walked, de-duplicated by id.
    """
    q = queue or Queue()
    owed: dict[str, QueueEntry] = {}
    for entry in (*q.unfinished(), *q.orphaned()):
        owed.setdefault(entry.id, entry)
    return [add(cfg, entry.url, content=entry.content, reprocess=True, queue=q)
            for entry in owed.values()]
