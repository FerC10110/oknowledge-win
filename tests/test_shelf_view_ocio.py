"""Ocio as one URL describes it (spec §3): pure, no app."""

import pytest

from oknowledge.model import Note
from oknowledge.web.library_view import CHUNK
from oknowledge.web.shelf_view import (CardView, card_filters, catalog_name, choose_cards,
                                       poster_fill, sort_cards, year_of)


def card(title, kind="movie", saved="2026-10-01", published=None, score=0, state="",
         tags=(), author=None):
    return Note(id=title.lower().replace(" ", "")[:12].ljust(12, "x"), url="https://imdb.com/x",
                title=title, category="Películas", tags=list(tags), type=kind,
                source="imdb.com", saved=saved, summary="s", published=published,
                score=score, state=state, author=author)


def titles(notes):
    return [n.title for n in notes]


def test_unknown_values_are_all_and_recent():
    view = CardView.from_query({"tipo": "podcast", "estado": "dropped", "orden": "x",
                                "hasta": "3"})
    assert (view.tipo, view.estado, view.orden, view.hasta) == ("", "", "recientes", CHUNK)


def test_the_url_leaves_out_the_defaults_and_keeps_the_rest():
    assert CardView().url() == "/ocio"
    view = CardView(tipo="book", estado="done", orden="anio")
    assert view.url(sel="abc") == "/ocio?tipo=book&estado=done&sel=abc&orden=anio"
    assert CardView(q="dune").url("/ocio/lista", desde=60) == "/ocio/lista?q=dune&desde=60"


def test_the_label():
    t = lambda text, *a: text
    assert CardView().label(t) == "Leisure"
    assert CardView(tipo="book").label(t) == "Books"
    assert CardView(tipo="book", estado="doing").label(t) == "Books · Reading"
    assert CardView(estado="done").label(t) == "Watched"
    assert CardView(q="x").label(t) == "Results"


def test_recent_is_newest_saved_first():
    notes = [card("A", saved="2026-10-01"), card("B", saved="2026-10-03"), card("C", saved="2026-10-02")]
    assert titles(sort_cards(notes, "recientes")) == ["B", "C", "A"]


def test_title_ignores_case_and_accents():
    notes = [card("Ébano"), card("alien"), card("Dune")]
    assert titles(sort_cards(notes, "titulo")) == ["alien", "Dune", "Ébano"]


def test_year_newest_first_and_missing_or_odd_years_last():
    """Review Focus 4: no year, or a published nobody can read, goes last,
    newest saved first among them; nothing raises."""
    notes = [card("Old", published="1984-10-26"), card("None", saved="2026-10-05"),
             card("New", published="2021"), card("Odd", published="s/f", saved="2026-10-09")]
    assert titles(sort_cards(notes, "anio")) == ["New", "Old", "Odd", "None"]
    assert year_of(card("x", published="s/f")) is None
    assert year_of(card("x", published="1999-01-01")) == 1999


def test_stars_most_first_and_none_last():
    """Review Focus 4: 0 stars last, newest first among them."""
    notes = [card("Two", score=2), card("Zero", saved="2026-10-02"), card("Five", score=5),
             card("Zero too", saved="2026-10-04")]
    assert titles(sort_cards(notes, "estrellas")) == ["Five", "Two", "Zero too", "Zero"]


def test_choose_filters_kind_state_and_words():
    notes = [card("Dune", kind="book", state="done", author="Frank Herbert"),
             card("Alien", state="done", tags=("terror",)), card("Bebop", kind="anime")]
    assert titles(choose_cards(notes, CardView(tipo="book"))) == ["Dune"]
    assert titles(choose_cards(notes, CardView(estado="done", orden="titulo"))) == ["Alien", "Dune"]
    assert titles(choose_cards(notes, CardView(q="herbert"))) == ["Dune"]
    assert titles(choose_cards(notes, CardView(q="#terror"))) == ["Alien"]


def test_the_type_group_hides_a_kind_with_no_cards():
    notes = [card("Dune", kind="book"), card("Alien")]
    kinds, states = card_filters(notes, CardView())
    assert kinds["title"] == "TYPE"
    assert [(r["label"], r["count"]) for r in kinds["rows"]] == [("All", 2), ("Movies", 1), ("Books", 1)]
    assert kinds["rows"][2]["href"] == "/ocio?tipo=book"


def test_the_state_group_speaks_the_kind_and_counts_within_it():
    notes = [card("Dune", kind="book", state="doing"), card("Alien", state="doing"),
             card("Solaris", kind="book")]
    _, states = card_filters(notes, CardView(tipo="book", estado="doing"))
    assert states["title"] == "STATE"
    assert [(r["label"], r["count"], r["on"]) for r in states["rows"]] == [
        ("All", 2, False), ("To read", 0, False), ("Reading", 1, True), ("Read", 0, False)]
    assert states["rows"][2]["dot"] == "#a9b4de"
    assert states["rows"][2]["href"] == "/ocio?tipo=book&estado=doing"


def test_a_filter_keeps_the_order_and_drops_the_search_and_the_pick():
    kinds, _ = card_filters([card("Alien")], CardView(q="x", sel="abc", orden="anio"))
    assert kinds["rows"][1]["href"] == "/ocio?tipo=movie&orden=anio"


def test_a_poster_without_a_cover_is_its_kind_s_gradient():
    """Review Focus 5."""
    assert poster_fill("movie") == ("linear-gradient(160deg, oklch(0.42 0.06 300), "
                                    "oklch(0.18 0.03 300))")
    assert poster_fill("book").endswith("oklch(0.18 0.03 60))")
    assert poster_fill("podcast") == "linear-gradient(160deg, #2a2c34, #17181d)"


def test_the_catalog_is_named_like_people_say_it():
    assert catalog_name("imdb.com") == "IMDb"
    assert catalog_name("openlibrary.org") == "Open Library"
    assert catalog_name("example.com") == "example.com"
