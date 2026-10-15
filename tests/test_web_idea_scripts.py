"""What autosave.js and idea.js promise (spec §1 autosave, §2.2 polling).
node --check runs them in tests/test_packaging.py; the behaviour is checked
in a browser in this task's last step. These pin the parts a reviewer would
otherwise have to trust."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.vault import note_path, rebuild_indexes, write_note
from oknowledge.web.app import create_app

STATIC = Path(__file__).resolve().parent.parent / "src" / "oknowledge" / "web" / "static"
IDEA = (STATIC / "idea.js").read_text(encoding="utf-8") if (STATIC / "idea.js").exists() else ""


def between(text, start, end):
    head = text.index(start)
    return text[head:text.index(end, head)]


@pytest.fixture
def client(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    rebuild_indexes(cfg, "es")
    note = new_idea("Una vpn.", "VPN", "2026-10-13", "2026-10-13T00:00:00.000001+00:00")
    write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ideas))
    client = TestClient(create_app(cfg))
    client.idea = note.id
    return client


def test_the_screen_loads_autosave_before_idea(client):
    body = client.get(f"/ideas/{client.idea}").text
    first = body.index('<script src="/static/autosave.js" defer></script>')
    assert first < body.index('<script src="/static/idea.js" defer></script>')


@pytest.mark.parametrize("name", ["autosave.js", "idea.js"])
def test_the_scripts_are_served(client, name):
    assert client.get(f"/static/{name}").status_code == 200


def test_the_links_search_is_live_and_keeps_only_the_newest_answer():
    assert "250" in IDEA
    body = between(IDEA, "function search", "function started")
    assert "searchAsked" in body and "!== searchAsked" in body


def test_the_parts_come_from_the_server():
    assert "new DOMParser()" in IDEA and "fetch(location.href" in IDEA


def test_a_landed_save_toasts_only_what_the_server_warns():
    """Fix round 1: the server leaves the plain "Saved." out of the JSON; the
    scripts toast the notice it does send (indexes-stale) and nothing of
    their own -- the indicator is what says a save landed."""
    # autosave.js's half is run in node (test_web_autosave_settle.py, batch G).
    assert "if (body.notice && !form.dataset.runs) ok.toast(body.notice);" in IDEA
    assert "dataset.saved" not in IDEA


# autosave.js's timing, one save at a time, empty titles, the leave, and idea.js's
# poll, its 404 and its URL are run in node: tests/test_web_autosave_settle.py and
# tests/test_web_idea_js.py (batch G).
