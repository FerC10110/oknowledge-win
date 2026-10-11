"""The fields a card has and a link does not, and the note you write yourself.

Four of them come from a catalog -- how long it is, what it scored there --
and two are yours: a state and a score out of five. `## Mi nota` is yours as
well, and like the mentions a hand typed, it comes back word for word after
the model has rewritten everything around it.

The 1184 notes already in the vault must not grow a single line from any of
this, which is what the empty defaults are for.
"""

import pytest

from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.vault import note_path, read_note, render, write_note


@pytest.fixture
def cfg(tmp_path):
    return Config(vault=tmp_path)


def card(**over) -> Note:
    fields = dict(
        id="aaaaaaaaaaaa", url="https://imdb.com/title/tt0088247",
        title="The Terminator", category="Películas", tags=["ciencia-ficcion"],
        type="movie", source="imdb.com", saved="2026-10-11",
        summary="Un cyborg viaja al pasado.",
    )
    fields.update(over)
    return Note(**fields)


def a_link_note() -> Note:
    return Note(
        id="bbbbbbbbbbbb", url="https://example.com/page", title="Una página",
        category="Redes", tags=["python"], type="article", source="example.com",
        saved="2026-10-10", summary="Algo sobre redes.",
    )


def test_the_four_fields_survive_the_round_trip(cfg):
    note = card(length="108 min", rating="8.1", score=4, state="done")
    path = write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ocio))
    back = read_note(path)
    assert (back.length, back.rating, back.score, back.state) == (
        "108 min", "8.1", 4, "done")


def test_a_plain_link_does_not_grow_a_single_line(cfg):
    """Las 1184 notas de hoy no cambian de formato."""
    text = render(a_link_note(), "es")
    for field in ("length:", "rating:", "score:", "state:", "Mi nota"):
        assert field not in text


def test_your_own_note_comes_back_word_for_word(cfg):
    note = card(my_note="La vi en el cine.\n\n- La segunda es mejor.")
    path = write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ocio))
    assert read_note(path).my_note == "La vi en el cine.\n\n- La segunda es mejor."


def test_a_rewrite_replaces_the_summary_and_keeps_what_is_yours(cfg):
    """La promesa del diseño, probada donde se rompe: el modelo reescribe."""
    note = card(summary="Catalog synopsis", my_note="Mía", score=5, state="doing")
    path = write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ocio))
    fresh = read_note(path)
    fresh.summary, fresh.points, fresh.engine = "Reescrita", ["uno"], "opencode"
    write_note(cfg, fresh, "es", path=path)
    back = read_note(path)
    assert back.summary == "Reescrita"
    assert (back.my_note, back.score, back.state) == ("Mía", 5, "doing")


def test_a_score_that_is_not_a_number_is_no_score(cfg):
    """El frontmatter se edita a mano en Obsidian."""
    note = card(score=4)
    path = write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ocio))
    path.write_text(path.read_text(encoding="utf-8").replace("score: 4",
                                                             "score: muchísimo"),
                    encoding="utf-8")
    assert read_note(path).score == 0
