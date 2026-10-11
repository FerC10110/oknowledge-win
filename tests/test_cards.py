"""What `película:Terminator` means.

The box in the header takes links. A line that starts with one of nine
words and a colon is not a link, it is a thing to look up, and this is where
that is decided -- before anything is fetched, saved or shown.
"""

import pytest

from oknowledge.cards import wanted


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
