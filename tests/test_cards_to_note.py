"""A catalog's answer, as one of our notes.

Pure: no disk, no network, no poster. What comes out is a Note like every
other note in the vault, which is the whole reason the cards get search,
filters, the timeline, the trash and Obsidian for free.
"""

import pytest

from oknowledge.cards import note_from_card
from oknowledge.catalog import Card
from oknowledge.config import Config
from oknowledge.urls import link_id
from oknowledge.vault import ensure_inside_root, note_path


def a_card(**over) -> Card:
    fields = dict(
        url="https://imdb.com/title/tt0088247", source="imdb.com",
        title="The Terminator", year="1984", people="James Cameron",
        released="1984-10-26", genres=["Action", "Adventure", "Sci-Fi"],
        length="108 min", rating="8.1",
        synopsis="A cyborg assassin from the future.",
        poster="https://images.metahub.space/poster/small/tt0088247/img",
    )
    fields.update(over)
    return Card(**fields)


@pytest.fixture
def cfg(tmp_path):
    return Config(vault=tmp_path)


@pytest.fixture
def terminator_card():
    return a_card()


@pytest.fixture
def any_card():
    return a_card()


@pytest.fixture
def bare_card():
    return Card(url="https://imdb.com/title/tt0000001", source="imdb.com",
                title="Sin nada")


def test_terminator_becomes_a_note(terminator_card):
    note = note_from_card(terminator_card, "movie", "es", saved="2026-10-11")
    assert note.url == "https://imdb.com/title/tt0088247"
    assert note.id == link_id("https://imdb.com/title/tt0088247")
    assert note.title == "The Terminator"
    assert note.type == "movie"
    assert note.source == "imdb.com"
    assert note.category == "Películas"
    assert note.tags == ["accion", "aventura", "ciencia-ficcion"]
    assert note.author == "James Cameron"
    assert note.published == "1984-10-26"
    assert note.length == "108 min"
    assert note.rating == "8.1"
    assert note.saved == "2026-10-11"
    assert note.summary == "A cyborg assassin from the future."
    assert note.status == "ok"        # una ficha del catálogo está completa
    assert note.engine == ""          # y nadie la reescribió todavía
    assert note.content == "summary"
    assert note.score == 0 and note.state == ""


@pytest.mark.parametrize("kind, category", [
    ("movie", "Películas"), ("series", "Series"),
    ("anime", "Anime"), ("book", "Libros"),
])
def test_the_category_is_the_kind(kind, category, any_card):
    assert note_from_card(any_card, kind, "es", "2026-10-11").category == category


def test_in_english_the_categories_are_english(any_card):
    assert note_from_card(any_card, "movie", "en", "2026-10-11").category == "Movies"


def test_in_english_the_genres_are_english_too(any_card):
    assert note_from_card(any_card, "movie", "en", "2026-10-11").tags == [
        "action", "adventure", "sci-fi"]


def test_a_title_that_would_escape_the_folder_does_not(cfg):
    """El título viene de un catálogo público: es texto de internet."""
    card_ = a_card(title="../../etc/passwd")
    note = note_from_card(card_, "movie", "es", "2026-10-11")
    path = note_path(cfg, note, shelf=cfg.ocio)
    assert path.parent == cfg.ocio.dir
    ensure_inside_root(cfg, path)          # no levanta


@pytest.mark.parametrize("title", ["Fate/Zero", "a\\b", "Misión 🚀", "....", "C:nombre"])
def test_no_title_from_the_internet_leaves_the_shelf(cfg, title):
    note = note_from_card(a_card(title=title), "movie", "es", "2026-10-11")
    path = note_path(cfg, note, shelf=cfg.ocio)
    assert path.parent == cfg.ocio.dir
    ensure_inside_root(cfg, path)


def test_a_card_with_nothing_but_a_title_is_still_a_note(bare_card):
    note = note_from_card(bare_card, "movie", "es", "2026-10-11")
    assert note.summary == ""
    assert (note.length, note.rating, note.author, note.cover) == ("", "", None, None)
    assert note.tags == []
    assert note.published is None
