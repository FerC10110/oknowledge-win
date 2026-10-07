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
from typing import NamedTuple
from urllib.parse import quote, urlencode

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import (
    FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse, Response,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..config import CONFIG_PATH, CONTENT_MODES, ENGINE_NAMES, MENTION_MODES, Config
from ..config import save as save_config
from ..i18n import LANGUAGES, set_ui_language, translator, ui_language
from ..pipeline import add as add_link
from ..pipeline import icon_path, import_links, is_domain
from ..queue import Locked, Queue
from ..urls import is_search_url, link_id, normalize
from ..vault import (
    BadCategory, IndexesStale, ProtectedNote, clean_category, delete_note,
    rename_category, update_note,
)
from ..whatsapp import BadExport, parse as parse_export
from .import_file import BadUpload, drop, stage, staged, text_of
from .index import PER_PAGE, Library, read_full, terms

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
    "language-not-saved": "The settings were saved, but the interface language is "
                          "shared with my other plugins and that file could not be "
                          "written.",
}

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


def see_other(path: str, **params) -> RedirectResponse:
    """The answer to every write: 303 to a page that reads the result back."""
    query = urlencode({k: v for k, v in params.items() if v not in (None, "")})
    return RedirectResponse(path + ("?" + query if query else ""), status_code=303)


def item_url(link_id: str) -> str:
    return "/item/" + quote(link_id, safe="")


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


def reanalyze(cfg: Config, url: str, engine: str | None) -> None:
    """Re-run the analysis outside the request, and never raise into the server.

    The chain can take minutes per engine, which is far too long to hold a
    browser. If the process dies mid-run (the idle timer, a laptop closing),
    the lock goes with it and the queue entry stays `pending` for the next
    `retry` to pick up: nothing is lost by answering early.
    """
    try:
        add_link(cfg, url, engine=engine, reprocess=True)
    except Exception:                 # a background task has nowhere to raise to
        log.exception("re-analysing %s failed", url)


def create_app(cfg: Config) -> FastAPI:
    app = FastAPI(title="oknowledge", docs_url=None, redoc_url=None)
    app.add_middleware(SameOriginOnly)
    library = Library(cfg)
    # The settings page can change the engine chain while the server runs. The
    # vault paths it cannot change, so the library stays valid either way.
    current = {"cfg": cfg}
    templates = Jinja2Templates(directory=str(WEB.joinpath("templates")))
    templates.env.filters["plain"] = plain
    templates.env.filters["slug"] = lambda value: quote(str(value), safe="")
    templates.env.tests["web_url"] = is_web_url
    templates.env.tests["search_link"] = is_search_url
    app.mount("/static", StaticFiles(directory=str(WEB.joinpath("static"))), name="static")

    def page(request: Request, name: str, status_code: int = 200, **context) -> HTMLResponse:
        language = ui_language()
        t = translator(language)
        base = {"t": t, "lang": language, "query": "",
                "unreadable": library.unreadable, "links_dir": cfg.links_dir,
                "heading": None, "prev_url": None, "next_url": None,
                "page": 1, "pages": 1, "notice": notice_for(request, t)}
        if library.error is not None:
            return templates.TemplateResponse(
                request=request, name="error.html", status_code=503,
                context={**base, "error": library.error, "categories": {}, "tags": {}})
        return templates.TemplateResponse(
            request=request, name=name, status_code=status_code,
            context={**base, "categories": library.categories(), "tags": library.tags(),
                     **context},
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
    def home(request: Request, category: str | None = None, tag: str | None = None):
        library.refresh()
        notes = library.filter(category=category, tag=tag)
        pages = -(-len(notes) // PER_PAGE)
        number = page_number(request.query_params.get("page", "1"), pages)
        params = {k: v for k, v in (("category", category), ("tag", tag)) if v}
        shown = notes[(number - 1) * PER_PAGE:number * PER_PAGE]
        return page(request, "library.html", notes=shown, category=category, tag=tag,
                    filtered=bool(category or tag), **pager("/", params, number, pages))

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

    @app.get("/item/{link_id}", response_class=HTMLResponse)
    def item(request: Request, link_id: str):
        library.refresh()
        if library.error is not None:
            return page(request, "item.html")
        entry = library.entry(link_id)
        if entry is None:
            raise HTTPException(status_code=404, detail="no such link")
        # The index holds list views without bodies; this note is read fresh.
        return page(request, "item.html", note=read_full(entry))

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
        library.refresh()
        note = library.by_id(link_id)
        if note is None or not note.cover:
            raise HTTPException(status_code=404, detail="no cover")
        # note.cover comes from frontmatter the user can edit: untrusted input.
        try:
            path = (cfg.links_dir / note.cover).resolve()
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

    def edit(link_id: str, change, done: str, stale: str) -> Edited:
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
        library.refresh()
        if library.by_id(link_id) is None:
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
            library.refresh()
            return Edited(stale, True)
        except (OSError, ProtectedNote) as error:
            # A read-only vault, a trash/ that is a file, a full disk. Every
            # vault write is atomic and the rebuild has its own answer above,
            # so reaching here really does mean nothing was written.
            log.warning("the vault could not be written: %s", error)
            return Edited("write-failed", False)
        library.refresh()
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
    def reprocess(background: BackgroundTasks, link_id: str, engine: str = Form("")):
        library.refresh()                 # a note deleted from Obsidian since the
        note = library.by_id(link_id)     # page was drawn must not be rewritten

        if note is None:
            raise HTTPException(status_code=404, detail="no such link")
        name = engine.strip() or None
        if name is not None and name not in ENGINE_NAMES:
            raise HTTPException(status_code=400, detail="unknown engine")
        # After the response, not before it: see reanalyze().
        background.add_task(reanalyze, current["cfg"], note.url, name)
        return see_other(item_url(link_id), notice="queued")

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

    @app.get("/settings", response_class=HTMLResponse)
    def settings_page(request: Request):
        saved = current["cfg"]
        order = [name for name in saved.chain if name in WEB_ENGINES]
        order += [name for name in WEB_ENGINES if name not in order]
        return page(request, "settings.html", cfg=saved, ui=ui_language(),
                    engines=order, config_path=config_file())

    @app.post("/settings")
    def save_settings(chain: list[str] = Form([]), language: str = Form(""),
                      default_content: str = Form(""), mentions: str = Form(""),
                      interface: str = Form("", alias="ui_language"),
                      opencode_model: str = Form(""), ollama_model: str = Form(""),
                      api_model: str = Form("")):
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
        try:
            if interface in LANGUAGES:
                set_ui_language(interface)
        except OSError as error:
            # The config itself did land. Saying it did not would be a lie
            # about the half that worked.
            log.warning("the shared language file could not be written: %s", error)
            return see_other("/settings", notice="language-not-saved")
        return see_other("/settings", notice="saved")

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
            t = translator(ui_language())
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
    return app
