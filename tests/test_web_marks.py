"""Marks on the web: the picker, the route that writes one, the sidebar group."""

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


def marks_group(body):
    return re.search(r'<nav class="group" aria-label="Marks">.*?</nav>', body, re.S).group(0)


def test_no_marks_only_pinned_in_the_sidebar(client):
    group = marks_group(client.get("/").text)
    assert group.count('class="filter') == 1
    assert "📌" in group and '<b class="count mono">0</b>' in group


def test_a_mark_in_use_is_listed_in_the_sidebar(client):
    client.post(f"/item/{LINK}/mark", data={"mark": "🔥", "back": "/"})
    group = marks_group(client.get("/").text)
    assert "🔥" in group and "mark=%F0%9F%94%A5" in group


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


def test_a_mark_leaves_out_the_other_marks(client):
    client.post(f"/item/{LINK}/mark", data={"mark": "🔥", "back": "/"})
    assert f'id="card-{LINK}"' not in client.get("/", params={"mark": "⭐"}).text
    assert f'id="card-{LINK}"' in client.get("/", params={"mark": "🔥"}).text


def test_a_mark_nobody_uses_is_an_empty_list(client):
    answer = client.get("/", params={"mark": "🦄"})
    assert answer.status_code == 200 and 'id="card-' not in answer.text


@pytest.mark.parametrize("path, link_id", [(f"/panel/{LINK}", LINK)])
def test_every_card_and_note_page_has_the_picker(client, path, link_id):
    body = client.get(path).text
    assert f'action="/item/{link_id}/mark"' in body
    assert body.count('value="⭐"') >= 1


def test_tapping_the_mark_you_have_takes_it_off(client):
    client.post(f"/item/{LINK}/mark", data={"mark": "⭐", "back": "/"})
    body = client.get(f"/panel/{LINK}").text
    assert re.search(r'name="mark" value=""[^>]*aria-pressed="true"[^>]*><svg class="icon star-glyph"', body)


def test_the_picker_is_not_inside_a_link(client):
    """A form inside an <a> is a click that both marks and opens. The old
    check looked for a link class the redesign no longer draws, so it held
    over nothing (batch G): now every link of the pages that show the
    picker is looked in, and the picker has to be there."""
    for path in (f"/?sel={LINK}", f"/?vista=lista&sel={LINK}", f"/panel/{LINK}", "/ocio"):
        body = client.get(path).text
        links = re.findall(r"<a\b[^>]*>.*?</a>", body, re.S)
        assert links, path
        assert [link for link in links if "/mark" in link] == [], path
    assert f'action="/item/{LINK}/mark"' in client.get(f"/?sel={LINK}").text


# The favourite star is drawn, not typed. No font the page names has U+2605,
# so a browser falls back to whatever fontconfig puts first -- here a colour
# emoji font that ignores CSS `color` -- and the gold of a favourite, the one
# visible state of the panel's ★ button, never shows.
STAR = re.compile(r'<svg class="icon star-glyph"[^>]*>.*?fill="currentColor".*?</svg>', re.S)


def test_the_panel_star_is_drawn_so_its_colour_can_say_favourite(client):
    for mark in ("", "⭐"):
        client.post(f"/item/{LINK}/mark", data={"mark": mark, "back": "/"})
        body = client.get(f"/panel/{LINK}").text
        button = re.search(r'<button name="mark" value="⭐?"[^>]*class="btn icon star[^"]*".*?</button>',
                           body, re.S).group(0)
        assert STAR.search(button)
        assert "★" not in button


def test_the_card_flag_of_a_favourite_is_drawn(client):
    client.post(f"/item/{LINK}/mark", data={"mark": "⭐", "back": "/"})
    card = re.search(rf'id="card-{LINK}".*?</li>', client.get("/").text, re.S).group(0)
    flag = re.search(r'<span class="flag fav"[^>]*>.*?</span>', card, re.S).group(0)
    assert STAR.search(flag)
    assert "★" not in flag
