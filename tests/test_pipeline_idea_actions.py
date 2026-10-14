"""One action on one idea, behind the page.

The model is asked outside the lock; the idea is read again under it and
only that action's section is written. Everything else in the note --
your text above all -- is as you left it.
"""

import json

import pytest

from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.model import Note
from oknowledge.pipeline import run_idea_action
from oknowledge.queue import Locked
from oknowledge.vault import find_note, note_path, write_note

INSTANT = "2026-10-12T21:04:05.123456+00:00"


@pytest.fixture(autouse=True)
def state_tree(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))


@pytest.fixture
def cfg(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    return Config(vault=vault, chain=("fake",))


def put(cfg, **fields):
    note = new_idea("Una app de rutinas.", "Gym", "2026-10-12", INSTANT)
    for key, value in fields.items():
        setattr(note, key, value)
    path = write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ideas))
    return note, path


def now(cfg, note):
    return find_note(cfg, note.id, shelf=cfg.ideas)


@pytest.fixture
def engine(monkeypatch):
    class Faker:
        model = "fake-1"
        searches = True

        def __init__(self):
            self.reply = json.dumps({"items": ["Modo offline"]})
            self.meanwhile = None
            self.used = []
            self.prompts = []

        def _answer(self, how):
            self.used.append(how)
            if self.meanwhile is not None:
                self.meanwhile()
            return self.reply

        def complete(self, prompt):
            self.prompts.append(prompt)
            return self._answer("complete")

        def search(self, prompt):
            return self._answer("search")

    faker = Faker()
    monkeypatch.setattr("oknowledge.ai.build_engine", lambda name, cfg: faker)
    return faker


def test_an_action_writes_its_own_section(cfg, engine):
    note, _ = put(cfg)
    assert run_idea_action(cfg, note.id, "expand") is None
    assert now(cfg, note)[1].actions == {"expand": "- Modo offline"}


def test_nothing_else_in_the_idea_changes(cfg, engine):
    note, _ = put(cfg, state="doing", score=4, related=["2026-10-02-vpn"],
                  tags=["gym"], summary="Rutinas.", points=["Uno."])
    run_idea_action(cfg, note.id, "expand")
    after = now(cfg, note)[1]
    assert (after.my_note, after.title, after.tags, after.summary, after.points,
            after.related, after.state, after.score) == (
        "Una app de rutinas.", "Gym", ["gym"], "Rutinas.", ["Uno."],
        ["2026-10-02-vpn"], "doing", 4)


def test_another_action_s_section_is_kept(cfg, engine):
    note, _ = put(cfg, actions={"improve": "- a mano"})
    run_idea_action(cfg, note.id, "expand")
    assert now(cfg, note)[1].actions == {"improve": "- a mano", "expand": "- Modo offline"}


def test_asking_again_replaces_only_that_section(cfg, engine):
    note, _ = put(cfg, actions={"expand": "- viejo"})
    run_idea_action(cfg, note.id, "expand")
    assert now(cfg, note)[1].actions["expand"] == "- Modo offline"


def test_exists_searches(cfg, engine):
    engine.reply = json.dumps({"verdict": "new", "matches": []})
    note, _ = put(cfg)
    assert run_idea_action(cfg, note.id, "exists") is None
    assert engine.used == ["search"]


def test_an_idea_deleted_while_the_model_thinks_is_not_resurrected(cfg, engine):
    note, path = put(cfg)
    engine.meanwhile = path.unlink
    assert run_idea_action(cfg, note.id, "expand") == "the idea is no longer there"
    assert now(cfg, note) is None


def test_text_you_typed_while_it_thought_survives(cfg, engine):
    note, path = put(cfg)

    def edit():
        fresh = now(cfg, note)[1]
        fresh.my_note = "Lo cambié mientras pensaba."
        write_note(cfg, fresh, "es", path=path)

    engine.meanwhile = edit
    run_idea_action(cfg, note.id, "expand")
    after = now(cfg, note)[1]
    assert after.my_note == "Lo cambié mientras pensaba."
    assert after.actions == {"expand": "- Modo offline"}


def test_a_useless_answer_leaves_the_file_as_it_was(cfg, engine):
    note, path = put(cfg, actions={"expand": "- viejo"})
    before = path.read_bytes()
    engine.reply = "no json at all"
    problem = run_idea_action(cfg, note.id, "expand")
    assert problem and "fake" in problem
    assert path.read_bytes() == before


def test_a_busy_idea_says_so(cfg, engine, monkeypatch):
    class Busy:
        def lock(self, link):
            raise Locked(link)

    monkeypatch.setattr("oknowledge.pipeline.Queue", Busy)
    note, _ = put(cfg)
    assert run_idea_action(cfg, note.id, "expand") == "the idea was busy: ask again"


def test_a_missing_idea_asks_nobody(cfg, engine):
    assert run_idea_action(cfg, "nope", "expand") == "the idea is no longer there"
    assert engine.used == []


def test_an_unknown_action_is_a_programming_error(cfg, engine):
    note, _ = put(cfg)
    with pytest.raises(ValueError):
        run_idea_action(cfg, note.id, "delete")


def test_it_is_traced_start_and_end(cfg, engine):
    note, _ = put(cfg)
    steps = []
    run_idea_action(cfg, note.id, "expand", trace=steps.append)
    assert [(s.name, s.state) for s in steps] == [("expand", "start"), ("expand", "ok")]


def test_a_lock_busy_for_a_moment_does_not_throw_the_answer_away(cfg, engine, monkeypatch):
    from contextlib import nullcontext
    tries = []

    class BusyOnce:
        def lock(self, link):
            tries.append(link)
            if len(tries) == 1:
                raise Locked(link)
            return nullcontext()

    monkeypatch.setattr("oknowledge.pipeline.Queue", BusyOnce)
    monkeypatch.setattr("oknowledge.pipeline.LOCK_WAIT", 0)
    note, _ = put(cfg)
    assert run_idea_action(cfg, note.id, "expand") is None
    assert now(cfg, note)[1].actions == {"expand": "- Modo offline"}


def test_the_linked_links_reach_the_model(cfg, engine):
    stem = write_note(cfg, Note(id="l00000000001", url="https://wg.com", title="WireGuard",
                                category="Redes", tags=[], type="article", source="wg.com",
                                saved="2026-10-10", summary="Una vpn."), "es").stem
    note, _ = put(cfg, related=[stem])
    assert run_idea_action(cfg, note.id, "expand", scope="vinculados") is None
    assert "Una vpn." in engine.prompts[0]
    assert now(cfg, note)[1].actions["expand"].startswith("*Con 1 link: WireGuard.*")
