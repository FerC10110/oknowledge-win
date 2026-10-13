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


@pytest.mark.parametrize("link_id", [LINK, CARD, IDEA])
def test_a_mark_goes_on_a_link_a_card_and_an_idea(client, cfg, link_id):
    client.post(f"/item/{link_id}/mark", data={"mark": "⭐", "back": "/"})
    assert mark_of(cfg, link_id) == "⭐"


def test_an_empty_mark_takes_it_off(client, cfg):
    client.post(f"/item/{LINK}/mark", data={"mark": "⭐", "back": "/"})
    client.post(f"/item/{LINK}/mark", data={"mark": "", "back": "/"})
    assert mark_of(cfg, LINK) == ""


def test_it_goes_back_to_the_same_card(client):
    answer = client.post(f"/item/{LINK}/mark", data={"mark": "⭐", "back": "/?category=Redes"},
                         follow_redirects=False)
    assert answer.status_code == 303
    assert answer.headers["location"] == f"/?category=Redes#card-{LINK}"


def test_what_is_not_a_mark_writes_nothing_and_says_so(client, cfg):
    files = sorted(cfg.root.rglob("*.md"))
    before = [p.read_text(encoding="utf-8") for p in files]
    answer = client.post(f"/item/{LINK}/mark", data={"mark": "ok", "back": "/"},
                         follow_redirects=False)
    assert answer.headers["location"] == f"/?notice=bad-mark#card-{LINK}"
    assert [p.read_text(encoding="utf-8") for p in files] == before


@pytest.mark.parametrize("back", ["//evil.com/x", "https://evil.com/", "/\\evil.com",
                                  "evil", "", "/\x07"])
def test_a_way_back_that_is_not_ours_goes_to_the_note(client, back):
    answer = client.post(f"/item/{LINK}/mark", data={"mark": "⭐", "back": back},
                         follow_redirects=False)
    assert answer.headers["location"] == f"/item/{LINK}#card-{LINK}"


def test_notices_do_not_pile_up_in_the_way_back(client):
    answer = client.post(f"/item/{LINK}/mark",
                         data={"mark": "ok", "back": "/?notice=bad-mark&page=2"},
                         follow_redirects=False)
    assert answer.headers["location"] == f"/?page=2&notice=bad-mark#card-{LINK}"


def test_a_note_that_is_not_there_is_404(client):
    assert client.post("/item/000000000000/mark", data={"mark": "⭐"}).status_code == 404


def test_the_bad_mark_notice_is_translated():
    from oknowledge.i18n import STRINGS
    from oknowledge.web.app import NOTICES
    assert NOTICES["bad-mark"] in STRINGS["es"]


def test_marked_shows_the_three_shelves(client):
    for link_id in (LINK, CARD, IDEA):
        client.post(f"/item/{link_id}/mark", data={"mark": "⭐", "back": "/"})
    body = client.get("/marked", params={"mark": "⭐"}).text
    assert body.index("Gimnasio") < body.index("The Terminator") < body.index("WireGuard")


def test_marked_leaves_out_the_other_marks(client):
    client.post(f"/item/{LINK}/mark", data={"mark": "🔥", "back": "/"})
    client.post(f"/item/{CARD}/mark", data={"mark": "⭐", "back": "/"})
    body = client.get("/marked", params={"mark": "⭐"}).text
    assert "The Terminator" in body and "WireGuard" not in body


def test_the_mark_you_are_on_is_lit_in_the_nav(client):
    client.post(f"/item/{CARD}/mark", data={"mark": "⭐", "back": "/"})
    assert 'class="mark on"' in nav(client.get("/marked", params={"mark": "⭐"}).text)


@pytest.mark.parametrize("mark", ["", "🦄"])
def test_a_mark_nobody_uses_is_an_empty_page(client, mark):
    answer = client.get("/marked", params={"mark": mark})
    assert answer.status_code == 200 and "card-" not in answer.text


def test_marked_pages_like_the_library(client, cfg, monkeypatch):
    monkeypatch.setattr("oknowledge.web.app.PER_PAGE", 1)
    for link_id in (LINK, CARD, IDEA):
        client.post(f"/item/{link_id}/mark", data={"mark": "⭐", "back": "/"})
    body = client.get("/marked", params={"mark": "⭐", "page": "2"}).text
    assert "The Terminator" in body and "WireGuard" not in body
    assert "page=3" in body
