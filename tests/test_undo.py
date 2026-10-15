"""The lots a Deshacer restores (spec §6.2): a small JSON per delete in the
state dir, never a note. conftest points XDG_STATE_HOME into tmp_path."""

import contextlib
import datetime as dt
import json

import pytest

from oknowledge import undo
from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.queue import Locked, state_dir
from oknowledge.vault import delete_note, find_note, note_path, rebuild_indexes, write_note

NOW = dt.datetime(2026, 10, 14, 12, 0, tzinfo=dt.timezone.utc)


def make(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    return Config(vault=vault)


def put(cfg, id, shelf=None, type="article"):
    note = Note(id=id, url=f"https://e.com/{id}", title=f"Nota {id}", category="Redes",
                tags=[], type=type, source="e.com", saved="2026-10-03", summary="s")
    shelf = shelf or cfg.links
    write_note(cfg, note, "es", path=note_path(cfg, note, shelf=shelf))
    rebuild_indexes(cfg, "es", shelf=shelf)
    return delete_note(cfg, id, "es", shelf=shelf)


def no_lock(link_id):
    return contextlib.nullcontext()


def test_a_lot_is_a_json_in_the_state_dir(tmp_path):
    cfg = make(tmp_path)
    moved = put(cfg, "a1")
    token = undo.remember(cfg, [("a1", "links", moved)], now=NOW)

    assert undo.TOKEN.fullmatch(token)
    path = state_dir() / "undo" / f"{token}.json"
    assert path.is_relative_to(tmp_path)
    lot = json.loads(path.read_text(encoding="utf-8"))
    assert lot["at"] == NOW.isoformat()
    assert lot["items"] == [{"id": "a1", "shelf": "links",
                             "source": "links/" + moved.source.name,
                             "target": "trash/" + moved.target.name}]


def test_restore_puts_every_note_back_and_forgets_the_lot(tmp_path):
    cfg = make(tmp_path)
    one, two = put(cfg, "a1"), put(cfg, "a2")
    token = undo.remember(cfg, [("a1", "links", one), ("a2", "links", two)], now=NOW)

    result = undo.restore(cfg, token, "es", no_lock, now=NOW)

    assert result.restored == ["a1", "a2"] and result.skipped == []
    assert result.shelf == "links" and result.stale is False
    assert find_note(cfg, "a1") and find_note(cfg, "a2")
    assert not (undo.folder() / f"{token}.json").exists()


def test_a_lot_is_used_once(tmp_path):
    cfg = make(tmp_path)
    token = undo.remember(cfg, [("a1", "links", put(cfg, "a1"))], now=NOW)
    assert undo.restore(cfg, token, "es", no_lock, now=NOW) is not None
    assert undo.restore(cfg, token, "es", no_lock, now=NOW) is None
    assert not undo.alive(token, now=NOW)


def test_an_expired_lot_restores_nothing(tmp_path):
    cfg = make(tmp_path)
    moved = put(cfg, "a1")
    token = undo.remember(cfg, [("a1", "links", moved)], now=NOW)
    later = NOW + dt.timedelta(hours=24, seconds=1)

    assert undo.alive(token, now=NOW) and not undo.alive(token, now=later)
    assert undo.restore(cfg, token, "es", no_lock, now=later) is None
    assert moved.target.exists() and find_note(cfg, "a1") is None


@pytest.mark.parametrize("token", ["", "short", "a" * 23, "../decoy", "a/b" + "c" * 19,
                                   "..", "a" * 21 + "."])
def test_tokens_of_another_shape_touch_nothing(tmp_path, token):
    decoy = state_dir() / "decoy.json"
    decoy.parent.mkdir(parents=True, exist_ok=True)
    decoy.write_text(json.dumps({"at": NOW.isoformat(), "items": []}), encoding="utf-8")
    assert undo.restore(make(tmp_path), token, "es", no_lock, now=NOW) is None
    assert not undo.alive(token, now=NOW)
    assert decoy.exists()


def test_purge_drops_only_expired_lots_and_never_a_note(tmp_path):
    cfg = make(tmp_path)
    old = undo.remember(cfg, [("a1", "links", put(cfg, "a1"))], now=NOW)
    new = undo.remember(cfg, [("a2", "links", put(cfg, "a2"))],
                        now=NOW + dt.timedelta(hours=20))
    stray = undo.folder() / "notes.md"
    stray.write_text("not ours to delete\n", encoding="utf-8")

    assert undo.purge(now=NOW + dt.timedelta(hours=25)) == 1

    assert not (undo.folder() / f"{old}.json").exists()
    assert (undo.folder() / f"{new}.json").exists()
    assert stray.exists()
    assert len(list((cfg.root / "trash").glob("*.md"))) == 2     # both notes still in trash/


def test_remember_purges_the_old_ones_first(tmp_path):
    cfg = make(tmp_path)
    old = undo.remember(cfg, [("a1", "links", put(cfg, "a1"))], now=NOW)
    undo.remember(cfg, [("a2", "links", put(cfg, "a2"))], now=NOW + dt.timedelta(days=2))
    assert not (undo.folder() / f"{old}.json").exists()


def test_purge_without_a_folder_creates_none():
    assert undo.purge(now=NOW) == 0
    assert not undo.folder().exists()


def test_a_busy_link_is_skipped_and_the_others_come_back(tmp_path):
    cfg = make(tmp_path)
    token = undo.remember(cfg, [("a1", "links", put(cfg, "a1")),
                                ("a2", "links", put(cfg, "a2"))], now=NOW)

    @contextlib.contextmanager
    def lock(link_id):
        if link_id == "a1":
            raise Locked(link_id)
        yield

    result = undo.restore(cfg, token, "es", lock, now=NOW)
    assert result.restored == ["a2"] and result.skipped == ["a1"]


def test_one_rebuild_per_shelf_touched(tmp_path, monkeypatch):
    cfg = make(tmp_path)
    items = [("a1", "links", put(cfg, "a1")), ("a2", "links", put(cfg, "a2")),
             ("i1", "ideas", put(cfg, "i1", shelf=cfg.ideas, type="idea"))]
    token = undo.remember(cfg, items, now=NOW)
    calls = []
    monkeypatch.setattr("oknowledge.undo.rebuild_indexes",
                        lambda cfg, language, shelf=None: calls.append(shelf.name))
    monkeypatch.setattr("oknowledge.vault.rebuild_indexes",
                        lambda *a, **k: pytest.fail("restore_note rebuilt on its own"))

    undo.restore(cfg, token, "es", no_lock, now=NOW)

    assert sorted(calls) == ["ideas", "links"]


def test_a_failed_rebuild_is_said_and_the_notes_stay_back(tmp_path, monkeypatch):
    cfg = make(tmp_path)
    token = undo.remember(cfg, [("a1", "links", put(cfg, "a1"))], now=NOW)

    def boom(cfg, language, shelf=None):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr("oknowledge.undo.rebuild_indexes", boom)

    result = undo.restore(cfg, token, "es", no_lock, now=NOW)
    assert result.stale is True and result.restored == ["a1"]
    assert find_note(cfg, "a1") is not None


def test_a_lot_naming_an_unknown_shelf_skips_that_item(tmp_path):
    cfg = make(tmp_path)
    moved = put(cfg, "a1")
    token = undo.remember(cfg, [("a1", "trash", moved)], now=NOW)
    assert undo.restore(cfg, token, "es", no_lock, now=NOW).skipped == ["a1"]
    assert moved.target.exists()
