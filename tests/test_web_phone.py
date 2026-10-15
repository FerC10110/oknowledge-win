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


# --- Task 5: the frame (spec §1, §2.2, §3, §4, §5, §12) ------------------------------------

PHONE = "@media (max-width: 60rem) {"
WIDE = "@media (max-width: 60rem) and (min-width: 42rem) {"


def test_one_phone_block_replaces_the_unpolished_one():
    css = static("app.css")
    assert css.count(PHONE) == 1
    assert ".app, .app.legacy { display: block; height: auto; }" not in css
    assert "--tabbar-h: calc(60px + env(safe-area-inset-bottom));" in css
    phone = block(css, PHONE)
    assert "height: 100vh; height: 100dvh;" in phone
    assert "overflow-x: clip" in phone
    assert "env(safe-area-inset-top)" in phone
    assert "max(8px, env(safe-area-inset-bottom))" in phone
    assert ".sidebar { display: none; }" in phone
    assert ".detail:not([data-open]) { display: none; }" in phone
    # block() stops at the closing brace: the marker sits right after it.
    assert css[css.index(PHONE):].startswith(phone + " /* end of the phone */")


def test_every_phone_field_is_16px_so_ios_does_not_zoom():
    phone = block(static("app.css"), PHONE)
    assert re.search(r"\.unified input\[type=text\] \{[^}]*height: 46px;[^}]*font-size: 16px;", phone)


def test_the_tabs_step_aside_while_typing():
    phone = block(static("app.css"), PHONE)
    assert re.search(r"textarea, select\):focus\) \.tabbar \{ display: none; \}", phone)


def test_between_42_and_60rem_only_the_grids_widen():
    wide = block(static("app.css"), WIDE)
    assert ".tiles { grid-template-columns: repeat(3, minmax(0, 1fr)); }" in wide
    assert ".posters { grid-template-columns: repeat(auto-fill, minmax(168px, 1fr)); }" in wide
    assert ".idea-shelf .tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); }" in wide


def test_a_finger_sees_the_checkbox_and_not_the_keys():
    css = static("app.css")
    assert ".check { opacity: 1; }" in block(css, "@media (hover: none) {")
    coarse = block(css, "@media (pointer: coarse) {")
    for sel in (".key", ".enter-hint", ".unified .hint", '[data-modal="keys"]'):
        assert sel in coarse, sel


def test_a_filter_with_no_twin_unlights_the_other_drawing_and_lights_its_tab():
    """★ Favoritos has no chip: the row must not keep the last one lit; and
    the tab bar follows a filter clicked (Cocina from Favoritos lights Biblioteca)."""
    js = static("shell.js")
    head = js.index("function setActive")
    body = js[head:js.index("\n  }\n", head)]
    assert 'if (!twin && link.closest("[data-apart]")) return;' in body
    assert "litTab(href);" in body
    head = js.index("function litTab")
    body = js[head:js.index("\n  }\n", head)]
    assert '".tabbar a"' in body
    assert 'classList.toggle("on"' in body


# --- Task 5, fix round 1 -------------------------------------------------------------------

def test_the_tab_lit_is_read_from_the_url_s_path_and_mark_not_its_whole_href():
    """★ from /?vista=lista carries vista: Favoritos still lights. A typed
    search drops the mark: Biblioteca lights (tabbar.html: a search is not
    Favoritos)."""
    js = static("shell.js")
    head = js.index("function litTab")
    body = js[head:js.index("\n  }\n", head)]
    assert 'searchParams.get("mark")' in body and "pathname" in body
    assert 'getAttribute("href") === href' not in body
    head = js.index("function loadList")
    body = js[head:js.index("\n  }\n", head)]
    assert "litTab(target.href);" in body


def test_a_phone_card_keeps_a_long_domain_on_one_line_and_clamps_a_long_word():
    phone = block(static("app.css"), PHONE)
    domain = re.search(r"\.tiles \.domain \{([^}]*)\}", phone).group(1)
    for rule in ("white-space: nowrap", "overflow: hidden", "text-overflow: ellipsis",
                 "max-width: calc(100% - 16px)"):
        assert rule in domain, rule
    assert re.search(r"\.tiles \.title \{[^}]*overflow-wrap: anywhere", phone)


# --- Task 6: the layer and an idea's screen (spec §6.2, §7) ---------------------------------

def test_the_open_detail_covers_the_screen_above_the_tabs():
    phone = block(static("app.css"), PHONE)
    rule = re.search(r"\.detail\[data-open\] \{[^}]*\}", phone).group(0)
    for part in ("position: fixed;", "inset: 0;", "z-index: 40;", "background: #141519;",
                 "padding-top: env(safe-area-inset-top);"):
        assert part in rule, part
    assert '.detail[aria-busy="true"] > :not(.detail-back) { visibility: hidden; }' in phone


def test_long_words_wrap_inside_the_detail():
    phone = block(static("app.css"), PHONE)
    assert re.search(r"\.detail h1, \.detail \.where[^{]*\{ overflow-wrap: anywhere; \}", phone)
    assert ".detail pre { max-width: 100%; overflow-x: auto; }" in phone


def test_an_idea_scrolls_as_a_page_with_its_rows_scrolling_sideways():
    phone = block(static("app.css"), PHONE)
    assert re.search(r"\.idea-ai \{[^}]*overflow-x: auto;", phone)
    assert ".idea-ai .label { display: none; }" in phone
    assert re.search(r"\.idea-text textarea \{[^}]*min-height: 40dvh;[^}]*font-size: 16px;", phone)
    assert re.search(r"\.idea-results \.tabs \{[^}]*overflow-x: auto;", phone)


# --- Task 7: Ajustes, menus, toast, old pages (spec §8, §9, §11) ------------------------------

def test_settings_fills_the_phone():
    phone = block(static("app.css"), PHONE)
    rule = re.search(r"\.modal\.settings \{[^}]*\}", phone).group(0)
    for part in ("width: 100vw;", "height: 100dvh;", "max-width: none;", "max-height: none;",
                 "margin: 0;", "border: 0;", "border-radius: 0;"):
        assert part in rule, part
    assert re.search(r"\.settings-tabs \{[^}]*overflow-x: auto;", phone)
    assert re.search(r"\.setting \{[^}]*flex-direction: column;", phone)


def test_a_menu_opens_as_a_sheet_from_the_bottom():
    phone = block(static("app.css"), PHONE)
    sheet = re.search(r"\.menu-list, [^{]*\{[^}]*\}", phone).group(0)
    for part in ("position: fixed;", "left: 0;", "right: 0;", "bottom: 0;", "top: auto;",
                 "min-width: 0;", "max-height: 60dvh;", "border-radius: 14px 14px 0 0;",
                 "max(8px, env(safe-area-inset-bottom))", "z-index: 45;"):
        assert part in sheet, part
    # Every placement the desktop gives a menu is overridden by name.
    for sel in (".menu.up .menu-list", ".menu.more .menu-list", ".idea-ai .menu-list",
                ".list-head .sort .menu-list", ".bulk .menu-list"):
        assert sel in sheet, sel
    assert re.search(r'\.menu\[open\] > summary::before \{ content: ""; position: fixed; inset: 0;'
                     r' background: #0009; z-index: 44;', phone)


def test_the_toast_stays_at_the_top_and_may_wrap():
    rule = re.search(r"\.toast \{[^}]*\}", block(static("app.css"), PHONE)).group(0)
    assert "top: calc(env(safe-area-inset-top) + 12px);" in rule
    assert "max-width: calc(100vw - 32px);" in rule and "white-space: normal;" in rule


def test_a_finger_is_not_asked_to_drop_a_file():
    assert ".drop-title" in block(static("app.css"), "@media (pointer: coarse) {")


# --- Task 8: Ajustes waits for its back before reloading (Ruling 14) --------------------------

def test_a_rename_reloads_only_after_the_layer_has_gone():
    js = static("settings.js")
    head = js.index('modal.addEventListener("close"')
    body = js[head:js.index("\n    });", head)]                # the listener's own end
    assert "ok.layers ? ok.layers.settled() : Promise.resolve()" in body
    assert "after.then(function () { location.reload(); })" in body


# --- Task 9: the layer in shell.js (spec §6.3, §10) -----------------------------------------

def between(text, start, end):
    head = text.index(start)
    return text[head:text.index(end, head)]


def test_a_tap_opens_the_layer_and_a_key_does_not():
    js = static("shell.js")
    click = between(js, 'document.addEventListener("click"', "// --- remembered layout")
    assert "loadPanel(link.dataset.sel, false, { push: true })" in click
    body = between(js, "function loadPanel", "function loadCatalog")
    assert "opts && opts.push && phone() && !isOpen() && openLayer(url)" in body
    assert 'panel.setAttribute("aria-busy", "true")' in body
    assert 'panel.removeAttribute("aria-busy")' in body
    # j/k (pick), the poller and loadList never push.
    assert re.search(r"function pick\(id\) \{\n[^}]*loadPanel\(id\);", js)


def test_a_shut_layer_keeps_the_pick_out_of_the_url():
    js = static("shell.js")
    assert "if (phone() && !isOpen()) return;" in between(js, "function writePick", "\n  }\n")
    assert "writePick(url)" in between(js, "function keepShown", "\n  }\n")
    assert "if (phone()) return;" in between(js, "// --- the pick in the URL", "observe();")


def test_shell_keeps_the_entry_s_state():
    js = static("shell.js")
    assert "replaceState(null" not in js
    assert "history.replaceState(history.state," in js


@pytest.mark.parametrize("name", ["idea.js", "settings.js"])
def test_the_other_pages_keep_the_entry_s_state_too(name):
    # A replaceState(null, …) under a layer's entry would wipe {layer, base}.
    js = static(name)
    assert "replaceState(null" not in js
    assert "history.replaceState(history.state," in js


def test_back_forward_and_the_way_back_go_through_the_layers():
    js = static("shell.js")
    assert 'ok.layers.open("panel", closedLayer, url.pathname + url.search)' in js
    assert js.count('ok.layers.adopt("panel", closedLayer)') == 2      # on load, and forward
    forward = between(js, 'window.addEventListener("popstate"', "});")
    assert 'event.state.layer !== "panel"' in forward
    click = between(js, 'document.addEventListener("click"', "// --- remembered layout")
    assert 'closest("a[data-back]")' in click and 'ok.layers.top() === "panel"' in click


def test_a_delete_from_the_layer_goes_back_to_the_list_and_opens_nothing():
    handler = between(static("shell.js"), "// --- edits in place", "// --- links being read")
    assert 'deleting && phone() && ok.layers && ok.layers.top() === "panel"' in handler
    assert "ok.offerUndo(answer.notice, answer.undo, function () { ok.list.reload(); });" in handler
    assert 'ok.layers.close().then(function () { loadList(here().href, true, "refresh"); });' in handler


def test_an_empty_panel_does_not_stay_open():
    assert 'if (phone() && isOpen() && ok.layers) ok.layers.close();' in between(
        static("shell.js"), "function emptyPanel", "\n  }\n")


def test_the_catalogs_open_the_layer_too():
    js = static("shell.js")
    assert "push && phone() && !isOpen() && openLayer(url)" in between(js, "function showCatalog", "function emptyPanel")
    submit = between(js, 'form.addEventListener("submit"', "// --- more at the end")
    assert 'loadCatalog(field.value.trim().split(/\\s+/).join(" "), undefined, true)' in submit


def test_keys_draw_the_pick_until_a_finger_touches():
    js = static("shell.js")
    assert 'list.classList.add("keyed")' in between(js, "function step", "\n  }\n")
    assert 'document.addEventListener("pointerdown", function () { list.classList.remove("keyed"); }, true);' in js


def test_a_list_reload_under_the_open_layer_keeps_its_note():
    # Task 9 review, fix round 1: an edit in the layer (an Ocio state change
    # under an estado filter) reloads the list; a server pick that differs
    # must not swap the open layer to a note nobody tapped.
    body = between(static("shell.js"), "function loadList", "function sideFilters")
    guard = body.index("} else if (panel && phone() && isOpen()) {")
    assert guard < body.index("loadPanel(serverPick, true)")
    assert "markCurrent(open.dataset.panel)" in body[guard:body.index("loadPanel(serverPick, true)")]


# --- Task 10: selection without hover (spec §9) -----------------------------------------

BUTTON = ('<button type="button" class="btn select-mode js-only" data-select-mode data-on="Cancel" '
          'aria-pressed="false">Select</button>')


@pytest.mark.parametrize("path", ["/", "/lista", "/?vista=lista", "/ocio", "/ocio/lista", "/ideas",
                                  "/ideas/lista"])
def test_every_list_head_offers_seleccionar(client, path):
    head = re.search(r'<div class="list-head">.*?<div class="list-body"', client.get(path).text, re.S).group(0)
    assert BUTTON in head
    # Left of the layout switch or the sort.
    assert head.index(BUTTON) < max(head.find('<nav class="seg"'), head.find('<details class="menu sort"'))


def test_the_checkboxes_wait_for_seleccionar_on_the_phone():
    css = static("app.css")
    assert ".select-mode { display: none; }" in css
    phone = block(css, PHONE)
    assert ".check { display: none; }" in phone
    assert re.search(r"#list\.selecting \.check \{[^}]*display: grid;[^}]*width: 44px; height: 44px;", phone)
    assert "body:has(#list.selecting, #bulk:not([hidden])) .tabbar { display: none; }" in phone
    bar = re.search(r"\n  \.bulk \{[^}]*\}", phone).group(0)
    for part in ("position: fixed;", "left: 8px;", "right: 8px;",
                 "bottom: max(8px, env(safe-area-inset-bottom));", "transform: none;"):
        assert part in bar, part


def test_the_bulk_star_is_named_once(client):
    """Spec §9: on the phone the words hide behind a ★ ::before; the name stays one word."""
    bar = re.search(r'<form id="bulk".*?</form>', client.get("/").text, re.S).group(0)
    assert re.search(r'<button[^>]*class="bulk-star" aria-label="Favorite">', bar)


# --- Task 11: the desktop (Review Focus 5) ------------------------------------------------

def test_outside_its_media_blocks_delivery_4_only_hides():
    """Every rule of the delivery-4 section that a desktop reads: the parts
    the phone adds are hidden, the ↵ hint keeps its button's width, and a
    custom property nobody above 60rem uses. Anything else is a leak."""
    css = static("app.css")
    section = css[css.index("/* --- delivery 4: the phone"):]
    for head in (PHONE, WIDE, "@media (hover: none) {", "@media (pointer: coarse) {"):
        section = section.replace(block(section, head), "")
    section = re.sub(r"/\*.*?\*/", "", section, flags=re.S)
    rules = {" ".join(rule.split()) for rule in section.split("}") if rule.strip()}
    assert rules == {
        ".topbar, .tabbar { display: none;", ".chip-row { display: none;",
        ".detail-back { display: none;", ".btn:has(> .enter-hint) { gap: 0;",
        ".select-mode { display: none;",
        ":root { --tabbar-h: calc(60px + env(safe-area-inset-bottom));"}


def test_a_finger_hides_shortcuts_even_in_the_sidebar():
    """Spec §1, §4: a wide tablet with a finger keeps the sidebar, but not
    "Atajos". `.sidebar .foot-link { display: flex }` outranks a bare
    `[data-modal="keys"]`, so the coarse block names it inside the sidebar."""
    coarse = block(static("app.css"), "@media (pointer: coarse) {")
    assert '.sidebar [data-modal="keys"]' in coarse


def test_ocio_s_head_keeps_its_buttons_on_the_count_s_row():
    """Spec §4: in Ocio the "N fichas sin reescribir" notice takes a row of its
    own *below*, and Seleccionar and "Recientes ▾" stay on the right of
    "Ocio · N". The notice sits inside the count's span, so the span gives its
    parts to the head and the notice is ordered last."""
    phone = block(static("app.css"), PHONE)
    assert ".list-head > span:has(> .unrewritten) { display: contents; }" in phone
    assert re.search(r"\.list-head > span:has\(> \.unrewritten\) > b \{[^}]*margin-right: auto;", phone)
    assert re.search(r"\.list-head \.unrewritten \{[^}]*flex-basis: 100%;[^}]*order: 1;", phone)


# --- Final review fixes ------------------------------------------------------------------

def test_a_tag_in_the_open_layer_shuts_it_before_it_filters():
    """Final review, Important 1: a `data-nav` link inside the phone's layer
    (the detail's #tag) would filter the list hidden under it and write the
    filter onto the layer's entry. The layer goes first, by its back(), and
    the filter then lands on the list's own entry."""
    click = between(static("shell.js"), 'document.addEventListener("click"', "// --- remembered layout")
    guard = 'phone() && isOpen() && panel.contains(link) && link.hasAttribute("data-nav")'
    assert guard in click
    assert "ok.layers.close().then(function () { filter(link); });" in click
    assert click.index(guard) < click.index("filter(link);")
    # The desktop path is the same filter, called at once.
    assert "function filter(link) {" in static("shell.js")
    assert "loadList(target.href);" in between(static("shell.js"), "function filter(link) {", "\n  }\n")


def test_the_detail_s_tag_is_touched_44px_tall():
    """Spec §12: the detail's tag chips get a 44px zone by ::after; the #tag
    link is 15px tall and its ✕ already has one."""
    phone = block(static("app.css"), PHONE)
    assert re.search(r"\.detail \.chips \.chip > a \{[^}]*position: relative;", phone)
    # 15px tall: -15px above and below make it 45 (-14px, as the ✕ has, is 43).
    assert re.search(r'\.detail \.chips \.chip > a::after \{ content: ""; position: absolute; inset: -15px 0; \}', phone)
