"""The keys of the lists (spec §4) and the panel's delete with Deshacer
(spec §6.4): the hooks the server draws for them, and shell.js's rules."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.model import Note
from oknowledge.vault import note_path, rebuild_indexes, write_note
from oknowledge.web.app import create_app

SHELL = (Path(__file__).resolve().parent.parent / "src" / "oknowledge" / "web" / "static"
         / "shell.js")
CARD = "c00000000001"


@pytest.fixture
def client(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    write_note(cfg, Note(id="a1", url="https://www.e.com/a1", title="A", category="Redes",
                         tags=[], type="article", source="e.com", saved="2026-10-03",
                         summary="s"), "es")
    card = Note(id=CARD, url="https://www.imdb.com/title/tt1", title="Dune", category="Películas",
                tags=[], type="movie", source="imdb.com", saved="2026-10-02", summary="s",
                engine="")
    write_note(cfg, card, "es", path=note_path(cfg, card, shelf=cfg.ocio))
    idea = new_idea("Una idea.", "Idea", "2026-10-13", "2026-10-13T00:00:00.000001+00:00")
    write_note(cfg, idea, "es", path=note_path(cfg, idea, shelf=cfg.ideas))
    for shelf in (cfg.links, cfg.ocio, cfg.ideas):
        rebuild_indexes(cfg, "es", shelf=shelf)
    return TestClient(create_app(cfg))


def between(text, start, end):
    head = text.index(start)
    return text[head:text.index(end, head)]


# --- the hooks ----------------------------------------------------------------------

def test_the_panels_delete_is_inline_and_asks_nothing(client):
    panel = client.get("/panel/a1").text
    form = re.search(r'<form method="post" action="/item/a1/delete"[^>]*>', panel).group(0)
    assert "data-inline" in form and "data-ask" not in form


def test_the_original_link_is_marked_for_enter(client):
    assert re.search(r'<a class="btn primary" href="https://www.e.com/a1"[^>]*data-open',
                     client.get("/panel/a1").text)
    assert re.search(r'<a class="btn primary" href="https://www.imdb.com/title/tt1"[^>]*data-open',
                     client.get(f"/panel/{CARD}").text)


def test_the_tag_box_answers_to_e_and_never_posts_empty(client):
    for path in ("/panel/a1", f"/panel/{CARD}"):
        form = re.search(r'<form method="post" action="/item/[^"]+/tags" data-inline class="tag-new">.*?</form>',
                         client.get(path).text, re.S).group(0)
        box = re.search(r'<input name="add"[^>]*>', form).group(0)
        assert 'id="tag-add"' in box and "required" in box, path


def test_the_ideas_list_keeps_a_cursor(client):
    assert '<ul class="items tiles" id="items" data-current="">' in client.get("/ideas").text


def test_the_body_carries_the_opening_words(client):
    assert 'data-opening="Opening %1…"' in client.get("/").text


# --- shell.js -------------------------------------------------------------------------

def test_moving_keeps_the_pick_in_view():
    assert 'scrollIntoView({ block: "nearest" })' in SHELL.read_text(encoding="utf-8")


def test_the_list_tells_why_it_changed():
    text = SHELL.read_text(encoding="utf-8")
    assert '"oknowledge:list"' in text and "bubbles: true" in text
    for reason in ('"filter"', '"refresh"', '"more"'):
        assert reason in text, reason


def test_a_delete_from_the_panel_picks_the_next_and_offers_undo():
    text = SHELL.read_text(encoding="utf-8")
    handler = between(text, "// --- edits in place", "// --- links being read")
    assert "neighbour(" in handler and "offerUndo(answer.notice, answer.undo)" in handler
    assert "emptyPanel()" in handler


def test_the_list_is_offered_to_the_other_scripts():
    text = SHELL.read_text(encoding="utf-8")
    assert re.search(r"ok\.list = \{", text)
    for name in ("current:", "pick:", "next:", "reload:", "shown:"):
        assert name in between(text, "ok.list = {", "};"), name


# j, k, the arrows by a row, and f, e and Enter waiting for the panel are run in
# node: tests/test_web_layer_history.py (batch G).
