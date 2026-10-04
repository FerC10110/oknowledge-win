"""The web. Reads the vault and shows it; this module writes nothing."""

from __future__ import annotations

import re
from importlib.resources import files
from urllib.parse import quote, urlencode

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..config import Config
from ..i18n import translator, ui_language
from .index import PER_PAGE, Library, read_full, terms

WEB = files("oknowledge").joinpath("web")

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


def create_app(cfg: Config) -> FastAPI:
    app = FastAPI(title="oknowledge", docs_url=None, redoc_url=None)
    library = Library(cfg)
    templates = Jinja2Templates(directory=str(WEB.joinpath("templates")))
    templates.env.filters["plain"] = plain
    templates.env.filters["slug"] = lambda value: quote(str(value), safe="")
    app.mount("/static", StaticFiles(directory=str(WEB.joinpath("static"))), name="static")

    def page(request: Request, name: str, status_code: int = 200, **context) -> HTMLResponse:
        language = ui_language()
        base = {"t": translator(language), "lang": language, "query": "",
                "unreadable": library.unreadable, "links_dir": cfg.links_dir,
                "heading": None, "prev_url": None, "next_url": None,
                "page": 1, "pages": 1}
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

    app.state.library = library
    app.state.cfg = cfg
    return app
