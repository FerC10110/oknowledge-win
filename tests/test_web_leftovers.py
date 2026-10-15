"""docs/2026-10-14-rediseno-biblioteca-pendientes.md, the part spec §4 takes."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.model import Note
from oknowledge.urls import link_id
from oknowledge.vault import note_path, rebuild_indexes, write_note
from oknowledge.web import index
from oknowledge.web.app import create_app

STATIC = Path(__file__).resolve().parent.parent / "src" / "oknowledge" / "web" / "static"
SHELL = STATIC / "shell.js"
IDEA = STATIC / "idea.js"


@pytest.fixture
def cfg(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    config = Config(vault=vault)
    write_note(config, Note(id=link_id("https://e.com/x"), url="https://e.com/x", title="Uno",
                            category="Redes", tags=["x"], type="article", source="e.com",
                            saved="2026-10-10", summary="s", mark="⭐"), "es")
    rebuild_indexes(config, "es")
    return config


def test_the_chip_rules_stay_in_the_redesigned_screens():
    css = (STATIC / "app.css").read_text(encoding="utf-8")
    for name in (".chip", ".chips", ".warn"):
        bare = re.findall(rf"^{re.escape(name)}[ ,:{{]", css, re.M)
        assert bare == [], f"{name} is still global in app.css"
    assert ":where(.app:not(.legacy)) .chip {" in css


def test_pasting_a_link_you_have_opens_it(cfg):
    answer = TestClient(create_app(cfg)).post("/add", data={"q": "https://e.com/x"},
                                              follow_redirects=False)
    assert answer.headers["location"] == f"/?sel={link_id('https://e.com/x')}&notice=already-saved"


def test_the_notice_leaves_the_url_once_said():
    script = (STATIC / "layout.js").read_text(encoding="utf-8")
    assert "history.replaceState" in script
    for name in ('"notice"', '"n"', '"m"'):
        assert name in script


def test_the_pick_is_written_when_the_url_has_none():
    script = (STATIC / "shell.js").read_text(encoding="utf-8")
    assert "dataset.current" in script and 'searchParams.get("sel")' in script
    assert "// --- the pick in the URL" in script


def test_the_favorite_star_on_a_card_is_said(cfg):
    body = TestClient(create_app(cfg)).get("/").text
    flag = re.search(r'<span class="flag fav"[^>]*>', body).group(0)
    assert 'role="img"' in flag and 'aria-label="Favorite"' in flag


def test_the_dead_helpers_are_gone():
    for name in ("tally", "tag_home", "years", "months"):
        assert not hasattr(index.Library, name) and not hasattr(index, name)


def test_no_page_ranks_marks_any_more():
    source = (Path(__file__).resolve().parent.parent / "src" / "oknowledge" / "web"
              / "app.py").read_text(encoding="utf-8")
    assert "used_marks" not in source and "rank_marks" not in source


def test_the_pick_is_not_written_beside_the_catalog_panel():
    """/ocio?buscar=X shows the catalog's panel while #items still holds the
    first card: writing sel there would pair a card with a search."""
    script = (STATIC / "shell.js").read_text(encoding="utf-8")
    block = script.split("// --- the pick in the URL", 1)[1]
    assert 'searchParams.get("buscar")' in block
    assert '[data-panel=""]' in block


def test_the_chip_text_needs_no_reset_in_the_card_panel():
    css = (STATIC / "app.css").read_text(encoding="utf-8")
    assert ".detail-scroll.card .tags span" not in css
    assert ".tags span" not in (STATIC / "style.css").read_text(encoding="utf-8")


# --- Spec §9: what deliveries 1 and 2 left open in shell.js and idea.js. Each
# is a guard on a race a browser check cannot time, so the guard is pinned.


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
    assert body.index('if (!link.closest(".sidebar, .chip-row")) return;') < body.index("querySelectorAll")


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
