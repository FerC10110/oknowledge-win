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
    failing = between(text, "function unreachable", "ok.openSettings = function")
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
    assert "body.moved" in renaming


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


# Fix round 1 of the review.

def test_closing_the_modal_while_a_rename_is_out_reloads_once_it_lands():
    text = SETTINGS.read_text(encoding="utf-8")
    renaming = between(text, "function renames", "function drops")
    assert "renamesOut.push(" in renaming
    closing = between(text, 'modal.addEventListener("close"', "});")
    assert "renamesOut" in closing and "location.reload()" in closing


def test_a_redraw_waits_for_the_saves_still_out():
    text = SETTINGS.read_text(encoding="utf-8")
    assert "whenIdle()" in between(text, "function redraw", "function bind")
    saving = between(text, "function autosave", "function syncKeep")
    assert "hold()" in saving and "release()" in saving


def test_a_rename_that_landed_can_be_sent_again():
    renaming = between(SETTINGS.read_text(encoding="utf-8"), "function renames", "function drops")
    landed = between(renaming, ".then(function (body)", ".catch(")
    assert "sending = false" in landed


def test_an_action_button_waits_for_its_answer():
    acting = between(SETTINGS.read_text(encoding="utf-8"), "function actions", "function renames")
    assert "disabled = true" in acting and "disabled = false" in acting


def test_a_pane_does_not_send_the_same_thing_twice_in_a_row():
    saving = between(SETTINGS.read_text(encoding="utf-8"), "function autosave", "function syncKeep")
    assert "lastSent" in saving
