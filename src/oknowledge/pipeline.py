"""From a URL to a note. The orchestrator, and the keeper of one rule:
whatever fails, the link stays saved.

Everything here is arranged around that rule. The page can be unreadable,
every engine can be down, the cover can refuse to download, the indexes can
fail to rebuild: each of those costs the user part of the note's content, and
never the note itself. What cannot be finished now is left in the queue with a
status a later `retry` picks up.

The rule has one corollary, and it points the other way: a note that was
analyzed is already the user's content, so a failed attempt never replaces it
with a partial one. Saving a link must not be able to destroy one.
"""

from __future__ import annotations

import datetime as dt
import os
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
from .vault import (
    categories,
    find_note,
    note_stem,
    read_note,
    rebuild_indexes,
    write_note,
)

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
KEPT_NOTE = ("the note already saved was left as it is: a failed re-analysis "
             "never replaces a finished note")
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


def _typed(error: BaseException) -> str:
    """The failure with its class name in front, for anything that is not
    already prose written for the user."""
    detail = str(error)
    return f"{type(error).__name__}: {detail}" if detail else type(error).__name__


def _reason(error: BaseException) -> str:
    """The failure as the queue records it.

    Unreadable already reads as a sentence about the page, so it speaks for
    itself. Anything else is a surprise -- a bug in an extractor, a library or
    in us -- and keeps its type name, so it is not passed off to the user as
    "the page could not be read".
    """
    if isinstance(error, Unreadable):
        return str(error) or type(error).__name__
    return _typed(error)


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
    try:
        # The lock first, the queue only inside it. enqueue() overwrites, so
        # queueing a link another process holds would reset its entry to
        # pending and throw away the title and error it had recorded.
        with q.lock(link):
            q.enqueue(link, clean, mode)
            return _process(cfg, q, link, clean, mode, engine, existing)
    except Locked as error:
        # Expected, not a failure: somebody else has this link. The queue was
        # left exactly as it was, and a later retry will finish it.
        return Result(id=link, url=clean, path=None, status="pending", error=str(error))


def _process(cfg: Config, q: Queue, link: str, url: str, mode: str,
             engine: str | None, existing: tuple[Path, Note] | None) -> Result:
    # Reprocessing rewrites the note already on disk, whatever the new title
    # would have named it: a second file carrying the same id is the duplicate
    # link that find_note() exists to prevent.
    target = existing[0] if existing else None
    # An analyzed note is the user's content. Somebody who asks to reprocess is
    # asking for more, not less, so when there is nothing to put in its place
    # it is left alone and only the attempt is recorded. The rule is narrow: a
    # partial note never replaces an ok one.
    kept = existing[1] if existing and existing[1].status == "ok" else None

    try:
        page = extract(url)
    except Exception as error:
        # extract() promises to raise only Unreadable, and the rule that a link
        # is never lost must not rest on that promise: a bug in trafilatura,
        # pypdf, yt-dlp or in our own dispatcher would otherwise cost the user
        # the link. _reason() keeps the type name so a real bug stays legible.
        # BaseException -- Ctrl-C, SystemExit -- passes through untouched.
        return _give_up(cfg, q, link, url, mode, None, _reason(error), kept, target)

    try:
        analysis, used = analyze_with_chain(
            cfg, page.text, {"url": url, "title": page.title},
            list(categories(cfg)), engine=engine,
        )
    except AllEnginesFailed as error:
        # The text is already out of the page: keep it, so a retry only has to
        # ask a model again instead of fetching the page again.
        return _give_up(cfg, q, link, url, mode, page, str(error), kept, target)

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


def _give_up(cfg: Config, q: Queue, link: str, url: str, mode: str,
             page: Extracted | None, reason: str, kept: Note | None,
             target: Path | None) -> Result:
    """Record a failure that produced no analysis.

    With an analyzed note already on disk there is nothing to write that would
    not be worse than what is there: the note, its name and the indexes are all
    left untouched and only the queue records the attempt, which is enough to
    keep the link retryable. Otherwise the partial note is written as usual --
    partial over partial is idempotent, and partial over nothing is the rule
    that a link is never lost.
    """
    if kept is not None:
        q.set_status(link, "failed", error=reason, title=kept.title)
        return Result(id=link, url=url, path=target, status="failed", error=reason,
                      warnings=[KEPT_NOTE])
    note = _partial_note(cfg, link, url, mode, page)
    return _save(cfg, q, link, url, note, "partial", reason, None, target)


def _save(cfg: Config, q: Queue, link: str, url: str, note: Note, status: str,
          error: str, engine: str | None, target: Path | None) -> Result:
    """Write the note, record its status, fix its name, rebuild the indexes.

    The order is the point. The queue is what a retry reads and the indexes are
    derived data, so reindexing before the status would let a full disk leave a
    finished note on disk with its entry still saying pending. The rename comes
    before the reindex so the wikilinks name the file that actually exists.
    """
    path = write_note(cfg, note, cfg.language, path=target)
    q.set_status(link, status, error=error, title=note.title)
    warnings: list[str] = []
    if target is not None:
        path, trouble = _rename_to_title(cfg, note, path)
        if trouble:
            warnings.append(trouble)
    warnings += _reindex(cfg)
    return Result(id=link, url=url, path=path, status=status, engine=engine,
                  error=error or None, warnings=warnings)


def _rename_to_title(cfg: Config, note: Note, path: Path) -> tuple[Path, str | None]:
    """Move a reprocessed note onto the name its title now earns.

    Returns where the note ended up, and a warning if it could not be moved.

    A note saved while the site or the AI was down is named after its URL, and
    that is the name Obsidian's file explorer, quick switcher and graph all
    show -- the indexes render `[[stem|title]]` and read fine, the vault does
    not. Those are exactly the notes retry() finishes, so this is the common
    case and not the rare one.

    The note is rewritten in place first and only then renamed, never written
    under the new name and unlinked from the old: os.replace is atomic, so
    there is no instant at which two files carry the same id, which is the
    thing all of this exists to prevent.
    """
    ideal = (cfg.links_dir / f"{note_stem(note)}.md").resolve()
    if ideal == path:
        return path, None
    if ideal.exists():
        taken = read_note(ideal)
        if taken is None or taken.id != note.id:
            # A file of the user's, or one of ours we cannot read. Our own name
            # is already correct and unique, so leave both alone -- but say so,
            # or the user is left with an oddly named note and no explanation.
            return path, (f"the note kept the name {path.name}: another file "
                          f"already holds {ideal.name}")
    try:
        os.replace(path, ideal)
    except OSError as error:
        # The note is written and its status recorded; only the name is wrong.
        return path, (f"the note stayed as {path.name}: it could not be renamed "
                      f"to {ideal.name} ({_typed(error)})")
    return ideal, None


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

    results: list[Result] = []
    for entry in owed.values():
        try:
            results.append(add(cfg, entry.url, content=entry.content,
                               reprocess=True, queue=q))
        except Exception as error:
            # One link that cannot be written -- a full disk, or a note file the
            # user replaced with one of their own -- must not take the rest of
            # the run down with it. add() leaves the entry behind either way, so
            # nothing is lost whichever way this goes.
            results.append(_failed(q, entry, error))
    return results


def _failed(q: Queue, entry: QueueEntry, error: BaseException) -> Result:
    """Report a link add() could not finish at all, and keep it retryable."""
    reason = _typed(error)
    try:
        q.set_status(entry.id, "failed", error=reason)
    except Exception:
        # Whatever broke the note's write breaks this one too. The entry keeps
        # the status it had, and pending is the right outcome: orphaned() will
        # offer it to the next retry.
        pass
    return Result(id=entry.id, url=entry.url, path=None, status="failed", error=reason)
