"""The sidebar that replaces the header on every page."""

import re

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.vault import rebuild_indexes, write_note
from oknowledge.web.app import create_app


def note(id, category="Redes"):
    return Note(id=id, url=f"https://e.com/{id}", title=id, category=category, tags=[],
                type="article", source="e.com", saved="2026-10-03", summary="s")


@pytest.fixture
def client(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    for i in range(3):
        write_note(cfg, note(f"a{i}"), "es")
    rebuild_indexes(cfg, "es")
    return TestClient(create_app(cfg))


def sidebar(body):
    return re.search(r'<aside class="sidebar".*?</aside>', body, re.S).group(0)


@pytest.mark.parametrize("path", ["/settings", "/ocio", "/ideas", "/import",
                                  "/categories", "/retry", "/nothing-here"])
def test_every_page_has_the_sidebar(client, path):
    body = client.get(path).text
    side = sidebar(body)
    assert 'href="/"' in side and 'href="/ocio"' in side and 'href="/ideas"' in side
    assert 'href="/settings"' in side and 'href="/categories"' in side and 'href="/retry"' in side


def test_the_old_header_is_gone(client):
    body = client.get("/settings").text
    assert "<header>" not in body
    assert 'action="/search"' not in body
    assert "paste-form" not in body


def test_the_sections_carry_their_counts(client):
    side = sidebar(client.get("/settings").text)
    assert re.search(r'href="/"[^>]*>.*?<b class="count[^"]*">3</b>', side, re.S)


@pytest.mark.parametrize("path,active", [("/ocio", "/ocio"), ("/ideas", "/ideas")])
def test_the_section_you_are_in_is_marked(client, path, active):
    side = sidebar(client.get(path).text)
    assert f'href="{active}" class="section on"' in side


def test_a_page_outside_the_sections_marks_none(client):
    assert "section on" not in sidebar(client.get("/settings").text)


def test_the_legacy_pages_scroll_in_their_own_column(client):
    body = client.get("/settings").text
    assert '<div class="app legacy">' in body
    assert '<div class="legacy-main">' in body


def test_the_counts_follow_the_vault_on_every_page(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    client = TestClient(create_app(cfg))
    client.get("/settings")
    from oknowledge.vault import note_path
    card = note("c1")
    write_note(cfg, card, "es", path=note_path(cfg, card, shelf=cfg.ocio))
    idea = note("i1")
    write_note(cfg, idea, "es", path=note_path(cfg, idea, shelf=cfg.ideas))
    side = sidebar(client.get("/settings").text)
    assert re.search(r'href="/ocio"[^>]*>.*?<b class="count[^"]*">1</b>', side, re.S)
    assert re.search(r'href="/ideas"[^>]*>.*?<b class="count[^"]*">1</b>', side, re.S)
