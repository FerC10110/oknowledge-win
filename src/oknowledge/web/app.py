"""The web: it shows the vault, and it is the only reader that can change it.

Every route that writes goes through one of three narrow doors -- update_note,
delete_note, rename_category -- and every one of them is a POST behind the
origin check below. Nothing here unlinks a note: deleting moves the file to
trash/, which is what makes a mis-click in a browser recoverable.
"""

from __future__ import annotations

import dataclasses
import logging
import re
from importlib.resources import files
from urllib.parse import quote, urlencode

from fastapi import BackgroundTasks, FastAPI, Form, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import (
    FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..config import CONFIG_PATH, CONTENT_MODES, ENGINE_NAMES, Config
from ..config import save as save_config
from ..i18n import LANGUAGES, set_ui_language, translator, ui_language
from ..pipeline import add as add_link
from ..vault import BadCategory, delete_note, rename_category, update_note
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
    "bad-category": "That name cannot be used as a category: no slashes, no dots "
                    "at the start, no control characters.",
    "renamed": "%1 notes moved.",
    "renamed-partial": "%1 notes moved, %2 could not be written. "
                       "Check the folder and try again.",
}

# Writing is refused unless the browser says the request came from this app.
# The server listens on localhost, which stops nothing: any page the user
# visits can POST here, and a POST with no-cors needs no permission and shows
# no error. Sec-Fetch-Site is the modern answer; Origin covers the clients
# that do not send it. A write with neither is a shell, not a page.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
SAFE_SITES = frozenset({"same-origin", "none"})

# Cover images are served only as one of these: a hand-edited cover pointing at
# an .svg or .html inside attachments/ would otherwise be a same-origin document.
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
               ".gif": "image/gif", ".webp": "image/webp", ".avif": "image/avif"}


def plain(text: str) -> str:
    """The first line of a summary without markdown decoration, for a card."""
    line = next((ln for ln in text.splitlines() if ln.strip()), "")
    line = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", line)     # links and images
    line = re.sub(r"^\s*(#+|>|[-*+]|\d+\.)\s+", "", line)        # heading, quote, list
    line = re.sub(r"[*_`~]+", "", line)
    return line.strip()


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
        if exc.status_code == 404 and not path.startswith(("/cover/", "/static/")):
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

    # --- the routes that write ----------------------------------------------
    #
    # All of them: POST, behind SameOriginOnly, 303 to a page that reads the
    # result back from the vault, and never a write of their own -- the three
    # vault functions are the only things that touch a file.

    @app.post("/item/{link_id}/category")
    def move(link_id: str, category: str = Form("")):
        try:
            written = update_note(cfg, link_id, ui_language(), category=category)
        except BadCategory:
            return see_other(item_url(link_id), notice="bad-category")
        if written is None:
            raise HTTPException(status_code=404, detail="no such link")
        library.refresh()
        return see_other(item_url(link_id), notice="saved")

    @app.post("/item/{link_id}/tags")
    def retag(link_id: str, tags: str = Form("")):
        wanted = [word for word in tags.replace(",", " ").split() if word]
        if update_note(cfg, link_id, ui_language(), tags=wanted) is None:
            raise HTTPException(status_code=404, detail="no such link")
        library.refresh()
        return see_other(item_url(link_id), notice="saved")

    @app.post("/item/{link_id}/delete")
    def remove(link_id: str):
        # Moves the file to <vault>/<folder>/trash/. The notice says so,
        # because "deleted" would be a lie and a worrying one.
        if delete_note(cfg, link_id, ui_language()) is None:
            raise HTTPException(status_code=404, detail="no such link")
        library.refresh()
        return see_other("/", notice="trashed")

    @app.post("/item/{link_id}/reprocess")
    def reprocess(background: BackgroundTasks, link_id: str, engine: str = Form("")):
        note = library.by_id(link_id)
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
        try:
            result = rename_category(cfg, old, new, ui_language())
        except BadCategory:
            return see_other("/categories", notice="bad-category")
        library.refresh()
        return see_other("/categories",
                         notice="renamed-partial" if result.failed else "renamed",
                         n=result.moved, m=len(result.failed))

    @app.get("/settings", response_class=HTMLResponse)
    def settings_page(request: Request):
        saved = current["cfg"]
        order = [name for name in saved.chain if name in WEB_ENGINES]
        order += [name for name in WEB_ENGINES if name not in order]
        return page(request, "settings.html", cfg=saved, ui=ui_language(),
                    engines=order, config_path=CONFIG_PATH)

    @app.post("/settings")
    def save_settings(chain: list[str] = Form([]), language: str = Form(""),
                      default_content: str = Form(""),
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
            engines=engines,
        )
        save_config(updated, CONFIG_PATH)
        if interface in LANGUAGES:
            set_ui_language(interface)
        current["cfg"] = updated
        return see_other("/settings", notice="saved")

    app.state.library = library
    app.state.cfg = cfg               # the vault config: paths never change here
    app.state.settings = current      # the live one, which the settings page edits
    return app
