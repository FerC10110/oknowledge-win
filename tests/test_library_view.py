"""The library as one URL describes it: pure functions, no server."""

import pytest

from oknowledge.model import Note
from oknowledge.web.library_view import (
    CHUNK, View, choose, dot, hue, is_url, paragraphs, reading_minutes,
    short_date, side_groups, tint,
)


def t(text, *args):
    for i, arg in enumerate(args, 1):
        text = text.replace(f"%{i}", str(arg))
    return text


def note(id, category="Redes", tags=(), mark="", collections=(), saved="2026-10-04",
         title=None, summary="s"):
    return Note(id=id, url=f"https://e.com/{id}", title=title or id, category=category,
                tags=list(tags), type="article", source="e.com", saved=saved,
                summary=summary, mark=mark, collections=list(collections))


# --- colours ---------------------------------------------------------------

def test_the_handoff_categories_keep_their_hue():
    assert [hue(n) for n in ("Productividad", "Programación", "Redes", "Salud")] == [80, 160, 265, 25]


def test_any_other_category_gets_a_hue_that_does_not_change():
    assert hue("Cocina") == hue("Cocina")
    assert 0 <= hue("Cocina") < 360


def test_the_dot_and_the_tint_are_the_handoff_formulas():
    assert dot("Redes") == "oklch(0.74 0.09 265)"
    assert tint("Redes") == "oklch(0.30 0.045 265)"


def test_no_category_is_grey():
    assert hue("") is None
    assert dot("") == "#6d6f78"
    assert tint("") == "#24252b"


# --- small formats ---------------------------------------------------------

def test_a_short_date_is_day_and_month():
    assert short_date("2026-10-04", t) == "4 Oct"


@pytest.mark.parametrize("raw", ["", "2026", "someday", "2026-13-01"])
def test_a_date_that_is_not_one_is_shown_as_it_is(raw):
    assert short_date(raw, t) == raw


def test_reading_minutes_never_says_zero():
    assert reading_minutes("") == 1
    assert reading_minutes("palabra " * 450) == 2


def test_paragraphs_split_on_blank_lines():
    assert paragraphs("Uno.\nsigue\n\n  \nDos.") == ["Uno. sigue", "Dos."]


@pytest.mark.parametrize("text,expected", [
    ("https://x.com", True), ("http://x", True), ("www.x.com", True),
    ("  HTTPS://X.COM", True), ("docker", False), ("", False), ("http", False),
])
def test_what_counts_as_a_link_to_save(text, expected):
    assert is_url(text) is expected


# --- the view in the URL ---------------------------------------------------

def test_a_view_reads_its_parameters():
    view = View.from_query({"cat": "Redes", "tag": "vpn", "mark": "⭐", "col": "Casa",
                            "sel": "a1", "vista": "lista"})
    assert (view.cat, view.tag, view.mark, view.col, view.sel, view.vista) == (
        "Redes", "vpn", "⭐", "Casa", "a1", "lista")


def test_the_old_parameter_names_still_work():
    view = View.from_query({"category": "Redes", "collection": "Casa"})
    assert (view.cat, view.col) == ("Redes", "Casa")


def test_an_unknown_layout_is_cards():
    assert View.from_query({"vista": "mosaico"}).vista == "tarjetas"


@pytest.mark.parametrize("raw,expected", [("", CHUNK), ("x", CHUNK), ("-5", CHUNK),
                                          ("120", 120), ("130", 180), ("999999", 6000)])
def test_how_many_to_show_is_whole_chunks_within_limits(raw, expected):
    assert View.from_query({"hasta": raw}).hasta == expected


def test_the_query_is_squeezed():
    assert View.from_query({"q": "  wire   guard "}).q == "wire guard"


@pytest.mark.parametrize("q", ["", "   ", "!!!", "#"])
def test_a_query_with_no_words_is_no_search(q):
    view = View.from_query({"q": q})
    assert view.searching == ""
    assert not view.filtered


def test_a_link_in_the_field_is_not_a_search():
    assert View.from_query({"q": "https://x.com"}).searching == ""


def test_the_url_keeps_the_view_and_applies_changes():
    view = View.from_query({"cat": "Redes", "vista": "lista"})
    assert view.url(sel="a1") == "/?cat=Redes&sel=a1&vista=lista"
    assert view.url("/lista", desde=60) == "/lista?cat=Redes&vista=lista&desde=60"


def test_the_default_url_is_bare():
    assert View().url() == "/"


def test_a_search_drops_the_other_filters_from_the_url():
    assert View(cat="Redes", q="vpn").url() == "/?q=vpn"


@pytest.mark.parametrize("view,label", [
    (View(), "Library"), (View(cat="Redes"), "Redes"), (View(tag="vpn"), "#vpn"),
    (View(mark="⭐"), "Favorites"), (View(mark="📌"), "Pinned"), (View(mark="🔥"), "🔥"),
    (View(col="Casa"), "Casa"), (View(q="vpn"), "Results"),
])
def test_the_header_names_the_view(view, label):
    assert view.label(t) == label


# --- which notes ---------------------------------------------------------

class FakeLibrary:
    def __init__(self, notes):
        self._notes = notes

    @property
    def notes(self):
        return list(self._notes)

    def filter(self, category=None, tag=None, collection=None):
        found = self.notes
        if category:
            found = [n for n in found if n.category == category]
        if tag:
            found = [n for n in found if tag in n.tags]
        if collection:
            found = [n for n in found if collection in n.collections]
        return found

    def search(self, q, page=1, per_page=20):
        class Hit:
            def __init__(self, note):
                self.note = note
        hits = [Hit(n) for n in self._notes if q.lower() in n.title.lower()]
        return hits[:per_page], len(hits)


LIB = FakeLibrary([note("a", tags=["vpn"], mark="⭐", collections=["Casa"]),
                   note("b", category="Salud", mark="📌"),
                   note("c", category="Salud", tags=["vpn"])])


@pytest.mark.parametrize("view,ids", [
    (View(), ["a", "b", "c"]), (View(cat="Salud"), ["b", "c"]),
    (View(tag="vpn"), ["a", "c"]), (View(mark="⭐"), ["a"]),
    (View(col="Casa"), ["a"]), (View(cat="Salud", tag="vpn"), ["c"]),
    (View(q="b"), ["b"]), (View(q="https://b.com"), ["a", "b", "c"]),
])
def test_choose_applies_the_view(view, ids):
    assert [n.id for n in choose(LIB, view)] == ids


def test_a_search_is_not_cut_at_a_page():
    many = FakeLibrary([note(f"n{i}", title=f"vpn {i}") for i in range(150)])
    assert len(choose(many, View(q="vpn"))) == 150


# --- the sidebar ---------------------------------------------------------

def test_the_sidebar_counts_favourites_and_lists_the_other_marks_pinned_first():
    notes = [note("a", mark="⭐"), note("b", mark="🔥"), note("c", mark="🔥"), note("d", mark="📌")]
    groups = side_groups(notes, {"Redes": 4}, {}, ("⭐", "🔥", "📌"))
    assert groups["total"] == 4
    assert groups["favorites"] == 1
    assert groups["marks"] == [("📌", 1), ("🔥", 2)]


def test_pinned_is_there_even_when_nothing_is_pinned():
    groups = side_groups([note("a")], {"Redes": 1}, {"Casa": 1}, ("⭐", "📌"))
    assert groups["marks"] == [("📌", 0)]
    assert groups["collections"] == {"Casa": 1}
    assert groups["categories"] == {"Redes": 1}
