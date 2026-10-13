"""Marks on the web: the picker, the route that writes one, the nav, /marked."""

import re
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.vault import find_note, note_path, rebuild_indexes, write_note
from oknowledge.web.app import create_app

LINK, CARD, IDEA = "aaaaaaaaaaaa", "bbbbbbbbbbbb", "cccccccccccc"


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
    write_note(config, Note(id=LINK, url="https://wireguard.com", title="WireGuard",
                            category="Redes", tags=[], type="article",
                            source="wireguard.com", saved="2026-10-10",
                            summary="Una vpn."), "es")
    card = Note(id=CARD, url="https://imdb.com/title/tt0088247", title="The Terminator",
                category="Películas", tags=[], type="movie", source="imdb.com",
                saved="2026-10-11", summary="Un cyborg.")
    write_note(config, card, "es", path=note_path(config, card, shelf=config.ocio))
    idea = Note(id=IDEA, url="", title="Gimnasio", category="Ideas", tags=[],
                type="idea", source="", saved="2026-10-12", summary="Una app.")
    write_note(config, idea, "es", path=note_path(config, idea, shelf=config.ideas))
    for shelf in (None, config.ocio, config.ideas):
        rebuild_indexes(config, "es", shelf)
    return config


@pytest.fixture
def client(cfg):
    return TestClient(create_app(cfg))


def mark_of(cfg, link_id):
    for shelf in (None, cfg.ocio, cfg.ideas):
        found = find_note(cfg, link_id, shelf)
        if found:
            return found[1].mark
    raise AssertionError("gone")


def nav(body):
    return re.search(r"<nav[^>]*>.*?</nav>", body, re.S).group(0)


def test_no_marks_nothing_in_the_nav(client):
    assert "/marked" not in nav(client.get("/").text)


def test_the_marks_in_use_are_in_the_nav_most_used_first(client, cfg):
    for link_id, mark in ((LINK, "🔥"), (CARD, "⭐"), (IDEA, "⭐")):
        path, note = next(f for f in (find_note(cfg, link_id, s)
                                      for s in (None, cfg.ocio, cfg.ideas)) if f)
        note.mark = mark
        write_note(cfg, note, "es", path=path)
    links = re.findall(r'href="/marked\?mark=([^"]+)"', nav(client.get("/").text))
    assert links == [quote("⭐"), quote("🔥")]
