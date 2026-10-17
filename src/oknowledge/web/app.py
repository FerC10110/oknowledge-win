"""The web: it shows the vault, and it is the only reader that can change it.

Every route that writes goes through one of three narrow doors -- update_note,
delete_note, rename_category -- and every one of them is a POST behind the
origin check below. Nothing here unlinks a note: deleting moves the file to
trash/, which is what makes a mis-click in a browser recoverable.
"""

from __future__ import annotations

import contextlib
import dataclasses
import datetime as dt
import logging
import math
import re
import threading
import time
import unicodedata
from collections import OrderedDict
from importlib.resources import files
from pathlib import Path
from collections.abc import Callable
from typing import NamedTuple
from urllib.parse import parse_qsl, quote, urlencode, urlsplit

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import (
    FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException as StarletteHTTPException

from .. import cards, env, places, undo
from ..catalog import Candidate, cinemeta, openlibrary
from ..ai import build_engine, can_search
from ..ai.base import normalize_collections
from ..ai.providers import PROVIDERS
from ..ai.providers import find as find_provider
from ..config import CONFIG_PATH, CONTENT_MODES, ENGINE_NAMES, MENTION_MODES, Config
from ..config import save as save_config
from ..idea_actions import SCOPES, may_serve
from ..ideas import IdeaFull, add_related, drop_related, new_idea
from ..i18n import LANGUAGES, NATIVE_NAMES, translator
from ..marks import clean_mark
from ..pipeline import add as add_link
from ..pipeline import describe, download_cover, icon_path, import_links
from ..pipeline import is_domain, owed
from ..pipeline import complete_idea, retitle_idea, run_idea_action, today
from ..models_cache import read as read_models
from ..models_cache import remember as remember_models
from ..queue import Locked, Queue
from ..trace import trace_run
from ..urls import is_search_url, link_id, normalize
from ..vault import ACTIONS, IDEA_STATES, MAX_RELATED, states_for
from ..vault import (
    BadCategory, IndexesStale, ProtectedNote, clean_category, delete_note,
    find_note, note_path, rebuild_indexes, rename_category, update_note,
    write_note,
)
from ..whatsapp import BadExport, parse as parse_export
from .batch import Batch
from .batch import run as run_batch
from .import_file import BadUpload, drop, stage, staged, text_of
from .library_view import (
    CHUNK, View, choose, date_groups, dot, is_url, paragraphs, reading_minutes, saves,
    short_date, side_groups, tint,
)
from .index import Library, read_full, terms
from .markup import section_cards
from .shelf_view import (AI_BUTTONS, CARD_CHIP, CARD_DOTS, IDEA_DOTS, IDEA_WORDS, KIND_NAMES, KIND_ONE,
                         SECTION_NAMES,
                         SORTS, TAB_OF, TABS, WORKING, CardView, IdeaView, card_filters,
                         catalog_name, choose_cards, choose_ideas, excerpt, idea_filters,
                         idea_url, poster_fill, scope_of, tab_of, web_domain, words_for,
                         year_of)
from .working import Working

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
    "bad-mark": "That is not an emoji the mark can be.",
    "bad-kind": "That is not a type a card can have.",
    "bad-state": "That is not a state it can be in.",
    "state-not-for-cards": "That state does not apply to Ocio cards.",
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
    # A delete asked by a script: the toast is one word, and Deshacer is
    # beside it (spec §6.3). A redirect keeps the long "trashed" sentence,
    # which is also true after the 5 s are gone.
    "deleted": "Deleted",
    "undo-gone": "It can no longer be undone",
    # Why a note stayed behind is not known here (another note took its
    # link, a symlink, an error...): the notices say where it is instead.
    "undo-blocked": "Nothing was restored: it is all still in oknowledge/trash/",
    "restored-one": "Restored",
    "restored": "%1 restored",
    "restored-one-partial": "Restored · %2 not restored, still in oknowledge/trash/",
    "restored-partial": "%1 restored · %2 not restored, still in oknowledge/trash/",
    "restored-indexes-stale": "Restored, but the indexes could not be rebuilt. "
                              "Run `oknowledge reindex` once the folder is "
                              "writable again.",
    # Both at once: the notes that did not come back are not to be lost
    # behind the stale indexes (the JSON lists them, the toast must too).
    "restored-one-partial-indexes-stale":
        "Restored · %2 not restored, still in oknowledge/trash/. The "
        "indexes could not be rebuilt: run `oknowledge reindex` once the folder "
        "is writable again.",
    "restored-partial-indexes-stale":
        "%1 restored · %2 not restored, still in oknowledge/trash/. The "
        "indexes could not be rebuilt: run `oknowledge reindex` once the folder "
        "is writable again.",
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
    "rewriting-all": "Rewriting the cards one after the other. Reload in a while to read them.",
    "nothing-to-rewrite": "Every card is already rewritten.",
    # Saving an idea: it is on disk already, and its name and tags come in
    # behind the page, like a card's summary.
    "completing": "Saved. The model is filling in the title and the tags: "
                  "reload in a moment to see them.",
    "idea-empty": "Write the idea first: there is nothing to save yet.",
    "idea-full": "That idea already has 16 links. Take one off before adding another.",
    "no-such-idea": "That idea is not there any more.",
    "title-empty": "Write a title: an empty one is not saved.",
    # An idea's action: it runs behind the page, like a card's summary.
    "thinking": "Thinking it over. Reload in a moment to read it.",
    "cannot-search": "No engine in your chain searches the web: "
                     "opencode or the Anthropic API do.",
    "not-a-catalog-link": "Only an IMDb or Open Library page makes a card. Paste it in the "
                          "Library to save it as a link.",
    "not-a-link": "That is not a link: it has to be an address, like "
                  "https://example.com/page.",
    "searched": "That is a page of search results, not a page. Open the result "
                "you want and paste that one.",
    "batch-started": "Analysing. This page comes back on its own; you can close it.",
    "batch-running": "A batch is already running. This page shows how it is going.",
    # The same start, said to a script: the modal stays open and the toast
    # says what started (spec §3.1); "this page comes back" would be false.
    "analysing": "Analysing %1 links",
    "analysing-one": "Analysing 1 link",
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
    "nothing-selected": "No notes were selected, so nothing changed.",
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

KEYS_HELP = (
    (("/",), "Search or paste a link"),
    (("1", "2", "3"), "Library · Leisure · Ideas"),
    (("j", "k", "←", "→"), "Previous / next"),
    (("↑", "↓"), "Row up / down"),
    (("↵",), "Open the original link"),
    (("f",), "Favorite"),
    (("e",), "Add a tag"),
    (("x",), "Select"),
    (("⌫",), "Delete the selected"),
    (("v",), "List / cards"),
    (("esc",), "Close / deselect"),
)
"""The shortcuts help (spec §3.2), in its order: the keys and a t() key."""

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
STALE = "stale"
"""edit()'s answer to an autosave whose revision is not newer than the last
one written: a newer text of that field already landed, so this one is not
written, and it is not an error either."""


REVISIONS_KEPT = 10000
"""How many (note, field, page) revisions the server remembers at most."""


def ordered(field: str, page: str | None, raw: str | None) -> tuple[str, str, float] | None:
    """An autosave's place in its page's order: the field, the page's id
    (any text the page chose; none is a page of its own) and its rev. None
    when there is no rev: always written."""
    number = revision(raw)
    return (field, page or "", number) if number is not None else None


def revision(raw: str | None) -> float | None:
    """An autosave's `rev`: a number the page raises with every save of a
    field. Anything else (the form without JavaScript sends none) is None,
    which is always written."""
    try:
        value = float(raw) if raw not in (None, "") else None
    except ValueError:
        return None
    return value if value is not None and math.isfinite(value) else None

SECTION_HOMES = {"links": "/", "ocio": "/ocio", "ideas": "/ideas"}
"""Where a shelf's notes are listed: where a delete and a Deshacer go."""

BULK_ACTIONS = ("category", "kind", "state", "mark", "delete")
"""What the floating bar can do to the ticked items (spec §5.1)."""

BULK_HOMES = {"category": "/", "mark": "/", "kind": "/ocio", "state": "/ideas", "delete": "/"}
"""Where a bulk action's redirect goes when no `back` came with it."""

SETTINGS_TABS = (("motores", "Engines"), ("idioma", "Language and saving"),
                 ("importar", "Import"), ("categorias", "Categories"))
"""Settings' four panes (spec §3.1), by the key their URL carries. The
labels are t() keys: the template asks for them through this table."""


def settings_url(tab: str) -> str:
    """Where a settings write goes back to: its own pane, or the page."""
    return f"/settings?tab={tab}" if tab in dict(SETTINGS_TABS) else "/settings"


def bulk_words(t, action: str, done: int, failed: int, label: str = "",
               unstar: bool = False, mixed: bool = False) -> str:
    """What a bulk action says (spec §5.1), in words: it names a category,
    a kind or a state, which a NOTICES key cannot carry in its numbers."""
    if action == "delete":
        said = t("Deleted") if done == 1 else t("%1 deleted", done)
    elif action == "mark":
        if unstar:
            said = t("Favorite removed from %1", done)
        else:
            said = t("1 marked as favorite") if done == 1 else t("%1 marked as favorites", done)
    elif mixed:
        # Ideas and cards in one batch: no state word fits both, so none is said.
        said = t("1 changed") if done == 1 else t("%1 changed", done)
    elif action == "state":
        # A state is not a place, and in Spanish it has a gender and a number
        # of its own ("descartada"): said with a verb that has none, and
        # quoted as the label it is in the menu, so it agrees with nothing.
        said = t("1 is now «%2»", done, label) if done == 1 else t("%1 are now «%2»", done, label)
    else:
        said = t("1 moved to %2", done, label) if done == 1 else t("%1 moved to %2", done, label)
    if failed:
        said += " · " + (t("1 could not be changed") if failed == 1
                         else t("%1 could not be changed", failed))
    return said


class Edited(NamedTuple):
    """What edit() answers: the notice to show, whether the change really
    landed on disk -- which is what decides where a delete sends the user, and
    must never be guessed from the notice -- and what the change returned
    (a delete's Trashed, which a Deshacer needs)."""

    notice: str
    landed: bool
    value: object = None

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


def cover_file(note, folder: Path, attachments: Path) -> Path | None:
    """The image a note's `cover` names, or None when there is none to show.

    `cover` comes from frontmatter the user can edit: untrusted input. It is
    relative to the folder the note is in, which is the shelf's -- a card's
    "../attachments/x.png" starts from ocio/, not links/ -- and must land in
    the attachments, be an image, and be there."""
    if not note.cover:
        return None
    try:
        path = (folder / note.cover).resolve()
        inside = attachments.resolve() in path.parents
        usable = inside and path.suffix.lower() in IMAGE_TYPES and path.is_file()
    except (OSError, ValueError):
        usable = False
    return path if usable else None


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


# What each step of the activity page did, for a person. The pipeline's own
# names (find, extract, analyze...) are its vocabulary, not the reader's.
STEP_WORDS = {
    "find": "Look for the note", "extract": "Read the page",
    "analyze": "Analyse with the model", "cover": "Fetch the picture",
    "save": "Save the note", "describe": "Rewrite the card",
    "complete": "Fill in the idea", "exists": "Look for it out there",
    "improve": "Improve the idea", "expand": "Expand the idea",
    "links": "Find links for the idea",
}
STEP_STATES = {"start": "in progress", "ok": "finished", "fail": "failed"}


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


GONE = "That is not there any more."
"""What a script is told when the note it was editing has gone."""

FAILURES = {"undo-gone": 404, "undo-blocked": 409, "bad-category": 400, "bad-mark": 400,
            "bad-kind": 400, "bad-state": 400, "state-not-for-cards": 400, "nothing-picked": 400, "nothing-selected": 400,
            "bad-collection": 400, "title-empty": 400, "busy": 409, "idea-full": 409,
            "cannot-search": 409, "no-such-idea": 404, "write-failed": 500,
            "settings-failed": 500, "env-failed": 500, "env-there": 409, "batch-running": 409}
"""The notices that mean nothing was written, and the status each is
answered with when a script asked for JSON. Every other notice landed."""


QUIET = {"saved"}
"""The notices that only say a write landed. A script shows that with its
indicator (spec §1), so its JSON leaves them out: a toast on every pause in
the typing would cover the ones that matter. A form's redirect still says
them, and every other notice of a write that landed (indexes-stale) is a
warning the toast has to show."""


RUNS = {"rewriting", "rewriting-all", "completing", "thinking"}
"""The notices that say a run started behind the page ("reload in a moment
to read it"). Their JSON says `runs`: a script that watches the run says
when it ends, and does not toast its start as if it had."""


async def sent_fields(request: Request) -> frozenset[str]:
    """Which form fields arrived, empty ones included. FastAPI hands an empty
    optional field over as None, the same as an absent one, and Settings has to
    tell "this pane has no such box" from "the box was emptied"."""
    return frozenset((await request.form()).keys())


def wants_json(request: Request) -> bool:
    """A script asking for the answer as data: the redesigned screens save in
    place and need to know how it went, not a page to go to (spec §1)."""
    return "application/json" in request.headers.get("accept", "")


ONWARD = ("undo", "reload")
"""What a script needs besides the words: the token Deshacer posts back
(spec §6.3) and whether the page must reload (§3.1)."""


def answer(request: Request, where: str, notice: str = "", extra: dict | None = None,
           **params) -> Response:
    """The answer to a write: a 303 for a form, JSON for a script.

    The JSON carries the notice in words, so the toast says what the page
    would have said after the redirect, plus `undo`/`reload` when given and
    whatever `extra` a route adds (the ids a Deshacer restored).
    """
    if not wants_json(request):
        params.pop("reload", None)            # never in a URL: the page is new anyway
        return see_other(where, notice=notice, **params)
    t = translator(request.app.state.settings["cfg"].ui_language)
    text = None if notice in QUIET else NOTICES.get(notice)
    said = t(text, params.get("n") or 0, params.get("m") or 0) if text else ""
    status = FAILURES.get(notice)
    if status is not None:
        return JSONResponse({"ok": False, "error": said}, status_code=status)
    body = {"ok": True, "notice": said}
    if notice in RUNS:
        body["runs"] = True
    body.update({key: params[key] for key in ONWARD if params.get(key)})
    body.update(extra or {})
    return JSONResponse(body)


IDEA_SEARCH_LIMIT = 12
"""Results beside an idea: enough to choose from, few enough to fit beside it."""


FRESH_SECONDS = 120
"""How long a link just pasted counts as being read before the queue has an
entry for it: the background task that enqueues it starts after the answer."""


def item_url(link_id: str) -> str:
    return "/item/" + quote(link_id, safe="")


def section_of(path: str) -> str | None:
    """Which sidebar section a page belongs to, by its path."""
    if path == "/" or path.startswith(("/lista", "/panel/")):
        return "links"
    for key in ("ocio", "ideas"):
        if path == f"/{key}" or path.startswith(f"/{key}/"):
            return key
    return None


def local_path(back: str) -> str | None:
    """A page of ours to go back to, or None.

    It arrives from a form, so it can arrive as anything: only a path on
    this server is taken, never another host (//x, \\x, a scheme), and a
    notice it already carries is dropped, with its numbers and its Deshacer
    token, so they do not pile up.
    """
    text = (back or "").strip()
    if not text.startswith("/") or text.startswith("//") or "\\" in text:
        return None
    if any(unicodedata.category(ch)[0] == "C" for ch in text):
        return None
    parts = urlsplit(text)
    if parts.scheme or parts.netloc:
        return None
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query)
                       if k not in ("notice", "n", "m", "undo")])
    return parts.path + ("?" + query if query else "")


def ideas_back(raw: str) -> str:
    """Where "← Ideas" goes: the list as it was when the idea was opened
    (spec §2), and never anywhere but the list."""
    path = local_path(raw)
    return path if path and (path == "/ideas" or path.startswith("/ideas?")) else "/ideas"


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
    """The models from a form, in order: "a, b", "" to clear them, None if
    it is not a list of names.

    Each is trimmed, the empty ones between two commas dropped and a repeat
    kept only where it first appears -- asking a model that just failed
    again is a wait for the same answer.
    """
    text = raw.strip()[:1000]
    if not text.isprintable():
        return None
    names: list[str] = []
    for part in text.split(","):
        name = part.strip()[:200]
        if name and name not in names:
            names.append(name)
    return ", ".join(names)


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

    # The undo lots of earlier runs: the server can run for weeks
    # (idle_timeout 0), so a lot is also purged whenever a new one is made.
    try:
        undo.purge()
    except OSError as error:
        log.warning("old undo lots could not be cleared: %s", error)
    library = Library(cfg)
    # The cards. A second index over a second folder, so a page of films
    # costs nothing to the 1184 links and the two can never mix.
    shelf = Library(cfg, shelf=cfg.ocio)
    # The ideas: a third index over a third folder, for the same reason.
    ideas = Library(cfg, shelf=cfg.ideas)
    # The settings page can change the engine chain while the server runs. The
    # vault paths it cannot change, so the library stays valid either way.
    current = {"cfg": cfg}
    # One batch at a time, in memory. A run only exists while this process
    # does, so there is nothing to resume after a restart and no stale file to
    # explain -- the queue on disk is the record of what is still owed.
    progress = Batch()
    # Which idea actions are running, and how each one last ended. In memory
    # and per process, like the batch.
    working = Working()
    app.state.working = working
    # The same for a card's rewrite: running, or how it last failed. A
    # rewrite runs behind the page, and without this a failure vanished.
    rewriting = Working()
    app.state.rewriting = rewriting
    templates = Jinja2Templates(directory=str(WEB.joinpath("templates")))
    templates.env.filters["plain"] = plain
    templates.env.filters["slug"] = lambda value: quote(str(value), safe="")
    templates.env.filters["dot"] = dot
    templates.env.filters["catalog_name"] = catalog_name
    templates.env.filters["poster_fill"] = poster_fill
    templates.env.filters["year_of"] = year_of
    templates.env.filters["tint"] = tint
    templates.env.filters["short_date"] = short_date
    templates.env.filters["paragraphs"] = paragraphs
    templates.env.tests["web_url"] = is_web_url
    templates.env.tests["search_link"] = is_search_url
    # A card whose cover file is gone is drawn as one with no cover: its
    # title over the kind's colour, never a broken image.
    templates.env.tests["drawn_cover"] = lambda note, on="ocio": cover_file(
        note, cfg.shelf(on).dir, cfg.attachments_dir) is not None
    templates.env.filters["web_domain"] = web_domain
    # The engines there is an icon for. A name outside this never reaches an
    # include: `engine:` is frontmatter and frontmatter is typed by hand.
    templates.env.globals["engines"] = ENGINE_ICONS
    templates.env.globals["KEYS_HELP"] = KEYS_HELP
    # The bulk bar's choices (spec §5), on whatever page includes it.
    templates.env.globals["KIND_ONE"] = KIND_ONE
    templates.env.globals["IDEA_WORDS"] = IDEA_WORDS
    templates.env.globals["IDEA_DOTS"] = IDEA_DOTS
    app.mount("/static", StaticFiles(directory=str(WEB.joinpath("static"))), name="static")

    def page(request: Request, name: str, status_code: int = 200, **context) -> HTMLResponse:
        # From the config in use, not from the one this app was built with: the
        # settings page saves a new Config, and the page that comes back has to
        # be in the language that was just picked.
        language = current["cfg"].ui_language
        t = translator(language)
        # Where this page is, for the forms that bring you back to it.
        here = request.url.path + ("?" + request.url.query if request.url.query else "")
        section = context.pop("section", None) or section_of(request.url.path)
        base = {"t": t, "lang": language, "query": "", "here": here,
                "marks": current["cfg"].marks, "active_mark": None,
                "unreadable": library.unreadable, "links_dir": cfg.links_dir,
                "heading": None, "prev_url": None, "next_url": None,
                "page": 1, "pages": 1, "notice": notice_for(request, t),
                # On every page, because the link to the batch is in the nav
                # and it says there how far along a run is. It is a read of
                # memory, not of the queue: no page pays for it.
                "batch": progress.snapshot(),
                "toast": False,
                # A Deshacer the redirect after a delete carries. Only for a
                # lot that still exists and is fresh: an old URL reloaded, or
                # an invented token, offers nothing (spec §2).
                "undo": (request.query_params.get("undo")
                         if "notice" in request.query_params
                         and undo.alive(request.query_params.get("undo"))
                         else None),
                "undo_back": local_path(here) or "/"}
        if library.error is not None:
            return templates.TemplateResponse(
                request=request, name="error.html", status_code=503,
                context={**base, "error": library.error, "categories": {},
                         "tags": {}, "collections": {},
                         "side": {"section": section, "counts": {
                             "links": 0, "ocio": 0, "ideas": 0}}})
        # Every shelf, because the filter is in the nav and the nav is on
        # every page. Each refresh is a stat per file, and the library one
        # already ran for this request anyway.
        for other in (shelf, ideas):
            other.refresh()
        return templates.TemplateResponse(
            request=request, name=name, status_code=status_code,
            context={**base,
                     "side": {"section": section,
                              "counts": {"links": len(library.entries),
                                         "ocio": len(shelf.entries),
                                         "ideas": len(ideas.entries)}},
                     "categories": library.categories(), "tags": library.tags(),
                     "collections": library.collections(), "collection": None,
                     **context},
        )

    @app.exception_handler(StarletteHTTPException)
    async def not_found(request: Request, exc: StarletteHTTPException):
        path = request.url.path
        if exc.status_code == 404 and wants_json(request):
            t = translator(request.app.state.settings["cfg"].ui_language)
            return JSONResponse({"ok": False, "error": t(GONE)}, status_code=404)
        if exc.status_code == 404 and not path.startswith(("/cover/", "/static/")):
            return page(request, "notfound.html", status_code=404)
        return await http_exception_handler(request, exc)

    fresh: dict[str, tuple[str, float]] = {}

    def analyzing() -> dict[str, str]:
        """{id: url} of the links being read now, newest first."""
        q = Queue()
        try:
            found = {e.id: e.url for e in q.busy()}
        except (OSError, ValueError):
            found = {}
        now = time.monotonic()
        for key, (url, at) in list(fresh.items()):
            if now - at > FRESH_SECONDS:
                fresh.pop(key, None)
            elif key not in found and q.get(key) is None:
                found = {key: url, **found}
        return found

    def listing(view: View, working: dict[str, str]) -> dict:
        notes = choose(library, view)
        known = {n.id for n in library.notes}
        # Only on the unfiltered list: a link being read has no category,
        # tag or mark yet, so no filter could hold it.
        pending = [] if view.filtered else [(i, u) for i, u in working.items() if i not in known]
        ids = [i for i, _ in pending] + [n.id for n in notes]
        current = view.sel if view.sel in ids else (ids[0] if ids else "")
        return {"view": view, "notes": notes[:view.hasta], "pending": pending,
                "busy": set(working), "total": len(notes) + len(pending),
                "more": len(notes) > view.hasta, "chunk": CHUNK,
                "current": current, "saving": saves(view.q),
                # Every note the view holds, for /lista?desde= to slice
                # without choosing them a second time.
                "chosen": notes}

    def panel_context(link_id: str, view: View, working: dict[str, str]) -> dict | None:
        """What the panel of one link shows, or None when there is no such
        link -- neither a note nor one being analysed right now."""
        entry = library.entry(link_id)
        if entry is None:
            url = working.get(link_id)
            return None if url is None else {"note": None, "panel_id": link_id,
                                             "pending_url": url, "reading": True,
                                             "list_url": view.url(sel="")}
        note = read_full(entry)
        ideas.refresh()
        return {"note": note, "panel_id": link_id, "reading": link_id in working,
                "minutes": reading_minutes(note.summary),
                # Your ideas, the dropped ones left out: the relation is
                # noticed while reading the link, so this is where it is made.
                "idea_choices": [(n.id, n.title) for n in ideas.notes if n.state != "dropped"],
                "back": view.url(sel=link_id),
                # The phone's "← Biblioteca" (docs/2026-10-15-rediseno-celular-design.md §6.1).
                "list_url": view.url(sel="")}

    def card_context(card_id: str, view) -> dict | None:
        """What a card's panel shows (spec §3), or None for no such card."""
        shelf.refresh()
        entry = shelf.entry(card_id)
        if entry is None:
            return None
        note = read_full(entry)
        running, failed = rewriting.of(card_id)
        return {"note": note, "panel_id": card_id, "card": True,
                "words": words_for(note.type), "rewriting": "describe" in running,
                "rewrite_failed": failed.get("describe", ""), "back": view.url(sel=card_id),
                "list_url": view.url(sel=""),
                "KIND_ONE": KIND_ONE, "KIND_NAMES": KIND_NAMES, "CARD_DOTS": CARD_DOTS}

    def library_groups(view: View) -> dict:
        """The library's sidebar groups, over the index as it is now.

        The dates group is the only one that depends on the view: its
        counters are what the other filters left.
        """
        return {**side_groups(library.notes, library.categories(), library.collections(),
                              current["cfg"].marks),
                **date_groups(library, view)}

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request):
        library.refresh()
        view = View.from_query(request.query_params)
        working = analyzing()
        shown = listing(view, working)
        panel = panel_context(shown["current"], view, working) if shown["current"] else None
        return page(request, "home.html", section="links", toast=True,
                    groups=library_groups(view),
                    default_content=current["cfg"].default_content,
                    save_prefixes=" ".join(sorted(cards.PREFIXES)),
                    panel=panel is not None, **shown, **(panel or {}))

    @app.get("/panel/{link_id}", response_class=HTMLResponse)
    def detail(request: Request, link_id: str):
        """The right column alone, for the list to swap in without a reload."""
        library.refresh()
        view = View.from_query(request.query_params)
        found = panel_context(link_id, view, analyzing())
        if found is None:
            card = card_context(link_id, CardView.from_query(request.query_params))
            if card is None:
                raise HTTPException(status_code=404, detail="no such link")
            return page(request, "card-panel.html", **card)
        return page(request, "panel.html", **found)

    @app.get("/lista", response_class=HTMLResponse)
    def list_column(request: Request, desde: str = ""):
        library.refresh()
        view = View.from_query(request.query_params)
        shown = listing(view, analyzing())
        if not desde:
            # The sidebar comes with the list, for a bulk action's counts.
            return page(request, "list.html", side_groups=library_groups(view), **shown)
        try:
            start = max(0, int(desde))
        except ValueError:
            start = 0
        notes = shown["chosen"]
        end = start + CHUNK
        return page(request, "list-more.html", **{**shown, "notes": notes[start:end],
                    "more": len(notes) > end, "next_desde": end,
                    "next_hasta": end + CHUNK})

    @app.get("/search")
    def search(q: str = ""):
        return see_other("/", q=" ".join(q.split()))

    @app.get("/marked")
    def marked(mark: str = ""):
        return see_other("/", mark=mark)

    def anywhere(link_id: str):
        """(entry, the shelf it is on), looking in the links first.

        One note page and one cover route serve both shelves: a card is a
        note, and everything a note page does -- read it, edit it, throw it
        away -- it does for a card too.
        """
        for shelves in (library, shelf, ideas):
            shelves.refresh()
            entry = shelves.entry(link_id)
            if entry is not None:
                return entry, shelves.shelf
        return None, None

    def links_for(note, q: str) -> tuple[bool, list]:
        """(whether `q` is a search at all, the links it finds that the idea
        does not hold yet). A word of two characters at least, counted
        after folding: one letter, or "#a", would list the whole library."""
        if max(map(len, terms(q)), default=0) < 2:
            return False, []
        linked = set(note.related)
        hits, _ = library.search(q, page=1, per_page=IDEA_SEARCH_LIMIT + len(linked))
        found = []
        for hit in hits:
            entry = library.entry(hit.note.id)
            if entry is None or entry.path.stem in linked:
                continue
            found.append(hit.note)
            if len(found) == IDEA_SEARCH_LIMIT:
                break
        return True, found

    @app.get("/item/{link_id}/buscar-links", response_class=HTMLResponse)
    def idea_link_search(request: Request, link_id: str, q: str = ""):
        """The idea's search box, as you type: a fragment, not a page."""
        ideas.refresh()
        idea = ideas.by_id(link_id)
        if idea is None:
            raise HTTPException(status_code=404, detail="no such idea")
        return page(request, "idea-links.html", note=idea, **links_context(idea, q))

    @app.get("/item/{link_id}", response_class=HTMLResponse)
    def item(request: Request, link_id: str):
        library.refresh()
        if library.error is not None:
            return page(request, "notfound.html")
        entry, where = anywhere(link_id)
        if entry is None:
            raise HTTPException(status_code=404, detail="no such link")
        if where.name == "links":
            # One screen for the library now: the note opens in its panel.
            params = request.query_params
            return see_other("/", sel=link_id, notice=params.get("notice"),
                             n=params.get("n"), m=params.get("m"))
        if where.name == "ideas":
            params = request.query_params
            return see_other(idea_url(link_id), notice=params.get("notice"),
                             n=params.get("n"), m=params.get("m"))
        # A card opens in Ocio's panel (spec §3).
        params = request.query_params
        return see_other("/ocio", sel=link_id, notice=params.get("notice"),
                         n=params.get("n"), m=params.get("m"))

    @app.get("/cover/{link_id}")
    def cover(link_id: str):
        entry, where = anywhere(link_id)
        note = entry.note if entry is not None else None
        if note is None or not note.cover:
            raise HTTPException(status_code=404, detail="no cover")
        path = cover_file(note, where.dir, cfg.attachments_dir)
        if path is None:
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

    def held_by(link_id: str):
        """Which Library holds this note and which Shelf to write on.

        The two editing routes a card shares with a link -- the tags and
        the delete -- are the same three steps over a different index, so
        the only thing they need to know is where the note lives. Links
        first, as everywhere else.
        """
        for shelves in (library, shelf, ideas):
            shelves.refresh()
            if shelves.by_id(link_id) is not None:
                return shelves, shelves.shelf
        return library, library.shelf

    # The newest revision written of each (note, field, page) an autosave
    # posts, in memory (review I-1): a save the browser gave up on can still
    # run late on the server, and must not land over that page's newer text.
    # Revs are ordered within one page only (final review I-1): they come
    # from each device's clock, and a device whose clock is behind must not
    # have its saves refused for another's. A restart forgets them, which is
    # safe: the page's next rev is the clock's. The oldest entries are
    # dropped past REVISIONS_KEPT, the same as a restart for those pages.
    revisions: OrderedDict[tuple[str, str, str], float] = OrderedDict()
    revisions_lock = threading.Lock()

    def edit(link_id: str, change, done: str, stale: str, shelves=None,
             rev: tuple[str, str, float] | None = None) -> Edited:
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
        key = (link_id, rev[0], rev[1]) if rev is not None else None

        def record():
            with revisions_lock:
                revisions[key] = max(rev[2], revisions.get(key, -math.inf))
                revisions.move_to_end(key)
                while len(revisions) > REVISIONS_KEPT:
                    revisions.popitem(last=False)

        try:
            with link_lock(link_id):
                # Under the lock, after the refresh: two saves of one field
                # from one page are ordered by their rev, not by when each
                # got here.
                if key is not None:
                    with revisions_lock:
                        if rev[2] <= revisions.get(key, -math.inf):
                            return Edited(STALE, False)
                try:
                    value = change(live, live.language)
                except IndexesStale:
                    if key is not None:          # written: only the indexes are behind
                        record()
                    raise
                if value is None:
                    return Edited(MISSING, False)
                if key is not None:
                    record()
        except Locked:
            return Edited("busy", False)
        except BadCategory:
            return Edited("bad-category", False)
        except IndexesStale as error:
            log.warning("the indexes could not be rebuilt: %s", error)
            shelves.refresh()
            return Edited(stale, True, error.done)
        except (OSError, ProtectedNote) as error:
            # A read-only vault, a trash/ that is a file, a full disk. Every
            # vault write is atomic and the rebuild has its own answer above,
            # so reaching here really does mean nothing was written.
            log.warning("the vault could not be written: %s", error)
            return Edited("write-failed", False)
        shelves.refresh()
        return Edited(done, True, value)

    def move_one(link_id: str, category: str, rebuild: bool = True) -> Edited:
        """A link to another category: the route's body, and each id of a
        bulk move. The name is checked by the caller, once."""
        return edit(link_id, lambda cfg, language: update_note(
            cfg, link_id, language, category=category, rebuild=rebuild),
            "saved", "indexes-stale")

    @app.post("/item/{link_id}/category")
    def move(request: Request, link_id: str, category: str = Form("")):
        if clean_category(category) is None:
            # Before the lock, so a refused name creates nothing anywhere --
            # not even the lock file. update_note() checks it again anyway.
            return answer(request, item_url(link_id), notice="bad-category")
        result = move_one(link_id, category)
        if result.notice == MISSING:
            raise HTTPException(status_code=404, detail="no such link")
        return answer(request, item_url(link_id), notice=result.notice)

    @app.post("/item/{link_id}/tags")
    def retag(request: Request, link_id: str, tags: str = Form(""), add: str = Form("")):
        # A card's tags are the catalog's genres, and correcting them by
        # hand is part of the design: the model never writes over them.
        shelves, which = held_by(link_id)
        # `add` is the panel's "+ tag" box: its words go after the ones
        # the note has, and a word typed twice is kept once.
        wanted = list(dict.fromkeys(
            word for word in (tags + " " + add).replace(",", " ").split() if word))
        result = edit(link_id, lambda cfg, language: update_note(
            cfg, link_id, language, shelf=which, tags=wanted),
            "saved", "indexes-stale", shelves=shelves)
        if result.notice == MISSING:
            raise HTTPException(status_code=404, detail="no such link")
        return answer(request, item_url(link_id), notice=result.notice)

    def stale_or(request: Request, link_id: str, result: Edited) -> Response:
        """A save's answer: ok, and `stale` when a newer text was there first."""
        if result.notice == STALE:
            return answer(request, item_url(link_id), extra={"stale": True})
        return answer(request, item_url(link_id), notice=result.notice)

    def mine(request: Request, link_id: str, rev: tuple[str, str, float] | None = None, **change):
        """One of your fields on one card or one idea, and nothing else.

        Not on a link: these fields exist on every Note, but a state and a
        score mean nothing on a link, and a 404 says that better than a
        button nobody can see would.
        """
        shelves, which = held_by(link_id)
        if which.name == "links":
            raise HTTPException(status_code=404, detail="no such card")
        result = edit(link_id, lambda cfg, language: update_note(
            cfg, link_id, language, shelf=cfg.shelf(which.name), **change),
            "saved", "indexes-stale", shelves=shelves, rev=rev)
        if result.notice == MISSING:
            raise HTTPException(status_code=404, detail="no such card")
        return stale_or(request, link_id, result)

    @app.post("/item/{link_id}/describe")
    def rewrite_card(request: Request, background: BackgroundTasks, link_id: str):
        """Ask the model again: a card's summary in your language,
        or an idea's name, tags, summary and points.

        Only the cards: a link is re-read from its page by /reprocess, and
        a card has no page to re-read -- the catalog already said all it
        knows and what is left is how it is written.
        """
        ideas.refresh()
        if ideas.by_id(link_id) is not None:
            if working.start(link_id, "complete"):
                background.add_task(complete, current["cfg"], link_id)
            return answer(request, idea_url(link_id), "completing")
        shelf.refresh()
        if shelf.by_id(link_id) is None:
            raise HTTPException(status_code=404, detail="no such card")
        if rewriting.start(link_id, "describe"):
            background.add_task(rewrite, current["cfg"], link_id)
        return answer(request, item_url(link_id), "rewriting")

    def restate_one(link_id: str, state: str, held=None) -> Edited:
        """A card's or an idea's state: the route's body, and each id of a
        bulk change. A link has no state: it is MISSING here, as its route
        has always said with a 404. `held` is the (Library, Shelf) the caller
        already looked up."""
        shelves, which = held or held_by(link_id)
        if which.name == "links":
            return Edited(MISSING, False)
        return edit(link_id, lambda cfg, language: update_note(
            cfg, link_id, language, shelf=cfg.shelf(which.name), state=state),
            "saved", "indexes-stale", shelves=shelves)

    @app.post("/item/{link_id}/mine/state")
    def set_state(request: Request, link_id: str, state: str = Form("")):
        result = restate_one(link_id, state)
        if result.notice == MISSING:
            raise HTTPException(status_code=404, detail="no such card")
        return answer(request, item_url(link_id), notice=result.notice)

    @app.post("/item/{link_id}/mine/score")
    def set_score(request: Request, link_id: str, score: str = Form("")):
        return mine(request, link_id, score=score)

    @app.post("/item/{link_id}/mine/note")
    def set_my_note(request: Request, link_id: str, my_note: str = Form(""),
                    title: str | None = Form(None),
                    title_was: str | None = Form(None), rev: str | None = Form(None),
                    page: str | None = Form(None)):
        # An idea's page sends its title with its text: one form, so a
        # renamed idea and its text land in one write. A card's never does.
        order = ordered("my_note", page, rev)
        shelves, which = held_by(link_id)
        if which.name != "ideas" or title is None:
            return mine(request, link_id, rev=order, my_note=my_note)
        # The box as it was drawn, and you did not touch it: the title on
        # disk stands, whatever the model named the idea since.
        wanted = None if title_was is not None and title == title_was else title

        def retitle(cfg, language):
            done = retitle_idea(cfg, link_id, wanted, my_note, language)
            if done is not None and done[1]:
                log.warning("%s", done[1])
            return done

        result = edit(link_id, retitle, "saved", "indexes-stale", shelves=shelves, rev=order)
        if result.notice == MISSING:
            raise HTTPException(status_code=404, detail="no such idea")
        return stale_or(request, link_id, result)

    @app.post("/item/{link_id}/title")
    def retitle_route(request: Request, link_id: str, title: str = Form(""),
                      rev: str | None = Form(None), page: str | None = Form(None)):
        """An idea's name, from the box in its header (spec §2). An empty box
        is not a name: the one on disk stays and the screen keeps what you
        typed. The file moves onto the name the title earns, as before."""
        ideas.refresh()
        if ideas.by_id(link_id) is None:
            raise HTTPException(status_code=404, detail="no such idea")
        if not title.strip():
            return answer(request, item_url(link_id), "title-empty")

        def rename(cfg, language):
            done = retitle_idea(cfg, link_id, title, None, language)
            if done is not None and done[1]:
                log.warning("%s", done[1])
            return done

        result = edit(link_id, rename, "saved", "indexes-stale", shelves=ideas,
                      rev=ordered("title", page, rev))
        if result.notice == MISSING:
            raise HTTPException(status_code=404, detail="no such idea")
        return stale_or(request, link_id, result)

    def mark_one(link_id: str, mark: str, held=None) -> Edited:
        """Your one emoji on a note: the route's body, and each id of a bulk
        star. `held` is the (Library, Shelf) the caller already looked up."""
        shelves, which = held or held_by(link_id)
        return edit(link_id, lambda cfg, language: update_note(
            cfg, link_id, language, shelf=cfg.shelf(which.name), mark=mark),
            "", "indexes-stale", shelves=shelves)

    @app.post("/item/{link_id}/mark")
    def set_mark(request: Request, link_id: str, mark: str = Form(""), back: str = Form("")):
        """Your one emoji on a note, on any shelf. Back to the card it was
        set from, so marking ten cards is ten taps and no scrolling.

        Success says nothing: the mark itself, on the card, is the answer.
        """
        shelves, which = held_by(link_id)
        if shelves.by_id(link_id) is None:
            raise HTTPException(status_code=404, detail="no such note")
        home = local_path(back) or item_url(link_id)

        def to_card(notice: str):
            if wants_json(request):
                return answer(request, home, notice)
            moved = see_other(home, notice=notice)
            moved.headers["location"] += "#card-" + quote(link_id, safe="")
            return moved

        if clean_mark(mark) is None:
            return to_card("bad-mark")
        result = mark_one(link_id, mark, (shelves, which))
        if result.notice == MISSING:
            raise HTTPException(status_code=404, detail="no such note")
        return to_card(result.notice)

    def retype_one(link_id: str, kind: str, rebuild: bool = True) -> Edited:
        """A card's type and the category that goes with it: the route's
        body, and each id of a bulk change. The kind is checked by the caller."""
        def retype(cfg, language):
            names = cards.CATEGORIES.get(language, cards.CATEGORIES["en"])
            return update_note(cfg, link_id, language, shelf=cfg.ocio, kind=kind,
                               category=names[kind], rebuild=rebuild)
        return edit(link_id, retype, "saved", "indexes-stale", shelves=shelf)

    @app.post("/item/{link_id}/kind")
    def change_kind(request: Request, link_id: str, kind: str = Form("")):
        """A card's type, and the category that goes with it, as when it was
        made (spec §3, "Cambiar tipo"). A type nobody knows changes nothing."""
        shelf.refresh()
        if shelf.by_id(link_id) is None:
            raise HTTPException(status_code=404, detail="no such card")
        home = f"/ocio?sel={quote(link_id, safe='')}"
        if kind not in cards.KINDS:
            return answer(request, home, "bad-kind")
        result = retype_one(link_id, kind)
        if result.notice == MISSING:
            raise HTTPException(status_code=404, detail="no such card")
        return answer(request, home, result.notice)

    @app.post("/item/{link_id}/mentions/delete")
    def drop_mention(request: Request, link_id: str, name: str = Form("")):
        # No index names a mention, so update_note() does not rebuild them and
        # the "indexes-stale" notice cannot happen here.
        result = edit(link_id, lambda cfg, language: update_note(
            cfg, link_id, language, drop_mention=name), "saved", "indexes-stale")
        if result.notice == MISSING:
            raise HTTPException(status_code=404, detail="no such link")
        return answer(request, item_url(link_id), notice=result.notice)

    def delete_one(link_id: str, rebuild: bool = True) -> tuple[Edited, str]:
        """One note to trash/, under its lock, on whichever shelf holds it:
        the delete route's body and each id of a bulk delete. Returns the
        shelf's name with the result, for the undo lot and the rebuilds."""
        shelves, which = held_by(link_id)
        result = edit(link_id, lambda cfg, language: delete_note(
            cfg, link_id, language, shelf=which, rebuild=rebuild),
            "trashed", "trashed-indexes-stale", shelves=shelves)
        return result, which.name

    def keep_lot(items) -> str | None:
        """The token a Deshacer posts back, or None when the state dir cannot
        be written: the notes are in trash/ either way and the delete stands."""
        try:
            return undo.remember(current["cfg"], items)
        except (OSError, ValueError) as error:
            # ValueError: a shelf or trash/ that is a symlink resolving outside the vault.
            log.warning("the undo lot could not be written: %s", error)
            return None

    @app.post("/item/{link_id}/delete")
    def remove(request: Request, link_id: str):
        # Moves the file to <vault>/oknowledge/trash/, any shelf. A note that
        # really went to trash/ sends the user back to its section, whatever
        # the indexes did (the item page would 404 now), with a Deshacer; a
        # refused delete leaves them on the note they still have.
        result, name = delete_one(link_id)
        if result.notice == MISSING:
            raise HTTPException(status_code=404, detail="no such link")
        if not result.landed:
            return answer(request, item_url(link_id), result.notice)
        token = keep_lot([(link_id, name, result.value)])
        notice = ("deleted" if result.notice == "trashed" and wants_json(request)
                  else result.notice)
        return answer(request, SECTION_HOMES[name], notice, undo=token)

    @app.post("/undo/{token}")
    def take_back(request: Request, token: str, back: str = Form("")):
        """Deshacer (spec §6.3): a lot's notes back where they were, once."""
        live = current["cfg"]
        result = undo.restore(live, token, live.language, link_lock)
        where = local_path(back)
        if result is None:
            return answer(request, where or "/", "undo-gone")
        for each in (library, shelf, ideas):
            each.refresh()
        home = where or SECTION_HOMES.get(result.shelf, "/")
        if not result.restored:
            return answer(request, home, "undo-blocked")
        n, m = len(result.restored), len(result.skipped)
        if m:
            code = "restored-one-partial" if n == 1 else "restored-partial"
            if result.stale:
                code += "-indexes-stale"
        elif result.stale:
            code = "restored-indexes-stale"
        else:
            code = "restored-one" if n == 1 else "restored"
        return answer(request, home, code, n=n, m=m or None,
                      extra={"restored": result.restored, "skipped": result.skipped})

    @app.post("/bulk/{action}")
    def bulk(request: Request, action: str, ids: list[str] = Form([]),
             category: str = Form(""), new_category: str = Form(""),
             kind: str = Form(""), state: str = Form(""), mark: str = Form(""),
             back: str = Form("")):
        """One action over the ticked items (spec §5.1).

        Each id goes through the function its own route uses, under its own
        lock. The value is checked once, before the first id: a refused one
        writes nothing. The indexes are rebuilt once per shelf at the end,
        not once per note. An id that is gone, on another shelf or busy is
        counted in `failed` and the others still land.
        """
        if action not in BULK_ACTIONS:
            raise HTTPException(status_code=404, detail="no such action")
        live = current["cfg"]
        t = translator(live.ui_language)
        home = local_path(back) or BULK_HOMES[action]
        picked = list(dict.fromkeys(one for one in ids if one))
        if not picked:
            return answer(request, home, "nothing-selected")
        label, unstar = "", False

        def restate_checked(link: str) -> tuple[Edited, str]:
            shelves, which = held_by(link)
            note = shelves.by_id(link)
            if note is None or which.name == "links":
                return Edited(MISSING, False), ""
            if state not in states_for(note.type):
                # Only a card can refuse one: the ideas take every state.
                return Edited("state-not-for-cards", False), ""
            return restate_one(link, state, (shelves, which)), which.name

        if action == "category":
            label = clean_category(category.strip() or new_category.strip())
            if label is None:
                return answer(request, home, "bad-category")
            one = lambda link: (move_one(link, label, rebuild=False), "links")
        elif action == "kind":
            if kind not in cards.KINDS:
                return answer(request, home, "bad-kind")
            label = t(KIND_NAMES[kind])
            one = lambda link: (retype_one(link, kind, rebuild=False), "ocio")
        elif action == "state":
            if state not in IDEA_STATES:
                return answer(request, home, "bad-state")
            label = t(IDEA_WORDS[state])
            one = restate_checked
        elif action == "mark":
            if mark != "⭐":
                return answer(request, home, "bad-mark")
            library.refresh()
            present = [n for n in (library.by_id(link) for link in picked) if n is not None]
            unstar = bool(present) and all(n.mark == "⭐" for n in present)
            wanted = "" if unstar else "⭐"
            one = lambda link: (mark_one(link, wanted, (library, live.links)), "links")
        else:
            one = lambda link: delete_one(link, rebuild=False)

        done, failed, refused, touched, lot = [], [], [], set(), []
        for link in picked:
            result, name = one(link)
            if result.landed:
                done.append(link)
                touched.add(name)
                if action == "delete":
                    lot.append((link, name, result.value))
            else:
                failed.append(link)
                refused.append(result.notice)
        stale = False
        if action in ("category", "kind", "delete") and done:
            for name in sorted(touched):
                try:
                    rebuild_indexes(live, live.language, live.shelf(name))
                except OSError as error:
                    log.warning("the indexes could not be rebuilt: %s", error)
                    stale = True
            for each in (library, shelf, ideas):
                each.refresh()
        if not done:
            worst = next((code for code in refused if code != MISSING), None)
            if worst is None:
                raise HTTPException(status_code=404, detail="none of them is there")
            return answer(request, home, worst)
        token = keep_lot(lot) if lot else None
        if not wants_json(request):
            if action == "delete":
                where = local_path(back) or SECTION_HOMES.get(lot[0][1], "/")
                return see_other(where, notice="trashed", undo=token)
            return see_other(home, notice="saved")
        # A state is said in the ideas' words only when only ideas took it.
        mixed = action == "state" and touched != {"ideas"}
        said = bulk_words(t, action, len(done), len(failed), label, unstar, mixed)
        if stale:
            said += " · " + t(NOTICES["indexes-stale"])
        body = {"ok": True, "notice": said, "done": done, "failed": failed}
        if token:
            body["undo"] = token
        return JSONResponse(body)

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
    def collections_of(request: Request, link_id: str, add: str = Form(""), drop: str = Form("")):
        """One note, one collection at a time: a chip with an x to leave one,
        a box to join one. No list to re-type, and no separator to invent for
        names that have spaces in them."""
        if drop:
            result = edit(link_id, lambda cfg, language: update_note(
                cfg, link_id, language, drop_collection=drop), "saved", "indexes-stale")
        else:
            wanted = normalize_collections([add], library.collections())
            if not wanted:
                return answer(request, item_url(link_id), notice="bad-collection")
            result = edit(link_id, lambda cfg, language: update_note(
                cfg, link_id, language, add_collection=wanted[0]),
                "saved", "indexes-stale")
        if result.notice == MISSING:
            raise HTTPException(status_code=404, detail="no such link")
        return answer(request, item_url(link_id), notice=result.notice)

    @app.post("/item/{link_id}/ideas")
    def join_idea(request: Request, link_id: str, idea: str = Form(""), back: str = Form(""),
                  q: str = Form("")):
        """Add this link to one of your ideas.

        The idea's note is the one written -- the relation lives there, so
        the idea reads on its own in Obsidian -- under the idea's lock, and
        read again inside it. Only a link joins: a card or another idea is
        not something an idea is built from. `back=idea` is the Add button
        of a suggestion on the idea's page, which returns there.
        """
        library.refresh()
        entry = library.entry(link_id)
        if entry is None:
            raise HTTPException(status_code=404, detail="no such link")
        stem = entry.path.stem
        # Added from the idea's own screen: back to it with the same query,
        # so the next result is one click away too.
        home = idea_url(idea, q=q) if back == "idea" else item_url(link_id)
        try:
            result = edit(idea, lambda cfg, language: add_related(
                cfg, idea, stem, language), "saved", "indexes-stale", shelves=ideas)
        except IdeaFull:
            return answer(request, home, "idea-full")
        if result.notice == MISSING:
            return answer(request, item_url(link_id), notice="no-such-idea")
        return answer(request, home, result.notice)

    @app.post("/item/{link_id}/related/drop")
    def leave_idea(request: Request, link_id: str, stem: str = Form("")):
        """Take one link off this idea, by the file name the idea holds --
        which is how a link that is gone can still be taken off."""
        result = edit(link_id, lambda cfg, language: drop_related(
            cfg, link_id, stem, language), "saved", "indexes-stale", shelves=ideas)
        if result.notice == MISSING:
            raise HTTPException(status_code=404, detail="no such idea")
        return answer(request, idea_url(link_id), result.notice)

    def rewrite(live: Config, card: str) -> None:
        """The background half of a card's rewrite: run it, then say how it
        ended. The caller has claimed it with rewriting.start."""
        problem: str | None = "it stopped before it could say why"
        failures: list[str] = []

        def heard(step) -> None:
            progress.note(step)
            if step.state == "fail" and step.detail:
                failures.append(step.detail)
        try:
            done = describe(live, card, trace=heard)
            problem = None if done else (failures[-1] if failures
                                         else "the model did not answer")
        except Exception as error:        # a background task has nowhere to raise to
            problem = str(error) or type(error).__name__
        finally:
            rewriting.finish(card, "describe", problem)

    def rewrite_all(live: Config, claimed: list[str]) -> None:
        """One after the other: the chain is one engine at a time anyway,
        and a free tier counts requests per minute."""
        for card in claimed:
            rewrite(live, card)

    def act(live: Config, idea: str, action: str, scope: str) -> None:
        """The background half of an action: run it, then say how it ended."""
        problem: str | None = "it stopped before it could say why"
        try:
            problem = run_idea_action(live, idea, action, "", trace=progress.note,
                                      scope=scope)
        except Exception as error:        # a background task has nowhere to raise to
            problem = str(error) or type(error).__name__
        finally:
            working.finish(idea, action, problem)

    def complete(live: Config, idea: str) -> None:
        """The background half of naming an idea: its title, tags, summary and
        points. Watched under "complete" like an action, so the screen can
        wait for the title (spec 2.2)."""
        problem: str | None = "it stopped before it could say why"
        failures: list[str] = []

        def heard(step) -> None:
            progress.note(step)
            if step.state == "fail" and step.detail:
                failures.append(step.detail)
        try:
            # The step's own reason when it gave one (the idea was deleted
            # meanwhile, the file was locked), as a card's rewrite says it.
            problem = (None if complete_idea(live, idea, trace=heard)
                       else failures[-1] if failures else "the model did not answer")
        except Exception as error:        # a background task has nowhere to raise to
            problem = str(error) or type(error).__name__
        finally:
            working.finish(idea, "complete", problem)

    @app.post("/item/{link_id}/actions/{action}")
    def ask_about_idea(request: Request, background: BackgroundTasks, link_id: str,
                       action: str, alcance: str = Form("")):
        """One of the actions on an idea, behind the page.

        `alcance` says which links improve and expand read (spec 2.1); the
        old `category`, `with_links` and `use` are not read any more. Already
        out there? needs an engine that searches, and ignores the scope.
        """
        if action not in ACTIONS:
            raise HTTPException(status_code=404, detail="no such action")
        ideas.refresh()
        if ideas.by_id(link_id) is None:
            return answer(request, "/ideas", "no-such-idea")
        live = current["cfg"]
        if action == "exists" and not can_search(live):
            return answer(request, idea_url(link_id, pestana="existe"), "cannot-search")
        scope = alcance if alcance in SCOPES else "vinculados"
        if working.start(link_id, action):
            background.add_task(act, live, link_id, action, scope)
        return answer(request, idea_url(link_id, pestana=TAB_OF.get(action, ""), alcance=scope),
                      "thinking")

    @app.get("/item/{link_id}/actions/state")
    def idea_state(link_id: str):
        """What is running on an idea and what last failed, for its screen to
        wait on (spec 2.2). In memory: a restart forgets it, as before."""
        ideas.refresh()
        note = ideas.by_id(link_id)
        if note is None:
            return JSONResponse({"ok": False, "running": [], "failed": [], "title": ""},
                                status_code=404)
        running, failed = working.of(link_id)
        return JSONResponse({"running": sorted(running), "failed": sorted(failed),
                             "title": note.title})

    @app.get("/categories")
    def category_page():
        """Renaming lives in Settings now (spec §3.1): an old bookmark lands there."""
        return RedirectResponse("/settings?tab=categorias", status_code=303)

    @app.post("/categories/rename")
    def rename(request: Request, old: str = Form(...), new: str = Form(...)):
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
            return answer(request, settings_url("categorias"), "bad-category")
        except IndexesStale as error:
            log.warning("the indexes could not be rebuilt: %s", error)
            result, stale = error.done, True
        except (OSError, ProtectedNote) as error:
            log.warning("the vault could not be written: %s", error)
            return answer(request, settings_url("categorias"), "write-failed")
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
        # `moved` tells settings.js whether the list under the modal changed
        # (a reload only then).
        return answer(request, settings_url("categorias"), code,
                      extra={"moved": result.moved}, n=result.moved, m=len(result.failed))

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

    def settings_context(tab: str) -> dict:
        """What Settings draws, on the page and in the modal (spec §3.1): one
        function, so the two cannot drift apart."""
        saved = current["cfg"]
        library.refresh()
        order = [name for name in saved.chain if name in WEB_ENGINES]
        order += [name for name in WEB_ENGINES if name not in order]
        waiting = len(owed(Queue())[0])
        api = saved.engines.get("api", {})
        known = find_provider(str(api.get("provider", "anthropic")))
        return {"tab": tab if tab in dict(SETTINGS_TABS) else "motores",
                "tabs": SETTINGS_TABS, "cfg": saved, "ui": saved.ui_language,
                "engines": order, "config_path": config_file(),
                # The whole table, every row a choice: the addresses are the
                # point. Picking a provider should teach you what you are
                # pointing at, and where its key comes from.
                "providers": PROVIDERS, "picked": known.id if known else "",
                "keys": provider_keys(),
                # A provider somebody wrote by hand that this does not know.
                # Said out loud rather than quietly unticked.
                "stranger": "" if known else str(api.get("provider", "")),
                "by_hand": str(api.get("base_url", "")), "key": env_file_state(),
                # So the page can stop talking about chmod on a system where
                # the mode decides nothing. Not inside `key`: it is a fact
                # about the machine, not about the key.
                "windows": places.WINDOWS,
                # Read from disk, never asked for here: three engines with
                # their timeouts is up to twelve seconds to open Settings, and
                # the slow case -- a server that is down -- is the common one.
                "models": read_models(),
                # What "Analizar" would do: the saved size unless fewer links
                # than that are left.
                "owed": waiting, "size": min(saved.batch, waiting),
                # Both language pickers are built from this one order (they
                # once drifted into opposite orders).
                "languages": LANGUAGES, "language_names": NATIVE_NAMES,
                "categories": library.categories()}

    @app.get("/settings", response_class=HTMLResponse)
    def settings_page(request: Request, tab: str = ""):
        return page(request, "settings.html", **settings_context(tab))

    @app.get("/settings/panel", response_class=HTMLResponse)
    def settings_panel(request: Request, tab: str = ""):
        """Settings without the page around it, for the modal (spec §3.1)."""
        language = current["cfg"].ui_language
        return templates.TemplateResponse(
            request=request, name="settings-body.html",
            context={"t": translator(language), "lang": language,
                     "batch": progress.snapshot(), **settings_context(tab)})

    # Settings' writes, one at a time: each reads the config, changes its
    # pane and writes it back. And the newest rev each page's pane wrote
    # (final review M-1): a save the page gave up on can still run late, and
    # must not put back older values over that pane's newer save.
    settings_lock = threading.Lock()
    settings_revisions: OrderedDict[tuple[str, str], float] = OrderedDict()

    @app.post("/settings")
    def save_settings(request: Request, chain: list[str] = Form([]), language: str = Form(""),
                      default_content: str = Form(""), mentions: str = Form(""),
                      batch: str = Form(""),
                      interface: str = Form("", alias="ui_language"),
                      opencode_model: str | None = Form(None),
                      ollama_model: str | None = Form(None),
                      api_model: str | None = Form(None), api_provider: str = Form(""),
                      tab: str = Form(""), rev: str | None = Form(None),
                      page: str | None = Form(None),
                      sent: frozenset[str] = Depends(sent_fields)):
        """One pane of Settings (spec §3.1). A field that does not arrive keeps
        what is saved: each pane is its own form and sends only its fields. An
        empty model box that does arrive still clears that model."""
        where = settings_url(tab)
        number = revision(rev)
        key = (page or "", tab)
        with settings_lock:
            if number is not None and number <= settings_revisions.get(key, -math.inf):
                return answer(request, where, extra={"stale": True})
            result, written = write_settings(request, where, sent, chain, language, default_content,
                                    mentions, batch, interface, opencode_model, ollama_model,
                                    api_model, api_provider)
            if number is not None and written:      # a refused write leaves no mark
                settings_revisions[key] = number
                settings_revisions.move_to_end(key)
                while len(settings_revisions) > REVISIONS_KEPT:
                    settings_revisions.popitem(last=False)
            return result

    def write_settings(request, where, sent, chain, language, default_content, mentions, batch,
                       interface, opencode_model, ollama_model, api_model, api_provider):
        """save_settings()'s write, under its lock: the answer, and whether
        the config was written."""
        saved = current["cfg"]
        engines = {name: dict(options) for name, options in saved.engines.items()}
        for name, raw in (("opencode", opencode_model), ("ollama", ollama_model),
                          ("api", api_model)):
            if f"{name}_model" not in sent:    # not in this pane: leave it
                continue
            model = model_name(raw or "")
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
            return answer(request, where, "settings-failed"), False
        current["cfg"] = updated
        # The interface language is in the config here: a change of it is
        # what makes the page reload to redraw itself in the other language.
        changed = updated.ui_language != saved.ui_language
        return answer(request, where, "saved", reload=changed or None), True

    @app.get("/item/{link_id}/state")
    def link_state(link_id: str):
        """Whether this link is being worked on, for the card drawing a spinner.

        The queue and never the vault: every card the user clicked asks this
        every few seconds, and re-reading a thousand notes for it would be
        absurd. The rule is the list's own, analyzing(): a lock some process
        holds -- it dies with that process, so nothing here can be stale -- or
        a link just added whose entry does not exist yet. A `pending` entry
        nobody holds is owed work, not work: its run died, and calling it
        working would keep an open page's card spinning for ever.

        A card is never in the queue: what works on it is a rewrite, and
        that is what it speaks for.
        """
        shelf.refresh()
        if shelf.by_id(link_id) is not None:
            running, failed = rewriting.of(link_id)
            if "describe" in running:
                return JSONResponse({"working": True, "status": "rewriting"})
            return JSONResponse({"working": False,
                                 "status": "failed" if failed.get("describe") else "ok"})
        q = Queue()
        try:
            entry = q.get(link_id)
            working = q.held(link_id) or link_id in analyzing()
            if entry is None and working:
                return JSONResponse({"working": True, "status": "pending"})
        except (OSError, ValueError):
            # An unreadable state tree. "Nobody is working on it" stops a
            # spinner; claiming work nobody is doing never stops one.
            return JSONResponse({"working": False, "status": "unknown"})
        return JSONResponse({"working": working,
                             "status": entry.status if entry else "unknown"})

    @app.post("/settings/models/{engine}")
    def find_models(request: Request, engine: str):
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
            return answer(request, settings_url("motores"), "models-none")
        return answer(request, settings_url("motores"), "models-found", n=len(found))

    @app.post("/settings/env")
    def make_env_file(request: Request, provider: str = Form("")):
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
            return answer(request, settings_url("motores"), "env-there")
        if not env.create(name, config_file()):
            return answer(request, settings_url("motores"), "env-failed")
        return answer(request, settings_url("motores"), "env-made")

    # --- analysing a batch of what the import left ---------------------------
    #
    # An imported chat leaves a thousand notes saved and none analysed: each
    # one is a model call, and running a thousand of them is a night. The
    # button here runs as many as the settings say, and this page draws it.

    @app.get("/retry", response_class=HTMLResponse)
    def retry_page(request: Request):
        live = current["cfg"]
        waiting = len(owed(Queue())[0])
        # Which note each line is about, by its title, from whichever shelf
        # holds it. A link being saved for the first time has none yet and
        # shows its id.
        for each in (library, shelf, ideas):
            each.refresh()
        seen = {line.link for line in progress.snapshot().lines}
        named = {}
        for link in seen:
            for each in (library, shelf, ideas):
                note = each.by_id(link)
                if note is not None:
                    named[link] = note.title or link
                    break
        now = dt.datetime.now(dt.timezone.utc)
        return page(request, "retry.html", owed=waiting,
                    size=min(live.batch, waiting), refresh=REFRESH,
                    named=named, now=now, STEP_WORDS=STEP_WORDS,
                    STEP_STATES=STEP_STATES)

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
        except (OSError, ProtectedNote):
            return "", "write-failed"
        notice = ""
        try:
            rebuild_indexes(live, live.language, shelf=live.ocio)
        except OSError as error:
            # The card is on disk and only the shelf's index is behind,
            # which is the distinction the editing routes already make:
            # "nothing happened" would send somebody to paste the title
            # again over a card that is already there.
            log.warning("the indexes could not be rebuilt: %s", error)
            notice = "indexes-stale"
        shelf.refresh()
        if background is not None:
            # After the response and only for a card that was just written:
            # the second save of the same card has nothing to improve.
            if rewriting.start(note.id, "describe"):
                background.add_task(rewrite, live, note.id)
        return note.id, notice

    def card_listing(view: CardView) -> dict:
        shelf.refresh()
        notes = choose_cards(shelf.notes, view)
        ids = [n.id for n in notes]
        running, _ = rewriting.all_of("describe")
        left = [n.id for n in shelf.notes if not n.engine]
        return {"view": view, "notes": notes[:view.hasta], "chosen": notes,
                "total": len(notes), "more": len(notes) > view.hasta, "chunk": CHUNK,
                # A pick that is not in the list opens the first card (spec §3).
                "current": view.sel if view.sel in ids else (ids[0] if ids else ""),
                "unrewritten": len(left),
                "rewriting_all": bool(left) and all(i in running for i in left),
                "busy": running, "KIND_ONE": KIND_ONE, "CARD_DOTS": CARD_DOTS, "CARD_CHIP": CARD_CHIP,
                "SORTS": SORTS, "words_for": words_for}

    @app.get("/ocio", response_class=HTMLResponse)
    def leisure(request: Request):
        """The cards (spec §3). An unknown filter shows everything rather
        than nothing: these arrive from a URL somebody can type."""
        view = CardView.from_query(request.query_params)
        shown = card_listing(view)
        params = request.query_params
        # The catalogs' answers take the panel's place (spec §3); without
        # JavaScript this is how the field's button shows them.
        found = candidates_context(params.get("buscar", ""),
                                   params.get("catalogo", "") or view.tipo,
                                   params.get("year", ""), grid=view.tipo)
        if found is not None:
            # The way back is to this list, with its estado, orden and q.
            found["list_url"] = view.url(sel="")
        card = None
        if found is None and shown["current"]:
            card = card_context(shown["current"], view)
        # One dict: both carry the kind tables, and a call cannot take a
        # keyword twice.
        return page(request, "ocio-shelf.html", section="ocio", toast=True,
                    filters=card_filters(shelf.notes, view),
                    save_prefixes=" ".join(sorted(cards.PREFIXES)),
                    unreadable_cards=shelf.unreadable, panel=card is not None,
                    catalog=found is not None, field_saves=saves(view.q),
                    **{**shown, **(card or {}), **(found or {})})

    @app.get("/ocio/lista", response_class=HTMLResponse)
    def card_column(request: Request, desde: str = ""):
        """The centre column alone: the live search and "show more" (spec §3)."""
        view = CardView.from_query(request.query_params)
        shown = card_listing(view)
        if not desde:
            # TIPO and ESTADO come with the list: their words, counts and
            # links follow the filter (final review I-1).
            return page(request, "ocio-list.html", side_filters=card_filters(shelf.notes, view),
                        **shown)
        try:
            start = max(0, int(desde))
        except ValueError:
            start = 0
        end = start + CHUNK
        notes = shown["chosen"]
        return page(request, "ocio-list-more.html", **{**shown, "notes": notes[start:end],
                    "more": len(notes) > end, "next_desde": end, "next_hasta": end + CHUNK})

    @app.post("/ocio/reescribir")
    def rewrite_every_card(request: Request, background: BackgroundTasks):
        """Every card still in the catalog's words, rewritten one after the
        other. A card already being rewritten is left to that run."""
        shelf.refresh()
        claimed = [n.id for n in shelf.notes
                   if not n.engine and rewriting.start(n.id, "describe")]
        if not claimed:
            return answer(request, "/ocio", "nothing-to-rewrite")
        background.add_task(rewrite_all, current["cfg"], claimed)
        return answer(request, "/ocio", "rewriting-all")

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

    def candidates_context(q: str, tipo: str, year: str = "",
                           grid: str = "") -> dict | None:
        """What the catalogs answer, for the panel (spec §3). All kinds is
        films; no words is no search."""
        query = " ".join(q.split())[:cards.LONGEST]
        if not query:
            return None
        kind = tipo if tipo in cards.KINDS else "movie"
        back = f"/ocio?tipo={grid}" if grid else "/ocio"
        ref = cards.reference(query)
        if ref:
            one = Candidate(ref=ref, kind=kind, via=catalog_type_for(kind), title=query)
            full = catalog_of(one.via).card(one)
            # An id the catalog does not know says so in the panel, where
            # it was asked.
            named = [] if full is None else [
                dataclasses.replace(one, title=full.title, year=full.year,
                                    rating=full.rating, poster=full.poster,
                                    people=full.people)]
            return {"query_text": query, "kind": kind, "candidates": named, "failed": "",
                    "KIND_ONE": KIND_ONE, "grid": grid, "list_url": back}
        found, failed = ask_catalogs(kind, query, year)
        # The reason travels even when there are rows; the panel shows it
        # only when there are none, because one of the two catalogs being
        # down while the other answers is not a failure anybody reads about.
        return {"query_text": query, "kind": kind, "candidates": found[:cards.MOST],
                "failed": failed, "KIND_ONE": KIND_ONE, "grid": grid,
                "list_url": back}

    @app.get("/ocio/candidatos", response_class=HTMLResponse)
    def catalog_candidates(request: Request, q: str = "", tipo: str = "", year: str = "",
                           grid: str = ""):
        """The catalogs' answers as the panel draws them. Writes nothing:
        saving is the POST of each row (a GET that wrote a card could be
        made by any <img>)."""
        found = candidates_context(q, tipo, year, grid if grid in cards.KINDS else "")
        if found is None:
            raise HTTPException(status_code=404, detail="no such search")
        return page(request, "catalog-panel.html", **found)

    def list_kept(estado: str, orden: str) -> dict:
        """The list's estado and orden, valid ones only, for a redirect to a
        catalog search: its way back is to that same list."""
        view = CardView.from_query({"estado": estado, "orden": orden})
        return {"estado": view.estado, "orden": "" if view.orden == "recientes" else view.orden}

    @app.get("/ocio/buscar")
    def card_candidates(q: str = "", tipo: str = "", year: str = "", estado: str = "",
                        orden: str = ""):
        """The old search page, and the field's button without JavaScript:
        the candidates live in Ocio's panel now."""
        query = " ".join(q.split())
        grid = tipo if tipo in cards.KINDS else ""
        if not query:
            return see_other("/ocio", tipo=grid, **list_kept(estado, orden))
        # `tipo` is the poster grid's filter and stays what it was;
        # `catalogo` is the kind the candidates are searched as.
        return see_other("/ocio", buscar=query, catalogo=grid or "movie", tipo=grid, year=year,
                         **list_kept(estado, orden))

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
        return see_other("/ocio", sel=saved, notice=notice)

    def idea_listing(view: IdeaView) -> dict:
        ideas.refresh()
        notes = choose_ideas(ideas.notes, view)
        return {"view": view, "notes": notes[:view.hasta], "chosen": notes,
                "total": len(notes), "more": len(notes) > view.hasta, "chunk": CHUNK,
                "IDEA_WORDS": IDEA_WORDS, "IDEA_DOTS": IDEA_DOTS}

    @app.get("/ideas", response_class=HTMLResponse)
    def idea_shelf(request: Request):
        """The ideas at full width (spec §2). An unknown filter is the usual
        view: these arrive from a URL somebody can type."""
        view = IdeaView.from_query(request.query_params)
        shown = idea_listing(view)
        return page(request, "idea-shelf.html", section="ideas", toast=True,
                    filters=idea_filters(ideas.notes, view),
                    unreadable_ideas=ideas.unreadable, **shown)

    @app.get("/ideas/lista", response_class=HTMLResponse)
    def idea_column(request: Request, desde: str = ""):
        """The list column alone, for the live search and "more". Registered
        before /ideas/{idea_id}, which would take "lista" for an id."""
        view = IdeaView.from_query(request.query_params)
        shown = idea_listing(view)
        if not desde:
            # ESTADO comes with the list, for a bulk action's counts.
            return page(request, "idea-list.html", side_filters=idea_filters(ideas.notes, view),
                        **shown)
        try:
            start = max(0, int(desde))
        except ValueError:
            start = 0
        end = start + CHUNK
        notes = shown["chosen"]
        return page(request, "idea-list-more.html", **{**shown, "notes": notes[start:end],
                    "more": len(notes) > end, "next_desde": end, "next_hasta": end + CHUNK})

    def links_context(note, q: str) -> dict:
        """The column beside an idea (spec 2). The rows that may help are
        ranked without asking anybody: words and tags in common."""
        library.refresh()
        by_stem = {entry.path.stem: entry.note for entry in library.entries}
        searched, found = links_for(note, q)
        # library.entries is newest first; may_serve() wants the vault's
        # order, oldest first.
        pool = [(entry.path, entry.note) for entry in reversed(library.entries)]
        return {"idea_id": note.id, "q": q, "searched": searched, "found": found,
                "related": [(stem, by_stem.get(stem)) for stem in note.related],
                "serve": [] if searched else [link for _, link in may_serve(note, pool)],
                "library_total": len(library.entries)}

    def idea_context(note, pestana: str, alcance: str, back: str, q: str) -> dict:
        """What an idea's screen shows (spec §2)."""
        tab, scope, home = tab_of(pestana), scope_of(alcance), ideas_back(back)
        running, failed = working.of(note.id)
        links = links_context(note, q)     # it refreshes the library
        present = {entry.path.stem for entry in library.entries}
        params = {"pestana": tab, "alcance": scope, "back": home, "q": q}
        return {
            **links,
            "note": note, "tab": tab, "scope": scope, "back": home, "q": q,
            "url": lambda **changes: idea_url(note.id, **{**params, **changes}),
            "running": running, "failed": failed,
            "searchable": can_search(current["cfg"]),
            "linked_now": sum(1 for stem in note.related if stem in present),
            # While the model names a new idea, the box shows the start of
            # its text, dimmed, and the screen's poll fills the name in.
            "placeholder": (excerpt(note.my_note)
                            if "complete" in running and not note.title.strip() else ""),
            "sections": {action: section_cards(note.actions.get(action, ""))
                         for action in ("exists", "improve", "expand")},
            "IDEA_STATES": IDEA_STATES, "IDEA_WORDS": IDEA_WORDS, "TABS": TABS,
            "AI_BUTTONS": AI_BUTTONS, "WORKING": WORKING, "SECTION_NAMES": SECTION_NAMES,
        }

    @app.get("/ideas/{idea_id}", response_class=HTMLResponse)
    def idea_screen(request: Request, idea_id: str, pestana: str = "", alcance: str = "",
                    back: str = "", q: str = ""):
        """One idea on a screen of its own. One that is not there is the app's 404."""
        ideas.refresh()
        entry = ideas.entry(idea_id)
        if entry is None:
            raise HTTPException(status_code=404, detail="no such idea")
        return page(request, "idea.html", section="ideas", toast=True,
                    **idea_context(read_full(entry), pestana, alcance, back, q))

    def save_idea(note) -> str:
        """Write a new idea and its shelf's index. Returns the notice, and
        raises when the note itself could not be written -- the two are
        told apart for the reason save_card tells them apart."""
        live = current["cfg"]
        write_note(live, note, live.language,
                   path=note_path(live, note, shelf=live.ideas))
        notice = "completing"
        try:
            rebuild_indexes(live, live.language, shelf=live.ideas)
        except OSError as error:
            log.warning("the indexes could not be rebuilt: %s", error)
            notice = "indexes-stale"
        ideas.refresh()
        return notice

    @app.post("/ideas/guardar")
    def save_the_idea(background: BackgroundTasks, text: str = Form(""),
                      title: str = Form(""), q: str = Form("")):
        """The "New idea" button of the list's field. Written at once, with
        your text; the name, the tags, the summary and the points come in
        behind the page.

        No text, no idea: the model has nothing to read, and a title alone
        is a note you would not know what to do with in a month. The field
        on /ideas is named `q`, the one it searches with.
        """
        text = text or q
        if not text.strip():
            return see_other("/ideas", notice="idea-empty")
        live = current["cfg"]
        instant = dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds")
        note = new_idea(text, title, today(), instant)
        try:
            notice = save_idea(note)
        except (OSError, ProtectedNote) as error:
            log.warning("the idea could not be written: %s", error)
            return see_other("/ideas", notice="write-failed")
        if working.start(note.id, "complete"):
            background.add_task(complete, live, note.id)
        return see_other(idea_url(note.id), notice=notice)

    @app.post("/add")
    def add_pasted(background: BackgroundTasks, url: str = Form(""),
                   content: str = Form(""), q: str = Form(""),
                   en: str = Form(""), tipo: str = Form(""), estado: str = Form(""),
                   orden: str = Form("")):
        """Take a pasted link, answer at once, read the page afterwards.

        What this route decides is only what the page says back. The pipeline
        never overwrites a note it did not just make, so a library index that
        is a second out of date here costs a message and never a note.

        The unified field on the library sends its text as `q`; the older
        paste box sent `url`.
        """
        url = url or q
        # Before pasted_link(), because "película:Terminator" is not a link
        # and never will be: asked afterwards, every card request would come
        # back as "that is not a link".
        asked = cards.wanted(url)
        if asked is None and en == "ocio":
            # "www.imdb.com/…" is a link too: read it as /add reads any link.
            asked = cards.from_link(pasted_link(url) or url, tipo)
        if asked is not None:
            # An id, or a year that leaves one answer, is not a question:
            # it is saved here, where the origin of the request was
            # checked, and the list is left to the ones that are.
            only = only_one_meant(asked.kind, asked.query, asked.year)
            if only is not None:
                saved, notice = save_card(asked.kind, only, background)
                if saved:
                    return see_other("/ocio", sel=saved, notice=notice)
            # The year travels as its own parameter and not as part of the
            # query: the catalog searches by title, and the year is what
            # picks among the answers.
            return see_other("/ocio", buscar=asked.query, catalogo=asked.kind,
                             tipo=tipo if tipo in cards.KINDS else "", year=asked.year,
                             **list_kept(estado, orden))
        if en == "ocio":
            # Ocio's field: a page that is no catalog's is not a card, and
            # plain words are a search of the catalogs (spec §3).
            if is_url(url):
                return see_other("/ocio", notice="not-a-catalog-link")
            words = " ".join(url.split())
            if not words:
                return see_other("/ocio")
            grid = tipo if tipo in cards.KINDS else ""
            return see_other("/ocio", buscar=words, catalogo=grid or "movie", tipo=grid,
                             **list_kept(estado, orden))
        if cards.prefixed(url):
            return see_other("/", notice="no-title")
        clean = pasted_link(url)
        if not clean:
            return see_other("/", notice="not-a-link")
        if is_search_url(clean):
            return see_other("/", notice="searched")
        library.refresh()
        if library.by_id(link_id(clean)) is not None:
            return see_other("/", sel=link_id(clean), notice="already-saved")
        # Neither button pressed is not a mode: `default_content` decides,
        # which is what the CLI does with no --full and no --summary.
        mode = content if content in CONTENT_MODES else None
        # After the response, not before it: see fetch(). The trace goes to
        # the same list the Reprocessing page draws, so one pasted link can be
        # watched there like any other work.
        new = link_id(clean)
        fresh[new] = (clean, time.monotonic())
        background.add_task(fetch, current["cfg"], clean, mode, trace=progress.note)
        return see_other("/", sel=new, notice="reading")

    @app.post("/retry")
    def start_batch(request: Request, background: BackgroundTasks, debug: str = Form("")):
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
            return answer(request, "/retry", "nothing-owed")
        size = min(live.batch, waiting)
        if not progress.start(size):
            # Two runs would reach for the same links and pay twice for each.
            return answer(request, "/retry", "batch-running")
        # After the response, not before it: a batch of fifty is an hour.
        background.add_task(run_batch, live, progress, live.batch)
        if wants_json(request):
            return answer(request, "/retry", "analysing-one" if size == 1 else "analysing",
                          n=size)
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
