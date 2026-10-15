"""Settings as a modal (spec §3.1): an empty dialog on every page that
settings.js fills from /settings/panel, saves as it changes, and that says so
when the server cannot be reached (Review Focus 5)."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.vault import rebuild_indexes, write_note
from oknowledge.web.app import create_app

SETTINGS = (Path(__file__).resolve().parent.parent / "src" / "oknowledge" / "web" / "static"
            / "settings.js")


@pytest.fixture(autouse=True)
def state_tree(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr("oknowledge.web.app.CONFIG_PATH", tmp_path / "config" / "config.toml")


@pytest.fixture
def client(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    write_note(cfg, Note(id="a1", url="https://e.com/a1", title="A", category="Redes", tags=[],
                         type="article", source="e.com", saved="2026-10-03", summary="s"), "es")
    rebuild_indexes(cfg, "es")
    return TestClient(create_app(cfg))


def between(text, start, end):
    head = text.index(start)
    return text[head:text.index(end, head)]


@pytest.mark.parametrize("path", ["/", "/ocio", "/ideas", "/retry", "/settings"])
def test_every_page_has_the_empty_settings_dialog(client, path):
    found = re.search(r'<dialog id="settings-modal" class="modal settings"[^>]*></dialog>',
                      client.get(path).text)
    assert found
    assert ('data-failed="The settings could not be loaded. Check that oknowledge is still running."'
            in found.group(0))


def test_the_modal_says_when_the_settings_cannot_be_loaded():
    text = SETTINGS.read_text(encoding="utf-8")
    opening = between(text, "ok.openSettings = function", "ok.bindSettings = ")
    assert '"/settings/panel' in opening and ".catch(" in opening
    failing = between(text, "function failed", "ok.openSettings = function")
    assert "modal.dataset.failed" in failing
    assert 'setAttribute("data-close", "")' in failing and "texts.close" in failing


def test_each_pane_saves_itself_one_request_at_a_time():
    text = SETTINGS.read_text(encoding="utf-8")
    saving = between(text, "function autosave", "function syncKeep")
    assert '"change"' in saving and '"submit"' in saving
    assert "busy" in saving and "again" in saving
    assert "body.reload" in saving and "location.reload()" in saving


def test_a_rename_into_another_category_asks_first():
    text = SETTINGS.read_text(encoding="utf-8")
    renaming = between(text, "function renames", "function drops")
    assert "confirm(" in renaming and "dataset.merge" in renaming
    assert "renamed = true" in renaming


def test_the_model_picker_saves_once():
    picking = between(SETTINGS.read_text(encoding="utf-8"), "function pickers", "function autosave")
    assert "stopPropagation" in picking and "requestSubmit" in picking


def test_settings_js_hides_the_save_buttons_and_never_writes_the_page_storage():
    text = SETTINGS.read_text(encoding="utf-8")
    assert "[data-nojs]" in text
    assert "localStorage" not in text


def test_the_fragment_and_the_page_carry_the_same_hooks(client):
    fragment = client.get("/settings/panel").text
    page = client.get("/settings").text
    for hook in ("data-settings-root", 'data-settings-tab="idioma"', "data-settings-rename",
                 "data-settings-drop", "data-settings-action"):
        assert hook in fragment and hook in page, hook
