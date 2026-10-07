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
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import dataclass, field, replace
from pathlib import Path
from urllib.parse import urlsplit

from .ai import AllEnginesFailed, analyze_with_chain, mentions_with_chain
from .ai.base import DEFAULT_LIMIT, UNCATEGORIZED
from .config import CONTENT_MODES, Config
from .extract import Unreadable, detect_type, extract
from .model import Extracted, Note, QueueEntry
from .net import fetch
from .queue import Locked, Queue
from .urls import link_id, normalize
from .vault import (
    ProtectedNote,
    all_notes,
    categories,
    ensure_inside_root,
    find_note,
    note_stem,
    read_note,
    rebuild_indexes,
    update_note,
    write_note,
)
from .whatsapp import Imported

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
# What import_links() leaves in a queue entry's error: the link is saved but no
# attempt has been made on it. retry() reads it back to tell those links from
# the ones it already tried, so both sides use this one string.
IMPORTED = "imported, not analysed yet"
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


def _now_iso() -> str:
    """The same format the queue writes, so the two compare as strings."""
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")


def _uncategorized(cfg: Config) -> str:
    return UNCATEGORIZED.get(cfg.language, UNCATEGORIZED["en"])


def _typed(error: BaseException) -> str:
    """The failure with its class name in front, for anything that is not
    already prose written for the user."""
    detail = str(error)
    return f"{type(error).__name__}: {detail}" if detail else type(error).__name__


def _kind(error: BaseException) -> str:
    """What a failure is, apart from which file it happened to: the class and
    its errno/strerror when it has them, so that one full disk is one kind
    however many paths it was reported against. Anything else is its own kind."""
    code, message = getattr(error, "errno", None), getattr(error, "strerror", None)
    if code is not None and message:
        return f"{type(error).__name__}: [Errno {code}] {message}"
    return _typed(error)


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


def is_domain(name: str) -> bool:
    """A domain we would write back unchanged as a file name, and no other."""
    return (1 <= len(name) <= 253
            and set(name) <= _DOMAIN_CHARS
            and name[0].isalnum() and name[-1].isalnum()
            and ".." not in name and "-." not in name and ".-" not in name)


def icon_path(cfg: Config, domain: str) -> Path | None:
    """The icon file saved for this domain, or None.

    Any suffix counts as "we have this one": fetching once per site is the
    point, and the route that serves these applies its own rules about which
    types it is willing to send.
    """
    try:
        return next((cfg.attachments_dir / "icons").glob(f"{domain}.*"), None)
    except OSError:
        return None


def backfill_icons(cfg: Config) -> tuple[int, int]:
    """Fetch the icon of every site in the vault, and say how it went.

    Returns how many distinct sites the library holds and how many of them
    have an icon now. The gap between the two numbers is the answer to "why
    does that card still show a letter": some sites simply have no favicon.

    No note is read for anything but its `source`, and none is written. That
    is the whole reason icons are keyed by domain instead of living in
    frontmatter -- see download_icon().
    """
    sites = sorted({note.source.strip().lower()
                    for note in all_notes(cfg) if note.source})
    for domain in sites:
        download_icon(cfg, domain)
    have = sum(1 for domain in sites if icon_path(cfg, domain) is not None)
    return len(sites), have


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
    if not is_domain(domain):          # one file, and never a silent nothing
        return
    if icon_path(cfg, domain) is not None:
        return
    icons = cfg.attachments_dir / "icons"
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
                  page: Extracted | None, keep: Note | None = None) -> Note:
    """The note that can always be written: the URL, plus whatever did arrive.

    `keep` is the partial note already on disk, when there is one. It answers
    one question -- what did that note already have that this attempt cannot
    better? -- for every field that has no other source: the date the link was
    saved, and the summary and body, which an import fills with the chat
    message the user wrote around the link. Rebuilding those from scratch
    replaces the user's own words with the boilerplate below, and nothing
    inside the system can undo it: the note exists, so a re-import counts the
    link `already` and never writes it again.

    A finished note never reaches here -- _give_up() writes nothing at all in
    that case -- so `keep` is ours and unfinished or it is None. Over a partial
    note this is idempotent, which may mean keeping the boilerplate a previous
    attempt left, and that is the right outcome.
    """
    return Note(
        id=link,
        url=url,
        title=(page.title if page else url),
        category=_uncategorized(cfg),
        tags=[],
        type=(page.type if page else detect_type(url)),
        source=(page.source if page else _host(url)),
        saved=(keep.saved if keep else _today()),
        summary=(keep.summary if keep else PARTIAL_SUMMARY.get(cfg.language,
                                                               PARTIAL_SUMMARY["en"])),
        points=[],
        status="partial",
        content=content,
        author=(page.author if page else None),
        published=(page.published if page else None),
        body=(page.text if page and content == "full"
              else (keep.body if keep else None)),
        # Carried like the summary: a retry that fails must not erase a section
        # an earlier run paid a model call for.
        mentions=(keep.mentions if keep else None),
        mentions_extra=(keep.mentions_extra if keep else []),
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
    finished = existing[1] if existing and existing[1].status != "partial" else None
    # The mirror of that test: our own unfinished note, which a failed attempt
    # does rewrite -- so everything it already holds and this attempt cannot
    # better has to be carried over rather than rebuilt. See _partial_note().
    keep = existing[1] if existing and existing[1].status == "partial" else None
    # A note was saved when it was saved: reanalysing it does not save it
    # again. Without this, a batch imported with its real dates would all pile
    # onto the day of the analysis. Taken from any existing note, partial or
    # not, so every branch below keeps it: the analyzed note below reads it
    # here, and the partial one through `keep`.
    kept_date = existing[1].saved if existing else None

    try:
        page = extract(url)
    except Exception as error:
        # extract() promises to raise only Unreadable, and the rule that a link
        # is never lost must not rest on that promise: a bug in trafilatura,
        # pypdf, yt-dlp or in our own dispatcher would otherwise cost the user
        # the link. _reason() keeps the type name so a real bug stays legible.
        # BaseException -- Ctrl-C, SystemExit -- passes through untouched.
        return _give_up(cfg, q, link, url, mode, None, _reason(error), finished,
                        target, keep=keep)

    try:
        analysis, used = analyze_with_chain(
            cfg, page.text, {"url": url, "title": page.title},
            list(categories(cfg)), engine=engine,
            # Only a video is asked, and only the pipeline sees both the type
            # and the config at once.
            mentions=cfg.mentions if page.type == "youtube" else None,
        )
    except AllEnginesFailed as error:
        # The text is already out of the page: keep it, so a retry only has to
        # ask a model again instead of fetching the page again.
        return _give_up(cfg, q, link, url, mode, page, str(error), finished,
                        target, keep=keep)

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
        saved=(kept_date or _today()),
        summary=summary,
        points=analysis.points,
        status="ok",
        content=mode,
        author=page.author,
        published=page.published,
        cover=download_cover(cfg, page.cover_url, link),
        body=page.text if mode == "full" else None,
        mentions=analysis.mentions if page.type == "youtube" else None,
        # Not among the things a reprocess says it replaces: what the user
        # typed in the section stays.
        mentions_extra=(existing[1].mentions_extra if existing else []),
    )
    return _save(cfg, q, link, url, note, "ok", "", used, target)


def _give_up(cfg: Config, q: Queue, link: str, url: str, mode: str,
             page: Extracted | None, reason: str, finished: Note | None,
             target: Path | None, keep: Note | None = None) -> Result:
    """Record a failure that produced no analysis.

    With an analyzed note already on disk there is nothing to write that would
    not be worse than what is there: the note, its name and the indexes are all
    left untouched and only the queue records the attempt. The Result still
    reports the failure, since that is what this call did; the entry describes
    the link, which is finished either way.

    Otherwise the partial note is written as usual: partial over partial is
    idempotent, and partial over nothing is the rule that a link is never lost.
    """
    if finished is not None:
        # The durable truth is that this link is saved and analyzed and there is
        # no unfinished work left, so the entry is ok and the reason the last
        # attempt failed stays in `error` for anyone who looks. Anything in
        # UNFINISHED would have every retry() re-attempt it forever and leave
        # the user a row they can never clear. It has to be set explicitly:
        # add() enqueued inside the lock, which reset the entry to pending, and
        # pending would feed it to orphaned() -- worse churn still.
        trouble = _record(q, link, "ok", reason, finished.title)
        return Result(id=link, url=url, path=target, status="failed", error=reason,
                      warnings=[KEPT_NOTE, *trouble])
    note = _partial_note(cfg, link, url, mode, page, keep=keep)
    return _save(cfg, q, link, url, note, "partial", reason, None, target)


def _save(cfg: Config, q: Queue, link: str, url: str, note: Note, status: str,
          error: str, engine: str | None, target: Path | None) -> Result:
    """Write the note, record its status, fix its name, rebuild the indexes.

    The order is the point. The queue is what a retry reads and the indexes are
    derived data, so reindexing before the status would let a full disk leave a
    finished note on disk with its entry still saying pending. The rename comes
    before the reindex so the wikilinks name the file that actually exists.

    The icon comes last, after the note is durable and the queue and indexes
    agree, because it is the one step whose absence costs nothing: a card with
    no favicon still shows its site's initial. It is also the only step here
    that touches the network, so going last means a slow or hanging site
    cannot delay the note it decorates. download_icon() catches everything by
    contract (see its docstring), which is why it is called bare.

    Only write_note() may raise: see _record() for why the status may not.
    """
    path = write_note(cfg, note, cfg.language, path=target)
    warnings = _record(q, link, status, error, note.title)
    if target is not None:
        path, trouble = _rename_to_title(cfg, note, path)
        if trouble:
            warnings.append(trouble)
    warnings += _reindex(cfg)
    download_icon(cfg, note.source)
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


def _once(warnings: list[str], said: set[str], template: str, reason: str) -> None:
    """Record a kind of trouble the first time it happens, and not again.

    Everything that can break a link's bookkeeping -- an unwritable locks/ or
    queue/ -- breaks it for every link of the batch, so one warning describes
    all 1215 of them and 1215 warnings describe nothing. The key is the
    template and not the finished sentence, because the reason names the file
    that failed and that is a different file for every link.
    """
    if template in said:
        return
    said.add(template)
    warnings.append(template.format(reason=reason))


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
    computes `finished` for exactly this, but only _give_up() ever reads it, so
    the guard covers the failure paths and not the one that writes.

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


@dataclass
class ImportResult:
    """What happened to an imported batch. No link leaves without showing up here."""

    found: int = 0                              # links the batch carried
    saved: int = 0                              # new notes written
    already: int = 0                            # already in the vault, or taken
    duplicated: int = 0                         # repeats within the batch
    # (url, why). An empty url is the sentinel for a failure of the whole
    # batch and of no one link -- the vault could not be read, so nothing was
    # even attempted -- and the report prints that row without the url.
    failed: list[tuple[str, str]] = field(default_factory=list)
    # url -> what kind of failure it was, where that differs from the reason
    # text (which can embed the file name). Only the report's grouping reads it.
    kinds: dict[str, str] = field(default_factory=dict)
    # What went wrong around the notes without costing one: the single index
    # rebuild this batch gets. Reported, not swallowed -- one failure here
    # leaves every note of the batch out of every index, and an index nobody
    # mentions stays stale forever.
    warnings: list[str] = field(default_factory=list)


def import_links(cfg: Config, items: list[Imported],
                 queue: Queue | None = None) -> ImportResult:
    """Write a batch of imported links as partial notes.

    This does not call add() once per link, and the reason is measured: add()
    pays two full vault scans -- find_note() to deduplicate and
    rebuild_indexes() on save -- and rewrites every index, every time. With
    1215 links that is quadratic: about 19 minutes of pure bookkeeping, plus
    1215 rounds of writes inside an Obsidian vault that syncs and reindexes on
    each one.

    Here the expensive steps are paid once for the batch. What is not made
    cheaper are the guarantees: write_note() is still the only write door, so
    it still goes through ensure_inside_root and the marker; links are
    deduplicated by id; each link's lock is taken; and each one leaves a queue
    entry so retry() can finish it.
    """
    q = queue or Queue()
    started = _now_iso()
    result = ImportResult(found=len(items))
    said: set[str] = set()          # the kinds of trouble already reported

    # One scan, not one per link. If the vault cannot be read there is no way
    # to deduplicate, and writing without deduplicating is the one thing this
    # project does not do: duplicate a note.
    try:
        existing = {note.id for note in all_notes(cfg)}
    except OSError as error:
        noun = "link" if len(items) == 1 else "links"
        result.failed.append(
            ("", f"the vault could not be read, so none of {len(items)} {noun} "
                 f"was imported ({_typed(error)})"))
        return result

    # Dedup within the batch, keeping the oldest date: that is when it was
    # first saved. normalize() already strips utm parameters, so two spellings
    # of the same link land on the same id.
    wanted: dict[str, Imported] = {}
    for one in items:
        clean = normalize(one.url)
        if not clean:
            result.failed.append((one.url, "not a usable URL"))
            continue
        link = link_id(clean)
        before = wanted.get(link)
        if before is None:
            wanted[link] = replace(one, url=clean)
        else:
            result.duplicated += 1
            if one.sent < before.sent:
                wanted[link] = replace(one, url=clean)

    mode = cfg.default_content
    for link, one in wanted.items():
        if link in existing:
            result.already += 1
            continue
        try:
            with ExitStack() as stack:
                try:
                    stack.enter_context(q.lock(link))
                except Locked:
                    # Somebody else holds this link and will finish it.
                    result.already += 1
                    continue
                except OSError as error:
                    # The call add() makes, for the reason add() gives: the
                    # state tree can be unwritable while the vault -- usually
                    # on another filesystem -- is fine, and a duplicated note
                    # is recoverable where a lost link is not. Said once: an
                    # unwritable locks/ is unwritable for all 1215 links, and
                    # 1215 copies of one sentence is not a report.
                    _once(result.warnings, said, NO_LOCK, _typed(error))
                # The queue as a cheap second index: it closes the window
                # between the scan above and now, because add() always
                # enqueues, and it is one JSON file instead of a second vault
                # scan. It only counts if the entry is from this run: a stale
                # entry from a note the user deleted must not keep that link
                # from coming back, because the vault is the source of truth
                # and the queue is only bookkeeping.
                entry = q.get(link)
                if entry is not None and entry.updated >= started:
                    result.already += 1
                    continue
                note = _partial_note(cfg, link, one.url, mode, None)
                # A link was saved when it was sent, not when it was imported.
                note.saved = one.sent
                if one.comment:
                    # The message the link came with, as the provisional
                    # summary and body. An analysis replaces both -- that is
                    # the trade the spec makes -- and a failed attempt keeps
                    # them, through _partial_note()'s `keep`.
                    note.summary = one.comment
                    note.body = one.comment
                # The entry goes in before the note, the order add() uses. A
                # crash between the two then leaves an entry with no note,
                # which orphaned() finds and retry() redoes. The other way
                # round leaves a partial note that no retry can ever reach,
                # because retry() walks the queue and not the vault.
                try:
                    q.enqueue(link, one.url, mode)
                except OSError as error:
                    # The same trade once more, one step on: with no entry no
                    # retry will ever reach this link, but the note is on disk
                    # and the user can see it, which is more than refusing to
                    # write would leave them.
                    _once(result.warnings, said, NO_ENTRY, _typed(error))
                write_note(cfg, note, cfg.language)
                try:
                    q.set_status(link, "partial",
                                 error=IMPORTED,
                                 title=note.title)
                except OSError as error:
                    # The note is on disk and safe, so the link is saved:
                    # the entry keeps the pending status enqueue() gave it,
                    # orphaned() finds it and the next retry redoes it.
                    # Reporting the link as failed would tell the user the
                    # opposite of the truth about their own vault.
                    _once(result.warnings, said, NO_STATUS, _typed(error))
                result.saved += 1
        except Exception as error:
            # A link that could not be written is reported and the run goes
            # on: 1214 saved and one reported beats 1215 unsaved.
            result.failed.append((one.url, _typed(error)))
            result.kinds[one.url] = _kind(error)

    if result.saved:
        result.warnings += _reindex(cfg)       # once, for the batch
    return result


def owed(queue: Queue | None = None) -> tuple[list[QueueEntry], list[str]]:
    """Every link retry() would work on, de-duplicated, and what could not be read.

    retry() walks this, and so does the page that offers to process a batch, so
    the number the user is shown and the work a run does cannot drift apart.

    Each listing can fail as a whole -- an unreadable lock file, say -- and must
    not stop the other, nor lose the links already found. The wording comes back
    as a string rather than raising: a caller counting links shows it, and
    retry() turns it into a failed Result of its own.
    """
    q = queue or Queue()
    found: dict[str, QueueEntry] = {}
    problems: list[str] = []
    for listing in (q.unfinished, q.orphaned):
        try:
            for entry in listing():
                found.setdefault(entry.id, entry)
        except Exception as error:
            problems.append(f"could not list the queue ({_typed(error)})")
    return list(found.values()), problems


def _announce(hook: Callable[[Result], None] | None, result: Result) -> None:
    """Tell a watcher a link is done, and never let the telling cost a link.

    The link is written and the queue is settled by the time this runs, so a
    hook that raises -- a browser gone, a bar with a bug -- has nothing left
    to damage, and the rest of the run is worth more than the bar.
    """
    if hook is None:
        return
    try:
        hook(result)
    except Exception:
        pass


def retry(cfg: Config, queue: Queue | None = None,
          limit: int | None = None,
          on_step: Callable[[Result], None] | None = None) -> list[Result]:
    """Finish every link the queue still owes, newest first, and settle the
    ones only the bookkeeping thinks are owed.

    `limit` stops the run after that many links finished, not attempted: an
    entry that turns out to be already settled does not use up the quota,
    because reconciling bookkeeping is not work. That is what lets an imported
    batch be analysed 50 a day without a day going to stale entries.

    `on_step` is called with each link's Result as it finishes, for a caller
    drawing a progress bar: once per unit of work, on the same count `limit`
    spends, so a bar's steps and its total are the same number twice over.
    A settled entry does not call it, for the same reason it costs no quota.

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
    entries, problems = owed(q)
    results = [Result(id="queue", url="", path=None, status="failed", error=problem)
               for problem in problems]
    # Newest first, within groups. The date is not in the queue -- `updated` is
    # when the entry was written, so an import runs oldest message first -- and
    # it comes from the note's `saved`: one scan per run, not one per link. An
    # entry with no note and no failure on record goes first: it is a link
    # that has not reached the vault yet, which is more urgent than any date. After it come the links
    # never worked on, then the ones already tried, by the day they were tried,
    # oldest day first: a dead link keeps its old date and would otherwise sit
    # at the top and use up every run's quota, forever. The note's date decides
    # inside each group. A no-note entry cannot stall the run that way: add()
    # writes a partial note even when the fetch fails, so after one attempt it
    # has a note and joins the day rotation -- and when the write itself fails
    # (a file of the user's in the way) the reason it leaves behind puts it in
    # its day group all the same.
    try:
        dates = {note.id: note.saved for note in all_notes(cfg)}
    except OSError:
        # With no dates the order below is arbitrary, which costs a run of
        # the wrong links first and never a link: every entry is still owed.
        dates = {}
    ordered = sorted(entries, key=lambda e: dates.get(e.id, "9999-99-99"),
                     reverse=True)
    ordered.sort(key=lambda e: _last_worked(e, dates))   # stable: date decides inside
    done = 0
    for entry in ordered:
        if limit is not None and done >= limit:
            break
        try:
            settled = _reconcile(cfg, q, entry)
            if settled is not None:
                results.append(settled)
                continue                  # bookkeeping, not work: no quota used
            results.append(add(cfg, entry.url, content=entry.content,
                               reprocess=True, queue=q))
            done += 1
            _announce(on_step, results[-1])
        except Exception as error:
            # One link that cannot be written -- a full disk, or a note file the
            # user replaced with one of their own -- must not take the rest of
            # the run down with it. add() leaves the entry behind either way, so
            # nothing is lost whichever way this goes.
            results.append(_failed(q, entry, error))
            done += 1                     # trying and failing is work too
            _announce(on_step, results[-1])
    return results


def _last_worked(entry: QueueEntry, dates: dict[str, str]) -> str:
    """The calendar day a link was last worked on, or "" if it never was.

    A link still carrying the import's own marker, or with no note and no
    failure on record, has not been worked on, and sorts before every date. A
    reason that is anything else means it was tried, note or no note: an entry
    whose write keeps failing never gets a note, and must not stay at the head
    of the order spending a quota slot on every run.
    """
    if entry.error == IMPORTED or (entry.id not in dates and not entry.error):
        return ""
    return entry.updated[:10]


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


def backfill_mentions(cfg: Config, limit: int | None = None,
                      queue: Queue | None = None) -> list[Result]:
    """Give the videos already in the library their mentions.

    Candidates are finished notes (status ok) of type youtube whose mentions
    are None -- never asked. An imported link nobody analysed yet is a
    youtube note too, but its body is a chat comment, not a transcript. A note asked before stops being one even if the answer was empty,
    which is what makes running this again cheap instead of pointless.

    The text comes from where it already is: a note saved with content == full
    holds the transcript in its body, so most of a backfill needs neither
    yt-dlp nor the network. One saved as summary is extracted again.

    Only the mentions section is written. The title, the summary and the points
    are left exactly as they are.
    """
    q = queue or Queue()
    candidates = [note for note in all_notes(cfg)
                  if note.type == "youtube" and note.status == "ok"
                  and note.mentions is None]
    # Newest first, like retry: the backlog is walked from what the user saved
    # most recently, which is what they are most likely to be looking for.
    candidates.sort(key=lambda note: note.saved, reverse=True)
    results: list[Result] = []
    todo = candidates[:limit] if limit is not None else candidates
    for index, note in enumerate(todo):
        try:
            with ExitStack() as stack:
                try:
                    stack.enter_context(q.lock(note.id))
                except Locked as error:
                    # A reprocess, an edit or another run is on this note.
                    # update_note() reads and writes it back, so writing now
                    # could land our copy over theirs. Unfinished, not failed:
                    # it stays a candidate and the next run does it.
                    results.append(Result(id=note.id, url=note.url, path=None,
                                          status="pending", error=str(error)))
                    continue
                except OSError as error:
                    # An unlockable state tree. add() carries on unlocked
                    # because a lost link costs more than a duplicated one, but
                    # nothing can be lost here: the note on disk is finished and
                    # the only thing at stake is adding a list to it, which the
                    # next run can do just as well. Carrying on could overwrite
                    # a note somebody else is writing, so, like _reconcile, this
                    # skips.
                    results.append(Result(id=note.id, url=note.url, path=None,
                                          status="failed", error=_reason(error)))
                    continue
                # What we were handed was read before the lock: look again, in
                # case somebody answered or removed the note in the meantime.
                found = find_note(cfg, note.id)
                if found is None or found[1].mentions is not None:
                    # Nothing happened and nothing went wrong: "ok", but
                    # skipped, like add() reports a link already saved, so the
                    # report neither counts it as work nor as a failure.
                    why = ("it is no longer in the library" if found is None
                           else "it already had its mentions")
                    results.append(Result(id=note.id, url=note.url, path=None,
                                          status="ok", skipped=True, warnings=[why]))
                    continue
                # The copy read under the lock, not the one handed in before it.
                fresh = found[1]
                text = fresh.body or extract(fresh.url).text
                found_mentions, engine = mentions_with_chain(
                    cfg, text, {"url": fresh.url, "title": fresh.title})
                written = update_note(cfg, note.id, cfg.language,
                                      mentions=found_mentions, found=found)
        except AllEnginesFailed as error:
            if error.answered:
                # An engine replied and the reply was no use: this video's
                # problem. The next one is independent and may answer well; a
                # bad answer already spent its call, so going on costs nothing
                # extra. No counter, no threshold.
                results.append(Result(
                    id=note.id, url=note.url, path=None, status="failed",
                    error=f"the answer could not be used: {_reason(error)}"))
                continue
            # Nothing answered: the chain is down. Same shape as import_links'
            # _once() -- trouble that is the same for every video is reported
            # once -- except this stops, because carrying on costs an
            # extraction (yt-dlp, the network) per video to learn the same
            # thing. Nothing is written, so every video stays a candidate.
            left = len(todo) - index - 1
            reason = _reason(error)
            if left:
                reason += (f" -- stopped: {left} more video"
                           f"{'s' if left != 1 else ''} not tried, run it again "
                           "when an engine works")
            results.append(Result(id=note.id, url=note.url, path=None,
                                  status="failed", error=reason))
            break
        except Exception as error:
            # One video that cannot be read does not stop the others, exactly
            # as in retry(). The reason is reported, never swallowed.
            results.append(Result(id=note.id, url=note.url, path=None,
                                  status="failed", error=_reason(error)))
            continue
        results.append(Result(id=note.id, url=note.url, path=written, status="ok",
                              engine=engine))
    return results
