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


def count_rebuilds(monkeypatch):
    calls = []
    monkeypatch.setattr("oknowledge.undo.rebuild_indexes",
                        lambda cfg, language, shelf=None: calls.append(shelf.name))
    return calls


def test_a_trash_copy_that_stays_behind_is_still_restored_and_rebuilt(tmp_path, monkeypatch):
    cfg = make(tmp_path)
    moved = put(cfg, "a1")
    token = undo.remember(cfg, [("a1", "links", moved)], now=NOW)
    real = type(moved.target).unlink

    def unlink(self, missing_ok=False):
        if self.parent.name == "trash":
            raise PermissionError(13, "Permission denied", str(self))
        return real(self, missing_ok=missing_ok)
    monkeypatch.setattr(type(moved.target), "unlink", unlink)
    calls = count_rebuilds(monkeypatch)

    result = undo.restore(cfg, token, "es", no_lock, now=NOW)

    assert result.restored == ["a1"] and result.skipped == []
    assert calls == ["links"]
    assert find_note(cfg, "a1") is not None and moved.target.exists()
    assert undo.restore(cfg, token, "es", no_lock, now=NOW) is None   # the lot is spent


def test_an_unexpected_error_skips_that_note_and_the_rest_still_come_back(tmp_path,
                                                                          monkeypatch):
    cfg = make(tmp_path)
    items = [("a1", "links", put(cfg, "a1")), ("a2", "links", put(cfg, "a2")),
             ("i1", "ideas", put(cfg, "i1", shelf=cfg.ideas, type="idea"))]
    token = undo.remember(cfg, items, now=NOW)
    real = undo.restore_note

    def flaky(cfg, link, *args, **kwargs):
        if link == "a2":
            raise RuntimeError("something nobody expected")
        return real(cfg, link, *args, **kwargs)
    monkeypatch.setattr("oknowledge.undo.restore_note", flaky)
    calls = count_rebuilds(monkeypatch)

    result = undo.restore(cfg, token, "es", no_lock, now=NOW)

    assert result.restored == ["a1", "i1"] and result.skipped == ["a2"]
    assert sorted(calls) == ["ideas", "links"]
    assert find_note(cfg, "a1") and find_note(cfg, "i1", cfg.ideas)
    assert items[1][2].target.exists()                     # a2 is still in trash/


def test_an_unexpected_error_from_the_lock_skips_only_that_note(tmp_path, monkeypatch):
    cfg = make(tmp_path)
    token = undo.remember(cfg, [("a1", "links", put(cfg, "a1")),
                                ("a2", "links", put(cfg, "a2"))], now=NOW)

    @contextlib.contextmanager
    def lock(link_id):
        if link_id == "a1":
            raise RuntimeError("the lock broke")
        yield
    calls = count_rebuilds(monkeypatch)

    result = undo.restore(cfg, token, "es", lock, now=NOW)
    assert result.restored == ["a2"] and result.skipped == ["a1"]
    assert calls == ["links"]


def test_an_unexpected_error_in_a_rebuild_is_stale_and_the_others_still_rebuild(
        tmp_path, monkeypatch):
    cfg = make(tmp_path)
    token = undo.remember(cfg, [("a1", "links", put(cfg, "a1")),
                                ("i1", "ideas", put(cfg, "i1", shelf=cfg.ideas, type="idea"))],
                          now=NOW)
    calls = []

    def rebuild(cfg, language, shelf=None):
        calls.append(shelf.name)
        if shelf.name == "links":
            raise RuntimeError("a template broke")
    monkeypatch.setattr("oknowledge.undo.rebuild_indexes", rebuild)

    result = undo.restore(cfg, token, "es", no_lock, now=NOW)
    assert result.restored == ["a1", "i1"] and result.stale is True
    assert sorted(calls) == ["ideas", "links"]


def test_a_lot_dated_in_the_future_is_expired(tmp_path):
    """The clock went back: a lot from 'later' would otherwise never expire."""
    cfg = make(tmp_path)
    moved = put(cfg, "a1")
    token = undo.remember(cfg, [("a1", "links", moved)], now=NOW + dt.timedelta(hours=2))

    assert not undo.alive(token, now=NOW)
    assert undo.restore(cfg, token, "es", no_lock, now=NOW) is None
    assert moved.target.exists()
    assert undo.purge(now=NOW) == 1
    assert not (undo.folder() / f"{token}.json").exists()


def test_an_unreadable_lot_with_a_future_mtime_is_purged(tmp_path):
    import os
    undo.folder().mkdir(parents=True)
    path = undo.folder() / ("x" * 22 + ".json")
    path.write_text("not json", encoding="utf-8")
    future = (NOW + dt.timedelta(hours=2)).timestamp()
    os.utime(path, (future, future))

    assert undo.purge(now=NOW) == 1 and not path.exists()


def test_two_undos_of_one_lot_at_once_restore_it_once(tmp_path, monkeypatch):
    """Both read the lot before either claims it: only the one whose unlink
    wins restores; the other finds nothing, and nothing is doubled or lost."""
    import threading

    cfg = make(tmp_path)
    one, two = put(cfg, "a1"), put(cfg, "a2")
    token = undo.remember(cfg, [("a1", "links", one), ("a2", "links", two)], now=NOW)
    both_read = threading.Barrier(2, timeout=5)
    real = undo._read

    def read(path):
        lot = real(path)
        both_read.wait()
        return lot
    monkeypatch.setattr(undo, "_read", read)
    results = [None, None]

    def run(i):
        results[i] = undo.restore(cfg, token, "es", no_lock, now=NOW)
    threads = [threading.Thread(target=run, args=(i,)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)

    done = [r for r in results if r is not None]
    assert len(done) == 1 and results.count(None) == 1
    assert done[0].restored == ["a1", "a2"]
    assert len(list(cfg.links.dir.glob("*.md"))) == 2
    assert list((cfg.root / "trash").glob("*.md")) == []


def test_a_small_step_back_of_the_clock_keeps_a_fresh_lot(tmp_path):
    """NTP nudging the clock back a little must not cost the Undo just
    offered: a lot up to undo.SKEW in the future still counts."""
    cfg = make(tmp_path)
    moved = put(cfg, "a1")
    token = undo.remember(cfg, [("a1", "links", moved)], now=NOW + dt.timedelta(seconds=1))
    undo.remember(cfg, [("b2", "links", put(cfg, "b2"))], now=NOW)    # purges first

    assert (undo.folder() / f"{token}.json").exists()
    assert undo.alive(token, now=NOW)
    assert undo.alive(token, now=NOW + dt.timedelta(seconds=1) - undo.SKEW)
    assert not undo.alive(token, now=NOW - undo.SKEW)
    assert undo.restore(cfg, token, "es", no_lock, now=NOW).restored == ["a1"]


def test_an_unreadable_lot_a_little_in_the_future_is_kept(tmp_path):
    import os
    undo.folder().mkdir(parents=True)
    path = undo.folder() / ("y" * 22 + ".json")
    path.write_text("not json", encoding="utf-8")
    soon = (NOW + dt.timedelta(seconds=30)).timestamp()
    os.utime(path, (soon, soon))

    assert undo.purge(now=NOW) == 0 and path.exists()
