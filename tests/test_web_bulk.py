"""Bulk actions (spec §5.1): each id goes through its own route's rule and
lock, a refused value writes nothing, the indexes are rebuilt once per shelf,
and an id that is gone (or on another shelf, or busy) is counted, not fatal."""

import re
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.model import Note
from oknowledge.queue import Queue
from oknowledge.vault import find_note, index_path, note_path, rebuild_indexes, trash_dir, write_note
from oknowledge.web.app import create_app

JSON = {"Accept": "application/json"}
CARD1, CARD2 = "c00000000001", "c00000000002"


def link(id, title, category):
    return Note(id=id, url=f"https://e.com/{id}", title=title, category=category, tags=[],
                type="article", source="e.com", saved="2026-10-03", summary="s")


@pytest.fixture
def s(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    for id, title, category in (("a1", "WireGuard", "Redes"), ("b2", "Masa madre", "Cocina"),
                                ("c3", "SSH", "Redes")):
        write_note(cfg, link(id, title, category), "es")
    for id, kind, category in ((CARD1, "movie", "Películas"), (CARD2, "book", "Libros")):
        card = Note(id=id, url=f"https://www.imdb.com/title/{id}", title=f"Ficha {id}",
                    category=category, tags=[], type=kind, source="imdb.com",
                    saved="2026-10-01", summary="s", engine="")
        write_note(cfg, card, "es", path=note_path(cfg, card, shelf=cfg.ocio))
    ideas = []
    for n in (1, 2):
        idea = new_idea(f"Idea {n}.", f"Idea {n}", "2026-10-13",
                        f"2026-10-13T00:00:00.00000{n}+00:00")
        write_note(cfg, idea, "es", path=note_path(cfg, idea, shelf=cfg.ideas))
        ideas.append(idea.id)
    for shelf in (cfg.links, cfg.ocio, cfg.ideas):
        rebuild_indexes(cfg, "es", shelf=shelf)
    return SimpleNamespace(cfg=cfg, client=TestClient(create_app(cfg)), ideas=ideas,
                           vault=vault)


def post(s, action, **data):
    return s.client.post(f"/bulk/{action}", data=data, headers=JSON)


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


# --- move ------------------------------------------------------------------------

def test_a_bulk_move_moves_each_and_says_where(s):
    answer = post(s, "category", ids=["a1", "b2", "c3"], category="Seguridad")
    assert answer.json() == {"ok": True, "notice": "3 moved to Seguridad",
                             "done": ["a1", "b2", "c3"], "failed": []}
    assert {find_note(s.cfg, i)[1].category for i in ("a1", "b2", "c3")} == {"Seguridad"}
    assert index_path(s.cfg, "Seguridad").exists()
    assert not index_path(s.cfg, "Redes").exists() and not index_path(s.cfg, "Cocina").exists()


def test_one_moved_is_said_in_the_singular(s):
    assert post(s, "category", ids=["a1"], category="Seguridad").json()["notice"] == \
        "1 moved to Seguridad"


def test_a_new_category_typed_in_the_bar_is_used(s):
    post(s, "category", ids=["a1"], category="", new_category="Hogar")
    assert find_note(s.cfg, "a1")[1].category == "Hogar"


def test_ids_that_are_gone_or_on_another_shelf_are_counted_as_failed(s):
    body = post(s, "category", ids=["a1", "zzz", CARD1], category="Seguridad").json()
    assert body["done"] == ["a1"] and body["failed"] == ["zzz", CARD1]
    assert body["notice"] == "1 moved to Seguridad · 2 could not be changed"
    assert find_note(s.cfg, CARD1, s.cfg.ocio)[1].category == "Películas"


def test_bulk_move_with_an_id_deleted_meanwhile(s):
    path = find_note(s.cfg, "b2")[0]
    path.unlink()                                  # gone in Obsidian since the page was drawn
    body = post(s, "category", ids=["a1", "b2"], category="Seguridad").json()
    assert body["done"] == ["a1"] and body["failed"] == ["b2"]
    assert not path.exists() and find_note(s.cfg, "b2") is None


# --- refused values -----------------------------------------------------------------

@pytest.mark.parametrize("action,data,error", [
    ("category", {"category": "a/b"}, "cannot be used"),
    ("kind", {"kind": "opera"}, "type"),
    ("state", {"state": "abandonada"}, "state"),
    ("mark", {"mark": "🦄"}, "emoji"),
])
def test_a_refused_value_writes_nothing(s, action, data, error):
    before = snapshot(s.vault)
    answer = post(s, action, ids=["a1", CARD1, *s.ideas], **data)
    assert answer.status_code == 400 and error in answer.json()["error"]
    assert snapshot(s.vault) == before


def test_nothing_ticked_is_refused(s):
    answer = post(s, "delete")
    assert answer.status_code == 400
    assert answer.json()["error"] == "No notes were selected, so nothing changed."


def test_an_action_nobody_knows_is_a_404(s):
    assert s.client.post("/bulk/explode", data={"ids": ["a1"]}, headers=JSON).status_code == 404


# --- one rebuild per shelf ------------------------------------------------------------

def test_one_rebuild_per_shelf(s, monkeypatch):
    calls = []
    monkeypatch.setattr("oknowledge.web.app.rebuild_indexes",
                        lambda cfg, language, shelf=None: calls.append(shelf.name))
    monkeypatch.setattr("oknowledge.vault.rebuild_indexes",
                        lambda *a, **k: pytest.fail("rebuilt once per note"))

    post(s, "category", ids=["a1", "b2", "c3"], category="Seguridad")
    post(s, "kind", ids=[CARD1, CARD2], kind="series")
    post(s, "delete", ids=["a1", CARD1, s.ideas[0]])

    assert calls == ["links", "ocio", "ideas", "links", "ocio"]


def test_a_failed_rebuild_is_added_to_the_words(s, monkeypatch):
    def boom(cfg, language, shelf=None):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr("oknowledge.web.app.rebuild_indexes", boom)
    body = post(s, "category", ids=["a1"], category="Seguridad").json()
    assert body["ok"] is True
    assert body["notice"].startswith("1 moved to Seguridad · Saved, but the indexes")


# --- kind, state, mark ----------------------------------------------------------------

def test_kind_retypes_the_cards(s):
    body = post(s, "kind", ids=[CARD1, CARD2], kind="series").json()
    assert body["notice"] == "2 moved to Series"
    for card in (CARD1, CARD2):
        note = find_note(s.cfg, card, s.cfg.ocio)[1]
        assert (note.type, note.category) == ("series", "Series")


def test_state_changes_the_ideas_and_not_a_link(s):
    body = post(s, "state", ids=[*s.ideas, "a1"], state="doing").json()
    assert body["done"] == s.ideas and body["failed"] == ["a1"]
    assert body["notice"] == "2 are now «under way» · 1 could not be changed"
    assert {find_note(s.cfg, i, s.cfg.ideas)[1].state for i in s.ideas} == {"doing"}


def test_dropped_is_not_a_state_a_card_can_have(s):
    answer = post(s, "state", ids=[CARD1], state="dropped")
    assert answer.status_code == 400
    assert find_note(s.cfg, CARD1, s.cfg.ocio)[1].state == ""


def marks(s, *ids):
    return [find_note(s.cfg, i)[1].mark for i in ids]


def test_the_star_goes_on_all_unless_all_have_it(s):
    s.client.post("/item/a1/mark", data={"mark": "⭐"})
    assert post(s, "mark", ids=["a1", "b2"], mark="⭐").json()["notice"] == \
        "2 marked as favorites"
    assert marks(s, "a1", "b2") == ["⭐", "⭐"]
    assert post(s, "mark", ids=["a1", "b2"], mark="⭐").json()["notice"] == \
        "Favorite removed from 2"
    assert marks(s, "a1", "b2") == ["", ""]


def test_one_star_is_said_in_the_singular(s):
    assert post(s, "mark", ids=["a1"], mark="⭐").json()["notice"] == "1 marked as favorite"


def test_the_star_is_for_links_only(s):
    answer = post(s, "mark", ids=[CARD1], mark="⭐")
    assert answer.status_code == 404


# --- delete ----------------------------------------------------------------------------

def test_a_bulk_delete_gives_one_token_for_all(s):
    body = post(s, "delete", ids=["a1", "b2", CARD1]).json()
    assert body["notice"] == "3 deleted" and body["done"] == ["a1", "b2", CARD1]
    back = s.client.post(f"/undo/{body['undo']}", headers=JSON).json()
    assert back["notice"] == "3 restored"
    assert sorted(back["restored"]) == sorted(["a1", "b2", CARD1])
    assert find_note(s.cfg, "a1") and find_note(s.cfg, CARD1, s.cfg.ocio)


def test_one_deleted_says_deleted(s):
    assert post(s, "delete", ids=["a1"]).json()["notice"] == "Deleted"


def test_bulk_delete_with_an_id_deleted_meanwhile(s):
    find_note(s.cfg, "b2")[0].unlink()
    body = post(s, "delete", ids=["a1", "b2"]).json()
    assert body["done"] == ["a1"] and body["failed"] == ["b2"]
    assert body["notice"] == "Deleted · 1 could not be changed"
    assert len(list(trash_dir(s.cfg).glob("*.md"))) == 1


def test_all_gone_is_a_404_with_the_words(s):
    answer = post(s, "delete", ids=["zzz", "yyy"])
    assert answer.status_code == 404
    assert answer.json() == {"ok": False, "error": "That is not there any more."}


def test_a_busy_link_is_skipped(s):
    with Queue().lock("a1"):
        body = post(s, "category", ids=["a1", "b2"], category="Seguridad").json()
    assert body["done"] == ["b2"] and body["failed"] == ["a1"]


def test_all_busy_is_a_409(s):
    with Queue().lock("a1"):
        answer = post(s, "delete", ids=["a1"])
    assert answer.status_code == 409
    assert find_note(s.cfg, "a1") is not None


# --- without a script --------------------------------------------------------------

def test_without_a_script_it_goes_back_with_saved(s):
    answer = s.client.post("/bulk/category", data={"ids": ["a1"], "category": "Seguridad",
                                                   "back": "/?vista=lista"},
                           follow_redirects=False)
    assert answer.headers["location"] == "/?vista=lista&notice=saved"


def test_a_bulk_delete_without_a_script_offers_undo(s):
    answer = s.client.post("/bulk/delete", data={"ids": [CARD1]}, follow_redirects=False)
    assert re.fullmatch(r"/ocio\?notice=trashed&undo=[A-Za-z0-9_-]{22}",
                        answer.headers["location"])


# --- polish: delivery 6, batch C ----------------------------------------------------

def count_library_refreshes(monkeypatch):
    """How often the Biblioteca's index is read to find a note: held_by()
    reads it first, every time. The reads once the indexes are rebuilt are
    not lookups (they pick up what the batch wrote) and are not counted."""
    import oknowledge.web.app as web_app
    from oknowledge.web.index import Library
    calls, rebuilt = [], []
    real, real_rebuild = Library.refresh, web_app.rebuild_indexes

    def counting(self, *a, **k):
        if self.shelf.name == "links" and not rebuilt:
            calls.append(1)
        return real(self, *a, **k)

    def rebuilding(*a, **k):
        rebuilt.append(1)
        return real_rebuild(*a, **k)
    monkeypatch.setattr(Library, "refresh", counting)
    monkeypatch.setattr(web_app, "rebuild_indexes", rebuilding)
    return calls


def test_a_bulk_state_looks_up_the_shelf_once_per_note(s, monkeypatch):
    calls = count_library_refreshes(monkeypatch)
    post(s, "state", ids=s.ideas, state="doing")
    assert len(calls) == len(s.ideas)


def test_a_bulk_delete_looks_up_the_shelf_once_per_note(s, monkeypatch):
    calls = count_library_refreshes(monkeypatch)
    post(s, "delete", ids=s.ideas)
    assert len(calls) == len(s.ideas)


def test_a_mixed_state_batch_does_not_speak_in_the_words_of_ideas(s):
    body = post(s, "state", ids=[s.ideas[0], CARD1, "a1"], state="doing").json()
    assert body["done"] == [s.ideas[0], CARD1] and body["failed"] == ["a1"]
    assert "under way" not in body["notice"]
    assert body["notice"] == "2 changed · 1 could not be changed"


def test_a_card_that_cannot_follow_is_counted_not_hidden(s):
    body = post(s, "state", ids=[s.ideas[0], CARD1], state="dropped").json()
    assert body["done"] == [s.ideas[0]] and body["failed"] == [CARD1]
    # Only the idea changed, so the idea's word is true; the card is counted.
    assert body["notice"] == "1 is now «dropped» · 1 could not be changed"


def test_a_batch_of_ideas_alone_keeps_the_state_words(s):
    assert post(s, "state", ids=s.ideas, state="doing").json()["notice"] == \
        "2 are now «under way»"


def test_nothing_ticked_in_a_bulk_speaks_of_notes_not_cards(s):
    answer = post(s, "delete")
    assert answer.json()["error"] == "No notes were selected, so nothing changed."


def test_a_bulk_state_and_a_bulk_mark_rebuild_no_index(s, monkeypatch):
    monkeypatch.setattr("oknowledge.web.app.rebuild_indexes",
                        lambda *a, **k: pytest.fail("rebuilt"))
    monkeypatch.setattr("oknowledge.vault.rebuild_indexes",
                        lambda *a, **k: pytest.fail("rebuilt"))
    assert post(s, "state", ids=s.ideas, state="done").json()["ok"] is True
    assert post(s, "mark", ids=["a1", "b2"], mark="⭐").json()["ok"] is True


def test_a_busy_note_is_skipped_in_bulk_kind_state_and_mark(s):
    with Queue().lock(CARD1):
        body = post(s, "kind", ids=[CARD1, CARD2], kind="series").json()
    assert body["done"] == [CARD2] and body["failed"] == [CARD1]
    with Queue().lock(s.ideas[0]):
        body = post(s, "state", ids=s.ideas, state="doing").json()
    assert body["done"] == [s.ideas[1]] and body["failed"] == [s.ideas[0]]
    with Queue().lock("a1"):
        body = post(s, "mark", ids=["a1", "b2"], mark="⭐").json()
    assert body["done"] == ["b2"] and body["failed"] == ["a1"]


# --- the words of a bulk state (batch G) ----------------------------------------------

def test_a_bulk_state_says_the_notes_are_now_in_it():
    """Spanish gives a state its own gender ("descartada"): "movido a" would
    not agree, so a state is said with a verb that has none."""
    from oknowledge.i18n import translator
    from oknowledge.web.app import bulk_words
    es = translator("es")
    # Final review M-3: "2 pasaron a descartada" did not agree in number; the
    # state is quoted as the label it is in the menu, lower case as there.
    assert bulk_words(es, "state", 1, 0, "descartada") == "1 pasó a «descartada»"
    assert bulk_words(es, "state", 2, 0, "descartada") == "2 pasaron a «descartada»"
    en = translator("en")
    assert bulk_words(en, "state", 1, 0, "dropped") == "1 is now «dropped»"
    assert bulk_words(en, "state", 3, 0, "dropped") == "3 are now «dropped»"
    # A category is a place, and keeps its words.
    assert bulk_words(es, "category", 2, 0, "Redes") == "2 movidos a Redes"


@pytest.mark.parametrize("ids", [[CARD1, CARD2], [CARD1, "a1"]])
def test_when_no_card_can_take_the_state_the_answer_says_why(s, ids):
    answer = post(s, "state", ids=ids, state="dropped")
    assert answer.status_code == 400
    assert answer.json()["error"] == "That state does not apply to Ocio cards."


# --- the sidebar's counts follow a bulk action (batch G) ------------------------------
# Every bulk action, and its Deshacer, reloads the list: the list's answer
# brings the sidebar drawn again for shell.js to swap in, the sections'
# counts with it.

def side_of(body):
    found = re.search(r'<template id="side-filters">(.*?)</template>', body, re.S)
    assert found, "the list's answer brings no sidebar"
    return found.group(1)


def section_count(side, href):
    found = re.search(rf'<nav class="sections">.*?href="{re.escape(href)}"[^>]*>.*?'
                      r'<b class="count mono">(\d+)</b>', side, re.S)
    assert found, f"no section count for {href}"
    return int(found.group(1))


def row_count(side, label):
    found = re.search(rf'<span>{re.escape(label)}</span><b class="count mono">(\d+)</b>', side)
    return int(found.group(1)) if found else None


def test_after_a_bulk_move_the_library_list_brings_the_new_category_counts(s):
    before = side_of(s.client.get("/lista").text)
    assert (row_count(before, "Redes"), row_count(before, "Cocina")) == (2, 1)
    post(s, "category", ids=["b2"], category="Redes")
    answer = s.client.get("/lista").text
    after = side_of(answer)
    assert (row_count(after, "Redes"), row_count(after, "Cocina")) == (3, None)
    # The phone's chip row comes along, drawn for the same counts.
    assert '<template id="chip-filters">' in answer


def test_after_a_bulk_delete_and_its_undo_the_sections_count_again(s):
    token = post(s, "delete", ids=["a1", "b2"]).json()["undo"]
    assert section_count(side_of(s.client.get("/lista").text), "/") == 1
    s.client.post(f"/undo/{token}", headers=JSON)
    assert section_count(side_of(s.client.get("/lista").text), "/") == 3


def test_after_a_bulk_state_the_ideas_list_brings_its_state_counts(s):
    post(s, "state", ids=s.ideas, state="doing")
    answer = s.client.get("/ideas/lista").text
    side = side_of(answer)
    assert row_count(side, "under way") == 2 and row_count(side, "seed") == 0
    assert section_count(side, "/ideas") == 2
    assert '<template id="chip-filters">' in answer


def test_after_a_bulk_delete_of_a_card_the_ocio_list_counts_one_less(s):
    post(s, "delete", ids=[CARD1])
    assert section_count(side_of(s.client.get("/ocio/lista").text), "/ocio") == 1


def test_show_more_brings_no_sidebar(s):
    assert '<template id="side-filters">' not in s.client.get("/lista?desde=1").text
    assert '<template id="side-filters">' not in s.client.get("/ideas/lista?desde=1").text


def test_the_first_page_does_not_carry_a_second_sidebar(s):
    for path in ("/", "/ideas", "/ocio"):
        assert '<template id="side-filters">' not in s.client.get(path).text
