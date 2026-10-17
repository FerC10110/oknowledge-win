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

from .. import cards
from ..marks import rank_marks
from .index import UNDATED, tally, terms

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


def saves(text: str) -> bool:
    """What the unified field sends to /add: a link, or a card asked for
    by its prefix ("película:Terminator", spec §6)."""
    return is_url(text) or cards.wanted(text) is not None


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
    when: str = ""
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
                   when=get("when"), sel=get("sel"), vista=vista if vista in LAYOUTS else "tarjetas",
                   hasta=_count(get("hasta")))

    @property
    def searching(self) -> str:
        """The words to search for, or "" for none: a link (or a card asked
        for by its prefix) is saved, not searched, and "!!!" has nothing to
        look for."""
        words = any(c.isalnum() for word in terms(self.q) for c in word)
        return self.q if words and not saves(self.q) else ""

    @property
    def by_what(self) -> bool:
        """Whether anything of the "what" axis is on: a search, a category, a
        tag, a mark or a collection. The period is the other axis, and "All"
        on this one stays lit while a year is open."""
        return bool(self.searching or self.cat or self.tag or self.mark or self.col)

    @property
    def filtered(self) -> bool:
        """Whether this view shows less than the whole library."""
        return bool(self.by_what or self.when)

    def url(self, path: str = "/", **changes) -> str:
        own = {k: v for k, v in changes.items() if k in _FIELDS}
        extra = {k: v for k, v in changes.items() if k not in _FIELDS}
        view = dataclasses.replace(self, **own)
        if view.searching:
            pairs = [("q", view.q)]
        else:
            pairs = [("cat", view.cat), ("tag", view.tag), ("mark", view.mark),
                     ("col", view.col),
                     # Time is the other axis: it crosses the "what" filters
                     # instead of competing with them, so a category keeps
                     # the period that was open and a period keeps the
                     # category. A search drops it: that list is ordered by
                     # how well it matches, not by time.
                     ("when", view.when)]
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
        if self.cat:
            return self.cat
        return self.period(t) or t("Library")

    def period(self, t) -> str:
        """The open period, as a person reads it: "2021", "nov 2021", or the
        words for a note nobody can date. "" when no period is open."""
        if not self.when:
            return ""
        if self.when == UNDATED:
            return t("Undated")
        if len(self.when) == 7:
            return f"{t(MONTHS[int(self.when[5:7]) - 1])} {self.when[:4]}"
        return self.when


_FIELDS = {f.name for f in dataclasses.fields(View)}


def choose(library, view: View) -> list:
    """The notes this view shows, newest first (or best first, searching)."""
    if view.searching:
        hits, _ = library.search(view.searching, page=1,
                                 per_page=max(1, len(library.notes)), snippets=False)
        return [hit.note for hit in hits]
    found = library.filter(category=view.cat or None, tag=view.tag or None,
                           collection=view.col or None, when=view.when or None)
    if view.mark:
        found = [n for n in found if n.mark == view.mark]
    return found


def date_groups(library, view: View) -> dict:
    """The sidebar's DATES group: every year the library holds and the months
    of the year that is open, with what they hold of this view.

    The list of years is the library's own, so the shape of time does not
    change from page to page; the numbers beside them are counted over the
    notes the other filters left, before the period itself is applied, so a
    collection says which years that project lives in and the year you
    opened is not the only one with a number.
    """
    if view.searching:
        # A search is ordered by how well it matches: dates beside it would
        # claim an order the list does not have.
        return {"when_total": 0, "years": [], "months": []}
    pool = choose(library, dataclasses.replace(view, when=""))
    counted = tally(pool)
    year = view.when[:4] if view.when and view.when != UNDATED else ""
    months = [(name, MONTHS[int(name[5:7]) - 1], counted.get(name, 0))
              for name in library.months() if name[:4] == year] if year else []
    return {"when_total": len(pool), "months": months,
            "years": [(name, counted.get(name, 0)) for name in library.years()]}


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
