"""The rewrite in Spanish, over a card that already exists.

A card is saved complete, in the catalog's English, and is useful from that
second on. The model comes afterwards and improves exactly two things: the
summary and the points. It never touches the category (the kind decides
it), the tags (the genres are the tags), or anything of yours.

An engine that fails leaves the card as it was. There is nothing to retry
and nothing owed: the card is not a half-written note.
"""

import pytest

from oknowledge.ai import AllEnginesFailed
from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.pipeline import describe
from oknowledge.vault import find_note, note_path, rebuild_indexes, write_note

CARD = "aaaaaaaaaaaa"


@pytest.fixture
def cfg(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    config = Config(vault=vault, chain=("fake",))
    rebuild_indexes(config, "es")
    note = Note(id=CARD, url="https://imdb.com/title/tt0088247",
                title="The Terminator", category="Películas",
                tags=["accion", "ciencia-ficcion"], type="movie",
                source="imdb.com", saved="2026-10-11",
                summary="Catalog synopsis: a cyborg assassin from the future.",
                author="James Cameron", published="1984-10-26",
                length="108 min", rating="8.1", score=4, state="done",
                my_note="La vi en el cine.")
    write_note(config, note, "es", path=note_path(config, note, shelf=config.ocio))
    return config


def note_now(cfg, link_id=CARD):
    return find_note(cfg, link_id, shelf=cfg.ocio)[1]


@pytest.fixture
def fake_engine(monkeypatch):
    """The chain, answering one thing and remembering what it was asked."""

    class Faker:
        name = "fake"
        model = "fake-1"
        last_prompt = ""

        def __init__(self):
            self.reply = '{"summary": "Algo.", "points": []}'
            self.error = None

        def answers(self, reply):
            self.reply = reply

        def raises(self, error):
            self.error = error

        def complete(self, prompt):
            self.last_prompt = prompt
            if self.error is not None:
                raise self.error
            return self.reply

    faker = Faker()
    monkeypatch.setattr("oknowledge.ai.build_engine", lambda name, cfg: faker)
    return faker


def test_the_model_rewrites_the_summary_and_signs_it(cfg, fake_engine):
    fake_engine.answers('{"summary": "Un cyborg viaja al pasado.", '
                        '"points": ["uno", "dos"]}')
    assert describe(cfg, CARD) is True
    note = note_now(cfg)
    assert note.summary == "Un cyborg viaja al pasado."
    assert note.points == ["uno", "dos"]
    assert note.engine == "fake"
    assert note.model == "fake-1"


def test_it_does_not_touch_anything_else(cfg, fake_engine):
    """Ni la categoría, ni las etiquetas, ni el puntaje, ni tu nota."""
    before = note_now(cfg)
    fake_engine.answers('{"summary": "Otra cosa.", "points": ["x"]}')
    describe(cfg, CARD)
    after = note_now(cfg)
    assert (after.category, after.tags, after.rating, after.length) == (
        before.category, before.tags, before.rating, before.length)
    assert (after.score, after.state, after.my_note) == (
        before.score, before.state, before.my_note)
    assert (after.author, after.published, after.title) == (
        before.author, before.published, before.title)


def test_an_engine_that_fails_leaves_the_card_as_it_was(cfg, fake_engine):
    fake_engine.raises(AllEnginesFailed("nothing configured"))
    assert describe(cfg, CARD) is False
    assert note_now(cfg).summary.startswith("Catalog synopsis")
    assert note_now(cfg).engine == ""


def test_an_answer_that_is_not_json_is_a_failure_and_not_a_traceback(cfg, fake_engine):
    fake_engine.answers("Claro! Acá va el resumen:")
    assert describe(cfg, CARD) is False
    assert note_now(cfg).summary.startswith("Catalog synopsis")


def test_an_empty_summary_is_not_an_improvement(cfg, fake_engine):
    fake_engine.answers('{"summary": "   ", "points": ["uno"]}')
    assert describe(cfg, CARD) is False
    assert note_now(cfg).summary.startswith("Catalog synopsis")


def test_a_card_that_is_not_there(cfg, fake_engine):
    assert describe(cfg, "zzzzzzzzzzzz") is False


def test_a_link_is_not_a_card(cfg, fake_engine):
    """describe() mira sólo el estante de ocio: un link se reanaliza con
    reprocess, que sí lee la página."""
    link = Note(id="bbbbbbbbbbbb", url="https://example.com/x", title="Página",
                category="Redes", tags=[], type="article", source="example.com",
                saved="2026-10-10", summary="Algo.")
    write_note(cfg, link, "es")
    assert describe(cfg, "bbbbbbbbbbbb") is False


def test_the_prompt_carries_what_the_model_needs(cfg, fake_engine):
    describe(cfg, CARD)
    sent = fake_engine.last_prompt
    for part in ("The Terminator", "1984", "accion", "cyborg assassin",
                 "español", "James Cameron", "108 min"):
        assert part in sent


def test_the_prompt_says_what_kind_of_thing_it_is(cfg, fake_engine):
    describe(cfg, CARD)
    assert "película" in fake_engine.last_prompt
