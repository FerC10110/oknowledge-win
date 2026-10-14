"""Ocio and the ideas as one URL describes them, and the words and colours
they are drawn with (docs/2026-10-14-rediseno-ocio-ideas-design.md). Pure:
no request, no disk -- what the routes and templates in app.py need,
testable on its own, like library_view."""

from __future__ import annotations

from urllib.parse import quote, urlencode

from ..idea_actions import SCOPES
from ..vault import IDEA_STATES

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
