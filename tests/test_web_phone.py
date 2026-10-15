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


# --- Task 3: the chip row (spec §3) ----------------------------------------------------------

def chips(body):
    return re.search(r'<nav class="chip-row" aria-label="Filters">.*?</nav>', body, re.S).group(0)


def groups(row):
    return re.findall(r'<div class="chip-group"( data-apart)?[^>]*>(.*?)</div>', row, re.S)


def test_the_library_row_has_all_categories_marks_and_collections_but_no_star(client):
    row = chips(client.get("/").text)
    found = groups(row)
    assert len(found) == 3
    names = [re.sub(r"<[^>]+>", "", a).strip() for a in re.findall(r"<a [^>]*>(.*?)</a>", found[0][1], re.S)]
    assert names == ["All", "Cocina", "Redes"]
    assert "📌" in found[1][1] and "Pinned" in found[1][1] and "⭐" not in found[1][1]
    assert ">Casa</a>" in found[2][1]
    assert "Favorites" not in row and "★" not in row
    # The count is in the title, never drawn.
    assert re.search(r'<a href="/\?cat=Redes" data-nav title="2" class="fchip">', row)
    assert re.search(r'title="3" class="fchip on">All</a>', row)


@pytest.mark.parametrize("path, lit", [("/?cat=Redes", "Redes"), ("/?mark=%F0%9F%93%8C", "📌"),
                                       ("/?col=Casa", "Casa"), ("/?mark=%E2%AD%90", None)])
def test_the_chip_lit_is_the_filter_in_the_url(client, path, lit):
    row = chips(client.get(path).text)
    on = re.findall(r'class="fchip on">(.*?)</a>', row, re.S)
    if lit is None:
        assert on == []           # ★ lights the Favoritos tab, not a chip
    else:
        assert len(on) == 1 and lit in on[0]


def test_an_empty_group_is_not_drawn(tmp_path):
    vault = tmp_path / "solo"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    config = Config(vault=vault)
    write_note(config, Note(id="z1", url="https://e.com/z1", title="Z", category="Redes", tags=[],
                            type="article", source="e.com", saved="2026-10-03", summary="s"), "es")
    rebuild_indexes(config, "es")
    row = chips(TestClient(create_app(config)).get("/").text)
    assert len(groups(row)) == 2      # categories and marks (📌 always); no collections


def test_ocio_and_ideas_rows_are_their_sidebar_groups_each_apart(client):
    ocio = groups(chips(client.get("/ocio").text))
    assert len(ocio) == 2 and all(apart for apart, _ in ocio)
    ideas = groups(chips(client.get("/ideas").text))
    assert len(ideas) == 1 and ideas[0][0]


def test_ocio_s_column_answer_brings_the_row(client):
    body = client.get("/ocio/lista?tipo=movie").text
    template = re.search(r'<template id="chip-filters">(.*?)</template>', body, re.S).group(1)
    assert '<nav class="chip-row"' in template
    assert re.search(r'class="fchip on">.*?</a>', template, re.S)
    assert '<template id="side-filters">' in body


def test_the_row_sits_between_the_field_and_the_list(client):
    for path in ("/", "/ocio", "/ideas"):
        body = client.get(path).text
        assert body.index('id="unified"') < body.index('<nav class="chip-row"') < body.index('id="list"'), path


def test_a_filter_lights_its_twin_in_the_other_drawing():
    js = static("shell.js")
    head = js.index("function setActive")
    body = js[head:js.index("\n  }\n", head)]
    assert '".sidebar, .chip-row"' in body
    assert 'getAttribute("href") === href' in body
    assert 'closest("[data-apart]")' in body
    assert '"a.filter.on, a.fchip.on"' in body
    assert "litChipInView();" in body


def test_ocio_s_answer_swaps_the_row_too():
    js = static("shell.js")
    head = js.index("function sideFilters")
    body = js[head:js.index("\n  }\n", head)]
    assert 'list.querySelector("template#chip-filters")' in body
    assert "replaceWith(chips.content)" in body


def test_the_lit_chip_is_brought_into_view_without_moving_the_page():
    js = static("shell.js")
    assert 'scrollIntoView({ inline: "nearest", block: "nearest" })' in js


def test_the_row_is_not_drawn_on_a_desktop():
    assert ".chip-row { display: none; }" in static("app.css")


# --- Task 4: the detail's markup (spec §6.1) and the ↵ hints (spec §4) ----------------------

@pytest.fixture
def no_catalogs(monkeypatch):
    monkeypatch.setattr("oknowledge.catalog.cinemeta.search", lambda kind, query, via="": ([], ""))
    monkeypatch.setattr("oknowledge.catalog.openlibrary.search", lambda kind, query, via="": ([], ""))


def panel_tag(body):
    return re.search(r'<section class="detail" id="panel"[^>]*>', body).group(0)


@pytest.mark.parametrize("path, opened", [
    ("/?sel=a1", True), ("/?cat=Cocina&sel=b2", True), ("/", False), ("/?sel=zzz", False),
    ("/?cat=Cocina&sel=a1", False),          # a1 is not in Cocina: the first one is shown, shut
    (f"/ocio?sel={CARD}", True), ("/ocio", False), ("/ocio?buscar=Dune&catalogo=movie", True)])
def test_the_detail_is_open_when_the_url_names_the_pick_shown(client, no_catalogs, path, opened):
    assert (" data-open" in panel_tag(client.get(path).text)) is opened


def back(text):
    return re.search(r'<a class="detail-back"[^>]*>[^<]*</a>', text).group(0)


def test_the_library_panel_starts_with_its_way_back(client):
    body = client.get("/?cat=Redes&sel=a1&vista=lista").text
    panel = body[body.index('id="panel"'):]
    assert panel.index('class="detail-back"') < panel.index("data-panel=")
    link = back(panel)
    assert 'href="/?cat=Redes&amp;vista=lista"' in link
    assert " data-back" in link and 'aria-label="Back to Library"' in link
    assert link.endswith(">← Library</a>")


def test_a_panel_fetched_alone_goes_back_to_the_list_it_came_from(client):
    link = back(client.get("/panel/a1?cat=Redes&sel=a1").text)
    assert 'href="/?cat=Redes"' in link and "← Library" in link


def test_a_card_panel_goes_back_to_ocio(client):
    link = back(client.get(f"/panel/{CARD}?tipo=movie&sel={CARD}").text)
    assert 'href="/ocio?tipo=movie"' in link and "← Leisure" in link
    body = client.get(f"/ocio?sel={CARD}").text
    assert "← Leisure" in back(body[body.index('id="panel"'):])


def test_the_catalogs_go_back_to_the_grid(client, no_catalogs):
    assert 'href="/ocio?tipo=series"' in back(client.get("/ocio/candidatos?q=Dune&tipo=movie&grid=series").text)
    assert 'href="/ocio"' in back(client.get("/ocio/candidatos?q=Dune&tipo=movie").text)


def test_a_link_being_analysed_has_its_way_back_too():
    """panel_context's first return (no note yet) carries list_url as well."""
    app = WEB.joinpath("app.py").read_text(encoding="utf-8")
    head = app.index("def panel_context")
    body = app[head:app.index("def card_context", head)]
    assert body.count('"list_url": view.url(sel="")') == 2


HINT = '<span class="enter-hint" aria-hidden="true">&nbsp;↵</span>'


@pytest.mark.parametrize("path, words", [("/", "Save"), ("/ocio", "Save"),
                                         ("/ocio", "Search the catalogs"), ("/ideas", "New idea"),
                                         ("/?sel=a1", "Open original")])
def test_the_enter_hints_are_spans_a_finger_does_not_see(client, path, words):
    body = client.get(path).text
    assert f"{words}{HINT}" in body
    assert f"{words} ↵" not in body


def test_neither_the_hint_nor_the_way_back_moves_the_desktop():
    css = static("app.css")
    assert ".btn:has(> .enter-hint) { gap: 0; }" in css
    assert ".detail-back { display: none; }" in css
