"""Ocio and the ideas as one URL describes them, and the words and colours
they are drawn with (docs/2026-10-14-rediseno-ocio-ideas-design.md). Pure:
no request, no disk -- what the routes and templates in app.py need,
testable on its own, like library_view."""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import quote, urlencode, urlsplit

from .. import cards
from ..idea_actions import SCOPES
from ..vault import IDEA_STATES
from ..vault import STATES as CARD_STATES
from .index import fold, terms
from .library_view import CHUNK, LAYOUTS, _count

IDEA_WORDS = {"pending": "seed", "doing": "under way", "done": "done", "dropped": "dropped"}
"""An idea's four states, in its own words: an idea is had, worked on, made,
or let go."""
IDEA_DOTS = {"pending": "#6d6f78", "doing": "#a9b4de", "done": "#8fc29a",
             "dropped": "#55575f"}
"""The handoff's three state colours (spec §1); a dropped idea is the
dimmest grey there is."""

TABS = (("resumen", "Summary", ""), ("existe", "Already out there?", "exists"),
        ("mejoras", "Improvements", "improve"), ("ampliacion", "Expansion", "expand"))
"""An idea's results: the key in the URL (`pestana=`), the label, and the
action that fills it -- "" for the summary, which naming the idea fills."""
TAB_OF = {action: key for key, _, action in TABS if action}
TAB_OF["complete"] = "resumen"

AI_BUTTONS = (("exists", "Already out there?"), ("improve", "Improve"), ("expand", "Expand"))
WORKING = {"exists": "Searching…", "improve": "Improvements…", "expand": "Expansion…",
           "complete": "Regenerating…"}
SECTION_NAMES = {"exists": "Already out there?", "improve": "Improvements",
                 "expand": "Expansion", "complete": "Summary"}
"""What "Listo: {sección}" names when each run ends (spec 2.2)."""

_DEFAULTS = {"pestana": "resumen", "alcance": "vinculados", "back": "/ideas"}


def tab_of(raw: str) -> str:
    return raw if raw in {key for key, _, _ in TABS} else "resumen"


def scope_of(raw: str) -> str:
    return raw if raw in SCOPES else "vinculados"


def excerpt(text: str, size: int = 60) -> str:
    """The start of an idea's text, for its title box while the model names it."""
    flat = " ".join((text or "").split())
    return flat if len(flat) <= size else flat[:size].rstrip() + "…"


def idea_url(idea_id: str, **params) -> str:
    """An idea's screen, with the parameters that are not their default."""
    pairs = [(k, str(v)) for k, v in params.items() if v and v != _DEFAULTS.get(k)]
    query = urlencode(pairs)
    return "/ideas/" + quote(idea_id, safe="") + ("?" + query if query else "")


@dataclass(frozen=True)
class IdeaView:
    """/ideas as its URL says it: `estado`, `q`, `vista`, `hasta` (spec §2)."""

    estado: str = ""
    q: str = ""
    vista: str = "tarjetas"
    hasta: int = CHUNK

    @classmethod
    def from_query(cls, params: Mapping[str, str]) -> IdeaView:
        estado, vista = params.get("estado", ""), params.get("vista", "")
        return cls(estado=estado if estado in IDEA_STATES else "",
                   q=" ".join(params.get("q", "").split()),
                   vista=vista if vista in LAYOUTS else "tarjetas",
                   hasta=_count(params.get("hasta", "")))

    def url(self, path: str = "/ideas", **changes) -> str:
        own = {k: v for k, v in changes.items() if k in _IDEA_FIELDS}
        extra = [(k, str(v)) for k, v in changes.items() if k not in _IDEA_FIELDS]
        view = dataclasses.replace(self, **own)
        pairs = [("estado", view.estado), ("q", view.q),
                 ("vista", view.vista if view.vista != "tarjetas" else ""),
                 ("hasta", str(view.hasta) if view.hasta != CHUNK else "")] + extra
        query = urlencode([(k, v) for k, v in pairs if v])
        return path + ("?" + query if query else "")

    def label(self, t) -> str:
        if self.q:
            return t("Results")
        return t(IDEA_WORDS[self.estado]) if self.estado else t("Ideas")

    def open(self, idea_id: str) -> str:
        """The idea's screen, with "← Ideas" coming back to this list."""
        return idea_url(idea_id, back=self.url())


_IDEA_FIELDS = {f.name for f in dataclasses.fields(IdeaView)}


def _words(note) -> str:
    return fold(" ".join([note.title, note.my_note, " ".join(note.tags)]))


def choose_ideas(notes, view: IdeaView) -> list:
    """Newest first; a state, or all of them but the dropped; every word of
    the search somewhere in the title, the text or the tags."""
    found = sorted(notes, key=lambda n: (n.saved, n.title), reverse=True)
    if view.estado:
        found = [n for n in found if n.state == view.estado]
    else:
        found = [n for n in found if n.state != "dropped"]
    words = terms(view.q)
    if words:
        found = [n for n in found if all(word in _words(n) for word in words)]
    return found


def idea_filters(notes, view: IdeaView) -> list[dict]:
    """The sidebar's ESTADO group for the ideas (spec §1). "All" counts what
    "All" shows: every idea but the dropped ones."""
    counts = {state: 0 for state in IDEA_STATES}
    for note in notes:
        if note.state in counts:
            counts[note.state] += 1
    rows = [{"href": view.url(estado="", q="", hasta=CHUNK), "label": "All", "dot": "#6d6f78",
             "count": sum(1 for n in notes if n.state != "dropped"),
             "on": not view.estado and not view.q}]
    rows += [{"href": view.url(estado=state, q="", hasta=CHUNK), "label": IDEA_WORDS[state],
              "dot": IDEA_DOTS[state], "count": counts[state], "on": view.estado == state}
             for state in IDEA_STATES]
    return [{"title": "STATE", "param": "estado", "rows": rows}]


KIND_HUES = {"movie": 300, "series": 200, "anime": 20, "book": 60}
"""Each kind's hue for the poster with no cover (Ocio.dc.html)."""
KIND_NAMES = {"movie": "Movies", "series": "Series", "anime": "Anime", "book": "Books"}
# One card's kind. "TV series" and not "Series": English says one series and
# two series alike, so that key would translate the singular as the plural.
KIND_ONE = {"movie": "Movie", "series": "TV series", "anime": "Anime", "book": "Book"}
_WATCH = {"pending": "To watch", "doing": "Watching", "done": "Watched"}
_READ = {"pending": "To read", "doing": "Reading", "done": "Read"}
CARD_WORDS = {"movie": _WATCH, "series": _WATCH, "anime": _WATCH, "book": _READ}
CARD_DOTS = {"pending": "#6d6f78", "doing": "#a9b4de", "done": "#8fc29a"}
CARD_CHIP = {"pending": "#c9cbd1", "doing": "#a9b4de", "done": "#8fc29a"}
"""The poster's state chip, in words coloured by state (Ocio.dc.html's
statusColor): to watch is the light grey, not the dot's dim one."""
SORTS = (("recientes", "Recent"), ("titulo", "Title"), ("anio", "Year"),
         ("estrellas", "Your stars"))
_SORT_KEYS = {key for key, _ in SORTS}
CATALOGS = {"imdb.com": "IMDb", "openlibrary.org": "Open Library"}


def words_for(kind: str) -> dict[str, str]:
    """A book is read; everything else is watched -- and so is "All"."""
    return CARD_WORDS.get(kind, _WATCH)


def poster_fill(kind: str) -> str:
    hue = KIND_HUES.get(kind)
    if hue is None:
        return "linear-gradient(160deg, #2a2c34, #17181d)"
    return f"linear-gradient(160deg, oklch(0.42 0.06 {hue}), oklch(0.18 0.03 {hue}))"


def kind_dot(kind: str) -> str:
    hue = KIND_HUES.get(kind)
    return "#6d6f78" if hue is None else f"oklch(0.74 0.09 {hue})"


def catalog_name(source: str) -> str:
    return CATALOGS.get(source, source)


def web_domain(url: str, fallback: str = "") -> str:
    """The site a link is on, as "Abrir en {dominio}" names it: its host
    without "www.", or `fallback` when the URL has none."""
    try:
        host = urlsplit(str(url or "")).hostname or ""
    except ValueError:
        host = ""
    return host.removeprefix("www.") or fallback


def year_of(note) -> int | None:
    """The year a card came out, or None for no date or one nobody can read."""
    found = re.match(r"(\d{4})", note.published or "")
    return int(found.group(1)) if found else None


@dataclass(frozen=True)
class CardView:
    """/ocio as its URL says it: `tipo`, `estado`, `q`, `sel`, `orden`,
    `hasta` (spec §3). Unknown values are All and Recent."""

    tipo: str = ""
    estado: str = ""
    q: str = ""
    sel: str = ""
    orden: str = "recientes"
    hasta: int = CHUNK

    @classmethod
    def from_query(cls, params: Mapping[str, str]) -> CardView:
        tipo, estado, orden = (params.get(k, "") for k in ("tipo", "estado", "orden"))
        return cls(tipo=tipo if tipo in cards.KINDS else "",
                   estado=estado if estado in CARD_STATES else "",
                   q=" ".join(params.get("q", "").split()), sel=params.get("sel", ""),
                   orden=orden if orden in _SORT_KEYS else "recientes",
                   hasta=_count(params.get("hasta", "")))

    def url(self, path: str = "/ocio", **changes) -> str:
        own = {k: v for k, v in changes.items() if k in _CARD_FIELDS}
        extra = [(k, str(v)) for k, v in changes.items() if k not in _CARD_FIELDS]
        view = dataclasses.replace(self, **own)
        pairs = [("tipo", view.tipo), ("estado", view.estado), ("q", view.q),
                 ("sel", view.sel), ("orden", view.orden if view.orden != "recientes" else ""),
                 ("hasta", str(view.hasta) if view.hasta != CHUNK else "")] + extra
        query = urlencode([(k, v) for k, v in pairs if v])
        return path + ("?" + query if query else "")

    def label(self, t) -> str:
        if self.q:
            return t("Results")
        state = t(words_for(self.tipo)[self.estado]) if self.estado else ""
        if self.tipo:
            name = t(KIND_NAMES[self.tipo])
            return f"{name} · {state}" if state else name
        return state or t("Leisure")


_CARD_FIELDS = {f.name for f in dataclasses.fields(CardView)}


def sort_cards(notes, orden: str) -> list:
    """Newest saved first, then the order asked for; Python's sort is stable,
    so the cards a key cannot tell apart stay newest first (spec §3)."""
    found = sorted(notes, key=lambda n: (n.saved, n.id), reverse=True)
    if orden == "titulo":
        return sorted(found, key=lambda n: fold(n.title))
    if orden == "anio":
        return sorted(found, key=lambda n: (year_of(n) is None, -(year_of(n) or 0)))
    if orden == "estrellas":
        return sorted(found, key=lambda n: -max(0, min(int(n.score or 0), 5)))
    return found


def choose_cards(notes, view: CardView) -> list:
    found = [n for n in notes if (not view.tipo or n.type == view.tipo)
             and (not view.estado or n.state == view.estado)]
    words = terms(view.q)
    if words:
        def text(n):
            return fold(" ".join([n.title, n.author or "", " ".join(n.tags)]))
        found = [n for n in found if all(word in text(n) for word in words)]
    return sort_cards(found, view.orden)


def card_filters(notes, view: CardView) -> list[dict]:
    """TIPO (a kind with no cards is not drawn) and ESTADO, in the words of
    the kind chosen, counted within it (spec §1)."""
    fresh = {"q": "", "sel": "", "hasta": CHUNK}
    kinds = [{"href": view.url(tipo="", **fresh), "label": "All", "dot": "#6d6f78",
              "count": len(notes), "on": not view.tipo}]
    for kind in cards.KINDS:
        count = sum(1 for n in notes if n.type == kind)
        if count:
            kinds.append({"href": view.url(tipo=kind, **fresh), "label": KIND_NAMES[kind],
                          "dot": kind_dot(kind), "count": count, "on": view.tipo == kind})
    within = [n for n in notes if not view.tipo or n.type == view.tipo]
    words = words_for(view.tipo)
    states = [{"href": view.url(estado="", **fresh), "label": "All", "dot": "#6d6f78",
               "count": len(within), "on": not view.estado}]
    states += [{"href": view.url(estado=state, **fresh), "label": words[state],
                "dot": CARD_DOTS[state], "count": sum(1 for n in within if n.state == state),
                "on": view.estado == state} for state in CARD_STATES]
    return [{"title": "TYPE", "param": "tipo", "rows": kinds},
            {"title": "STATE", "param": "estado", "rows": states}]
