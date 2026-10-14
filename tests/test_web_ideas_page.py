"""The ideas section: write one, find it again.

Saving writes the idea at once, with your text, and leaves the model's part
to a task behind the page. These tests record that the task was queued and
never run a model.
"""

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.vault import all_notes, rebuild_indexes
from oknowledge.web.app import create_app


@pytest.fixture(autouse=True)
def state_tree(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr("oknowledge.web.app.CONFIG_PATH",
                        tmp_path / "config" / "config.toml")


@pytest.fixture
def queued(monkeypatch):
    calls = []
    monkeypatch.setattr("oknowledge.web.app.complete_idea",
                        lambda cfg, idea, trace=None: calls.append(idea))
    return calls


@pytest.fixture
def cfg(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    config = Config(vault=vault)
    rebuild_indexes(config, "es")
    return config


@pytest.fixture
def client(cfg):
    return TestClient(create_app(cfg))


def test_the_bar_has_a_way_in(client):
    assert 'href="/ideas"' in client.get("/").text


def test_saving_writes_the_idea_and_queues_the_model(cfg, client, queued):
    answer = client.post("/ideas/guardar",
                         data={"text": "  Una app para el gym.  ", "title": ""},
                         follow_redirects=False)
    [idea] = all_notes(cfg, cfg.ideas)
    assert (idea.my_note, idea.title, idea.type) == ("Una app para el gym.", "", "idea")
    assert answer.status_code == 303
    assert answer.headers["location"] == f"/ideas/{idea.id}?notice=completing"
    assert queued == [idea.id]


def test_a_title_you_type_is_kept(cfg, client, queued):
    client.post("/ideas/guardar", data={"text": "x", "title": "Mi gym"})
    assert all_notes(cfg, cfg.ideas)[0].title == "Mi gym"


def test_no_text_no_idea(cfg, client, queued):
    answer = client.post("/ideas/guardar", data={"text": "   ", "title": "Algo"},
                         follow_redirects=False)
    assert answer.headers["location"] == "/ideas?notice=idea-empty"
    assert all_notes(cfg, cfg.ideas) == []
    assert queued == []


def test_two_saves_are_two_ideas(cfg, client, queued):
    client.post("/ideas/guardar", data={"text": "La misma."})
    client.post("/ideas/guardar", data={"text": "La misma."})
    assert len(all_notes(cfg, cfg.ideas)) == 2


def test_a_stale_index_still_saves_and_says_so(cfg, client, queued, monkeypatch):
    def broken(*args, **kwargs):
        raise OSError("read-only")

    monkeypatch.setattr("oknowledge.web.app.rebuild_indexes", broken)
    answer = client.post("/ideas/guardar", data={"text": "x"}, follow_redirects=False)
    assert answer.headers["location"].endswith("?notice=indexes-stale")
    assert len(all_notes(cfg, cfg.ideas)) == 1
    assert len(queued) == 1


def test_a_failed_write_saves_nothing_and_queues_nothing(cfg, client, queued, monkeypatch):
    def broken(*args, **kwargs):
        raise OSError("read-only")

    monkeypatch.setattr("oknowledge.web.app.write_note", broken)
    answer = client.post("/ideas/guardar", data={"text": "x"}, follow_redirects=False)
    assert answer.headers["location"] == "/ideas?notice=write-failed"
    assert queued == []
