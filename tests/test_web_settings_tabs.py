"""Settings as four panes (spec §3.1, §7, §8): one fragment for the page and
the modal, each pane its own form, Categories folded in, and the sidebar's
new foot."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.vault import rebuild_indexes, write_note
from oknowledge.web import app as module
from oknowledge.web.app import create_app

WEB = Path(__file__).resolve().parent.parent / "src" / "oknowledge" / "web"
TABS = ["motores", "idioma", "importar", "categorias"]


@pytest.fixture
def client(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    for id, category in (("a1", "Redes"), ("b2", "Cocina")):
        write_note(cfg, Note(id=id, url=f"https://e.com/{id}", title=id, category=category,
                             tags=[], type="article", source="e.com", saved="2026-10-03",
                             summary="s"), "es")
    rebuild_indexes(cfg, "es")
    return TestClient(create_app(cfg))


def shown(body):
    """{pane: visible} for every pane in the page."""
    return {m.group(1): m.group(2) is None
            for m in re.finditer(r'data-settings-pane="([a-z]+)"( hidden)?', body)}


def sidebar(body):
    return re.search(r'<aside class="sidebar".*?</aside>', body, re.S).group(0)


# --- the fragment ------------------------------------------------------------------

def test_the_panel_is_a_fragment_with_four_tabs(client):
    body = client.get("/settings/panel").text
    assert "<html" not in body and '<aside class="sidebar"' not in body
    assert re.findall(r'data-settings-tab="([a-z]+)"', body) == TABS
    assert shown(body) == {"motores": True, "idioma": False, "importar": False,
                           "categorias": False}


@pytest.mark.parametrize("tab", TABS)
def test_the_tab_asked_for_is_the_one_shown(client, tab):
    for path in (f"/settings/panel?tab={tab}", f"/settings?tab={tab}"):
        body = client.get(path).text
        assert [name for name, visible in shown(body).items() if visible] == [tab], path
        assert f'data-settings-tab="{tab}" class="on" aria-current="page"' in body, path


def test_a_tab_nobody_knows_is_engines(client):
    assert shown(client.get("/settings/panel?tab=nope").text)["motores"] is True


def test_the_page_is_the_same_fragment_with_the_sidebar(client):
    body = client.get("/settings?tab=categorias").text
    assert '<aside class="sidebar"' in body and 'data-settings-root' in body


def test_opening_the_panel_asks_no_engine_anything(client, monkeypatch):
    monkeypatch.setattr(module, "build_engine",
                        lambda *a, **k: pytest.fail("Settings asked an engine"))
    assert client.get("/settings/panel").status_code == 200


# --- each pane its own form ------------------------------------------------------------

def test_each_pane_saves_on_its_own_with_a_save_button_without_js(client):
    body = client.get("/settings/panel").text
    forms = re.findall(r'<form action="/settings" method="post" data-settings[^>]*>.*?</form>',
                       body, re.S)
    assert len(forms) == 2
    assert 'name="tab" value="motores"' in forms[0] and 'name="chain"' in forms[0]
    assert 'name="tab" value="idioma"' in forms[1] and 'name="ui_language"' in forms[1]
    for form in forms:
        assert "data-nojs" in form


def test_the_action_buttons_post_their_own_forms(client):
    body = client.get("/settings/panel").text
    assert '<form id="find-opencode" action="/settings/models/opencode" method="post" data-settings-action>' in body


def test_language_and_saving_offers_the_handoff_rows(client):
    body = client.get("/settings/panel?tab=idioma").text
    for name in ("language", "ui_language", "default_content", "mentions"):
        assert f'type="radio" name="{name}"' in body, name
    assert 'type="number" name="batch"' in body
    for value in ("tools", "all", "discussed"):
        assert f'name="mentions" value="{value}"' in body


def test_import_offers_the_drop_and_the_batch(client):
    body = client.get("/settings/panel?tab=importar").text
    drop = re.search(r'<form action="/import"[^>]*>.*?</form>', body, re.S).group(0)
    assert 'enctype="multipart/form-data"' in drop and "data-settings-drop" in drop
    assert 'type="file" name="file"' in drop
    assert "Links waiting for analysis: 0" in body
    assert "Every link has been analysed." in body
    assert 'href="/retry"' in body


def test_a_running_batch_shows_its_count_instead_of_the_button(client):
    client.app.state.batch.start(3)
    body = client.get("/settings/panel?tab=importar").text
    assert "Analysing: 0/3" in body and 'action="/retry"' not in body


def test_categories_are_renamed_from_settings(client):
    body = client.get("/settings/panel?tab=categorias").text
    rows = re.findall(r'<form action="/categories/rename" method="post" class="cat-row" data-settings-rename>.*?</form>',
                      body, re.S)
    assert len(rows) == 2
    assert any('name="old" value="Redes"' in row and 'name="new" value="Redes"' in row
               for row in rows)
    assert 'data-merge="Merge «%1» into «%2»?"' in body


def test_the_categories_page_moved_into_settings(client):
    answer = client.get("/categories", follow_redirects=False)
    assert answer.status_code == 303
    assert answer.headers["location"] == "/settings?tab=categorias"
    assert not (WEB / "templates" / "categories.html").exists()


# --- the sidebar -------------------------------------------------------------------------

def test_the_foot_has_shortcuts_and_settings_only(client):
    side = sidebar(client.get("/").text)
    assert '<button type="button" class="foot-link js-only" data-modal="keys">' in side
    assert '<a href="/settings" class="foot-link" data-modal="settings">' in side
    assert 'href="/categories"' not in side and 'href="/retry"' not in side


def test_the_sections_show_their_keys(client):
    side = sidebar(client.get("/").text)
    for n in ("1", "2", "3"):
        assert f'<kbd class="key mono js-only">{n}</kbd>' in side


def test_settings_carries_the_batch_counter(client):
    client.app.state.batch.start(3)
    side = sidebar(client.get("/").text)
    assert re.search(r'data-modal="settings">Settings <b class="mono">0/3</b></a>', side)


def test_what_needs_javascript_is_hidden_without_it():
    css = (WEB / "static" / "app.css").read_text(encoding="utf-8")
    assert "html:not(.js) .js-only { display: none !important; }" in css
    assert 'classList.add("js")' in (WEB / "static" / "layout.js").read_text(encoding="utf-8")


def test_every_page_loads_the_settings_script(client):
    for path in ("/", "/ocio", "/ideas", "/settings", "/retry"):
        assert '<script src="/static/settings.js" defer></script>' in client.get(path).text, path
