"""The web. Reads the vault and shows it; this module writes nothing."""

from __future__ import annotations

from importlib.resources import files

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..config import Config
from ..i18n import translator, ui_language
from .index import Library

WEB = files("oknowledge").joinpath("web")


def create_app(cfg: Config) -> FastAPI:
    app = FastAPI(title="oknowledge", docs_url=None, redoc_url=None)
    library = Library(cfg)
    templates = Jinja2Templates(directory=str(WEB.joinpath("templates")))
    app.mount("/static", StaticFiles(directory=str(WEB.joinpath("static"))), name="static")

    def page(request: Request, name: str, **context) -> HTMLResponse:
        language = ui_language()
        base = {"t": translator(language), "lang": language, "query": "",
                "unreadable": library.unreadable, "links_dir": cfg.links_dir}
        if library.error is not None:
            return templates.TemplateResponse(
                request=request, name="error.html", status_code=503,
                context={**base, "error": library.error, "categories": {}, "tags": {}})
        return templates.TemplateResponse(
            request=request, name=name,
            context={**base, "categories": library.categories(), "tags": library.tags(),
                     **context},
        )

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request, category: str | None = None, tag: str | None = None):
        library.refresh()
        return page(request, "library.html",
                    notes=library.filter(category=category, tag=tag),
                    category=category, tag=tag)

    @app.get("/search", response_class=HTMLResponse)
    def search(request: Request, q: str = ""):
        library.refresh()
        return page(request, "library.html", notes=None, hits=library.search(q),
                    category=None, tag=None, query=q)

    @app.get("/item/{link_id}", response_class=HTMLResponse)
    def item(request: Request, link_id: str):
        library.refresh()
        if library.error is not None:
            return page(request, "item.html")
        note = library.by_id(link_id)
        if note is None:
            raise HTTPException(status_code=404, detail="no such link")
        return page(request, "item.html", note=note)

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
            usable = inside and path.is_file()
        except (OSError, ValueError):
            usable = False
        if not usable:
            raise HTTPException(status_code=404, detail="no cover")
        return FileResponse(path)

    app.state.library = library
    app.state.cfg = cfg
    return app
