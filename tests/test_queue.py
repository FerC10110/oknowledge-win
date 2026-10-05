import os
import stat
import time

import pytest

from oknowledge.queue import STATUSES, UNFINISHED, Locked, Queue, state_dir


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
    (q.dir / "bad4.json").write_text('{"url": 5, "status": "ok"}', encoding="utf-8")
    assert sorted(e.id for e in q.entries()) == ["good1", "good2"]
    assert q.get("bad1") is None


def test_missing_optional_fields_get_defaults(tmp_path):
    q = Queue(tmp_path)
    q.dir.mkdir(parents=True)
    (q.dir / "x.json").write_text(
        '{"url": "u", "status": "failed", "error": null}', encoding="utf-8",
    )
    entry = q.get("x")
    assert entry.content == ""
    assert entry.title is None
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


def test_a_lock_file_left_behind_by_a_dead_process_is_acquired(tmp_path):
    # flock dies with its process: a leftover file has no lock held on it.
    q = Queue(tmp_path)
    leftover = q.root / "locks" / "abc123.lock"
    leftover.parent.mkdir(parents=True, exist_ok=True)
    leftover.write_text("999999\n", encoding="utf-8")
    os.utime(leftover, (time.time() - 3600, time.time() - 3600))

    with q.lock("abc123"):
        assert leftover.read_text(encoding="utf-8").strip() == str(os.getpid())


def test_the_lock_file_is_never_deleted(tmp_path):
    q = Queue(tmp_path)
    with q.lock("abc123"):
        pass
    assert (q.root / "locks" / "abc123.lock").exists()


def test_a_live_process_in_another_process_holds_the_lock(tmp_path):
    q = Queue(tmp_path)
    ready_r, ready_w = os.pipe()
    release_r, release_w = os.pipe()
    pid = os.fork()
    if pid == 0:                                   # child: hold the lock
        code = 1
        try:
            os.close(ready_r)
            os.close(release_w)
            with q.lock("abc123"):
                os.write(ready_w, b"x")
                os.read(release_r, 1)
            code = 0
        finally:
            os._exit(code)
    os.close(ready_w)
    os.close(release_r)
    try:
        assert os.read(ready_r, 1) == b"x"
        with pytest.raises(Locked):
            with q.lock("abc123"):
                pass
    finally:
        os.write(release_w, b"x")
        _, status = os.waitpid(pid, 0)
        os.close(ready_r)
        os.close(release_w)
    assert status == 0
    with q.lock("abc123"):                         # released when the holder is gone
        pass


def test_a_failed_pid_write_closes_the_lock_descriptor(tmp_path, monkeypatch):
    q = Queue(tmp_path)
    written, closed = [], []
    real_close = os.close

    def boom(fd, data):
        written.append(fd)
        raise OSError("disk full")

    monkeypatch.setattr(os, "write", boom)
    monkeypatch.setattr(os, "close", lambda fd: (closed.append(fd), real_close(fd))[1])
    with pytest.raises(OSError):
        with q.lock("abc123"):
            pass
    assert len(written) == 1 and written[0] in closed
    monkeypatch.undo()
    with q.lock("abc123"):                         # and the lock is free again
        pass


def test_orphaned_is_pending_without_a_live_holder(tmp_path):
    q = Queue(tmp_path)
    for link_id in ["held", "dead", "never", "done"]:
        q.enqueue(link_id, f"https://e.com/{link_id}", "full")
    q.set_status("done", "ok")
    with q.lock("dead"):
        pass                                       # lock file exists, nobody holds it
    with q.lock("held"):
        assert sorted(e.id for e in q.orphaned()) == ["dead", "never"]
    assert sorted(e.id for e in q.orphaned()) == ["dead", "held", "never"]
    assert [e.id for e in q.unfinished()] == []
    with q.lock("dead"):                           # orphaned() did not keep a lock
        pass


def test_ids_that_are_not_plain_tokens_are_rejected(tmp_path):
    q = Queue(tmp_path)
    for bad in ["../esc", "/tmp/x", "a/b", "", "a.b", "a b"]:
        with pytest.raises(ValueError):
            q.enqueue(bad, "https://e.com/x", "full")
        with pytest.raises(ValueError):
            with q.lock(bad):
                pass
    assert not (tmp_path / "esc.json").exists()


def test_the_filename_is_the_id(tmp_path):
    q = Queue(tmp_path)
    q.enqueue("abc", "https://e.com/x", "full")
    (q.dir / "copy.json").write_text((q.dir / "abc.json").read_text(encoding="utf-8"),
                                     encoding="utf-8")
    q.set_status("copy", "failed")
    assert q.get("copy").status == "failed"
    assert q.get("copy").id == "copy"
    assert q.get("abc").status == "pending"


def test_deeply_nested_json_costs_one_entry(tmp_path):
    q = Queue(tmp_path)
    q.enqueue("good", "https://e.com/x", "full")
    (q.dir / "deep.json").write_text("[" * 200000, encoding="utf-8")
    assert [e.id for e in q.entries()] == ["good"]


def test_an_unknown_status_on_read_is_retryable(tmp_path):
    q = Queue(tmp_path)
    q.dir.mkdir(parents=True)
    (q.dir / "x.json").write_text('{"url": "u", "status": "Failed"}', encoding="utf-8")
    assert q.get("x").status == "failed"
    assert [e.id for e in q.unfinished()] == ["x"]


def test_a_non_string_optional_field_rejects_the_entry(tmp_path):
    q = Queue(tmp_path)
    q.dir.mkdir(parents=True)
    (q.dir / "x.json").write_text('{"url": "u", "status": "ok", "title": {"a": 1}}',
                                  encoding="utf-8")
    assert q.get("x") is None


def test_stray_things_in_the_queue_dir_are_ignored(tmp_path):
    q = Queue(tmp_path)
    q.enqueue("good", "https://e.com/x", "full")
    (q.dir / "x.json").mkdir()
    (q.dir / "dangling.json").symlink_to(tmp_path / "nowhere")
    (q.dir / ".oknowledge-abc.tmp").write_text("{", encoding="utf-8")
    (q.dir / "has space.json").write_text('{"url": "u", "status": "ok"}', encoding="utf-8")
    assert [e.id for e in q.entries()] == ["good"]


def test_a_relative_state_home_is_ignored(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_STATE_HOME", "relative/dir")
    assert state_dir() == tmp_path / ".local" / "state" / "oknowledge"
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "abs"))
    assert state_dir() == tmp_path / "abs" / "oknowledge"


def test_the_queue_syncs_the_directory_entry(tmp_path, monkeypatch):
    synced = []
    real = os.fsync
    monkeypatch.setattr(os, "fsync", lambda fd: (synced.append(os.fstat(fd).st_mode), real(fd))[1])
    Queue(tmp_path).enqueue("a", "https://e.com/a", "full")
    assert any(stat.S_ISDIR(m) for m in synced)


def test_an_unknown_id_is_none(tmp_path):
    assert Queue(tmp_path).get("nope") is None


def test_a_lookup_of_a_malformed_id_is_just_a_miss(tmp_path):
    # The id arrives straight from a web route, so "not found" is the honest
    # answer; only the write paths treat a bad id as a bug.
    q = Queue(tmp_path)
    for bogus in ["../escape", "/etc/passwd", "a b", ""]:
        assert q.get(bogus) is None


def test_writing_through_a_malformed_id_is_refused(tmp_path):
    q = Queue(tmp_path)
    for bogus in ["../escape", "/etc/passwd"]:
        with pytest.raises(ValueError):
            q.enqueue(bogus, "https://e.com/x", "full")
        with pytest.raises(ValueError):
            q.set_status(bogus, "ok")
        with pytest.raises(ValueError):
            with q.lock(bogus):
                pass


def test_no_test_can_reach_the_real_state_tree(tmp_path):
    """conftest pins XDG_STATE_HOME for every test, not only for the files
    whose tests mean to touch the queue. Asserted here because this is the
    module that owns the state tree."""
    import pathlib

    assert state_dir().is_relative_to(tmp_path)
    assert not state_dir().is_relative_to(pathlib.Path.home() / ".local" / "state")
    assert os.environ["XDG_STATE_HOME"].startswith(str(tmp_path))
