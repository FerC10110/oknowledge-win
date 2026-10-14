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
    assert "stillPicked(shown.dataset.panel)" in body
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
