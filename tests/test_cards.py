"""What `película:Terminator` means.

The box in the header takes links. A line that starts with one of nine
words and a colon is not a link, it is a thing to look up, and this is where
that is decided -- before anything is fetched, saved or shown.
"""

import pytest

from oknowledge.cards import prefixed, wanted


@pytest.mark.parametrize("raw, kind", [
    ("película:Terminator", "movie"), ("pelicula:Terminator", "movie"),
    ("PELÍCULA:Terminator", "movie"), ("peli:Terminator", "movie"),
    ("movie:Terminator", "movie"), ("serie:Bebop", "series"),
    ("series:Bebop", "series"), ("anime:Bebop", "anime"),
    ("libro:Dune", "book"), ("book:Dune", "book"),
])
def test_the_nine_prefixes(raw, kind):
    assert wanted(raw).kind == kind


def test_spaces_around_the_colon_are_allowed():
    assert wanted("peli : Terminator").query == "Terminator"


def test_a_title_may_have_colons_in_it():
    """Se parte en el primero y el resto es el título, dos puntos incluidos."""
    assert wanted("anime:Fate/Zero: Unlimited Blade Works").query == (
        "Fate/Zero: Unlimited Blade Works")


@pytest.mark.parametrize("raw", [
    "https://example.com/x", "example.com/x", "nota:algo", "Terminator",
    "", "   ", ":", "película:", "película:   ",
])
def test_everything_else_is_not_a_card(raw):
    assert wanted(raw) is None


def test_a_year_at_the_end_is_a_year_and_not_part_of_the_title():
    found = wanted("película:Terminator 1984")
    assert (found.query, found.year) == ("Terminator", "1984")


def test_a_number_that_is_not_a_year_stays_in_the_title():
    assert wanted("película:Fahrenheit 451").year == ""
    assert wanted("película:Fahrenheit 451").query == "Fahrenheit 451"


def test_a_year_in_the_middle_is_part_of_the_title():
    assert wanted("película:1984 de Orwell").year == ""
    found = wanted("película:Blade Runner 2049 remasterizada")
    assert (found.year, found.query) == ("", "Blade Runner 2049 remasterizada")


def test_a_four_digit_number_that_is_no_year_is_part_of_the_title():
    """Sólo 18xx, 19xx y 20xx son años; lo demás es parte del nombre."""
    found = wanted("libro:Fundación 2500")
    assert (found.year, found.query) == ("", "Fundación 2500")


def test_an_imdb_id_is_a_reference():
    assert wanted("película:tt0088247").ref == "tt0088247"


def test_an_open_library_id_is_a_reference():
    assert wanted("libro:OL893414W").ref == "/works/OL893414W"


def test_a_title_that_is_not_an_id_has_no_reference():
    assert wanted("película:Terminator").ref == ""


def test_a_novel_of_a_title_is_cut_at_120():
    assert len(wanted("libro:" + "x" * 300).query) == 120


@pytest.mark.parametrize("raw", ["película:", "película:   ", "peli : ", "LIBRO:"])
def test_a_prefix_with_no_title_is_still_about_a_card(raw):
    """No es una búsqueda, pero tampoco es un link: la página lo dice
    distinto."""
    assert wanted(raw) is None
    assert prefixed(raw) is True


@pytest.mark.parametrize("raw", ["https://example.com/x", "nota:algo", "", ":"])
def test_a_line_that_is_not_about_a_card_says_so(raw):
    assert prefixed(raw) is False


from oknowledge.cards import from_link


def test_an_imdb_link_is_a_film_by_its_id():
    asked = from_link("https://www.imdb.com/title/tt0088247/?ref_=x")
    assert (asked.kind, asked.query) == ("movie", "tt0088247")


def test_an_imdb_link_takes_the_kind_it_was_pasted_under():
    assert from_link("https://m.imdb.com/title/tt0213338/", "anime").kind == "anime"
    assert from_link("https://imdb.com/title/tt0213338/", "book").kind == "movie"


def test_an_open_library_work_is_a_book():
    asked = from_link("https://openlibrary.org/works/OL893414W/Dune")
    assert (asked.kind, asked.query) == ("book", "OL893414W")


def test_any_other_link_or_text_is_not_a_catalog_link():
    for text in ("https://myanimelist.net/anime/1", "https://www.goodreads.com/book/show/1",
                 "https://imdb.com/name/nm0000116", "Terminator", ""):
        assert from_link(text) is None
