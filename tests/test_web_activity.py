"""The activity page: every model call this process makes, not only a batch.

Pressing Expand on an idea used to leave nothing readable anywhere: the
steps were kept, but the page only reloaded during a batch, named no note,
and a new batch wiped them.
"""

import datetime

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.trace import Step
from oknowledge.vault import note_path, rebuild_indexes, write_note
from oknowledge.web.app import create_app
from oknowledge.web.batch import Batch


@pytest.fixture(autouse=True)
def state_tree(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr("oknowledge.web.app.CONFIG_PATH",
                        tmp_path / "config" / "config.toml")


@pytest.fixture
def cfg(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    config = Config(vault=vault)
    rebuild_indexes(config, "es")
    return config


@pytest.fixture
def idea(cfg):
    note = new_idea("Una huerta con sensores.", "Huerta con sensores", "2026-10-13",
                    "2026-10-13T00:00:00.000001+00:00")
    write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ideas))
    rebuild_indexes(cfg, "es", shelf=cfg.ideas)
    return note


def step(link, name, state, detail="", engine=""):
    return Step(link=link, name=name, state=state, seconds=0.0 if state == "start" else 2.5,
                engine=engine, detail=detail)


# --- what is kept ---------------------------------------------------------------

def test_each_line_knows_when_it_happened():
    held = Batch()
    before = datetime.datetime.now(datetime.timezone.utc)
    held.note(step("a", "expand", "start"))
    [line] = held.snapshot().lines
    assert line.at >= before and line.at.tzinfo is not None
    assert (line.link, line.name, line.state) == ("a", "expand", "start")


def test_a_step_that_started_and_has_not_ended_is_in_progress():
    held = Batch()
    held.note(step("a", "expand", "start"))
    held.note(step("b", "describe", "start"))
    held.note(step("b", "describe", "ok"))
    assert [(l.link, l.name) for l in held.snapshot().busy] == [("a", "expand")]


def test_a_new_batch_keeps_what_else_happened():
    held = Batch()
    held.note(step("a", "expand", "ok"))
    held.start(1)
    assert [l.link for l in held.snapshot().lines] == ["a"]


# --- the page ---------------------------------------------------------------------

def test_the_page_is_about_all_ai_activity(cfg):
    body = TestClient(create_app(cfg)).get("/retry").text
    assert "<h1>AI activity</h1>" in body
    assert "Links waiting to be analysed" in body


def test_the_nav_calls_it_activity(cfg):
    assert '<a href="/retry">Activity' in TestClient(create_app(cfg)).get("/").text


def test_an_idea_action_names_what_it_did_and_on_which_idea(cfg, idea):
    app = create_app(cfg)
    app.state.batch.note(step(idea.id, "expand", "ok", detail="opencode/big-pickle", engine="opencode"))
    body = TestClient(app).get("/retry").text
    assert "Expand the idea" in body
    assert f'<a href="/item/{idea.id}">Huerta con sensores</a>' in body
    assert "opencode/big-pickle" in body


def test_a_failure_says_why(cfg, idea):
    app = create_app(cfg)
    app.state.batch.note(step(idea.id, "improve", "fail", detail="every engine failed: 429"))
    body = TestClient(app).get("/retry").text
    assert "every engine failed: 429" in body
    assert "failed" in body


def test_something_in_progress_is_listed_and_the_page_reloads(cfg, idea):
    app = create_app(cfg)
    app.state.batch.note(step(idea.id, "expand", "start"))
    body = TestClient(app).get("/retry").text
    assert "In progress" in body
    progress = body[body.index("In progress"):]
    assert "Expand the idea" in progress
    assert 'http-equiv="refresh"' in body


def test_a_link_not_in_any_shelf_shows_its_id(cfg):
    app = create_app(cfg)
    app.state.batch.note(step("0123456789ab", "extract", "ok"))
    body = TestClient(app).get("/retry").text
    assert "0123456789ab" in body
    assert "Read the page" in body


def test_an_empty_history_says_so(cfg):
    body = TestClient(create_app(cfg)).get("/retry").text
    assert "No AI activity since the server started." in body


def test_a_finished_step_is_one_line_in_the_history(cfg, idea):
    """Its start is not a second line: what is running is under In progress."""
    app = create_app(cfg)
    app.state.batch.note(step(idea.id, "expand", "start"))
    app.state.batch.note(step(idea.id, "expand", "ok"))
    body = TestClient(app).get("/retry").text
    assert body.count("Expand the idea") == 1
    assert "In progress" not in body


def test_something_running_is_not_called_no_activity(cfg, idea):
    app = create_app(cfg)
    app.state.batch.note(step(idea.id, "expand", "start"))
    assert "No AI activity" not in TestClient(app).get("/retry").text
