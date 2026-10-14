"""A link joins an idea from the link's own page, and the idea shows it.

The relation lives in the idea's note, by the link's file name, so the
idea reads on its own in Obsidian. Only links join: a card or another idea
is not something an idea is built from.
"""

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.model import Note
from oknowledge.vault import find_note, note_path, rebuild_indexes, write_note
from oknowledge.web.app import create_app

CARD = "aaaaaaaaaaaa"
LINK = "bbbbbbbbbbbb"


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
def client(cfg):
    return TestClient(create_app(cfg))


@pytest.fixture
def link(cfg):
    path = write_note(cfg, Note(id=LINK, url="https://wireguard.com", title="WireGuard",
                                category="Redes", tags=[], type="article",
                                source="wireguard.com", saved="2026-10-10",
                                summary="Una vpn."), "es")
    rebuild_indexes(cfg, "es")
    return path


@pytest.fixture
def card(cfg):
    note = Note(id=CARD, url="https://imdb.com/title/tt1", title="The Terminator",
                category="Películas", tags=[], type="movie", source="imdb.com",
                saved="2026-10-11", summary="Un cyborg.")
    write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ocio))
    return note


def put(cfg, n=1, title="VPN propia", **fields):
    note = new_idea("x", title, "2026-10-12", f"2026-10-12T00:00:00.00000{n}+00:00")
    for key, value in fields.items():
        setattr(note, key, value)
    write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ideas))
    return note


def related_of(cfg, note):
    return find_note(cfg, note.id, shelf=cfg.ideas)[1].related


def test_a_link_s_page_offers_your_live_ideas(cfg, client, link):
    idea = put(cfg, 1, title="VPN propia")
    put(cfg, 2, title="Descartada", state="dropped")
    page = client.get(f"/item/{LINK}").text
    assert f'action="/item/{LINK}/ideas"' in page
    assert f'<option value="{idea.id}">VPN propia</option>' in page
    assert "Descartada" not in page


def test_no_ideas_no_picker(client, link):
    assert f'/item/{LINK}/ideas"' not in client.get(f"/item/{LINK}").text


def test_neither_a_card_nor_an_idea_offers_the_picker(cfg, client, card):
    idea = put(cfg)
    assert f'/item/{CARD}/ideas"' not in client.get(f"/item/{CARD}").text
    assert f'/item/{idea.id}/ideas"' not in client.get(f"/item/{idea.id}").text


def test_a_link_joins_an_idea_by_its_file_name(cfg, client, link):
    idea = put(cfg)
    answer = client.post(f"/item/{LINK}/ideas", data={"idea": idea.id},
                         follow_redirects=False)
    assert answer.headers["location"] == f"/item/{LINK}?notice=saved"
    assert related_of(cfg, idea) == [link.stem]


def test_joining_twice_is_once(cfg, client, link):
    idea = put(cfg)
    client.post(f"/item/{LINK}/ideas", data={"idea": idea.id})
    client.post(f"/item/{LINK}/ideas", data={"idea": idea.id})
    assert related_of(cfg, idea) == [link.stem]


def test_only_a_link_joins_an_idea(cfg, client, card):
    idea = put(cfg, 1)
    other = put(cfg, 2, title="Otra")
    assert client.post(f"/item/{CARD}/ideas", data={"idea": idea.id}).status_code == 404
    assert client.post(f"/item/{other.id}/ideas", data={"idea": idea.id}).status_code == 404
    assert related_of(cfg, idea) == []


def test_an_idea_that_is_gone_is_said_and_nothing_is_written(cfg, client, link):
    answer = client.post(f"/item/{LINK}/ideas", data={"idea": "000000000000"},
                         follow_redirects=False)
    assert answer.headers["location"] == f"/item/{LINK}?notice=no-such-idea"
    assert not cfg.ideas.dir.exists() or list(cfg.ideas.dir.glob("*.md")) == []


def test_a_full_idea_is_said(cfg, client, link):
    idea = put(cfg, related=[f"n{i}" for i in range(16)])
    answer = client.post(f"/item/{LINK}/ideas", data={"idea": idea.id},
                         follow_redirects=False)
    assert answer.headers["location"] == f"/item/{LINK}?notice=idea-full"
    assert link.stem not in related_of(cfg, idea)


def test_the_idea_shows_its_links_by_their_real_titles(cfg, client, link):
    idea = put(cfg, related=[link.stem])
    text = client.get(f"/item/{idea.id}").text
    aside = text[text.index('<aside class="idea-links"'):text.index("</aside>")]
    assert f'href="/item/{LINK}" data-popup="/embed/{LINK}"' in aside
    assert ">WireGuard</a>" in aside


def test_a_link_that_is_not_there_any_more_is_dimmed_not_dropped(cfg, client):
    idea = put(cfg, related=["2026-01-01-borrada"])
    page = client.get(f"/item/{idea.id}").text
    assert 'class="card gone"' in page
    assert "2026-01-01-borrada" in page


def test_a_link_leaves_the_idea(cfg, client, link):
    idea = put(cfg, related=[link.stem, "otro"])
    client.post(f"/item/{idea.id}/related/drop", data={"stem": link.stem})
    assert related_of(cfg, idea) == ["otro"]


def test_leaving_an_idea_that_is_not_there_is_404(client):
    answer = client.post("/item/000000000000/related/drop", data={"stem": "x"})
    assert answer.status_code == 404
