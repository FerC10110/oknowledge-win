"""Ocio and the ideas as one URL describes them, and the words and colours
they are drawn with (docs/2026-10-14-rediseno-ocio-ideas-design.md). Pure:
no request, no disk -- what the routes and templates in app.py need,
testable on its own, like library_view."""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import quote, urlencode

from ..idea_actions import SCOPES
from ..vault import IDEA_STATES
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
    return [{"title": "STATE", "rows": rows}]
