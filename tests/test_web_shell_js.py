"""What shell.js needs from the pages. The script itself is checked by node
(tests/test_packaging.py); these pin the markup it hooks into."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.vault import rebuild_indexes, write_note
from oknowledge.web.app import create_app

SCRIPT = (Path(__file__).resolve().parent.parent / "src" / "oknowledge" / "web" / "static" / "shell.js")


@pytest.fixture
def client(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    write_note(cfg, Note(id="a1", url="https://e.com/a1", title="A", category="Redes",
                         tags=["vpn"], type="article", source="e.com", saved="2026-10-03",
                         summary="s"), "es")
    rebuild_indexes(cfg, "es")
    return TestClient(create_app(cfg))


def test_the_home_loads_the_script(client):
    assert '<script src="/static/shell.js" defer></script>' in client.get("/").text


def test_the_script_is_served(client):
    assert client.get("/static/shell.js").status_code == 200


@pytest.mark.parametrize("hook", ['id="unified"', 'id="field-q"', 'id="save-link"',
                                  'id="list"', 'id="list-body"', 'id="items"', "data-current=",
                                  "data-sel=", "data-view=", "data-nav", 'id="panel"',
                                  "data-panel=", "data-inline", 'class="menu',
                                  "data-save-failed=", "data-done=", "data-failed=",
                                  "data-save-prefixes="])
def test_the_page_has_every_hook(client, hook):
    assert hook in client.get("/?sel=a1").text


@pytest.mark.parametrize("name", ["/lista", "/panel/", "/item/", "/state", "requestSubmit",
                                  "history.replaceState", "IntersectionObserver",
                                  "localStorage", "250", "3000", "savePrefixes"])
def test_the_script_uses_what_the_spec_says(name):
    assert name in SCRIPT.read_text(encoding="utf-8")


def between(text, start, end):
    """The source from `start` up to `end`, so a check is about one function."""
    head = text.index(start)
    return text[head:text.index(end, head)]


def test_a_list_that_lands_after_another_pick_keeps_the_pick():
    """Final review I3. A /lista asked with sel=X that lands after the user
    picked Y must not put X back in the URL or the panel: loadList remembers
    the selection counter it started under and, if it moved, keeps the
    user's sel and skips its follow-up loadPanel. Checked in a browser too
    (final-fix-report.md, I3)."""
    body = between(SCRIPT.read_text(encoding="utf-8"), "function loadList", "function markCurrent")
    assert "= shownAsked" in body
    assert "!== shownAsked" in body or "=== shownAsked" in body


def test_a_save_that_lands_after_another_pick_does_not_reload_the_old_panel():
    """The ★ on X, then a click on Y before Y's panel is back: the save must
    not reload X's panel over the user's pick (a second ★ would then toggle
    X again instead of Y). It asks what the user picked, not whether any
    panel load happened since: two quick saves on X must both reload X."""
    body = between(SCRIPT.read_text(encoding="utf-8"), 'form[data-inline]', "// --- links being read")
    assert "stillPicked(onScreen.dataset.panel)" in body
    assert "shownAsked" not in body


def test_a_finished_analysis_reloads_the_panel_only_if_it_is_still_the_pick():
    """The poller compared against the panel on screen, which is still X while
    Y's panel is on its way; it has to ask what the user picked."""
    body = between(SCRIPT.read_text(encoding="utf-8"), "function watch", "observe();\n  watch();")
    assert "stillPicked(id)" in body


def test_with_no_list_on_screen_the_panel_is_still_the_pick():
    """A search that matches nothing renders no #items; the panel on screen is
    then the pick, so a finished analysis still reloads it."""
    body = between(SCRIPT.read_text(encoding="utf-8"), "function stillPicked", "\n  }")
    assert "!items" in body
    assert "dataset.current === id" in body


def test_the_script_serves_any_list_column():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "list.dataset.source" in text
    assert 'form.dataset.mode' in text
    assert '"estado", "tipo", "orden"' in text


def test_in_ideas_enter_never_saves():
    body = between(SCRIPT.read_text(encoding="utf-8"), "function saves", "// --- the list column")
    assert 'mode === "ideas"' in body


def test_inline_writes_ask_for_json_and_say_what_came_back():
    body = between(SCRIPT.read_text(encoding="utf-8"), 'form[data-inline]', "// --- links being read")
    assert 'Accept: "application/json"' in body
    assert "answer.notice" in body and "answer.error" in body


def test_a_panel_that_lands_binds_its_autosave():
    body = between(SCRIPT.read_text(encoding="utf-8"), "function loadPanel", "function emptyPanel")
    assert "window.oknowledge" in body and ".bind(panel)" in body


def test_ocio_searches_the_catalogs_in_the_panel():
    text = SCRIPT.read_text(encoding="utf-8")
    body = between(text, "function loadCatalog", "function emptyPanel")
    assert '"/ocio/candidatos?"' in body and '"buscar"' in body
    assert "data-kind" in text and "catalog-search" in text


def test_the_catalog_search_keeps_the_grid_apart():
    """Task 10's contract: the page's `tipo` is the grid, `catalogo` the
    catalog's kind; the fragment takes the kind as `tipo` and the grid as
    `grid`, and the page's `tipo` is never overwritten."""
    body = between(SCRIPT.read_text(encoding="utf-8"), "function loadCatalog", "function emptyPanel")
    assert 'set("catalogo"' in body
    assert 'ask.set("grid"' in body
    assert 'url.searchParams.set("tipo"' not in body


def test_a_rewrite_says_its_own_words_when_it_ends():
    body = between(SCRIPT.read_text(encoding="utf-8"), "function watch", "observe();\n  watch();\n})")
    assert "doneAs" in body and "failedAs" in body
    assert "panel.querySelectorAll" in body


def test_a_panel_waits_for_its_note_before_it_is_swapped():
    """Fix round 1: the panel is fetched only after the note's saves have
    landed; a failed one keeps the panel (and the text) where it is, and a
    box typed in while the panel was on its way asks for it again."""
    body = between(SCRIPT.read_text(encoding="utf-8"), "function settled", "function loadCatalog")
    assert "settle(panel)" in body
    head = body.index("settle(panel)")
    assert body.index('fetch("/panel/"') > head
    assert "if (failed)" in body and "mine !== shownAsked" in body[head:]
    assert "dirty(panel)" in body


def test_picking_a_card_ends_a_catalog_search():
    body = between(SCRIPT.read_text(encoding="utf-8"), "function loadPanel", "function loadCatalog")
    assert '["buscar", "catalogo", "year"]' in body and "searchParams.delete(name)" in body


def test_a_list_reload_leaves_an_open_catalog_search_alone():
    body = between(SCRIPT.read_text(encoding="utf-8"), "function loadList", "function markCurrent")
    assert '!target.searchParams.get("buscar")' in body


def test_enter_cancels_the_live_filter_before_searching_the_catalogs():
    text = SCRIPT.read_text(encoding="utf-8")
    body = between(text, 'form.addEventListener("submit"', "// --- more at the end")
    assert body.index("clearTimeout(timer)") < body.index("loadCatalog(")


def test_only_the_start_of_a_run_is_kept_quiet():
    body = between(SCRIPT.read_text(encoding="utf-8"), 'form[data-inline]', "// --- links being read")
    assert "answer.runs" in body and "dataset.runs" not in body


def test_a_list_that_brings_its_sidebar_groups_swaps_them_in():
    """Final review I-1: Ocio's TIPO and ESTADO are redrawn by the server with
    the list, inside the list's own sequence guard, and only when the answer
    brings them (the library and the ideas do not)."""
    text = SCRIPT.read_text(encoding="utf-8")
    body = between(text, "function loadList", "function markCurrent")
    assert body.index("if (mine !== asked) return;") < body.index("sideFilters()")
    swap = between(text, "function sideFilters", "\n  }\n")
    assert 'list.querySelector("template#side-filters")' in swap
    assert "if (!fresh) return;" in swap
    assert 'querySelectorAll("nav.group")' in swap and "fresh.content" in swap


def test_a_filter_click_lights_its_row_only_in_its_own_group():
    """Ocio's groups are apart (data-apart): a TIPO click leaves ESTADO lit.
    The library's groups are one choice, so a click there clears them all."""
    body = between(SCRIPT.read_text(encoding="utf-8"), "function setActive", "\n  }\n")
    assert 'link.closest(".sidebar .group[data-apart]")' in body
    assert '".sidebar .filter.on"' in body
