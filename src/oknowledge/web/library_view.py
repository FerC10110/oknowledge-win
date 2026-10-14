"""The library as one URL describes it, and the small formats the redesign
draws it with. Pure: no request, no disk -- what the routes and templates
in app.py need, testable on its own."""

from __future__ import annotations

import dataclasses
import re
import zlib
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlencode

from ..marks import rank_marks
from .index import terms

CHUNK = 60
"""Items in the first answer and in each one after it."""

MOST = 100 * CHUNK
"""A URL can ask for this many at most: the page has to end somewhere."""

FAVORITE = "⭐"
PINNED = "📌"

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

HUES = {"Productividad": 80, "Programación": 160, "Redes": 265, "Salud": 25}
"""The handoff's own; any other category gets one from its name."""

NO_CATEGORY = ("#6d6f78", "#24252b")
LAYOUTS = ("tarjetas", "lista")
WORDS_A_MINUTE = 200


def hue(name: str) -> int | None:
    if not name:
        return None
    if name in HUES:
        return HUES[name]
    return zlib.crc32(name.casefold().encode("utf-8")) % 360


def dot(name: str) -> str:
    h = hue(name)
    return NO_CATEGORY[0] if h is None else f"oklch(0.74 0.09 {h})"


def tint(name: str) -> str:
    h = hue(name)
    return NO_CATEGORY[1] if h is None else f"oklch(0.30 0.045 {h})"


def short_date(saved: str, t) -> str:
    """"4 Oct": what a card has room for. Anything else is shown as it is."""
    match = re.fullmatch(r"\d{4}-(\d{2})-(\d{2})", saved or "")
    if not match or not 1 <= int(match.group(1)) <= 12:
        return saved
    return f"{int(match.group(2))} {t(MONTHS[int(match.group(1)) - 1])}"


def reading_minutes(text: str) -> int:
    return max(1, round(len(text.split()) / WORDS_A_MINUTE))


def paragraphs(text: str) -> list[str]:
    return [" ".join(p.split()) for p in re.split(r"\n\s*\n", text or "") if p.strip()]


def is_url(text: str) -> bool:
    """What the unified field saves instead of searching."""
    start = (text or "").strip().lower()
    return start.startswith(("http://", "https://", "www."))


def _count(raw: str) -> int:
    try:
        asked = int(raw)
    except (TypeError, ValueError):
        return CHUNK
    if asked <= CHUNK:
        return CHUNK
    return min(MOST, -(-asked // CHUNK) * CHUNK)


@dataclass(frozen=True)
class View:
    cat: str = ""
    tag: str = ""
    mark: str = ""
    col: str = ""
    q: str = ""
    sel: str = ""
    vista: str = "tarjetas"
    hasta: int = CHUNK

    @classmethod
    def from_query(cls, params: Mapping[str, str]) -> View:
        def get(*names: str) -> str:
            return next((params[n] for n in names if params.get(n)), "")
        vista = get("vista")
        return cls(cat=get("cat", "category"), tag=get("tag"), mark=get("mark"),
                   col=get("col", "collection"), q=" ".join(get("q").split()),
                   sel=get("sel"), vista=vista if vista in LAYOUTS else "tarjetas",
                   hasta=_count(get("hasta")))

    @property
    def searching(self) -> str:
        """The words to search for, or "" for none: a link is saved, not
        searched, and "!!!" has nothing to look for."""
        words = any(c.isalnum() for word in terms(self.q) for c in word)
        return self.q if words and not is_url(self.q) else ""

    @property
    def filtered(self) -> bool:
        return bool(self.searching or self.cat or self.tag or self.mark or self.col)

    def url(self, path: str = "/", **changes) -> str:
        own = {k: v for k, v in changes.items() if k in _FIELDS}
        extra = {k: v for k, v in changes.items() if k not in _FIELDS}
        view = dataclasses.replace(self, **own)
        if view.searching:
            pairs = [("q", view.q)]
        else:
            pairs = [("cat", view.cat), ("tag", view.tag), ("mark", view.mark),
                     ("col", view.col)]
        pairs += [("sel", view.sel),
                  ("vista", view.vista if view.vista != "tarjetas" else ""),
                  ("hasta", str(view.hasta) if view.hasta != CHUNK else "")]
        pairs += [(k, str(v)) for k, v in extra.items()]
        query = urlencode([(k, v) for k, v in pairs if v])
        return path + ("?" + query if query else "")

    def label(self, t) -> str:
        if self.searching:
            return t("Results")
        if self.mark == FAVORITE:
            return t("Favorites")
        if self.mark == PINNED:
            return t("Pinned")
        if self.mark:
            return self.mark
        if self.col:
            return self.col
        if self.tag:
            return "#" + self.tag
        return self.cat or t("Library")


_FIELDS = {f.name for f in dataclasses.fields(View)}


def choose(library, view: View) -> list:
    """The notes this view shows, newest first (or best first, searching)."""
    if view.searching:
        hits, _ = library.search(view.searching, page=1,
                                 per_page=max(1, len(library.notes)))
        return [hit.note for hit in hits]
    found = library.filter(category=view.cat or None, tag=view.tag or None,
                           collection=view.col or None)
    if view.mark:
        found = [n for n in found if n.mark == view.mark]
    return found


def side_groups(notes, categories: Mapping[str, int], collections: Mapping[str, int],
                marks) -> dict:
    """What the sidebar lists under the sections, with its counters."""
    notes = list(notes)
    used = [(m, n) for m, n in rank_marks(notes, marks) if m != FAVORITE]
    pinned = dict(used).get(PINNED, 0)
    return {"total": len(notes), "categories": dict(categories),
            "favorites": sum(1 for n in notes if n.mark == FAVORITE),
            "marks": [(PINNED, pinned), *[(m, n) for m, n in used if m != PINNED]],
            "collections": dict(collections)}
