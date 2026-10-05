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
import secrets
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from .ai import AllEnginesFailed, analyze_with_chain
from .ai.base import DEFAULT_LIMIT, UNCATEGORIZED
from .config import CONTENT_MODES, Config
from .extract import Unreadable, detect_type, extract
from .model import Extracted, Note, QueueEntry
from .net import fetch
from .queue import Locked, Queue
from .urls import link_id, normalize
from .vault import (
    ProtectedNote,
    categories,
    ensure_inside_root,
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
# The same notice for a note that keeps no body, where the one above would
# promise a "contenido original" section the file does not have.
TRUNCATED_SUMMARY = {
    "es": "\n\n(La página era más larga de lo que entra en el modelo: "
          "el resumen se hizo sobre su primera parte.)",
    "en": "\n\n(The page was longer than the model takes: the summary covers "
          "its first part only.)",
}
# A cover is only saved if what came back really is an image we know: a default
# extension would file an HTML error page away as cover.jpg.
EXTENSIONS = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
NO_LOCK = ("the queue could not be locked, so the link was saved without one "
           "({reason})")
NO_ENTRY = ("the queue entry could not be written ({reason}), so `oknowledge "
            "retry` will not see this link")
NO_STATUS = ("the note was saved, but its queue status could not be recorded "
             "({reason})")
KEPT_NOTE = ("the note already saved was left as it is: a failed re-analysis "
             "never replaces a finished note")
RECONCILED = ("the note is already saved and finished, so the queue entry was "
              "brought into line with it instead of re-analysing the link")
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

    It is still a write into the vault, so it passes the same containment rule
    as every other one. write_bytes() follows symlinks: an attachments/ that
    the user symlinked elsewhere -- an ordinary Obsidian habit -- would put the
    file outside the managed folder, and a symlink named <link_id>.jpg would
    let the download replace whatever it points at.
    """
    if not url:
        return None
    try:
        got = fetch(url, timeout=COVER_TIMEOUT, max_bytes=COVER_MAX_BYTES)
        suffix = EXTENSIONS.get(got.content_type.split(";")[0].strip().lower())
        if suffix is None:
            return None                      # not an image: an error page, most likely
        wanted = cfg.attachments_dir / f"{link}{suffix}"
        if wanted.is_symlink():
            return None                      # never write through somebody's link
        target = ensure_inside_root(cfg, wanted)        # location first, as everywhere
        target.parent.mkdir(parents=True, exist_ok=True)
        # Temp file plus os.replace, like every other write here: a cover the
        # note already points at is never left half overwritten.
        tmp = target.parent / f".oknowledge-{secrets.token_hex(8)}.tmp"
        try:
            tmp.write_bytes(got.content)
            os.replace(tmp, target)
        finally:
            tmp.unlink(missing_ok=True)
    except Exception:
        return None
    return f"../attachments/{link}{suffix}"


ICON_TIMEOUT = 8.0
ICON_MAX_BYTES = 512 * 1024
ICON_EXTENSIONS = dict(EXTENSIONS, **{"image/gif": ".gif",
                                      "image/x-icon": ".ico",
                                      "image/vnd.microsoft.icon": ".ico"})
_DOMAIN_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789.-")


def _is_domain(name: str) -> bool:
    """A domain we would write back unchanged as a file name, and no other."""
    return (1 <= len(name) <= 253
            and set(name) <= _DOMAIN_CHARS
            and name[0].isalnum() and name[-1].isalnum()
            and ".." not in name and "-." not in name and ".-" not in name)


def download_icon(cfg: Config, source: str | None) -> None:
    """Save a site's favicon once per domain, or do nothing at all.

    Keyed by the domain rather than the link, for two reasons. Twenty notes
    from one site share an icon, so this is one request instead of twenty. And
    nothing is written into a note: there is no new frontmatter key, so a
    backfill over an existing library touches none of the user's files, which
    the status invariant would otherwise forbid.

    Catches everything, like download_cover: an icon is decoration and must
    never cost somebody a note. The domain arrives from frontmatter the user
    can edit and becomes a file name, so it is validated before it becomes one.
    """
    if not source:
        return
    domain = source.strip().lower()     # domains are case-insensitive; one site,
    if not _is_domain(domain):          # one file, and never a silent nothing
        return
    icons = cfg.attachments_dir / "icons"
    try:
        # Any suffix counts as "we have this one": fetching once is the point.
        if next(icons.glob(f"{domain}.*"), None) is not None:
            return
    except OSError:
        return
    try:
        got = fetch(f"https://{domain}/favicon.ico",
                    timeout=ICON_TIMEOUT, max_bytes=ICON_MAX_BYTES)
        suffix = ICON_EXTENSIONS.get(got.content_type.split(";")[0].strip().lower())
        if suffix is None:
            return               # a site with no favicon answers with its 404 page
        wanted = icons / f"{domain}{suffix}"
        if wanted.is_symlink():
            return               # defence in depth behind the check above
        target = ensure_inside_root(cfg, wanted)        # location first, as everywhere
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.parent / f".oknowledge-{secrets.token_hex(8)}.tmp"
        try:
            tmp.write_bytes(got.content)
            os.replace(tmp, target)
        finally:
            tmp.unlink(missing_ok=True)
    except Exception:
        return


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
    trouble: list[str] = []

    with ExitStack() as stack:
        try:
            stack.enter_context(q.lock(link))
        except Locked as error:
            # Expected, not a failure: somebody else has this link. The queue
            # was left exactly as it was, and a later retry will finish it.
            return Result(id=link, url=clean, path=None, status="pending",
                          error=str(error))
        except OSError as error:
            # The state tree is unwritable while the vault -- usually on
            # another filesystem -- is perfectly fine: a full /home, a locks/
            # left root-owned by one sudo run, an unmounted XDG_STATE_HOME.
            # The queue is bookkeeping; the note is the durable artifact. So
            # carry on without the lock, which gives up mutual exclusion
            # deliberately: a duplicated note is recoverable, a lost link is
            # not, and this module exists for the second rule.
            trouble.append(NO_LOCK.format(reason=_typed(error)))

        # The scan belongs inside the lock. From outside it, it can miss a note
        # another process is halfway through writing, and we would then write a
        # second file for the same link: one URL listed twice in the index, in
        # a tool whose whole point is that links stop piling up unfindably.
        found = find_note(cfg, link)
        # One shape for every path a Result can carry: find_note() reports the
        # path it globbed and write_note() the resolved one, so a vault reached
        # through a symlink would otherwise give two spellings for one note.
        existing = (found[0].resolve(), found[1]) if found else None
        if existing and not reprocess:
            path, note = existing
            return Result(id=link, url=clean, path=path, status=note.status,
                          skipped=True, warnings=trouble)

        mode, complaints = _mode(cfg, content, existing[1] if existing else None)
        trouble += complaints

        try:
            # enqueue() overwrites, so it belongs inside the lock too: queueing
            # a link another process holds would reset its entry to pending and
            # throw away the title and error it had recorded.
            q.enqueue(link, clean, mode)
        except OSError as error:
            trouble.append(NO_ENTRY.format(reason=_typed(error)))

        # _process() is not guarded: an OSError from the vault is a real
        # failure to report, and retry() turns it into a failed Result.
        result = _process(cfg, q, link, clean, mode, engine, existing)
        result.warnings = [*trouble, *result.warnings]
        return result


def _mode(cfg: Config, content: str | None, existing: Note | None) -> tuple[str, list[str]]:
    """The content mode to save under, and anything the user should hear about.

    The mode reaches here from the queue's JSON file, which the QML widget
    reads and a user can therefore hand-edit, and from a note's frontmatter,
    which they edit by design. Anything other than "full" means "keep no body",
    so an unknown value must not be taken at face value. An existing note's own
    mode is inherited, so a plain --reprocess under a `summary` default does not
    quietly discard a body that is already saved.
    """
    wanted = content or (existing.content if existing else None) or cfg.default_content
    if wanted in CONTENT_MODES:
        return wanted, []
    return cfg.default_content, [
        f"{wanted!r} is not a content mode, so {cfg.default_content!r} was used"
    ]


def _process(cfg: Config, q: Queue, link: str, url: str, mode: str,
             engine: str | None, existing: tuple[Path, Note] | None) -> Result:
    # Reprocessing rewrites the note already on disk, whatever the new title
    # would have named it: a second file carrying the same id is the duplicate
    # link that find_note() exists to prevent.
    target = existing[0] if existing else None
    # A note that is not ours-and-unfinished is the user's content. Somebody who
    # asks to reprocess is asking for more, not less, so when there is nothing
    # to put in its place it is left alone and only the attempt is recorded.
    # The test is inverted on purpose: `status: partial` is the one value we
    # write ourselves to mean "unfinished", and this vault is edited by hand, so
    # a `status: done` or `status: reviewed` of the user's -- or a deleted status
    # line, which reads back as ok -- has to fall on the protected side.
    kept = existing[1] if existing and existing[1].status != "partial" else None

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
        # Only the full-content note keeps the text the longer notice promises.
        notice = TRUNCATED if mode == "full" else TRUNCATED_SUMMARY
        summary += notice.get(cfg.language, notice["en"])

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
    left untouched and only the queue records the attempt. The Result still
    reports the failure, since that is what this call did; the entry describes
    the link, which is finished either way.

    Otherwise the partial note is written as usual: partial over partial is
    idempotent, and partial over nothing is the rule that a link is never lost.
    """
    if kept is not None:
        # The durable truth is that this link is saved and analyzed and there is
        # no unfinished work left, so the entry is ok and the reason the last
        # attempt failed stays in `error` for anyone who looks. Anything in
        # UNFINISHED would have every retry() re-attempt it forever and leave
        # the user a row they can never clear. It has to be set explicitly:
        # add() enqueued inside the lock, which reset the entry to pending, and
        # pending would feed it to orphaned() -- worse churn still.
        trouble = _record(q, link, "ok", reason, kept.title)
        return Result(id=link, url=url, path=target, status="failed", error=reason,
                      warnings=[KEPT_NOTE, *trouble])
    note = _partial_note(cfg, link, url, mode, page)
    return _save(cfg, q, link, url, note, "partial", reason, None, target)


def _save(cfg: Config, q: Queue, link: str, url: str, note: Note, status: str,
          error: str, engine: str | None, target: Path | None) -> Result:
    """Write the note, record its status, fix its name, rebuild the indexes.

    The order is the point. The queue is what a retry reads and the indexes are
    derived data, so reindexing before the status would let a full disk leave a
    finished note on disk with its entry still saying pending. The rename comes
    before the reindex so the wikilinks name the file that actually exists.

    Only write_note() may raise: see _record() for why the status may not.
    """
    path = write_note(cfg, note, cfg.language, path=target)
    warnings = _record(q, link, status, error, note.title)
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
    wanted = f"{note_stem(note)}.md"
    squatted = (f"the note kept the name {path.name}: another file already "
                f"holds {wanted}")
    ideal = _usable_name(cfg, cfg.links_dir / wanted)
    if ideal is None:
        return path, squatted
    if ideal == path:
        return path, None
    if ideal.exists():
        try:
            taken = read_note(ideal)
        except Exception:
            # A file pathological enough to break the reader is not a name we
            # can take. vault._read_marked() does not catch RecursionError,
            # which queue.get() guards for, so the shape is known to exist --
            # and this runs after the note and its status are already safe, so
            # raising here would lose the caller its Result.
            taken = None
        if taken is None or taken.id != note.id:
            # A file of the user's, or one of ours we cannot read. Our own name
            # is already correct and unique, so leave both alone -- but say so,
            # or the user is left with an oddly named note and no explanation.
            return path, squatted
    try:
        os.replace(path, ideal)
    except OSError as error:
        # The note is written and its status recorded; only the name is wrong.
        return path, (f"the note stayed as {path.name}: it could not be renamed "
                      f"to {ideal.name} ({_typed(error)})")
    return ideal, None


def _usable_name(cfg: Config, ideal: Path) -> Path | None:
    """The resolved ideal path, if it really is a free name in the links folder.

    The name is resolved before anything moves onto it, so a symlink sitting
    there decides where the note lands: one pointing out of the vault sent it
    outside <vault>/oknowledge/, the one thing the vault module refuses to do,
    and one pointing back inside gave the note a name of the symlink's own
    choosing. (rename(2) does not follow a destination symlink -- it would have
    replaced the link itself, destroying a file of the user's instead.) Either
    way the name is not ours to take. write_note() checks the same containment
    rule before every write, and the rename has to as well, or it is less safe
    than the call whose output it moves.
    """
    if ideal.is_symlink():
        return None
    # Defense in depth: note_stem() emits [A-Za-z0-9-] only, so no name it
    # builds can reach out of the folder and nothing below can fire today. It
    # is here so that a change to that character class cannot quietly become a
    # write outside the vault, and the test pins the invariant that way round.
    try:
        resolved = ensure_inside_root(cfg, ideal)
    except (ProtectedNote, OSError):
        return None
    return resolved if resolved.parent == cfg.links_dir.resolve() else None


def _record(q: Queue, link: str, status: str, reason: str,
            title: str | None) -> list[str]:
    """Record the entry's final status, or report that it could not be.

    The same reasoning as the lock and the entry in add(): the queue is
    bookkeeping and the note is the durable artifact. With an entry already on
    disk this call reaches atomic_write, so a read-only or full state tree
    raises here -- after the note is written, and before the rename and the
    reindex. Raising would leave the user a correct note under its old name,
    missing from every index, and no Result at all.
    """
    try:
        q.set_status(link, status, error=reason, title=title)
    except OSError as error:
        return [NO_STATUS.format(reason=_typed(error))]
    return []


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
    return [
        *(f"the index {path.name} was left as it is: another file holds that name"
          for path in done.blocked),
        # A marked note of ours that cannot be parsed is missing from every
        # index, and it is the same hand-broken note that makes find_note()
        # blind and lets a second file for the link through. We cannot identify
        # it, so the least we can do is say it is there.
        *(f"the note {path.name} is ours but could not be read, so it is in no index"
          for path in done.skipped),
    ]


def _reconcile(cfg: Config, q: Queue, entry: QueueEntry) -> Result | None:
    """Settle one owed entry against the note on disk, without re-analysing.

    Returns the Result when the entry was settled, or None when the link
    really does still owe work and add() should take it from here.

    This exists because of one reachable sequence. add() writes the note, the
    process dies before its final set_status -- the Omarchy shell restarting
    mid-save is enough, and its own notes call that normal -- so the entry
    stays pending and orphaned() offers it to every retry from then on. Days
    later the user has edited that note by hand. A retry whose extraction and
    analysis both succeed would write a fresh note straight over it: _process()
    computes `kept` for exactly this, but only _give_up() ever reads it, so the
    guard covers the failure paths and not the one that writes.

    So: the queue is bookkeeping and the note is the durable artifact, and when
    they disagree while the note is complete, the bookkeeping is what is wrong.
    The entry becomes ok and the note is not touched. `status: partial` is the
    one value we write to mean unfinished, so it is the only one still
    re-analysed -- a `done` of the user's, or a deleted status line, which
    reads back as ok, falls on the protected side. That is the same test
    _process() makes, now made before anything can be written.

    An explicit reprocess is untouched: asking for a fresh analysis is asking
    for the note to be replaced, and both ways of asking (the web's button,
    which confirms, and a hand-typed `add --reprocess`) still do exactly that.

    The accepted trade-off: a link saved at `summary` whose entry asked for
    `full` stays at summary until somebody asks again, explicitly. A user's
    hand edits are worth more than an automatic depth upgrade.
    """
    # The note at risk is the one add() would write over, which is keyed by the
    # url, while the entry we have been asked to settle is keyed by its file
    # name. For an entry we wrote they are the same id.
    link = link_id(normalize(entry.url))
    with ExitStack() as stack:
        try:
            stack.enter_context(q.lock(link))
        except Locked as error:
            # Somebody is working on this link right now and will record what
            # happened. Nothing to do, and nothing to report but why.
            return Result(id=entry.id, url=entry.url, path=None, status="pending",
                          error=str(error))
        except OSError:
            # An unlockable state tree. add() carries on without the lock
            # because a lost link costs more than a duplicated one -- but here
            # carrying on would mean overwriting a finished note, so the
            # decision is made unlocked and it can only ever protect.
            pass
        found = find_note(cfg, link)
        if found is None or found[1].status == "partial":
            return None
        path, note = found
        # The error of the last attempt stays in `error`, as _give_up() leaves
        # it: an `ok` entry's error is a note for anyone who looks, and the
        # widget shows it only on an unfinished row.
        trouble = _record(q, entry.id, "ok", entry.error or "", note.title)
        return Result(id=entry.id, url=entry.url, path=path.resolve(), status="ok",
                      skipped=True, warnings=[RECONCILED, *trouble])


def retry(cfg: Config, queue: Queue | None = None) -> list[Result]:
    """Finish every link the queue still owes, and settle the ones only the
    bookkeeping thinks are owed.

    unfinished() is partial and failed only. A process that died between
    enqueue and its final set_status leaves its entry pending, and no retry
    would ever look at it again -- the link would be lost, which is the one
    thing this module does not allow. orphaned() is exactly those abandoned
    entries, so both lists are walked, de-duplicated by id.

    Every entry goes through _reconcile() first, which never re-analyses a
    note that is already finished. Re-analysing one would replace content the
    user may have written themselves, and a retry is not a request for that.
    """
    q = queue or Queue()
    owed: dict[str, QueueEntry] = {}
    results: list[Result] = []
    for listing in (q.unfinished, q.orphaned):
        # Each listing can fail as a whole (an unreadable lock file, say) and
        # must not stop the other, nor the links already found.
        try:
            for entry in listing():
                owed.setdefault(entry.id, entry)
        except Exception as error:
            results.append(Result(id="queue", url="", path=None, status="failed",
                                  error=f"could not list the queue ({_typed(error)})"))
    for entry in owed.values():
        try:
            settled = _reconcile(cfg, q, entry)
            if settled is not None:
                results.append(settled)
                continue
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
