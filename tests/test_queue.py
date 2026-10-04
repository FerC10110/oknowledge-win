import os
import time

import pytest

from oknowledge.queue import STATUSES, UNFINISHED, Locked, Queue


def test_a_new_link_starts_pending(tmp_path):
    q = Queue(tmp_path)
    entry = q.enqueue("abc123", "https://e.com/x", "full")
    assert entry.status == "pending"
    assert q.get("abc123").url == "https://e.com/x"
    assert q.get("abc123").content == "full"


def test_the_status_moves_and_keeps_the_error(tmp_path):
    q = Queue(tmp_path)
    q.enqueue("abc123", "https://e.com/x", "full")
    q.set_status("abc123", "partial", error="403 from the site", title="Algo")
    entry = q.get("abc123")
    assert entry.status == "partial"
    assert entry.error == "403 from the site"
    assert entry.title == "Algo"


def test_unfinished_lists_what_needs_a_retry(tmp_path):
    q = Queue(tmp_path)
    for link_id, status in [("a", "ok"), ("b", "partial"), ("c", "failed"), ("d", "pending")]:
        q.enqueue(link_id, f"https://e.com/{link_id}", "full")
        q.set_status(link_id, status)
    assert sorted(e.id for e in q.unfinished()) == ["b", "c"]


def test_entries_come_back_newest_first(tmp_path, monkeypatch):
    stamps = iter(["2026-01-01T00:00:00.001+00:00", "2026-01-01T00:00:00.002+00:00"])
    monkeypatch.setattr("oknowledge.queue._now", lambda: next(stamps))
    q = Queue(tmp_path)
    q.enqueue("old", "https://e.com/1", "full")
    q.enqueue("new", "https://e.com/2", "full")
    assert [e.id for e in q.entries()] == ["new", "old"]


def test_equal_timestamps_still_have_a_stable_order(tmp_path, monkeypatch):
    monkeypatch.setattr("oknowledge.queue._now", lambda: "2026-01-01T00:00:00.000+00:00")
    q = Queue(tmp_path)
    for link_id in ["b", "c", "a"]:
        q.enqueue(link_id, f"https://e.com/{link_id}", "full")
    assert [e.id for e in q.entries()] == ["c", "b", "a"]


def test_the_timestamp_has_sub_second_resolution(tmp_path):
    entry = Queue(tmp_path).enqueue("a", "https://e.com/a", "full")
    assert "." in entry.updated.split("+")[0]


def test_a_malformed_file_costs_only_its_own_entry(tmp_path):
    q = Queue(tmp_path)
    q.enqueue("good1", "https://e.com/1", "full")
    q.enqueue("good2", "https://e.com/2", "full")
    (q.dir / "bad1.json").write_text('{"id": "bad1", "unexpected": 1}', encoding="utf-8")
    (q.dir / "bad2.json").write_text("{not json", encoding="utf-8")
    (q.dir / "bad3.json").write_text("[1, 2]", encoding="utf-8")
    (q.dir / "bad4.json").write_text('{"id": 5, "url": "u", "status": "ok"}', encoding="utf-8")
    assert sorted(e.id for e in q.entries()) == ["good1", "good2"]
    assert q.get("bad1") is None


def test_optional_fields_are_coerced(tmp_path):
    q = Queue(tmp_path)
    q.dir.mkdir(parents=True)
    (q.dir / "x.json").write_text(
        '{"id": "x", "url": "u", "status": "failed", "title": 7, "error": null}',
        encoding="utf-8",
    )
    entry = q.get("x")
    assert entry.content == ""
    assert entry.title == "7"
    assert entry.error is None


def test_an_unknown_status_is_rejected(tmp_path):
    q = Queue(tmp_path)
    q.enqueue("a", "https://e.com/a", "full")
    with pytest.raises(ValueError):
        q.set_status("a", "faild")
    assert q.get("a").status == "pending"


def test_the_status_constants():
    assert STATUSES == frozenset({"pending", "ok", "partial", "failed"})
    assert set(UNFINISHED) == {"partial", "failed"}


def test_a_second_process_cannot_take_the_same_lock(tmp_path):
    q = Queue(tmp_path)
    with q.lock("abc123"):
        with pytest.raises(Locked):
            with q.lock("abc123"):
                pass


def test_the_lock_is_released_even_if_the_work_explodes(tmp_path):
    q = Queue(tmp_path)
    with pytest.raises(ValueError):
        with q.lock("abc123"):
            raise ValueError("boom")
    with q.lock("abc123"):
        pass


def test_a_lock_left_behind_by_a_dead_process_is_taken_over(tmp_path):
    # If the machine went down mid-add, the lock is orphaned.
    q = Queue(tmp_path)
    stale = q.root / "locks" / "abc123.lock"
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_text("999999\n", encoding="utf-8")
    os.utime(stale, (time.time() - 3600, time.time() - 3600))

    with q.lock("abc123", stale_after=900):
        pass


def test_a_lock_taken_over_by_someone_else_is_not_deleted(tmp_path):
    q = Queue(tmp_path)
    path = q.root / "locks" / "abc123.lock"
    with q.lock("abc123"):
        path.write_text("424242\n", encoding="utf-8")   # another process took over
    assert path.read_text(encoding="utf-8") == "424242\n"


def test_a_lock_released_during_the_stat_race_is_free(tmp_path, monkeypatch):
    q = Queue(tmp_path)
    path = q.root / "locks" / "abc123.lock"
    path.parent.mkdir(parents=True)
    path.write_text("1\n", encoding="utf-8")
    real_stat = type(path).stat

    def vanishing_stat(self, *a, **kw):
        if self == path:
            self.unlink()                  # the holder releases it right now
        return real_stat(self, *a, **kw)

    monkeypatch.setattr(type(path), "stat", vanishing_stat)
    with q.lock("abc123"):
        pass


def test_a_failed_write_does_not_leak_the_descriptor(tmp_path, monkeypatch):
    q = Queue(tmp_path)
    closed = []
    real_close = os.close
    monkeypatch.setattr(os, "close", lambda fd: (closed.append(fd), real_close(fd))[1])
    monkeypatch.setattr(os, "write", lambda fd, data: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        with q.lock("abc123"):
            pass
    assert closed
    assert not (q.root / "locks" / "abc123.lock").exists()


def test_an_unknown_id_is_none(tmp_path):
    assert Queue(tmp_path).get("nope") is None
