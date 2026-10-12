"""The web: it shows the vault, and it is the only reader that can change it.

Every route that writes goes through one of three narrow doors -- update_note,
delete_note, rename_category -- and every one of them is a POST behind the
origin check below. Nothing here unlinks a note: deleting moves the file to
trash/, which is what makes a mis-click in a browser recoverable.
"""

from __future__ import annotations

import contextlib
import dataclasses
import logging
import re
from importlib.resources import files
from pathlib import Path
from collections.abc import Callable
from typing import NamedTuple
from urllib.parse import quote, urlencode

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import (
    FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException as StarletteHTTPException

from .. import cards, env, places
from ..catalog import Candidate, cinemeta, openlibrary
from ..ai import build_engine
from ..ai.base import normalize_collections
from ..ai.providers import PROVIDERS
from ..ai.providers import find as find_provider
from ..config import CONFIG_PATH, CONTENT_MODES, ENGINE_NAMES, MENTION_MODES, Config
from ..config import save as save_config
from ..i18n import LANGUAGES, NATIVE_NAMES, translator
from ..pipeline import add as add_link
from ..pipeline import describe, download_cover, icon_path, import_links
from ..pipeline import is_domain, owed
from ..pipeline import today
from ..models_cache import read as read_models
from ..models_cache import remember as remember_models
from ..queue import Locked, Queue
from ..trace import trace_run
from ..urls import is_search_url, link_id, normalize
from ..vault import STATES as vault_states
from ..vault import (
    BadCategory, IndexesStale, ProtectedNote, clean_category, delete_note,
    find_note, note_path, rebuild_indexes, rename_category, update_note,
    write_note,
)
from ..whatsapp import BadExport, parse as parse_export
from .batch import Batch
from .batch import run as run_batch
from .import_file import BadUpload, drop, stage, staged, text_of
from .index import PER_PAGE, Library, read_full, tally, terms

WEB = files("oknowledge").joinpath("web")
log = logging.getLogger(__name__)

# The engines the settings page offers. "fake" is a test double and has no
# business being switchable from a browser.
WEB_ENGINES = ("opencode", "ollama", "api")

# What a redirect can tell the next page. A fixed table, so the only thing
# that ever travels in the query string is one of these keys and two numbers.
NOTICES = {
    "saved": "Saved.",
    "trashed": "The note was moved to the trash folder inside your vault. "
               "You can restore it from Obsidian.",
    "queued": "Re-running the analysis. The note stays pending until it finishes.",
    # The rule is spelled out, characters and all, because the field arrives
    # pre-filled with the value already saved: a user whose category is "Misc."
    # -- hand-written, or AI-written before ai.base stopped inventing those --
    # will click Save on it and has to be told the real reason. It has to say
    # what vault.clean_category() enforces, no less.
    "bad-category": 'That name cannot be used as a category: at most 80 '
                    'characters, no dots at either end, no control characters, '
                    'and none of \\ / : * ? " < > |',
    "renamed-one": "1 note moved.",
    "renamed": "%1 notes moved.",
    "merged-one": "1 note merged into a category that was already there.",
    "merged": "%1 notes merged into a category that was already there.",
    # Two counts, so two numbers to agree with, independently of each other.
    "renamed-partial": "%1 notes moved, %2 could not be written. "
                       "Check the folder and try again.",
    "renamed-partial-one-moved": "1 note moved, %2 could not be written. "
                                 "Check the folder and try again.",
    "renamed-partial-one-failed": "%1 notes moved, 1 could not be written. "
                                  "Check the folder and try again.",
    "renamed-partial-one-each": "1 note moved, 1 could not be written. "
                                "Check the folder and try again.",
    "busy": "An analysis is running on this link. Try again when it finishes.",
    "write-failed": "The vault could not be written. Check that the folder exists "
                    "and that you can write to it.",
    # Not the same thing as a failed write, and the difference is the whole
    # point: the change is on disk, only the indexes are behind.
    "indexes-stale": "Saved, but the indexes could not be rebuilt. Run "
                     "`oknowledge reindex` once the folder is writable again.",
    "trashed-indexes-stale": "The note was moved to the trash folder inside your "
                             "vault, but the indexes could not be rebuilt. Run "
                             "`oknowledge reindex` once the folder is writable again.",
    "settings-failed": "The settings could not be saved. Check that the config "
                       "folder exists and that you can write to it.",
    # Pasting a link in the header. There is no card to watch yet -- a card
    # is a note, and the note is written at the end -- so the notice is the
    # whole answer until it appears.
    "reading": "Reading that link now. It shows up in the library when it is done.",
    "already-saved": "You already have that link.",
    # A known prefix with nothing after it: the person meant to search and
    # stopped typing. Telling them it is not a link would be answering a
    # question they did not ask.
    "no-title": "Write what to look for after the colon, like "
                "película:Terminator.",
    # The catalog answered the search and then had nothing for the one that
    # was picked. Rare, and not the same as the catalog being down.
    "catalogue-silent": "The catalogue has no card for that one. Try another.",
    # The rewrite runs behind the page, like every other model call here.
    "rewriting": "Writing the summary now. Reload in a moment to read it.",
    "not-a-link": "That is not a link: it has to be an address, like "
                  "https://example.com/page.",
    "searched": "That is a page of search results, not a page. Open the result "
                "you want and paste that one.",
    "batch-started": "Analysing. This page comes back on its own; you can close it.",
    "batch-running": "A batch is already running. This page shows how it is going.",
    "nothing-owed": "Every link has been analysed. Nothing to do.",
    # A collection is never a file name, so the rule is only about a name
    # that would be nothing at all once the spaces are taken out.
    "bad-collection": "That name cannot be used as a collection: it has to be "
                      "something other than spaces, dots and slashes.",
    "models-found": "%1 models found. They are in the list beside each box.",
    # Not a failure: an engine that is not installed or not running has
    # nothing to say, and the box takes a name typed by hand either way.
    "models-none": "No models could be listed. The engine may not be "
                   "installed, running or reachable -- you can still type "
                   "the name by hand.",
    # The three answers of the button that makes the .env. None of them names
    # the file: the block right below the button already shows its path, and a
    # notice cannot carry anything but numbers.
    "env-made": "The file is there, with the variable ready. Paste the key "
                "after the = sign and save it.",
    "env-there": "That file already exists, so nothing was touched. Add the "
                 "variable to it yourself.",
    "env-failed": "The file could not be created. Check that its folder can "
                  "be written.",
    "nothing-picked": "No cards were selected, so nothing changed.",
    "collected-one": "The note was added to the collection.",
    "collected": "%1 notes added to the collection.",
    "collect-partial": "%1 of %2 notes added to the collection. The rest could "
                       "not be written; check the folder and try again.",
    "uncollected-one": "The note was taken out of the collection.",
    "uncollected": "%1 notes taken out of the collection.",
    "uncollect-partial": "%1 of %2 notes taken out of the collection. The rest "
                         "could not be written; check the folder and try again.",
}

# Three letters each, because the strip they go in is five characters wide.
# "2021-11" is a date for a database; a person reads "nov".
# One drawn icon each, by the engine's own name. `api` is one icon for every
# provider it can point at: the provider is named in the title beside it, and
# a logo guessed wrong is worse than no logo.
ENGINE_ICONS = ("opencode", "ollama", "api")

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

# How many tag chips the library shows before the rest go behind a disclosure.
# A thousand notes make hundreds of tags, and a row of them pushes the cards --
# the thing the page is for -- off the bottom of the screen.
TAGS_SHOWN = 12

# How long the running batch page waits before coming back. A link is tens of
# seconds of model call, so this is about a bar that moves, not a live one, and
# every reload is a queue listing.
REFRESH = 10

# Which `renamed-partial` to use: (one note moved, one note failed).
PARTIAL = {
    (False, False): "renamed-partial",
    (True, False): "renamed-partial-one-moved",
    (False, True): "renamed-partial-one-failed",
    (True, True): "renamed-partial-one-each",
}

# Writing is refused unless the browser says the request came from this app.
# The server listens on localhost, which stops nothing: any page the user
# visits can POST here, and a POST with no-cors needs no permission and shows
# no error. Sec-Fetch-Site is the modern answer; Origin covers the clients
# that do not send it. A write with neither is a shell, not a page.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
SAFE_SITES = frozenset({"same-origin", "none"})

# Not a notice: what edit() answers when the link is not a note of ours, which
# the route turns into a 404.
MISSING = "missing"


class Edited(NamedTuple):
    """What edit() answers: the notice to show, and whether the change really
    landed on disk -- which is what decides where a delete sends the user, and
    must never be guessed from the notice."""

    notice: str
    landed: bool

# Cover images are served only as one of these: a hand-edited cover pointing at
# an .svg or .html inside attachments/ would otherwise be a same-origin document.
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
               ".gif": "image/gif", ".webp": "image/webp", ".avif": "image/avif"}

# Favicons get one more type than covers do, because most sites still answer
# /favicon.ico with a real .ico. It stays out of IMAGE_TYPES so that widening
# it here cannot widen what /cover will serve.
ICON_TYPES = dict(IMAGE_TYPES, **{".ico": "image/vnd.microsoft.icon"})

# Icons never change for a given domain, and a full-width grid asks for one per
# card, so they are worth a day in the browser's cache.
ICON_CACHE = "public, max-age=86400"


def letter_icon(name: str) -> Response:
    """The stand-in when a site has no favicon: its initial, on its own colour.

    The route answers with this rather than a 404 so that the card template
    never has to ask whether a download happened. One page of cards therefore
    costs no filesystem lookups in the template and shows no broken images.
    """
    letter = next((char for char in name if char.isalnum()), "?")
    hue = sum(name.encode("utf-8", "replace")) * 7 % 360
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" '
        'width="32" height="32" role="img">'
        f'<rect width="32" height="32" rx="7" fill="hsl({hue} 45% 42%)"/>'
        '<text x="16" y="22" text-anchor="middle" fill="#fff" '
        'font-family="sans-serif" font-size="18" font-weight="600">'
        f'{letter}</text></svg>'
    )
    return Response(svg, media_type="image/svg+xml",
                    headers={"Cache-Control": ICON_CACHE,
                             "X-Content-Type-Options": "nosniff"})


def plain(text: str) -> str:
    """A whole summary without markdown decoration, for a card.

    The card is a fixed size and its summary box scrolls, so nothing is cut
    here: what does not fit at once is reached with the wheel. Every line is
    stripped, not just the first, because a summary of two paragraphs is
    still the summary.
    """
    lines = []
    for line in text.splitlines():
        if not line.strip():
            continue
        line = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", line)     # links and images
        line = re.sub(r"^\s*(#+|>|[-*+]|\d+\.)\s+", "", line)        # heading, quote, list
        lines.append(re.sub(r"[*_`~]+", "", line).strip())
    return "\n".join(lines)


def is_web_url(url: str) -> bool:
    """Whether this is a URL we are willing to put in an href.

    `url` is frontmatter, so it is whatever the user last typed there, and a
    card is rendered once per note on a page of a hundred. Anything that is
    not http(s) -- javascript:, data:, file: -- is shown as text instead:
    refusing to link it must not mean hiding it, because a link is never lost.
    """
    return str(url).lower().startswith(("http://", "https://"))


def page_number(raw: str, pages: int) -> int:
    try:
        number = int(raw)
    except ValueError:
        return 1
    return min(max(number, 1), max(pages, 1))


def count(request: Request, key: str) -> int:
    """One small, non-negative number from the query string, or zero."""
    try:
        return max(0, min(int(request.query_params.get(key, "0")), 1_000_000))
    except ValueError:
        return 0


MAX_URL = 2048
"""Longer than this is not an address. The same ceiling the panel uses on
Linux, and it is what keeps a pasted novel out of the queue and out of a
file name."""


def pasted_link(raw: str) -> str:
    """The URL from the paste box, or "" if it is not one.

    normalize() is a convenience and not a check: it turns "example.com/x"
    into an address as cheerfully as it turns "not a link" into
    "https://not a link/". So the question is asked of the result -- http(s),
    no whitespace left in it, short enough to be an address -- which is the
    panel's rule on Linux plus the typing normalize() saves.
    """
    raw = raw.strip()
    if not raw or len(raw) > MAX_URL:
        return ""
    clean = normalize(raw)
    if not is_web_url(clean) or any(ch.isspace() for ch in clean):
        return ""
    return clean


def notice_for(request: Request, t) -> str | None:
    text = NOTICES.get(request.query_params.get("notice", ""))
    return None if text is None else t(text, count(request, "n"), count(request, "m"))


def preview_of(scan, known: set[str]) -> dict:
    """What the preview page shows about a parsed export, before anything is written.

    `new` counts the way import_links() counts, by calling the same two
    functions it calls: unique on link_id(normalize(url)), minus what the vault
    already holds. It is an upper bound and the page says so -- a link another
    process is holding this second gets written by neither of us, and only
    import_links() can find that out, by trying.
    """
    ids: dict[str, object] = {}
    unusable = 0
    for one in scan.links:
        clean = normalize(one.url)
        if not clean:
            unusable += 1
            continue
        ids.setdefault(link_id(clean), one)
    already = sum(1 for link in ids if link in known)
    dates = sorted(one.sent for one in scan.links)
    return {
        "links": len(scan.links),
        "messages": scan.messages,
        "first": dates[0] if dates else "",
        "last": dates[-1] if dates else "",
        # Said in the same words as the CLI, so the two reports read alike.
        "order": "day/month" if scan.day_first else "month/day",
        "assumed": scan.assumed,
        "new": len(ids) - already,
        "already": already,
        "repeated": len(scan.links) - unusable - len(ids),
        "unusable": unusable,
        # The whole list, not a count: a sentence ending in a word that happens
        # to be a TLD looks exactly like a domain, and seeing them before the
        # write is the reason this preview exists.
        "bare": [one for one in scan.links if one.bare],
        "suspicious": scan.suspicious,
    }


STATE_WORDS = {
    # The design's table. A book is read, not watched, and four words per
    # kind is cheaper than pretending one word fits both.
    "movie": {"pending": "to watch", "doing": "watching", "done": "watched"},
    "series": {"pending": "to watch", "doing": "watching", "done": "watched"},
    "anime": {"pending": "to watch", "doing": "watching", "done": "watched"},
    "book": {"pending": "to read", "doing": "reading", "done": "read"},
}

KIND_WORDS = (("movie", "Movies"), ("series", "Series"),
              ("anime", "Anime"), ("book", "Books"))
"""The four kinds and the word each one wears on a chip, in the order the
chips are drawn. A tuple of pairs and not a dict: the order is the point."""

STATE_ORDER = (("pending", "Pending"), ("doing", "In progress"),
               ("done", "Finished"))
"""The three states, in the words the chips wear. Neutral on purpose: the
section mixes books with films, and one chip cannot be "watching" and
"reading" at once. The card's own buttons use the words of its kind."""


def _count_by(notes, field: str) -> dict[str, int]:
    """How many cards each value of one field has, for the filter chips."""
    counts: dict[str, int] = {}
    for note in notes:
        value = getattr(note, field, "")
        if value:
            counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def catalog_type_for(kind: str) -> str:
    """Which catalog shelf a kind is asked of by default."""
    return "book" if kind == "book" else cinemeta.catalog_type(kind)


def catalog_of(via: str):
    """The client that answers for a catalog shelf."""
    return openlibrary if via == "book" else cinemeta


def catalogs_for(kind: str) -> list[tuple[object, str]]:
    """Which catalogs to ask, in the order the answers are shown.

    Anime asks both of Cinemeta's, series first: Cowboy Bebop is a series
    and a film, and the specialist catalog for anime answers only over
    IPv6. Whichever one was meant, it is in one of the two answers.
    """
    if kind == "book":
        return [(openlibrary, "book")]
    if kind == "anime":
        return [(cinemeta, "series"), (cinemeta, "movie")]
    return [(cinemeta, cinemeta.catalog_type(kind))]


def see_other(path: str, **params) -> RedirectResponse:
    """The answer to every write: 303 to a page that reads the result back.

    `path` may already carry a query -- a card's button goes back to the
    library view it was clicked on -- so the join is & in that case. A second
    "?" would make the notice part of the value before it instead.
    """
    query = urlencode({k: v for k, v in params.items() if v not in (None, "")})
    if not query:
        return RedirectResponse(path, status_code=303)
    join = "&" if "?" in path else "?"
    return RedirectResponse(path + join + query, status_code=303)


def _clustered(tags: dict[str, int], home: dict[str, str]) -> list[tuple[str, int]]:
    """The same tags, reordered so the ones about the same thing are adjacent.

    Clusters lead with their most used tag and are ordered by it, so the row
    still opens with the tag the library uses most and nothing jumps about
    between page loads. No titles: a title per cluster turns a one-line row
    into one line per category, which is what the shortened row was for.
    """
    order: dict[str, list[tuple[str, int]]] = {}
    for tag, count in tags.items():                 # already most-used first
        order.setdefault(home.get(tag, ""), []).append((tag, count))
    return [pair for group in order.values() for pair in group]


def tag_chips(tags: dict[str, int], home: dict[str, str], active: str | None
              ) -> tuple[list[tuple[str, int]], dict[str, list[tuple[str, int]]]]:
    """(the tags to show at once, the rest grouped under their category).

    They arrive most-used first and there is no natural end to them. The one
    being filtered by is always in the first group, whatever its rank: it is
    the only chip that says what the page is filtered by, and a filter that
    hides its own name leaves no way back out of it.

    What is hidden gets the titles the row has no room for -- eighty chips in
    a drawer, in one run, are the wall this was meant to undo.
    """
    first = dict(list(tags.items())[:TAGS_SHOWN])
    if active in tags and active not in first:
        first[active] = tags[active]
    rest: dict[str, list[tuple[str, int]]] = {}
    for tag, count in tags.items():
        if tag not in first:
            rest.setdefault(home.get(tag, ""), []).append((tag, count))
    return _clustered(first, home), rest


def item_url(link_id: str) -> str:
    return "/item/" + quote(link_id, safe="")


# The two listings a card's button may send the user back to, and no others.
RETURNS = {"library": "/", "search": "/search"}


def return_url(back: str, category: str, tag: str, collection: str,
               when: str, query: str, number: str) -> str | None:
    """The listing a card was clicked on, rebuilt rather than echoed.

    None means `back` named no listing of ours and the caller should use the
    note's own page. The path comes out of RETURNS and the query is built here
    out of what those two routes understand, so a form made by hand can land
    the user on one of these pages and on nowhere else at all.

    A page that is not a page number is dropped: a wrong number costs the user
    their place, and page 1 needs no number anyway.
    """
    path = RETURNS.get(back)
    if path is None:
        return None
    params = {}
    if path == "/search":
        if not query.strip():
            return None            # a search with no terms is not a page to return to
        params["q"] = query.strip()[:200]
    else:
        for name, value in (("category", category), ("tag", tag),
                            ("collection", collection), ("when", when)):
            if value.strip():
                params[name] = value.strip()[:200]
    if number.isdigit() and int(number) > 1:
        params["page"] = number
    rest = urlencode(params)
    return path + ("?" + rest if rest else "")


def when_urls(axis: dict, periods) -> dict[str, str]:
    """Every link the strip can draw, built here rather than in the template.

    Each one keeps the category, tag and collection that are already chosen:
    time is the other axis, and travelling along it must not undo the "what".
    The empty key is the way back out of a period, which keeps them too.
    """
    def url(value: str) -> str:
        query = urlencode({**axis, **({"when": value} if value else {})})
        return "/" + ("?" + query if query else "")
    return {value: url(value) for value in ["", *periods]}


def batch_size(raw: str, saved: int) -> int:
    """A batch size from a form, or the saved one if that is not a size.

    Refused rather than clamped: config.load() refuses a 0, so saving one would
    leave a file the whole tool stops reading, and a number the user did not
    type is no better a guess than the one already saved.
    """
    try:
        size = int(raw)          # int() ignores the whitespace around a number
    except ValueError:
        return saved
    return size if size >= 1 else saved


def model_name(raw: str) -> str | None:
    """A model name from a form: trimmed, "" to clear it, None if it is not one."""
    name = raw.strip()[:200]
    if not name:
        return ""
    return name if name.isprintable() else None


def same_origin(headers: Headers, scheme: str) -> bool:
    site = headers.get("sec-fetch-site")
    if site is not None:
        return site.strip().lower() in SAFE_SITES
    origin = headers.get("origin")
    if origin is None:
        return True
    host = headers.get("host", "").strip().lower()
    return bool(host) and origin.strip().lower() == f"{scheme}://{host}"


class SameOriginOnly:
    """Refuse any write that did not come from this app, before it is routed.

    Pure ASGI, and middleware rather than a dependency, so a route added later
    cannot forget it: the request never reaches a handler, so nothing is read
    from its body and nothing is changed.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("method") not in SAFE_METHODS:
            if not same_origin(Headers(scope=scope), scope.get("scheme", "http")):
                answer = PlainTextResponse("cross-site write refused", status_code=403)
                await answer(scope, receive, send)
                return
        await self.app(scope, receive, send)


@contextlib.contextmanager
def link_lock(link_id: str):
    """Hold the link's queue lock while one of its notes is edited.

    pipeline.add() writes its note under this same lock, so holding it is what
    stops a background re-analysis from landing on top of an edit -- or, worse,
    from writing the note back into links/ after the user has just moved it to
    trash/, which would silently undo a delete. Taking the lock closes that
    race; probing it would only narrow it.

    A state tree that cannot be locked at all (an unwritable ~/.local/state)
    lets the edit through unlocked, which is the same call pipeline.add()
    makes: the queue is bookkeeping, the note is the artifact. So does an id
    the queue refuses to name (a hand-edited `id:` with a space in it): the
    queue cannot hold an entry for it, so nothing can be analysing it.
    """
    with contextlib.ExitStack() as stack:
        try:
            stack.enter_context(Queue().lock(link_id))
        except (OSError, ValueError):
            pass
        yield


def reanalyze(cfg: Config, url: str, engine: str | None,
              trace: Callable | None = None) -> None:
    """Re-run the analysis outside the request, and never raise into the server.

    The chain can take minutes per engine, which is far too long to hold a
    browser. If the process dies mid-run (the idle timer, a laptop closing),
    the lock goes with it and the queue entry stays `pending` for the next
    `retry` to pick up: nothing is lost by answering early.
    """
    try:
        add_link(cfg, url, engine=engine, reprocess=True, trace=trace)
    except Exception:                 # a background task has nowhere to raise to
        log.exception("re-analysing %s failed", url)


def fetch(cfg: Config, url: str, content: str | None,
          trace: Callable | None = None) -> None:
    """Save a pasted link outside the request, and never raise into the server.

    The twin of reanalyze(), for the same reason: minutes of model calls that
    no browser waits through. reprocess stays False, so a link that already
    has a note is left exactly as it is -- which is what the page said when it
    answered that you already had it.
    """
    try:
        add_link(cfg, url, content=content, trace=trace)
    except Exception:                 # a background task has nowhere to raise to
        log.exception("saving %s failed", url)


def create_app(cfg: Config) -> FastAPI:
    app = FastAPI(title="oknowledge", docs_url=None, redoc_url=None)
    app.add_middleware(SameOriginOnly)
    library = Library(cfg)
    # The cards. A second index over a second folder, so a page of films
    # costs nothing to the 1184 links and the two can never mix.
    shelf = Library(cfg, shelf=cfg.ocio)
    # The settings page can change the engine chain while the server runs. The
    # vault paths it cannot change, so the library stays valid either way.
    current = {"cfg": cfg}
    # One batch at a time, in memory. A run only exists while this process
    # does, so there is nothing to resume after a restart and no stale file to
    # explain -- the queue on disk is the record of what is still owed.
    progress = Batch()
    templates = Jinja2Templates(directory=str(WEB.joinpath("templates")))
    templates.env.filters["plain"] = plain
    templates.env.filters["slug"] = lambda value: quote(str(value), safe="")
    templates.env.tests["web_url"] = is_web_url
    templates.env.tests["search_link"] = is_search_url
    # The engines there is an icon for. A name outside this never reaches an
    # include: `engine:` is frontmatter and frontmatter is typed by hand.
    templates.env.globals["engines"] = ENGINE_ICONS
    app.mount("/static", StaticFiles(directory=str(WEB.joinpath("static"))), name="static")

    def page(request: Request, name: str, status_code: int = 200, **context) -> HTMLResponse:
        # From the config in use, not from the one this app was built with: the
        # settings page saves a new Config, and the page that comes back has to
        # be in the language that was just picked.
        language = current["cfg"].ui_language
        t = translator(language)
        base = {"t": t, "lang": language, "query": "",
                "unreadable": library.unreadable, "links_dir": cfg.links_dir,
                "heading": None, "prev_url": None, "next_url": None,
                "page": 1, "pages": 1, "notice": notice_for(request, t),
                # On every page, because the link to the batch is in the nav
                # and it says there how far along a run is. It is a read of
                # memory, not of the queue: no page pays for it.
                "batch": progress.snapshot()}
        if library.error is not None:
            return templates.TemplateResponse(
                request=request, name="error.html", status_code=503,
                context={**base, "error": library.error, "categories": {},
                         "tags": {}, "collections": {}})
        return templates.TemplateResponse(
            request=request, name=name, status_code=status_code,
            context={**base, "categories": library.categories(), "tags": library.tags(),
                     "collections": library.collections(), "collection": None,
                     "picking": False, **context},
        )

    def pager(path: str, params: dict, number: int, pages: int) -> dict:
        def url(n: int) -> str:
            query = urlencode({**params, **({"page": n} if n > 1 else {})})
            return path + ("?" + query if query else "")
        return {"page": number, "pages": pages,
                "prev_url": url(number - 1) if number > 1 else None,
                "next_url": url(number + 1) if number < pages else None}

    @app.exception_handler(StarletteHTTPException)
    async def not_found(request: Request, exc: StarletteHTTPException):
        path = request.url.path
        if exc.status_code == 404 and not path.startswith(("/cover/", "/static/", "/embed/")):
            return page(request, "notfound.html", status_code=404)
        return await http_exception_handler(request, exc)

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request, category: str | None = None, tag: str | None = None,
             collection: str | None = None, when: str | None = None,
             pick: str | None = None):
        library.refresh()
        # Twice on purpose: the strip counts what the OTHER filters left, so
        # that choosing a year does not empty the strip that chose it.
        axis = {k: v for k, v in (("category", category), ("tag", tag),
                                  ("collection", collection)) if v}
        dated = library.filter(category=category, tag=tag, collection=collection)
        notes = (library.filter(**{k: v for k, v in axis.items()}, when=when)
                 if when else dated)
        pages = -(-len(notes) // PER_PAGE)
        number = page_number(request.query_params.get("page", "1"), pages)
        params = {**axis, **({"when": when} if when else {})}
        shown = notes[(number - 1) * PER_PAGE:number * PER_PAGE]
        first, rest = tag_chips(library.tags(), library.tag_home(), tag)
        # Where the two selection links go: the same listing, on the same
        # page, with the mode turned on or off. Built here because the
        # template has no business assembling query strings.
        here = {**params, **({"page": str(number)} if number > 1 else {})}
        months = [m for m in library.months() if when and m.startswith(when[:4])]
        return page(request, "library.html", notes=shown, category=category, tag=tag,
                    collection=collection, picking=pick is not None,
                    pick_url="/?" + urlencode({**here, "pick": "1"}),
                    cancel_url="/" + ("?" + urlencode(here) if here else ""),
                    place=here, tags=first, tag_groups=rest,
                    hidden_tags=sum(map(len, rest.values())),
                    filtered=bool(category or tag or collection or when),
                    when=when, years=list(library.years()), months=months,
                    counted=tally(dated), dated=len(dated),
                    month_names={m: MONTHS[int(m[5:7]) - 1] for m in months},
                    when_urls=when_urls(axis, [*library.years(), *months]),
                    **pager("/", params, number, pages))

    @app.get("/search", response_class=HTMLResponse)
    def search(request: Request, q: str = ""):
        library.refresh()
        if not terms(q):
            return RedirectResponse("/", status_code=303)
        _, total = library.search(q, page=1, per_page=1)
        pages = -(-total // PER_PAGE)
        number = page_number(request.query_params.get("page", "1"), pages)
        found, _ = library.search(q, page=number)
        return page(request, "library.html", notes=None, hits=found, category=None,
                    tag=None, query=q, **pager("/search", {"q": q}, number, pages))

    def anywhere(link_id: str):
        """(entry, the shelf it is on), looking in the links first.

        One note page and one cover route serve both shelves: a card is a
        note, and everything a note page does -- read it, edit it, throw it
        away -- it does for a card too.
        """
        for shelves in (library, shelf):
            shelves.refresh()
            entry = shelves.entry(link_id)
            if entry is not None:
                return entry, shelves.shelf
        return None, None

    @app.get("/item/{link_id}", response_class=HTMLResponse)
    def item(request: Request, link_id: str):
        library.refresh()
        if library.error is not None:
            return page(request, "item.html")
        entry, where = anywhere(link_id)
        if entry is None:
            raise HTTPException(status_code=404, detail="no such link")
        # The index holds list views without bodies; this note is read fresh.
        return page(request, "item.html", note=read_full(entry),
                    card=where.name == "ocio",
                    words=STATE_WORDS.get(entry.note.type, STATE_WORDS["movie"]),
                    STATES=vault_states)

    @app.get("/embed/{link_id}", response_class=HTMLResponse)
    def embed(request: Request, link_id: str):
        """One note with no page around it: what a card's dialog loads.

        Read-only on purpose. Every write route checks the request's origin,
        and a form inside a fragment fetched by script is the exact shape
        that check exists for -- so the dialog reads and the item page writes.
        """
        library.refresh()
        if library.error is not None:
            return page(request, "embed.html")
        entry = library.entry(link_id)
        if entry is None:
            raise HTTPException(status_code=404, detail="no such link")
        return page(request, "embed.html", note=read_full(entry))

    @app.get("/cover/{link_id}")
    def cover(link_id: str):
        entry, where = anywhere(link_id)
        note = entry.note if entry is not None else None
        if note is None or not note.cover:
            raise HTTPException(status_code=404, detail="no cover")
        # note.cover comes from frontmatter the user can edit: untrusted input.
        try:
            # Relative to the folder the note is in, which is the shelf's:
            # a card's "../attachments/x.png" starts from ocio/, not links/.
            path = (where.dir / note.cover).resolve()
            inside = cfg.attachments_dir.resolve() in path.parents
            usable = inside and path.suffix.lower() in IMAGE_TYPES and path.is_file()
        except (OSError, ValueError):
            usable = False
        if not usable:
            raise HTTPException(status_code=404, detail="no cover")
        return FileResponse(path, media_type=IMAGE_TYPES[path.suffix.lower()],
                            headers={"X-Content-Type-Options": "nosniff"})

    @app.get("/icon/{domain}")
    def icon(domain: str):
        """A site's favicon, or its initial. Always an image, never a 404.

        The domain arrives from a note's `source`, which is frontmatter the
        user can edit, so it is validated before it becomes a path and the
        result is still checked for containment -- the same two steps the
        download side takes, because neither alone is enough.
        """
        name = domain.strip().lower()
        if is_domain(name):
            try:
                found = icon_path(cfg, name)
                if found is not None:
                    path = found.resolve()
                    inside = cfg.attachments_dir.resolve() in path.parents
                    suffix = path.suffix.lower()
                    if inside and suffix in ICON_TYPES and path.is_file():
                        return FileResponse(
                            path, media_type=ICON_TYPES[suffix],
                            headers={"Cache-Control": ICON_CACHE,
                                     "X-Content-Type-Options": "nosniff"})
            except (OSError, ValueError):
                pass
        return letter_icon(name)

    # --- the routes that write ----------------------------------------------
    #
    # All of them: POST, behind SameOriginOnly, 303 to a page that reads the
    # result back from the vault, and never a write of their own -- the three
    # vault functions are the only things that touch a file.

    def edit(link_id: str, change, done: str, stale: str, shelves=None) -> Edited:
        """Apply one change to one note, and say what to tell the user.

        `change(cfg, language)` is one of the vault's three editing functions,
        already bound to its own arguments. Three things are the same for all
        of them, which is why they share this:

        * `language` is the CONTENT language (`[ai] language`), never the
          interface language. It picks the note's headings and the index
          boilerplate, so passing the UI language here would re-render a
          Spanish note with English headings on every edit.
        * the change happens under the link's queue lock, so a background
          re-analysis cannot land on top of it -- and the lock is only taken
          for a link that exists, because a lock file is never deleted.
        * a failed write and a failed index rebuild are different answers.
          The first means nothing happened. The second means the change is on
          disk and only the indexes are behind.
        """
        live = current["cfg"]
        # Which shelf the note is on: a card is edited exactly the same way,
        # by the same three steps, over a different index.
        shelves = shelves or library
        shelves.refresh()
        if shelves.by_id(link_id) is None:
            return Edited(MISSING, False)
        try:
            with link_lock(link_id):
                if change(live, live.language) is None:
                    return Edited(MISSING, False)
        except Locked:
            return Edited("busy", False)
        except BadCategory:
            return Edited("bad-category", False)
        except IndexesStale as error:
            log.warning("the indexes could not be rebuilt: %s", error)
            shelves.refresh()
            return Edited(stale, True)
        except (OSError, ProtectedNote) as error:
            # A read-only vault, a trash/ that is a file, a full disk. Every
            # vault write is atomic and the rebuild has its own answer above,
            # so reaching here really does mean nothing was written.
            log.warning("the vault could not be written: %s", error)
            return Edited("write-failed", False)
        shelves.refresh()
        return Edited(done, True)

    @app.post("/item/{link_id}/category")
    def move(link_id: str, category: str = Form("")):
        if clean_category(category) is None:
            # Before the lock, so a refused name creates nothing anywhere --
            # not even the lock file. update_note() checks it again anyway.
            return see_other(item_url(link_id), notice="bad-category")
        result = edit(link_id, lambda cfg, language: update_note(
            cfg, link_id, language, category=category), "saved", "indexes-stale")
        if result.notice == MISSING:
            raise HTTPException(status_code=404, detail="no such link")
        return see_other(item_url(link_id), notice=result.notice)

    @app.post("/item/{link_id}/tags")
    def retag(link_id: str, tags: str = Form("")):
        wanted = [word for word in tags.replace(",", " ").split() if word]
        result = edit(link_id, lambda cfg, language: update_note(
            cfg, link_id, language, tags=wanted), "saved", "indexes-stale")
        if result.notice == MISSING:
            raise HTTPException(status_code=404, detail="no such link")
        return see_other(item_url(link_id), notice=result.notice)

    def mine(link_id: str, **change):
        """One of your three fields on one card, and nothing else.

        Only the cards: these fields exist on every Note, but a state and a
        score mean nothing on a link, and a 404 says that better than a
        button nobody can see would.
        """
        result = edit(link_id, lambda cfg, language: update_note(
            cfg, link_id, language, shelf=cfg.ocio, **change),
            "saved", "indexes-stale", shelves=shelf)
        if result.notice == MISSING:
            raise HTTPException(status_code=404, detail="no such card")
        return see_other(item_url(link_id), notice=result.notice)

    @app.post("/item/{link_id}/describe")
    def rewrite_card(background: BackgroundTasks, link_id: str):
        """Ask the model for this card's summary again, in your language.

        Only the cards: a link is re-read from its page by /reprocess, and
        a card has no page to re-read -- the catalog already said all it
        knows and what is left is how it is written.
        """
        shelf.refresh()
        if shelf.by_id(link_id) is None:
            raise HTTPException(status_code=404, detail="no such card")
        background.add_task(describe, current["cfg"], link_id,
                            trace=progress.note)
        return see_other(item_url(link_id), notice="rewriting")

    @app.post("/item/{link_id}/mine/state")
    def set_state(link_id: str, state: str = Form("")):
        return mine(link_id, state=state)

    @app.post("/item/{link_id}/mine/score")
    def set_score(link_id: str, score: str = Form("")):
        return mine(link_id, score=score)

    @app.post("/item/{link_id}/mine/note")
    def set_my_note(link_id: str, my_note: str = Form("")):
        return mine(link_id, my_note=my_note)

    @app.post("/item/{link_id}/mentions/delete")
    def drop_mention(link_id: str, name: str = Form("")):
        # No index names a mention, so update_note() does not rebuild them and
        # the "indexes-stale" notice cannot happen here.
        result = edit(link_id, lambda cfg, language: update_note(
            cfg, link_id, language, drop_mention=name), "saved", "indexes-stale")
        if result.notice == MISSING:
            raise HTTPException(status_code=404, detail="no such link")
        return see_other(item_url(link_id), notice=result.notice)

    @app.post("/item/{link_id}/delete")
    def remove(link_id: str):
        # Moves the file to <vault>/<folder>/trash/. The notice says so,
        # because "deleted" would be a lie and a worrying one.
        result = edit(link_id, lambda cfg, language: delete_note(
            cfg, link_id, language), "trashed", "trashed-indexes-stale")
        if result.notice == MISSING:
            raise HTTPException(status_code=404, detail="no such link")
        # A note that really went to trash/ sends the user back to the library,
        # whatever the indexes did: the item page would 404 on them now. A
        # refused delete leaves them on the note they still have.
        where = "/" if result.landed else item_url(link_id)
        return see_other(where, notice=result.notice)

    @app.post("/item/{link_id}/reprocess")
    def reprocess(request: Request, background: BackgroundTasks, link_id: str,
                  engine: str = Form(""), back: str = Form(""),
                  category: str = Form(""), tag: str = Form(""),
                  collection: str = Form(""), when: str = Form(""),
                  q: str = Form(""), page: str = Form("")):
        library.refresh()                 # a note deleted from Obsidian since the
        note = library.by_id(link_id)     # page was drawn must not be rewritten

        if note is None:
            raise HTTPException(status_code=404, detail="no such link")
        name = engine.strip() or None
        if name is not None and name not in ENGINE_NAMES:
            raise HTTPException(status_code=400, detail="unknown engine")
        # After the response, not before it: see reanalyze().
        # Pending now, not when the task gets round to it: the card that was
        # clicked polls for "is this being worked on", and between the answer
        # and the task starting there is no lock to find. It is also what the
        # note page has always said happens -- made true when it says it.
        with contextlib.suppress(OSError, ValueError):
            Queue().set_status(link_id, "pending")
        # The same list the batch page draws: one link re-analysed by hand is
        # the same five stages and the same model call, and the page that
        # shows them is the page to look at while this takes its minute.
        background.add_task(reanalyze, current["cfg"], note.url, name,
                            trace=progress.note)
        # Three destinations and no fourth: the listing the card was on --
        # the library or the search results -- or else the note's own page,
        # which is where the button on that page sends you back to.
        if request.headers.get("x-requested-with") == "redo":
            # The card's own script asked, and it is staying on the page it is
            # on: there is nothing to redirect it to and nothing to draw. A 204
            # says exactly that, and leaves no browser behaviour to assume.
            return Response(status_code=204)
        where = (return_url(back, category, tag, collection, when, q, page)
                 or item_url(link_id))
        return see_other(where, notice="queued")

    def collect(names, ids: list[str], add: bool, where: str):
        """Put every picked note into one collection, or take it out of it.

        One note failing does not stop the others: the twenty-nine that are
        still there belong in the project whatever happened to the thirtieth.
        The notice says how many of how many, because "saved" over a silent
        loss is the one answer this project never gives.

        No index is rebuilt. No file in the vault names a collection, so
        thirty notes joining a project write thirty notes and nothing else.
        """
        picked = [one for one in ids if one]
        if not picked:
            return see_other(where, notice="nothing-picked")
        # Spelled the way the library already spells it: which collections
        # exist is the index's business, and only this layer can ask it.
        wanted = normalize_collections(names, library.collections())
        if not wanted:
            return see_other(where, notice="bad-collection")
        name = wanted[0]
        done = 0
        for link_id in picked:
            change = (lambda cfg, language, link=link_id: update_note(
                cfg, link, language,
                **({"add_collection": name} if add else {"drop_collection": name})))
            if edit(link_id, change, "saved", "indexes-stale").landed:
                done += 1
        kind = "collect" if add else "uncollect"
        if done == len(picked):
            notice = f"{kind}ed-one" if done == 1 else f"{kind}ed"
        else:
            notice = f"{kind}-partial"
        return see_other(where, notice=notice, n=done, m=len(picked))

    @app.post("/collections/add")
    def add_to_collection(name: str = Form(""), id: list[str] = Form([]),
                          back: str = Form(""), category: str = Form(""),
                          tag: str = Form(""), collection: str = Form(""),
                          when: str = Form(""), q: str = Form(""),
                          page: str = Form("")):
        where = return_url(back, category, tag, collection, when, q, page) or "/"
        return collect([name], id, True, where)

    @app.post("/collections/remove")
    def remove_from_collection(name: str = Form(""), leave: str = Form(""),
                               id: list[str] = Form([]),
                               back: str = Form(""), category: str = Form(""),
                               tag: str = Form(""), collection: str = Form(""),
                               when: str = Form(""), q: str = Form(""),
                               page: str = Form("")):
        # `leave` is the button the user pressed, which names the collection
        # they are looking at. `name` is the box beside it, which is there to
        # join one; a form made by hand may still use it to say which to leave.
        where = return_url(back, category, tag, collection, when, q, page) or "/"
        return collect([leave or name], id, False, where)

    @app.post("/item/{link_id}/collections")
    def collections_of(link_id: str, add: str = Form(""), drop: str = Form("")):
        """One note, one collection at a time: a chip with an x to leave one,
        a box to join one. No list to re-type, and no separator to invent for
        names that have spaces in them."""
        if drop:
            result = edit(link_id, lambda cfg, language: update_note(
                cfg, link_id, language, drop_collection=drop), "saved", "indexes-stale")
        else:
            wanted = normalize_collections([add], library.collections())
            if not wanted:
                return see_other(item_url(link_id), notice="bad-collection")
            result = edit(link_id, lambda cfg, language: update_note(
                cfg, link_id, language, add_collection=wanted[0]),
                "saved", "indexes-stale")
        if result.notice == MISSING:
            raise HTTPException(status_code=404, detail="no such link")
        return see_other(item_url(link_id), notice=result.notice)

    @app.get("/categories", response_class=HTMLResponse)
    def category_page(request: Request):
        library.refresh()
        return page(request, "categories.html")

    @app.post("/categories/rename")
    def rename(old: str = Form(...), new: str = Form(...)):
        live = current["cfg"]
        library.refresh()
        target = clean_category(new)
        # Asked before the rename, because afterwards the two are one and
        # there is no way to tell that a merge is what happened.
        merging = target is not None and target != old and target in library.categories()
        stale = False
        try:
            # Each note is rewritten under its own lock, so a re-analysis that
            # finishes mid-rename is skipped and reported, not overwritten.
            result = rename_category(live, old, new, live.language, lock=link_lock)
        except BadCategory:
            return see_other("/categories", notice="bad-category")
        except IndexesStale as error:
            log.warning("the indexes could not be rebuilt: %s", error)
            result, stale = error.done, True
        except (OSError, ProtectedNote) as error:
            log.warning("the vault could not be written: %s", error)
            return see_other("/categories", notice="write-failed")
        library.refresh()
        if stale and result.failed and not result.moved:
            # A vault that cannot be written fails every note AND the rebuild.
            # "Saved, but the indexes..." would be a sentence about a write
            # that did not happen: say what landed, which is nothing.
            code = "write-failed"
        elif stale:
            # The counts lose their notice here. What the user has to know is
            # that the notes moved and the indexes did not follow.
            code = "indexes-stale"
        elif result.failed:
            code = PARTIAL[(result.moved == 1, len(result.failed) == 1)]
        elif merging and result.moved:
            code = "merged-one" if result.moved == 1 else "merged"
        else:
            code = "renamed-one" if result.moved == 1 else "renamed"
        return see_other("/categories", notice=code,
                         n=result.moved, m=len(result.failed))

    def config_file() -> Path:
        """The file this process reads its config from. `--config` arrives
        through the Config itself; CONFIG_PATH is the answer only for a Config
        that was never read from a file. Saving anywhere else would write a
        file the rest of the process does not read, and still say "saved"."""
        return current["cfg"].source or CONFIG_PATH

    def saved_provider() -> str:
        """Who the api engine talks to according to the file on disk."""
        return str(current["cfg"].engines.get("api", {}).get("provider",
                                                             "anthropic"))

    def key_variable(provider: str) -> str:
        """The variable the key for `provider` goes in.

        The table names one per provider, and config.toml can name its own.
        That one belongs to the provider the config names and to no other:
        ticking a different row must not send somebody to read a key out of a
        variable that was never meant for it.
        """
        api = current["cfg"].engines.get("api", {})
        override = str(api.get("key_env") or "")
        if override and provider == saved_provider():
            return override
        row = find_provider(provider)
        return row.key_env if row else override or "API_KEY"

    def provider_keys() -> dict[str, dict]:
        """Per provider: the variable, and whether a key can be found in it.

        Never the value. The page asks whether one is there, which is all it
        needs to say "paste it here" or "it is in place", and it asks for
        every row because every row is one tick away from being the one in
        use. One read of the .env answers the lot.
        """
        api = current["cfg"].engines.get("api", {})
        names = {p.id: key_variable(p.id) for p in PROVIDERS}
        found = env.present_each(set(names.values()), config_file())
        # A key written into config.toml counts: it is a bad place for it, but
        # saying "no key" over a key that works is worse. It is not tied to a
        # variable, so it counts for whichever row you tick.
        anywhere = bool(api.get("key"))
        return {pid: {"name": name, "ok": anywhere or found[name]}
                for pid, name in names.items()}

    def env_file_state() -> dict:
        """The .env itself: where it is, whether it is there, who can read it.

        About the file and not about any key -- which row needs which variable
        is `provider_keys`, and the value is nobody's business here.
        """
        where = env.path(config_file())
        return {"file": where, "exists": where.exists(),
                "exposed": env.exposed(config_file())}

    @app.get("/settings", response_class=HTMLResponse)
    def settings_page(request: Request):
        saved = current["cfg"]
        order = [name for name in saved.chain if name in WEB_ENGINES]
        order += [name for name in WEB_ENGINES if name not in order]
        waiting = len(owed(Queue())[0])
        api = saved.engines.get("api", {})
        known = find_provider(str(api.get("provider", "anthropic")))
        return page(request, "settings.html", cfg=saved, ui=saved.ui_language,
                    engines=order, config_path=config_file(),
                    # The whole table, every row a choice: the addresses are
                    # the point. Picking a provider should teach you what you
                    # are pointing at, and tell you where its key comes from
                    # before you have saved anything.
                    providers=PROVIDERS,
                    picked=known.id if known else "",
                    keys=provider_keys(),
                    # A provider somebody wrote by hand that this does not
                    # know. Said out loud rather than quietly unticked.
                    stranger="" if known else str(api.get("provider", "")),
                    by_hand=str(api.get("base_url", "")),
                    key=env_file_state(),
                    # So the page can stop talking about chmod on a system
                    # where the mode decides nothing. Not inside `key`: it is
                    # a fact about the machine, not about the key.
                    windows=places.WINDOWS,
                    # Read from disk, never asked for here: three engines with
                    # their timeouts is up to twelve seconds to open a page,
                    # and the slow case -- a server that is down -- is the
                    # common one.
                    models=read_models(),
                    # What the Procesar button would do, which is the saved
                    # size unless fewer links than that are left.
                    owed=waiting, size=min(saved.batch, waiting),
                    # Both language pickers are built from this one order. They
                    # used to be written out by hand and had drifted into
                    # opposite orders, which is a way to pick English while
                    # meaning Spanish.
                    languages=LANGUAGES, language_names=NATIVE_NAMES)

    @app.post("/settings")
    def save_settings(chain: list[str] = Form([]), language: str = Form(""),
                      default_content: str = Form(""), mentions: str = Form(""),
                      batch: str = Form(""),
                      interface: str = Form("", alias="ui_language"),
                      opencode_model: str = Form(""), ollama_model: str = Form(""),
                      api_model: str = Form(""), api_provider: str = Form("")):
        saved = current["cfg"]
        engines = {name: dict(options) for name, options in saved.engines.items()}
        for name, raw in (("opencode", opencode_model), ("ollama", ollama_model),
                          ("api", api_model)):
            model = model_name(raw)
            if model is None:                  # not a name: leave what is on disk
                continue
            if model:
                engines.setdefault(name, {})["model"] = model
            elif name in engines:
                engines[name].pop("model", None)
        # A provider the table does not have is not written: the file may name
        # a gateway of somebody's own, and this form must not be the thing
        # that replaces it with a guess.
        if find_provider(api_provider.strip()):
            engines.setdefault("api", {})["provider"] = api_provider.strip()
        # Every value is checked here, because config.load() would refuse the
        # file afterwards and the whole tool would stop reading its own config.
        picked = tuple(name for name in chain if name in ENGINE_NAMES)
        updated = dataclasses.replace(
            saved,
            chain=picked or saved.chain,
            language=language if language in LANGUAGES else saved.language,
            default_content=(default_content if default_content in CONTENT_MODES
                             else saved.default_content),
            mentions=mentions if mentions in MENTION_MODES else saved.mentions,
            batch=batch_size(batch, saved.batch),
            # One file, one save: the interface language used to go to a
            # separate file of Omarchy's, which is where the "saved, except
            # the language" notice came from. There is nothing left to half-fail.
            ui_language=interface if interface in LANGUAGES else saved.ui_language,
            engines=engines,
        )
        try:
            save_config(updated, config_file())
        except OSError as error:
            # The old file is still there, untouched: save() writes atomically
            # and backs up before it writes.
            log.warning("the config could not be saved: %s", error)
            return see_other("/settings", notice="settings-failed")
        current["cfg"] = updated
        return see_other("/settings", notice="saved")

    @app.get("/item/{link_id}/state")
    def link_state(link_id: str):
        """Whether this link is being worked on, for the card drawing a spinner.

        The queue and never the vault: every card the user clicked asks this
        every few seconds, and re-reading a thousand notes for it would be
        absurd. The lock is the honest half of the answer -- it dies with the
        process that held it, so nothing here can be stale -- and `pending`
        covers the moment between the click and the task reaching that lock.
        """
        q = Queue()
        try:
            entry = q.get(link_id)
            working = entry is not None and (entry.status == "pending"
                                             or q.held(link_id))
        except (OSError, ValueError):
            # An unreadable state tree. "Nobody is working on it" stops a
            # spinner; claiming work nobody is doing never stops one.
            return JSONResponse({"working": False, "status": "unknown"})
        return JSONResponse({"working": working,
                             "status": entry.status if entry else "unknown"})

    @app.post("/settings/models/{engine}")
    def find_models(engine: str):
        """Ask one engine what models it has, and write down the answer.

        Its own tiny form, so the button can sit in the row it belongs to
        without nesting a form inside the settings form -- and so pressing it
        does not save whatever is half-typed in that one.
        """
        if engine not in WEB_ENGINES:
            raise HTTPException(status_code=404, detail="no such engine")
        try:
            found = build_engine(engine, current["cfg"]).models()
        except Exception as error:
            # models() promises [] over raising and build_engine raises by
            # design (an unknown provider, a config it cannot use). Either way
            # the page has to come back, and come back saying so.
            log.info("could not list %s models: %s", engine, error)
            found = []
        remember_models(engine, found)
        if not found:
            return see_other("/settings", notice="models-none")
        return see_other("/settings", notice="models-found", n=len(found))

    @app.post("/settings/env")
    def make_env_file(provider: str = Form("")):
        """An empty .env with the right variable in it, to paste a key into.

        The variable is the one the row you pressed needs. A form cannot nest
        inside the settings form -- and this press must not save that form
        half typed -- so each row carries a one-field form of its own, and
        the field is which provider it belongs to. A name the table does not
        have chooses nothing: the file falls back to the saved row rather
        than growing a line named after whatever was posted.

        An existing file is never written to. What would be overwritten is a
        secret that exists nowhere else.
        """
        wanted = provider.strip()
        name = key_variable(wanted if find_provider(wanted) else saved_provider())
        if env_file_state()["exists"]:
            return see_other("/settings", notice="env-there")
        if not env.create(name, config_file()):
            return see_other("/settings", notice="env-failed")
        return see_other("/settings", notice="env-made")

    # --- analysing a batch of what the import left ---------------------------
    #
    # An imported chat leaves a thousand notes saved and none analysed: each
    # one is a model call, and running a thousand of them is a night. The
    # button here runs as many as the settings say, and this page draws it.

    @app.get("/retry", response_class=HTMLResponse)
    def retry_page(request: Request):
        live = current["cfg"]
        waiting = len(owed(Queue())[0])
        return page(request, "retry.html", owed=waiting,
                    size=min(live.batch, waiting), refresh=REFRESH)

    # --- a link pasted into the page ---------------------------------------
    #
    # What the bar panel is on Omarchy. The box is in the header of every
    # page, so this route is reached from wherever somebody happened to be
    # and always answers with the library: that is where the note will show
    # up when it is written.

    def save_card(kind: str, candidate, background: BackgroundTasks | None = None
                  ) -> tuple[str, str]:
        """Write the card for this candidate. Returns (link id, notice).

        An id of "" means nothing was written and the notice says why. The
        catalog is asked first and the vault is touched afterwards: a
        lookup that fails at the last step must leave no half note behind.
        """
        full = catalog_of(candidate.via).card(candidate)
        if full is None:
            return "", "catalogue-silent"
        found = find_note(current["cfg"], link_id(full.url), shelf=current["cfg"].ocio)
        if found is not None:
            # Two tabs on the same button. The note that is already there is
            # the one with your score in it, so it stays exactly as it is.
            return found[1].id, "already-saved"
        live = current["cfg"]
        note = cards.note_from_card(full, kind, live.language, today())
        note.cover = download_cover(live, full.poster, note.id)
        try:
            write_note(live, note, live.language,
                       path=note_path(live, note, shelf=live.ocio))
            rebuild_indexes(live, live.language, shelf=live.ocio)
        except (OSError, ProtectedNote):
            return "", "write-failed"
        shelf.refresh()
        if background is not None:
            # After the response and only for a card that was just written:
            # the second save of the same card has nothing to improve.
            background.add_task(describe, live, note.id, trace=progress.note)
        return note.id, ""

    @app.get("/ocio", response_class=HTMLResponse)
    def leisure(request: Request, tipo: str = "", estado: str = ""):
        """The cards. A film is not a link about Docker, and the shelf that
        holds one does not hold the other.

        An unknown filter shows everything rather than nothing: these
        arrive from a URL somebody can type, and an empty page would look
        like an empty shelf.
        """
        shelf.refresh()
        notes = shelf.notes
        if tipo in cards.KINDS:
            notes = [n for n in notes if n.type == tipo]
        if estado in vault_states:
            notes = [n for n in notes if n.state == estado]
        return page(request, "ocio.html", notes=notes, kind=tipo, state=estado,
                    counted=_count_by(shelf.notes, "type"),
                    states=_count_by(shelf.notes, "state"),
                    unreadable_cards=shelf.unreadable,
                    KINDS=KIND_WORDS, STATES=STATE_ORDER,
                    STATE_WORDS=dict(STATE_ORDER))

    def ask_catalogs(tipo: str, query: str, year: str = "") -> tuple[list, str]:
        """Every answer the catalogs give, and the reason a silent one gives.

        Read-only, and that is the point: this is asked by the list, which
        is a GET, and by the paste box, which is a POST. Whoever writes a
        card writes it from the POST.
        """
        found: list = []
        failed = ""
        for client, via in catalogs_for(tipo):
            rows, why = client.search(tipo, query, via=via)
            found.extend(rows)
            failed = failed or why
        if year:
            # A year nobody matches leaves the whole list: better the six
            # Terminators than an empty page because a digit was mistyped.
            found = [c for c in found if c.year == year] or found
        return found, failed

    def only_one_meant(tipo: str, query: str, year: str):
        """The candidate a request can only mean, or None.

        An id names one thing, and so does a year that leaves exactly one
        answer. Both skip the list -- from the paste box, which is where
        the save happens.
        """
        ref = cards.reference(query)
        if ref:
            return Candidate(ref=ref, kind=tipo, via=catalog_type_for(tipo),
                             title=query)
        if not year:
            return None
        found, _ = ask_catalogs(tipo, query, year)
        return found[0] if len(found) == 1 and found[0].year == year else None

    @app.get("/ocio/buscar", response_class=HTMLResponse)
    def card_candidates(request: Request, tipo: str = "", q: str = "",
                        year: str = ""):
        """Which one you meant. A page and nothing else: it writes nothing.

        Cinemeta answers "terminator" with Judgment Day first and the 1984
        one second, so picking is usually the feature and not a step in the
        way. A GET that wrote a note would be a note anybody could make the
        browser write with an <img>, so the shortcuts live on the POST and
        what an id names is offered here as one row with its button.
        """
        query = " ".join(q.split())[:cards.LONGEST]
        if tipo not in cards.KINDS or not query:
            raise HTTPException(status_code=404, detail="no such search")
        ref = cards.reference(query)
        if ref:
            one = Candidate(ref=ref, kind=tipo, via=catalog_type_for(tipo),
                            title=query)
            full = catalog_of(one.via).card(one)
            # An id the catalog does not know says so here rather than as a
            # notice on the library: this page is where it was asked.
            named = [] if full is None else [
                dataclasses.replace(one, title=full.title, year=full.year,
                                    rating=full.rating, poster=full.poster)]
            return page(request, "candidates.html", kind=tipo, query_text=query,
                        candidates=named, failed="")
        found, failed = ask_catalogs(tipo, query, year)
        # The reason travels even when there are rows; the page shows it
        # only when there are none, because one of the two catalogs being
        # down while the other answers is not a failure anybody reads about.
        return page(request, "candidates.html", kind=tipo, query_text=query,
                    candidates=found[:cards.MOST], failed=failed)

    @app.post("/ocio/guardar")
    def save_the_card(background: BackgroundTasks, tipo: str = Form(""),
                      ref: str = Form(""), via: str = Form("")):
        """The button on a candidate. Written at once, with no model.

        The catalog already answered and its synopsis is text; what takes
        minutes is the rewrite in Spanish, and that happens later over a
        note that already exists.
        """
        if tipo not in cards.KINDS or not ref:
            raise HTTPException(status_code=404, detail="no such card")
        candidate = Candidate(ref=ref, kind=tipo,
                              via=via if via in ("movie", "series", "book")
                              else catalog_type_for(tipo), title="")
        saved, notice = save_card(tipo, candidate, background)
        if not saved:
            return see_other("/ocio", notice=notice)
        return see_other(item_url(saved), notice=notice)

    @app.post("/add")
    def add_pasted(background: BackgroundTasks, url: str = Form(""),
                   content: str = Form("")):
        """Take a pasted link, answer at once, read the page afterwards.

        What this route decides is only what the page says back. The pipeline
        never overwrites a note it did not just make, so a library index that
        is a second out of date here costs a message and never a note.
        """
        # Before pasted_link(), because "película:Terminator" is not a link
        # and never will be: asked afterwards, every card request would come
        # back as "that is not a link".
        asked = cards.wanted(url)
        if asked is not None:
            # An id, or a year that leaves one answer, is not a question:
            # it is saved here, where the origin of the request was
            # checked, and the list is left to the ones that are.
            only = only_one_meant(asked.kind, asked.query, asked.year)
            if only is not None:
                saved, notice = save_card(asked.kind, only, background)
                if saved:
                    return see_other(item_url(saved), notice=notice)
            # The year travels as its own parameter and not as part of the
            # query: the catalog searches by title, and the year is what
            # picks among the answers.
            return see_other("/ocio/buscar", tipo=asked.kind, q=asked.query,
                             year=asked.year)
        if cards.prefixed(url):
            return see_other("/", notice="no-title")
        clean = pasted_link(url)
        if not clean:
            return see_other("/", notice="not-a-link")
        if is_search_url(clean):
            return see_other("/", notice="searched")
        library.refresh()
        if library.by_id(link_id(clean)) is not None:
            return see_other("/", notice="already-saved")
        # Neither button pressed is not a mode: `default_content` decides,
        # which is what the CLI does with no --full and no --summary.
        mode = content if content in CONTENT_MODES else None
        # After the response, not before it: see fetch(). The trace goes to
        # the same list the Reprocessing page draws, so one pasted link can be
        # watched there like any other work.
        background.add_task(fetch, current["cfg"], clean, mode, trace=progress.note)
        return see_other("/", notice="reading")

    @app.post("/retry")
    def start_batch(background: BackgroundTasks, debug: str = Form("")):
        live = current["cfg"]
        if debug:
            # This batch and no other: the box is on the page that starts a
            # run, not in Settings, because every run after this one writing
            # the full text of every page to disk is not what a tick meant.
            live = dataclasses.replace(live, trace_to=trace_run())
        # The same listing retry() walks, so the bar's total cannot promise
        # work the run will not find.
        waiting = len(owed(Queue())[0])
        if not waiting:
            return see_other("/retry", notice="nothing-owed")
        if not progress.start(min(live.batch, waiting)):
            # Two runs would reach for the same links and pay twice for each.
            return see_other("/retry", notice="batch-running")
        # After the response, not before it: a batch of fifty is an hour.
        background.add_task(run_batch, live, progress, live.batch)
        return see_other("/retry", notice="batch-started")

    # --- importing a WhatsApp export ---------------------------------------
    #
    # Two requests. The first reads the file and writes nothing; the second
    # writes. The text crosses between them through import_file's staging
    # folder, named by a token, because the file itself cannot: a browser will
    # not re-send one, and the alternative is making the user pick it twice.

    @app.get("/import", response_class=HTMLResponse)
    def import_page(request: Request):
        return page(request, "import.html")

    @app.post("/import", response_class=HTMLResponse)
    async def import_preview(request: Request, file: UploadFile = File(...)):
        """Say what the export holds. This route writes no note, by construction:
        it calls nothing that can."""
        try:
            text = text_of(await file.read())
            scan = parse_export(text)
        except (BadUpload, BadExport) as error:
            return page(request, "import.html", status_code=400, problem=str(error))
        # This route reads notes -- to say how many of these links the library
        # already holds -- so it refreshes first, like every other route that
        # does. Without it a second import of the same file offers to write
        # every link again.
        library.refresh()
        return page(request, "import.html", token=stage(text),
                    preview=preview_of(scan, {note.id for note in library.notes}))

    @app.post("/import/confirm", response_class=HTMLResponse)
    def import_confirm(request: Request, token: str = Form("")):
        """Write the staged export. The browser sends back the token and nothing
        else, so what is written is what the preview parsed and not what a form
        says it was."""
        text = staged(token)
        if text is None:
            # A refresh re-posts this form, and the upload is gone by then.
            # Saying so is what stops a second copy of every note.
            t = translator(current["cfg"].ui_language)
            return page(request, "import.html", status_code=400,
                        problem=t("That upload is no longer here. "
                                  "Choose the file again."))
        try:
            scan = parse_export(text)
        except BadExport as error:          # unreachable: the preview parsed it
            drop(token)
            return page(request, "import.html", status_code=400, problem=str(error))
        result = import_links(current["cfg"], scan.links)
        drop(token)
        # No library.refresh() here, unlike every route that reads notes: this
        # page lists none, and the next request refreshes on its way in. Doing
        # it here would re-parse all 1179 new notes at the end of the slowest
        # request in the app, for a page that does not look at them.
        return page(request, "import.html", result=result)

    app.state.library = library
    app.state.cfg = cfg               # the vault config: paths never change here
    app.state.settings = current      # the live one, which the settings page edits
    app.state.batch = progress
    return app
