"""What Ocio's page gives its scripts (spec §1 autosave, §3)."""

import re

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.vault import note_path, rebuild_indexes, write_note
from oknowledge.web.app import create_app


@pytest.fixture(autouse=True)
def state_tree(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr("oknowledge.web.app.CONFIG_PATH", tmp_path / "config" / "config.toml")


@pytest.fixture
def client(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    note = Note(id="c00000000001", url="https://www.imdb.com/title/tt1", title="Alien",
                category="Películas", tags=[], type="movie", source="imdb.com",
                saved="2026-10-01", summary="s", engine="")
    write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ocio))
    rebuild_indexes(cfg, "es")
    return TestClient(create_app(cfg))


def test_ocio_loads_autosave_then_the_shell(client):
    body = client.get("/ocio").text
    first = body.index('<script src="/static/autosave.js" defer></script>')
    assert first < body.index('<script src="/static/shell.js" defer></script>')


def test_a_card_panel_being_rewritten_carries_its_own_words(client):
    app = client.app
    app.state.rewriting.start("c00000000001", "describe")
    body = client.get("/panel/c00000000001").text
    root = re.search(r'<div class="detail-scroll card"[^>]*>', body).group(0)
    assert 'data-working="c00000000001"' in root
    assert 'data-done-as="Done: card rewritten"' in root
    assert 'data-failed-as="The card could not be rewritten"' in root


def test_the_grid_says_the_same_for_a_rewrite_of_all(client):
    body = client.get("/ocio").text
    grid = re.search(r'<ul class="posters"[^>]*>', body).group(0)
    assert 'data-done-as="Done: card rewritten"' in grid


def test_the_writes_that_start_a_rewrite_say_so(client):
    """shell.js does not toast "reload in a moment" for these: the watcher
    says when the rewrite ends."""
    for page in ("/panel/c00000000001", "/ocio"):
        body = client.get(page).text
        for form in re.findall(r'<form[^>]*action="[^"]*(?:/describe|/ocio/reescribir)"[^>]*>', body):
            assert "data-runs" in form, form
