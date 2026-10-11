"""What a catalog calls a genre, as a tag of ours.

A fixed table and no model: twenty-five words that do not change, against a
model call per card that would cost seconds and could invent. What comes out
is still raw -- normalize_tags() is what turns "ciencia ficción" into
"ciencia-ficcion", the same as every other tag in the vault.
"""

from oknowledge.catalog.genres import as_tags


def test_the_genres_of_terminator_come_out_in_spanish():
    assert as_tags(["Action", "Adventure", "Sci-Fi"], "es") == [
        "acción", "aventura", "ciencia ficción"]


def test_in_english_they_are_just_lowercased():
    assert as_tags(["Action", "Sci-Fi"], "en") == ["action", "sci-fi"]


def test_a_genre_nobody_translated_survives_as_it_came():
    assert as_tags(["Reality-TV"], "es") == ["reality-tv"]


def test_nothing_is_repeated_and_nothing_is_empty():
    assert as_tags(["Action", "action", "  ", None, "Acción"], "es") == ["acción"]


def test_six_at_most():
    """Un libro de Open Library trae cuarenta temas."""
    assert len(as_tags([f"Genre{n}" for n in range(40)], "es")) == 6
