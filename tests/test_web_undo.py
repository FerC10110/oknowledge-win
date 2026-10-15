"""Deleting with Deshacer (spec §6.3, §6.4, §2): every delete answers with a
token, the page after it offers Deshacer as a form, and the token puts the
notes back exactly once."""

import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from oknowledge import undo
from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.model import Note
from oknowledge.vault import (
    all_notes, delete_note, find_note, note_path, rebuild_indexes, trash_dir, write_note,
)
from oknowledge.web.app import create_app

JSON = {"Accept": "application/json"}
CARD = "c00000000001"
STATIC = Path(__file__).resolve().parent.parent / "src" / "oknowledge" / "web" / "static"


def link(id, title, category):
    return Note(id=id, url=f"https://e.com/{id}", title=title, category=category, tags=["vpn"],
                type="article", source="e.com", saved="2026-10-03", summary="s",
                cover=f"../attachments/{id}.png")


@pytest.fixture
def s(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    first = write_note(cfg, link("a1", "WireGuard", "Redes"), "es")
    write_note(cfg, link("b2", "Masa madre", "Cocina"), "es")
    card = Note(id=CARD, url="https://www.imdb.com/title/tt1", title="Alien",
                category="Películas", tags=[], type="movie", source="imdb.com",
                saved="2026-10-01", summary="s", engine="")
    write_note(cfg, card, "es", path=note_path(cfg, card, shelf=cfg.ocio))
    idea = new_idea("Una vpn para la familia.", "VPN familiar", "2026-10-13",
                    "2026-10-13T00:00:00.000001+00:00")
    idea.related = [first.stem]
    write_note(cfg, idea, "es", path=note_path(cfg, idea, shelf=cfg.ideas))
    for shelf in (cfg.links, cfg.ocio, cfg.ideas):
        rebuild_indexes(cfg, "es", shelf=shelf)
    return SimpleNamespace(cfg=cfg, client=TestClient(create_app(cfg)), idea=idea.id)


def deleted(s, which="a1"):
    return s.client.post(f"/item/{which}/delete", headers=JSON).json()["undo"]


# --- the delete ------------------------------------------------------------------

def test_a_delete_asked_by_a_script_answers_deleted_and_a_token(s):
    answer = s.client.post("/item/a1/delete", headers=JSON)
    body = answer.json()
    assert answer.status_code == 200
    assert body["ok"] is True and body["notice"] == "Deleted"
    assert undo.TOKEN.fullmatch(body["undo"])
    assert find_note(s.cfg, "a1") is None


@pytest.mark.parametrize("which,home", [("a1", "/"), (CARD, "/ocio"), ("idea", "/ideas")])
def test_a_delete_from_a_form_goes_home_with_its_token(s, which, home):
    target = s.idea if which == "idea" else which
    location = s.client.post(f"/item/{target}/delete", follow_redirects=False).headers["location"]
    assert re.fullmatch(re.escape(home) + r"\?notice=trashed&undo=[A-Za-z0-9_-]{22}", location)


def test_a_delete_still_lands_when_the_lot_cannot_be_written(s, monkeypatch):
    def boom(*args, **kwargs):
        raise OSError(30, "Read-only file system")
    monkeypatch.setattr("oknowledge.undo.remember", boom)
    body = s.client.post("/item/a1/delete", headers=JSON).json()
    assert body["ok"] is True and "undo" not in body
    assert find_note(s.cfg, "a1") is None


def test_a_delete_still_lands_when_the_lot_folder_resolves_outside_the_vault(s, monkeypatch):
    def boom(*args, **kwargs):
        raise ValueError("not in the subpath")
    monkeypatch.setattr("oknowledge.undo.remember", boom)
    answer = s.client.post("/item/a1/delete", headers=JSON)
    assert answer.status_code == 200
    assert answer.json()["ok"] is True and "undo" not in answer.json()
    assert find_note(s.cfg, "a1") is None
    assert len(list(trash_dir(s.cfg).glob("*.md"))) == 1


def test_the_delete_buttons_ask_nothing_and_reprocess_still_asks(s):
    for page in ("/?sel=a1", f"/ocio?sel={CARD}", f"/ideas/{s.idea}"):
        body = s.client.get(page).text
        assert not re.search(r'/delete"[^>]*data-ask', body), page
        assert "confirm(this.form.dataset.ask)\">Delete" not in body, page
    assert "confirm(" in s.client.get("/?sel=a1").text          # Reprocess keeps its own


# --- the server's toast ------------------------------------------------------------

def test_the_page_after_a_delete_offers_undo_as_a_form(s):
    location = s.client.post("/item/a1/delete", follow_redirects=False).headers["location"]
    token = location.rsplit("=", 1)[1]
    toast = re.search(r'<div id="toast".*?</div>', s.client.get(location).text, re.S).group(0)
    assert 'class="toast undo"' in toast and " hidden" not in toast
    assert f'<form method="post" action="/undo/{token}" class="toast-undo">' in toast
    assert '<input type="hidden" name="back" value="/">' in toast
    assert ">Undo</button>" in toast


def test_the_undo_form_goes_back_to_the_page_without_the_notice(s):
    token = deleted(s)
    body = s.client.get(f"/?vista=lista&notice=trashed&undo={token}").text
    assert 'name="back" value="/?vista=lista"' in body


@pytest.mark.parametrize("token", ["A" * 22, "nope"])
def test_an_invented_token_draws_no_undo(s, token):
    body = s.client.get(f"/?notice=trashed&undo={token}").text
    assert "/undo/" not in body
    assert '<span class="toast-text">' in body               # the notice is still said


def test_with_no_notice_there_is_no_toast(s):
    token = deleted(s)
    body = s.client.get(f"/?undo={token}").text
    assert "/undo/" not in body
    assert re.search(r'<div id="toast" class="toast" role="status" aria-live="polite" hidden>', body)


def test_the_layout_script_takes_the_token_out_of_the_url():
    script = STATIC.joinpath("layout.js").read_text(encoding="utf-8")
    assert '"undo"' in script


# --- the undo --------------------------------------------------------------------

@pytest.mark.parametrize("which,column,title", [("a1", "/lista", "WireGuard"),
                                                (CARD, "/ocio/lista", "Alien"),
                                                ("idea", "/ideas/lista", "VPN familiar")])
def test_undo_puts_the_note_back_in_its_list(s, which, column, title):
    target = s.idea if which == "idea" else which
    token = deleted(s, target)
    assert title not in s.client.get(column).text

    answer = s.client.post(f"/undo/{token}", headers=JSON)

    assert answer.json() == {"ok": True, "notice": "Restored", "restored": [target], "skipped": []}
    assert title in s.client.get(column).text


def test_a_restored_link_keeps_its_cover_and_its_idea(s):
    s.client.post(f"/undo/{deleted(s)}", headers=JSON)
    assert find_note(s.cfg, "a1")[1].cover == "../attachments/a1.png"
    assert "WireGuard" in s.client.get(f"/ideas/{s.idea}").text


def test_a_second_undo_is_gone(s):
    token = deleted(s)
    assert s.client.post(f"/undo/{token}", headers=JSON).status_code == 200
    again = s.client.post(f"/undo/{token}", headers=JSON)
    assert again.status_code == 404
    assert again.json() == {"ok": False, "error": "It can no longer be undone"}
    assert len([n for n in all_notes(s.cfg) if n.id == "a1"]) == 1


def test_the_form_and_the_script_cannot_both_undo(s):
    token = deleted(s)
    first = s.client.post(f"/undo/{token}", data={"back": "/"}, follow_redirects=False)
    assert first.headers["location"] == "/?notice=restored-one&n=1"
    assert s.client.post(f"/undo/{token}", headers=JSON).status_code == 404
    assert len([n for n in all_notes(s.cfg) if n.id == "a1"]) == 1


def test_undo_without_a_script_goes_to_the_section_of_the_note(s):
    token = deleted(s, CARD)
    answer = s.client.post(f"/undo/{token}", follow_redirects=False)
    assert answer.headers["location"] == "/ocio?notice=restored-one&n=1"


def test_a_back_to_another_host_is_ignored(s):
    token = deleted(s)
    answer = s.client.post(f"/undo/{token}", data={"back": "//evil.example/x"},
                           follow_redirects=False)
    assert answer.headers["location"] == "/?notice=restored-one&n=1"


def test_an_invented_token_is_gone_without_a_script_too(s):
    answer = s.client.post("/undo/" + "A" * 22, follow_redirects=False)
    assert answer.headers["location"] == "/?notice=undo-gone"


def test_undo_after_the_note_was_pasted_again_is_blocked(s):
    token = deleted(s)
    write_note(s.cfg, link("a1", "WireGuard otra vez", "Redes"), "es")
    answer = s.client.post(f"/undo/{token}", headers=JSON)
    assert answer.status_code == 409
    assert answer.json() == {"ok": False, "error":
                             "It could not be restored: there is already another note with that link"}
    assert len(list(trash_dir(s.cfg).glob("*.md"))) == 1


def test_undo_after_the_note_was_edited_in_obsidian_keeps_the_edit(s):
    token = deleted(s)
    (moved,) = trash_dir(s.cfg).glob("*.md")
    moved.write_text(moved.read_text(encoding="utf-8") + "\nMía.\n", encoding="utf-8")
    assert s.client.post(f"/undo/{token}", headers=JSON).json()["restored"] == ["a1"]
    assert find_note(s.cfg, "a1")[0].read_text(encoding="utf-8").endswith("\nMía.\n")


def test_undo_after_the_id_was_changed_in_obsidian_is_blocked(s):
    token = deleted(s)
    (moved,) = trash_dir(s.cfg).glob("*.md")
    moved.write_text(moved.read_text(encoding="utf-8").replace("id: a1", "id: zz"),
                     encoding="utf-8")
    assert s.client.post(f"/undo/{token}", headers=JSON).status_code == 409
    assert moved.exists() and find_note(s.cfg, "a1") is None


def test_a_lot_with_one_blocked_says_both(s):
    one = delete_note(s.cfg, "a1", "es")
    two = delete_note(s.cfg, "b2", "es")
    token = undo.remember(s.cfg, [("a1", "links", one), ("b2", "links", two)])
    write_note(s.cfg, link("a1", "WireGuard otra vez", "Redes"), "es")

    body = s.client.post(f"/undo/{token}", headers=JSON).json()

    assert body == {"ok": True, "restored": ["b2"], "skipped": ["a1"],
                    "notice": "Restored · 1 not: there is already another note with that link"}


# --- undo with the indexes behind --------------------------------------------------

def stale_rebuild(monkeypatch):
    def boom(cfg, language, shelf=None):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr("oknowledge.undo.rebuild_indexes", boom)


def test_an_undo_whose_rebuild_fails_says_so_and_the_note_is_back(s, monkeypatch):
    token = deleted(s)
    stale_rebuild(monkeypatch)

    body = s.client.post(f"/undo/{token}", headers=JSON).json()

    assert body == {"ok": True, "restored": ["a1"], "skipped": [],
                    "notice": "Restored, but the indexes could not be rebuilt. Run "
                              "`oknowledge reindex` once the folder is writable again."}
    assert find_note(s.cfg, "a1") is not None


def test_an_undo_with_stale_indexes_and_one_blocked_says_both(s, monkeypatch):
    one = delete_note(s.cfg, "a1", "es")
    two = delete_note(s.cfg, "b2", "es")
    token = undo.remember(s.cfg, [("a1", "links", one), ("b2", "links", two)])
    write_note(s.cfg, link("a1", "WireGuard otra vez", "Redes"), "es")
    stale_rebuild(monkeypatch)

    body = s.client.post(f"/undo/{token}", headers=JSON).json()

    assert body["restored"] == ["b2"] and body["skipped"] == ["a1"]
    assert body["notice"] == ("Restored · 1 not: there is already another note with that "
                              "link. The indexes could not be rebuilt: run `oknowledge "
                              "reindex` once the folder is writable again.")


def test_without_a_script_the_stale_partial_undo_keeps_its_counts(s, monkeypatch):
    one = delete_note(s.cfg, "a1", "es")
    two = delete_note(s.cfg, "b2", "es")
    token = undo.remember(s.cfg, [("a1", "links", one), ("b2", "links", two)])
    write_note(s.cfg, link("a1", "WireGuard otra vez", "Redes"), "es")
    stale_rebuild(monkeypatch)

    answer = s.client.post(f"/undo/{token}", data={"back": "/"}, follow_redirects=False)
    location = answer.headers["location"]
    assert location == "/?notice=restored-one-partial-indexes-stale&n=1&m=1"
    page = s.client.get(location).text
    assert "Restored · 1 not: there is already another note" in page
    assert "oknowledge reindex" in page


def test_a_stale_undo_of_several_with_some_blocked_counts_both(s, monkeypatch):
    one, two = delete_note(s.cfg, "a1", "es"), delete_note(s.cfg, "b2", "es")
    three = delete_note(s.cfg, CARD, "es", shelf=s.cfg.ocio)
    token = undo.remember(s.cfg, [("a1", "links", one), ("b2", "links", two),
                                  (CARD, "ocio", three)])
    write_note(s.cfg, link("a1", "WireGuard otra vez", "Redes"), "es")
    stale_rebuild(monkeypatch)

    body = s.client.post(f"/undo/{token}", headers=JSON).json()

    assert body["notice"] == ("2 restored · 1 not: there is already another note with that "
                              "link. The indexes could not be rebuilt: run `oknowledge "
                              "reindex` once the folder is writable again.")


def test_two_undos_at_once_through_the_web_restore_once(s, monkeypatch):
    import threading

    token = deleted(s)
    both_read = threading.Barrier(2, timeout=5)
    real = undo._read

    def read(path):
        lot = real(path)
        both_read.wait()
        return lot
    monkeypatch.setattr(undo, "_read", read)
    answers = []

    def run():
        answers.append(s.client.post(f"/undo/{token}", headers=JSON))
    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)

    assert sorted(a.status_code for a in answers) == [200, 404]
    gone = next(a for a in answers if a.status_code == 404)
    assert gone.json() == {"ok": False, "error": "It can no longer be undone"}
    assert len([n for n in all_notes(s.cfg) if n.id == "a1"]) == 1
    assert list(trash_dir(s.cfg).glob("*.md")) == []
