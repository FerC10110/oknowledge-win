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
                                  "localStorage", "250", "3000", "Escape", "savePrefixes"])
def test_the_script_uses_what_the_spec_says(name):
    assert name in SCRIPT.read_text(encoding="utf-8")
