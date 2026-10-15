"""docs/2026-10-14-rediseno-biblioteca-pendientes.md, the part spec §4 takes."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.urls import link_id
from oknowledge.vault import rebuild_indexes, write_note
from oknowledge.web import index
from oknowledge.web.app import create_app

STATIC = Path(__file__).resolve().parent.parent / "src" / "oknowledge" / "web" / "static"


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
