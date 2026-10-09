"""Choosing a model from a list instead of typing it from memory.

The trap this design has to avoid is the page itself: three engines with
their timeouts is up to twelve seconds to open Settings, and the slow case --
a server that is not running -- is the common one. So nothing is asked until
a button is pressed, and what it finds is kept.
"""

import json

import pytest
from fastapi.testclient import TestClient

from oknowledge import models_cache
from oknowledge.ai.base import EngineError
from oknowledge.ai.fake import FakeEngine
from oknowledge.config import Config
from oknowledge.vault import rebuild_indexes
from oknowledge.web import app as module
from oknowledge.web.app import create_app


@pytest.fixture(autouse=True)
def state_tree(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr("oknowledge.web.app.CONFIG_PATH",
                        tmp_path / "config" / "config.toml")


@pytest.fixture
def client(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    rebuild_indexes(cfg, "es")
    return TestClient(create_app(cfg))


def listed(names, engine="opencode"):
    """An engine that answers `names` when asked what it has."""
    def build(name, cfg):
        assert name == engine, f"asked {name}, not {engine}"
        found = FakeEngine([])
        found.models = lambda: list(names)
        return found
    return build


# --- the page ----------------------------------------------------------------

def test_opening_settings_asks_no_engine_anything(client, monkeypatch):
    """Twelve seconds of waiting to open a page is this design's one trap.

    conftest already fails any test that runs a program or reaches the
    network. This says so on purpose: the point is the page, not the plumbing.
    """
    monkeypatch.setattr(module, "build_engine",
                        lambda *a, **k: pytest.fail("Settings asked an engine"))
    assert client.get("/settings").status_code == 200


def test_the_box_offers_a_list_and_stays_typable(client):
    body = client.get("/settings").text
    assert 'list="models-opencode"' in body
    assert '<datalist id="models-opencode">' in body
    # A <select> would be the obvious control and the wrong one: an engine
    # that cannot be asked has to leave you able to type the name yourself.
    assert '<select name="opencode_model"' not in body


def test_what_was_found_is_offered(client):
    models_cache.remember("opencode", ["a/one", "b/two"])
    body = client.get("/settings").text
    assert '<option value="a/one">' in body
    assert '<option value="b/two">' in body


def test_the_page_says_how_old_the_list_is(client):
    models_cache.remember("opencode", ["a/one"])
    today = models_cache.read()["opencode"]["at"]
    assert today in client.get("/settings").text


def test_a_list_nobody_has_looked_for_says_nothing_about_dates(client):
    assert "models-opencode" in client.get("/settings").text   # the datalist is there
    assert client.get("/settings").text.count("Looked up") == 0


# --- the button ---------------------------------------------------------------

def test_the_button_asks_the_engine_and_remembers_what_it_said(client, monkeypatch):
    monkeypatch.setattr(module, "build_engine", listed(["a/one", "b/two"]))

    answer = client.post("/settings/models/opencode", follow_redirects=False)

    assert answer.status_code == 303
    assert "notice=models-found" in answer.headers["location"]
    assert "n=2" in answer.headers["location"]
    assert models_cache.read()["opencode"]["found"] == ["a/one", "b/two"]


def test_a_search_that_finds_nothing_says_so_and_keeps_the_box_typable(client,
                                                                       monkeypatch):
    monkeypatch.setattr(module, "build_engine", listed([], engine="ollama"))

    answer = client.post("/settings/models/ollama", follow_redirects=False)

    assert "notice=models-none" in answer.headers["location"]
    body = client.get("/settings").text
    assert 'list="models-ollama"' in body          # the datalist is still there, empty


def test_an_engine_that_cannot_even_be_built_is_an_answer_not_a_crash(client,
                                                                      monkeypatch):
    def refuse(name, cfg):
        raise EngineError("unknown provider: 'nope'")

    monkeypatch.setattr(module, "build_engine", refuse)
    answer = client.post("/settings/models/api", follow_redirects=False)
    assert "notice=models-none" in answer.headers["location"]


def test_an_engine_that_explodes_is_an_answer_not_a_crash(client, monkeypatch):
    def angry(name, cfg):
        raise RuntimeError("?!")

    monkeypatch.setattr(module, "build_engine", angry)
    answer = client.post("/settings/models/api", follow_redirects=False)
    assert "notice=models-none" in answer.headers["location"]


def test_there_is_no_such_engine(client):
    assert client.post("/settings/models/../../etc", follow_redirects=False
                       ).status_code in (404, 307)
    assert client.post("/settings/models/nope").status_code == 404


def test_the_button_does_not_save_the_rest_of_the_form(client, monkeypatch):
    """It submits a form of its own, so whatever is typed in the big one is
    not written. The page says as much."""
    monkeypatch.setattr(module, "build_engine", listed(["a/one"]))
    client.post("/settings/models/opencode")
    body = client.get("/settings").text
    assert 'form="find-opencode"' in body
    assert 'id="find-opencode"' in body


# --- the cache itself ---------------------------------------------------------

def test_the_cache_keeps_the_other_engines(client):
    models_cache.remember("opencode", ["a/one"])
    models_cache.remember("ollama", ["q:7b"])
    assert set(models_cache.read()) == {"opencode", "ollama"}


def test_a_second_look_replaces_the_first(client):
    models_cache.remember("opencode", ["a/one"])
    models_cache.remember("opencode", ["b/two"])
    assert models_cache.read()["opencode"]["found"] == ["b/two"]


def test_a_cache_file_of_nonsense_is_an_empty_cache(client):
    models_cache.path().parent.mkdir(parents=True, exist_ok=True)
    models_cache.path().write_text("}{ not json", encoding="utf-8")
    assert models_cache.read() == {}
    assert client.get("/settings").status_code == 200


@pytest.mark.parametrize("content", [
    '["a list, not an object"]',
    '{"opencode": "a string, not an entry"}',
    '{"opencode": {"found": "a string, not a list"}}',
    '{"opencode": {"found": ["ok", 7, null], "at": 2026}}',
])
def test_a_cache_file_of_the_wrong_shape_is_read_for_what_it_has(client, content):
    """It lives in the state dir, where a user can edit it and another tool
    can write over it."""
    models_cache.path().parent.mkdir(parents=True, exist_ok=True)
    models_cache.path().write_text(content, encoding="utf-8")
    table = models_cache.read()
    assert isinstance(table, dict)
    for entry in table.values():
        assert isinstance(entry.get("found"), list)
        assert all(isinstance(name, str) for name in entry["found"])
        assert isinstance(entry.get("at"), str)
    assert client.get("/settings").status_code == 200


def test_a_state_dir_that_cannot_be_written_is_not_an_error(client, tmp_path):
    models_cache.path().parent.mkdir(parents=True, exist_ok=True)
    models_cache.path().mkdir()        # a folder where the file goes
    assert models_cache.remember("opencode", ["a/one"]) == {}


def test_what_is_remembered_is_json_a_person_can_read(client):
    models_cache.remember("opencode", ["a/one"])
    data = json.loads(models_cache.path().read_text(encoding="utf-8"))
    assert data["opencode"]["found"] == ["a/one"]
    assert data["opencode"]["at"].startswith("20")
