"""Settings, polished (docs/2026-10-15-rediseno-modales-teclado-pendientes.md,
"Ajustes"): the engine boxes drawn like the rest of the app's, the file field
visible without JavaScript, Categories' autocomplete and links, and the
interface language's hint on one line. What settings.js does is in
test_web_settings_script.py."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.vault import rebuild_indexes, write_note
from oknowledge.web.app import create_app

WEB = Path(__file__).resolve().parent.parent / "src" / "oknowledge" / "web"
CSS = re.sub(r"/\*.*?\*/", "", (WEB / "static" / "app.css").read_text(encoding="utf-8"), flags=re.S)


@pytest.fixture(autouse=True)
def state_tree(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr("oknowledge.web.app.CONFIG_PATH", tmp_path / "config" / "config.toml")


@pytest.fixture
def client(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    for id, category in (("a1", "Redes"), ("b2", "Cocina"), ("c3", "Cocina")):
        write_note(cfg, Note(id=id, url=f"https://e.com/{id}", title=id, category=category,
                             tags=[], type="article", source="e.com", saved="2026-10-03",
                             summary="s"), "es")
    rebuild_indexes(cfg, "es")
    return TestClient(create_app(cfg))


def rule(selector_part):
    """Every rule of app.css whose selector holds `selector_part`, as text."""
    return [m.group(0) for m in re.finditer(r"[^{}]*\{[^{}]*\}", CSS)
            if selector_part in m.group(0).split("{")[0]]


# --- 1. the engine boxes are the app's checkbox -----------------------------------------

def test_the_engine_boxes_share_the_apps_checkbox():
    drawn = rule(".engine-row input[type=checkbox]")
    assert any("appearance: none" in r and "border-radius: 5px" in r for r in drawn), drawn
    assert any(":checked" in r.split("{")[0] and "background: #e7e7ea" in r for r in drawn), drawn
    assert any(":focus-visible" in r.split("{")[0] for r in drawn), drawn


# --- 2. the file field without JavaScript ------------------------------------------------

def test_the_file_field_shrinks_only_with_javascript():
    shrunk = [r for r in rule(".drop-file") if "width: 1px" in r]
    assert shrunk and all(r.split("{")[0].strip().startswith(".js ") for r in shrunk), shrunk


def test_without_javascript_the_file_field_says_its_own_choice(client):
    body = client.get("/settings/panel?tab=importar").text
    label = re.search(r'<label class="btn drop-choose">(.*?)</label>', body, re.S).group(1)
    assert '<span class="js-only">Choose file</span>' in label
    assert 'type="file" name="file"' in label
    assert rule("html:not(.js) .drop-choose")


# --- 3. Categories: autocomplete on merge, and each one's link -------------------------

def test_each_category_box_offers_the_others(client):
    body = client.get("/settings/panel?tab=categorias").text
    boxes = re.findall(r'<input name="new"[^>]*>', body)
    assert len(boxes) == 2 and all('list="settings-categories"' in box for box in boxes)
    listed = re.search(r'<datalist id="settings-categories">(.*?)</datalist>', body, re.S).group(1)
    assert re.findall(r'<option value="([^"]+)">', listed) == ["Cocina", "Redes"]


def test_each_category_links_to_its_list(client):
    body = client.get("/settings/panel?tab=categorias").text
    assert re.search(r'<a class="count mono" href="/\?category=Cocina"[^>]*>2</a>', body)
    assert re.search(r'<a class="count mono" href="/\?category=Redes"[^>]*>1</a>', body)


# --- 10. the interface language's hint is one line ------------------------------------------

def test_the_interface_language_has_one_hint(client):
    body = client.get("/settings/panel?tab=idioma").text
    row = re.search(r'<p class="setting-name">Interface language</p>(.*?)</div>', body, re.S).group(1)
    hints = re.findall(r'<p class="setting-hint">(.*?)</p>', row)
    assert hints == ["Changing it reloads the page"]


def test_the_interface_language_hint_is_in_spanish(client, tmp_path):
    # The fork keeps the interface language in its own config.
    spanish = TestClient(create_app(Config(vault=tmp_path / "vault", ui_language="es")))
    body = spanish.get("/settings/panel?tab=idioma").text
    assert "Cambiarlo recarga la página" in body


# --- 9. the dialog itself, focused, draws no ring ------------------------------------------

def test_the_settings_dialog_draws_no_ring_when_it_has_the_focus():
    assert any("outline: none" in r for r in rule(".modal.settings:focus"))


# --- review M2/M3: the count waits for saves, and is a real target on the phone ----------

def test_each_categorys_link_is_marked_to_wait_for_the_saves(client):
    body = client.get("/settings/panel?tab=categorias").text
    links = re.findall(r'<a class="count mono" href="/\?category=[^"]+"[^>]*>', body)
    assert links and all("data-leave" in link for link in links)


def test_on_the_phone_the_count_is_a_marked_44px_target_beside_the_box():
    phone = CSS[CSS.index("@media (max-width: 60rem)"):]
    drawn = [r for r in re.findall(r"[^{}]*\{[^{}]*\}", phone) if ".cat-row" in r.split("{")[0]]
    count = " ".join(r for r in drawn if "a.count" in r.split("{")[0])
    assert "min-width: 44px" in count and "min-height: 44px" in count
    assert "text-decoration: underline" in count and "var(--acc)" in count
    box = " ".join(r for r in drawn if r.split("{")[0].strip().endswith(".cat-row input"))
    assert "grid-column: 1 / -1" not in box
