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
AUTOSAVE = (STATIC / "autosave.js").read_text(encoding="utf-8") if (STATIC / "autosave.js").exists() else ""
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


def test_autosave_waits_a_second_and_saves_on_blur():
    assert "DELAY = 1000" in AUTOSAVE
    assert '"blur"' in AUTOSAVE and '"input"' in AUTOSAVE


def test_autosave_asks_for_json():
    assert 'Accept: "application/json"' in AUTOSAVE


def test_one_save_in_flight_per_field_and_the_newest_text_after_it():
    """Review Focus 1: a save that is in flight makes the next one wait; when
    it returns, what is in the field now is sent -- never the older value."""
    flush = between(AUTOSAVE, "function flush", "function schedule")
    assert "if (inflight) { again = true; return; }" in flush
    assert "var sending = field.value;" in flush
    # After a save that landed; one that failed ends the round (polish).
    assert "if (!failed) flush();" in flush


def test_a_reply_never_writes_the_field():
    """The older reply must not put the older text back: only settle(),
    which refuses while the field is focused, dirty or saving, writes it."""
    assert AUTOSAVE.count("field.value = ") == 1
    settle = between(AUTOSAVE, "field.oknowledgeSettle", "};")
    assert "field.value = value" in settle
    assert "document.activeElement === field" in settle and "inflight" in settle


def test_an_empty_title_is_not_sent():
    assert 'hasAttribute("data-skip-empty")' in AUTOSAVE


def test_a_failure_keeps_the_text_and_says_so():
    flush = between(AUTOSAVE, "function flush", "function schedule")
    assert "toast(" in flush and "saveFailed" in AUTOSAVE


def test_without_javascript_buttons_are_hidden_by_it():
    assert "[data-nojs]" in AUTOSAVE and ".hidden = true" in AUTOSAVE


def test_idea_polls_every_three_seconds_and_stops():
    assert "POLL = 3000" in IDEA and "/actions/state" in IDEA
    assert "clearInterval(polling)" in IDEA


def test_a_deleted_idea_stops_the_poll_and_goes_back():
    """Review Focus 3."""
    tick = between(IDEA, "function tick", "function gone")
    assert "status === 404" in tick and "stop()" in tick
    assert '"/ideas?notice=no-such-idea"' in IDEA


def test_the_tab_and_the_scope_live_in_the_url():
    assert '"pestana"' in IDEA and '"alcance"' in IDEA and "history.replaceState" in IDEA


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
    assert "if (body.notice) toast(body.notice);" in AUTOSAVE
    assert "if (body.notice && !form.dataset.runs) ok.toast(body.notice);" in IDEA
    assert "texts.saved" not in AUTOSAVE and "dataset.saved" not in IDEA


def test_leaving_the_page_sends_what_is_not_saved_yet():
    """Fix round 1: closing the tab or going back within the second after the
    last key still saves it, with a request that outlives the page, and not
    twice when that text is already on its way."""
    assert '"pagehide"' in AUTOSAVE and '"visibilitychange"' in AUTOSAVE
    # Within keepalive's 64 KB budget only (polish): the node tests in
    # test_web_autosave_settle.py check what goes past it.
    assert "keepalive: keepalive" in AUTOSAVE and "KEEP_MAX" in AUTOSAVE
    leave = between(AUTOSAVE, "function leave", "function schedule")
    assert "value === saved || value === outgoing" in leave
    assert "flush(true)" in leave and "send(field.dataset.autosave, data, true, value)" in leave
    assert 'addEventListener("blur", function () { flush(); })' in AUTOSAVE


def test_only_the_newest_poll_answer_counts():
    """Fix round 1: an answer that left before an action started, or that
    arrives after a newer one, must not say that action ended."""
    tick = between(IDEA, "function tick", "function gone")
    # By number, not age (polish): tests/test_web_idea_js.py runs the races.
    assert "var mine = ++ticks;" in tick and "if (mine <= since || mine <= applied) return;" in tick
    started = between(IDEA, "function started", "function poll")
    assert "since = ++ticks;" in started
