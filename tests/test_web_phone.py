"""Delivery 4, the phone (docs/2026-10-15-rediseno-celular-design.md): what has
to be in the HTML, the CSS and the scripts for a 390px screen. How it looks
and moves is checked in a browser (the plan's Playwright steps)."""

import re

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.model import Note
from oknowledge.vault import note_path, rebuild_indexes, write_note
from oknowledge.web.app import WEB, create_app

CARD = "c00000000001"


def static(name):
    return WEB.joinpath("static", name).read_text(encoding="utf-8")


def block(css, head):
    """The rules of the first `head { … }` in `css`, braces balanced."""
    start = css.index(head)
    depth = 0
    for at in range(start, len(css)):
        if css[at] == "{":
            depth += 1
        elif css[at] == "}":
            depth -= 1
            if depth == 0:
                return css[start:at + 1]
    raise AssertionError(f"{head} is not closed")


@pytest.fixture
def seeded(tmp_path):
    """Three links (a1 Redes ⭐ in "Casa", b2 Cocina 📌, c3 Redes), a card and
    an idea: (config, the idea's id)."""
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    config = Config(vault=vault)
    for id, category, mark, cols in (("a1", "Redes", "⭐", ["Casa"]), ("b2", "Cocina", "📌", []),
                                     ("c3", "Redes", "", [])):
        write_note(config, Note(id=id, url=f"https://e.com/{id}", title=f"T {id}", category=category,
                                tags=[], type="article", source="e.com", saved="2026-10-03",
                                summary="s", mark=mark, collections=cols), "es")
    card = Note(id=CARD, url="https://www.imdb.com/title/tt1", title="Dune", category="Películas",
                tags=[], type="movie", source="imdb.com", saved="2026-10-02", summary="s",
                state="pending")
    write_note(config, card, "es", path=note_path(config, card, shelf=config.ocio))
    idea = new_idea("Una idea.", "VPN", "2026-10-13", "2026-10-13T00:00:00.000001+00:00")
    write_note(config, idea, "es", path=note_path(config, idea, shelf=config.ideas))
    for shelf in (config.links, config.ocio, config.ideas):
        rebuild_indexes(config, "es", shelf=shelf)
    return config, idea.id


@pytest.fixture
def cfg(seeded):
    return seeded[0]


@pytest.fixture
def client(seeded):
    client = TestClient(create_app(seeded[0]))
    client.idea = seeded[1]
    return client


# --- Task 1: the viewport (spec §12) ---------------------------------------------------

def test_the_page_may_use_the_whole_screen(client):
    body = client.get("/").text
    assert ('<meta name="viewport" content="width=device-width, initial-scale=1, '
            'viewport-fit=cover">') in body
    # Pinch to zoom keeps working.
    assert "maximum-scale" not in body and "user-scalable" not in body


# --- Task 2: the top bar and the tabs (spec §2.1) ------------------------------------------

PAGES = ["/", "/?vista=lista", "/ocio", "/ideas", "IDEA", "/settings", "/import", "/retry",
         "/no-such-page"]


def get(client, path):
    return client.get(f"/ideas/{client.idea}" if path == "IDEA" else path)


def tabs(body):
    return re.search(r'<nav class="tabbar" aria-label="Sections">.*?</nav>', body, re.S).group(0)


@pytest.mark.parametrize("path", PAGES)
def test_every_page_has_the_top_bar_and_the_four_tabs(client, path):
    body = get(client, path).text
    top = re.search(r'<header class="topbar">.*?</header>', body, re.S).group(0)
    assert '<a class="logo" href="/">oknowledge</a>' in top
    assert '<a href="/settings" class="topbar-settings" data-modal="settings">Settings</a>' in top
    assert re.findall(r'<a href="([^"]+)"', tabs(body)) == ["/", "/ocio", "/ideas",
                                                            "/?mark=%E2%AD%90"]
    assert [t.strip() for t in re.findall(r">([^<]+)</a>", tabs(body))] == [
        "Library", "Leisure", "Ideas", "Favorites"]


def test_the_bars_are_inside_the_app_around_the_columns(client):
    body = client.get("/").text
    app = body[body.index('<div class="app'):body.index('<div id="toast"')]
    assert (app.index('<header class="topbar">') < app.index('<aside class="sidebar"')
            < app.index('id="panel"') < app.index('<nav class="tabbar"'))


@pytest.mark.parametrize("path, lit", [
    ("/", ["/"]), ("/?cat=Redes", ["/"]), ("/?mark=%E2%AD%90", ["/?mark=%E2%AD%90"]),
    ("/?mark=%E2%AD%90&q=wireguard", ["/"]), ("/?mark=%F0%9F%93%8C", ["/"]),
    ("/ocio", ["/ocio"]), ("/ideas", ["/ideas"]), ("IDEA", ["/ideas"]),
    ("/settings", []), ("/import", []), ("/no-such-page", [])])
def test_one_tab_is_lit_and_favorites_is_the_starred_library(client, path, lit):
    found = re.findall(r'<a href="([^"]+)" class="on" aria-current="page">', tabs(get(client, path).text))
    assert found == lit


def test_the_top_bar_counts_the_batch_as_the_sidebar_does(cfg, monkeypatch):
    from oknowledge.web import batch

    class Running(batch.Batch):
        def snapshot(self):
            return batch.State(running=True, total=10, done=3, failed=0, error=None,
                               lines=(), busy=())

    monkeypatch.setattr("oknowledge.web.app.Batch", Running)
    body = TestClient(create_app(cfg)).get("/").text
    top = re.search(r'<header class="topbar">.*?</header>', body, re.S).group(0)
    foot = re.search(r'<nav class="foot">.*?</nav>', body, re.S).group(0)
    assert 'data-modal="settings">Settings <b class="mono">3/10</b></a>' in top
    assert 'data-modal="settings">Settings <b class="mono">3/10</b></a>' in foot


def test_the_bars_are_not_drawn_on_a_desktop():
    css = static("app.css")
    assert ".topbar, .tabbar { display: none; }" in css
    assert css.index(".topbar, .tabbar { display: none; }") > css.index("/* --- delivery 4: the phone")
