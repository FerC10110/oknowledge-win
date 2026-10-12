"""Filling in an idea, behind the page.

The idea is on disk from the second it is saved, with your text. The model
comes afterwards and adds what it is good at -- a name if you gave none,
tags, a one-line summary, the points -- and never what is yours: the text,
a title you wrote, the state, the stars, the links.
"""

import json

import pytest

from oknowledge.ai.base import EngineError
from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.pipeline import complete_idea, retitle_idea
from oknowledge.vault import find_note, note_path, rebuild_indexes, write_note

INSTANT = "2026-10-12T21:04:05.123456+00:00"
ANSWER = {"title": "Gimnasio con IA", "tags": ["gimnasio", "ia"],
          "summary": "Una app que arma la rutina.",
          "points": ["Para quien entrena solo.", "Lee las series."]}


@pytest.fixture(autouse=True)
def state_tree(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))


@pytest.fixture
def cfg(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    return Config(vault=vault, chain=("fake",))


def put(cfg, title="", **mine):
    note = new_idea("Una app que me arme la rutina.", title, "2026-10-12", INSTANT)
    for key, value in mine.items():
        setattr(note, key, value)
    path = write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ideas))
    rebuild_indexes(cfg, "es", shelf=cfg.ideas)
    return note, path


def now(cfg, note):
    return find_note(cfg, note.id, shelf=cfg.ideas)


@pytest.fixture
def engine(monkeypatch):
    class Faker:
        model = "fake-1"

        def __init__(self):
            self.reply = json.dumps(ANSWER)
            self.meanwhile = None
            self.error = None
            self.prompt = ""

        def complete(self, prompt):
            self.prompt = prompt
            if self.meanwhile is not None:
                self.meanwhile()
            if self.error is not None:
                raise self.error
            return self.reply

    faker = Faker()
    monkeypatch.setattr("oknowledge.ai.build_engine", lambda name, cfg: faker)
    return faker


def test_an_untitled_idea_gets_its_name_and_its_file_name(cfg, engine):
    note, old = put(cfg)
    assert complete_idea(cfg, note.id) is True
    path, after = now(cfg, note)
    assert after.title == "Gimnasio con IA"
    assert path.name == "2026-10-12-gimnasio-con-ia.md"
    assert not old.exists()


def test_a_title_you_wrote_is_kept(cfg, engine):
    note, old = put(cfg, title="Mi gym")
    complete_idea(cfg, note.id)
    path, after = now(cfg, note)
    assert after.title == "Mi gym"
    assert path == old


def test_the_model_fills_in_tags_summary_points_and_signs_it(cfg, engine):
    note, _ = put(cfg)
    complete_idea(cfg, note.id)
    after = now(cfg, note)[1]
    assert after.tags == ["gimnasio", "ia"]
    assert after.summary == "Una app que arma la rutina."
    assert after.points == ["Para quien entrena solo.", "Lee las series."]
    assert (after.engine, after.model) == ("fake", "fake-1")


def test_the_model_reads_your_text(cfg, engine):
    note, _ = put(cfg)
    complete_idea(cfg, note.id)
    assert "Una app que me arme la rutina." in engine.prompt


def test_what_is_yours_survives(cfg, engine):
    note, _ = put(cfg, state="doing", score=4, related=["2026-10-02-rutina"])
    complete_idea(cfg, note.id)
    after = now(cfg, note)[1]
    assert after.my_note == "Una app que me arme la rutina."
    assert (after.state, after.score, after.related) == ("doing", 4, ["2026-10-02-rutina"])


def test_what_you_did_while_it_thought_survives(cfg, engine):
    note, _ = put(cfg)

    def you_meanwhile():
        path, there = now(cfg, note)
        there.state, there.my_note = "doing", "La amplié."
        write_note(cfg, there, "es", path=path)

    engine.meanwhile = you_meanwhile
    complete_idea(cfg, note.id)
    after = now(cfg, note)[1]
    assert (after.state, after.my_note) == ("doing", "La amplié.")
    assert after.summary == "Una app que arma la rutina."


def test_an_idea_thrown_away_while_it_thought_stays_thrown_away(cfg, engine):
    note, path = put(cfg)
    engine.meanwhile = path.unlink
    assert complete_idea(cfg, note.id) is False
    assert now(cfg, note) is None
    assert list(cfg.ideas.dir.glob("2026-*.md")) == []


def test_when_nobody_answers_the_idea_stays_as_you_left_it(cfg, engine):
    note, path = put(cfg)
    before = path.read_text(encoding="utf-8")
    engine.error = EngineError("down")
    assert complete_idea(cfg, note.id) is False
    assert path.read_text(encoding="utf-8") == before


def test_asking_again_does_not_rename_what_now_has_a_name(cfg, engine):
    note, _ = put(cfg)
    complete_idea(cfg, note.id)
    engine.reply = json.dumps(dict(ANSWER, title="Otro nombre", tags=["otra"]))
    complete_idea(cfg, note.id)
    after = now(cfg, note)[1]
    assert after.title == "Gimnasio con IA"
    assert after.tags == ["otra"]


def test_the_index_follows_the_new_name(cfg, engine):
    note, _ = put(cfg)
    complete_idea(cfg, note.id)
    index = (cfg.ideas.index_dir / "Ideas.md").read_text(encoding="utf-8")
    assert "[[2026-10-12-gimnasio-con-ia|Gimnasio con IA]]" in index


def test_an_idea_that_is_not_there_is_false(cfg, engine):
    assert complete_idea(cfg, "000000000000") is False


def test_your_title_and_text_from_the_page_move_the_file(cfg):
    note, old = put(cfg, title="Mi gym")
    path, trouble = retitle_idea(cfg, note.id, "  Gimnasio\ncon IA ", "Texto nuevo.\n", "es")
    assert trouble is None
    assert path.name == "2026-10-12-gimnasio-con-ia.md" and not old.exists()
    after = now(cfg, note)[1]
    assert (after.title, after.my_note) == ("Gimnasio con IA", "Texto nuevo.")
    assert "Gimnasio con IA" in (cfg.ideas.index_dir / "Ideas.md").read_text(encoding="utf-8")


def test_retitling_keeps_the_rest(cfg):
    note, _ = put(cfg, title="Mi gym", state="done", score=5, related=["x"])
    retitle_idea(cfg, note.id, "Mi gym", "Otro texto.", "es")
    after = now(cfg, note)[1]
    assert (after.state, after.score, after.related) == ("done", 5, ["x"])


def test_retitling_an_idea_that_is_not_there_is_none(cfg):
    assert retitle_idea(cfg, "000000000000", "t", "x", "es") is None
