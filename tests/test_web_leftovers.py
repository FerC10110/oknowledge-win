"""Spec §9: what deliveries 1 and 2 left open in shell.js and idea.js. Each
is a guard on a race that a browser check cannot time reliably, so the
guard itself is what is pinned."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.vault import note_path, rebuild_indexes, write_note
from oknowledge.web.app import create_app

STATIC = Path(__file__).resolve().parent.parent / "src" / "oknowledge" / "web" / "static"
SHELL = STATIC / "shell.js"
IDEA = STATIC / "idea.js"


def between(text, start, end):
    head = text.index(start)
    return text[head:text.index(end, head)]


def test_a_failed_list_navigates_only_if_it_was_the_last_asked():
    body = between(SHELL.read_text(encoding="utf-8"), "function loadList", "function sideFilters")
    assert ".catch(function () { if (mine === asked) location.href = target.href; });" in body


def test_more_from_a_list_that_changed_since_is_dropped():
    body = between(SHELL.read_text(encoding="utf-8"), "function more", "// --- menus")
    assert "var mine = asked;" in body and "if (mine !== asked) return;" in body


def test_the_poller_stops_for_an_id_no_longer_on_screen():
    body = between(SHELL.read_text(encoding="utf-8"), "watched[id] = setInterval", 'fetch("/item/"')
    assert "onScreen(id)" in body and "clearInterval(watched[id])" in body


def test_a_filter_click_cancels_the_pending_search():
    text = SHELL.read_text(encoding="utf-8")
    assert re.search(r"clearTimeout\(timer\);[^\n]*\n\s*setActive\(link\);", text)


def test_a_link_outside_the_sidebar_leaves_its_highlight_alone():
    body = between(SHELL.read_text(encoding="utf-8"), "function setActive", "\n  }\n")
    assert body.index('if (!link.closest(".sidebar")) return;') < body.index("querySelectorAll")


def test_the_idea_tag_box_gets_the_focus_back():
    text = IDEA.read_text(encoding="utf-8")
    assert 'refresh(["idea-controls", "idea-tags"]).then(' in text
    assert 'getElementById("tag-add")' in text


@pytest.fixture
def client(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    idea = new_idea("Una idea.", "Idea", "2026-10-13", "2026-10-13T00:00:00.000001+00:00")
    write_note(cfg, idea, "es", path=note_path(cfg, idea, shelf=cfg.ideas))
    rebuild_indexes(cfg, "es", shelf=cfg.ideas)
    client = TestClient(create_app(cfg))
    client.idea = idea.id
    return client


def test_the_idea_tag_box_has_its_id(client):
    body = client.get(f"/ideas/{client.idea}").text
    assert re.search(r'<input name="add" id="tag-add" required', body)
