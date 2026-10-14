"""The search box beside an idea: your links, as you type, minus the linked ones."""

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.model import Note
from oknowledge.vault import note_path, rebuild_indexes, write_note
from oknowledge.web.app import create_app


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


def a_link(cfg, n, title, summary="Una vpn."):
    return write_note(cfg, Note(id=f"l{n:011d}", url=f"https://e.com/{n}", title=title,
                                category="Redes", tags=["vpn"], type="article",
                                source="e.com", saved="2026-10-10", summary=summary),
                      "es").stem


def an_idea(cfg, related=()):
    note = new_idea("x", "VPN propia", "2026-10-12", "2026-10-12T00:00:00.000001+00:00")
    note.related = list(related)
    write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ideas))
    return note


def search(cfg, idea, q):
    return TestClient(create_app(cfg)).get(f"/item/{idea.id}/buscar-links", params={"q": q})


def test_it_finds_by_title_without_accents(cfg):
    a_link(cfg, 1, "Túnel WireGuard")
    reply = search(cfg, an_idea(cfg), "tunel")
    assert reply.status_code == 200
    assert "Túnel WireGuard" in reply.text
    assert 'class="card"' in reply.text
    assert 'data-popup="/embed/l00000000001"' in reply.text


def test_linked_links_are_left_out(cfg):
    stem = a_link(cfg, 1, "WireGuard")
    a_link(cfg, 2, "WireGuard rápido")
    reply = search(cfg, an_idea(cfg, related=[stem]), "wireguard")
    assert "WireGuard rápido" in reply.text
    assert ">WireGuard<" not in reply.text


def test_at_most_twelve(cfg):
    for n in range(1, 16):
        a_link(cfg, n, f"VPN {n}")
    assert search(cfg, an_idea(cfg), "vpn").text.count('class="card"') == 12


@pytest.mark.parametrize("q", ["", "v", "   ", "#", "#a", "a b"])
def test_too_little_to_search_is_empty(cfg, q):
    a_link(cfg, 1, "VPN")
    reply = search(cfg, an_idea(cfg), q)
    assert reply.status_code == 200 and 'class="card"' not in reply.text


def test_nothing_found_says_so(cfg):
    a_link(cfg, 1, "VPN")
    assert "Nothing matches" in search(cfg, an_idea(cfg), "zzzz").text


def test_a_missing_idea_is_404(cfg):
    assert TestClient(create_app(cfg)).get("/item/nope/buscar-links?q=vpn").status_code == 404


def test_each_result_adds_to_the_idea_and_keeps_the_query(cfg):
    a_link(cfg, 1, "WireGuard")
    idea = an_idea(cfg)
    text = search(cfg, idea, "wire").text
    assert 'action="/item/l00000000001/ideas"' in text
    assert f'name="idea" value="{idea.id}"' in text
    assert 'name="back" value="idea"' in text and 'name="q" value="wire"' in text


def test_adding_goes_back_to_the_search(cfg):
    a_link(cfg, 1, "WireGuard")
    idea = an_idea(cfg)
    reply = TestClient(create_app(cfg)).post(
        "/item/l00000000001/ideas", data={"idea": idea.id, "back": "idea", "q": "wire"},
        follow_redirects=False)
    assert reply.headers["location"] == f"/item/{idea.id}?notice=saved&q=wire"


def test_the_idea_page_shows_results_without_javascript(cfg):
    a_link(cfg, 1, "WireGuard")
    idea = an_idea(cfg)
    page = TestClient(create_app(cfg)).get(f"/item/{idea.id}", params={"q": "wire"}).text
    assert 'action="/item/l00000000001/ideas"' in page
