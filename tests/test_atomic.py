import os
import stat

from oknowledge.atomic import atomic_write


def _synced_kinds(monkeypatch):
    synced = []
    real = os.fsync
    monkeypatch.setattr(os, "fsync", lambda fd: (synced.append(os.fstat(fd).st_mode), real(fd))[1])
    return synced


def test_the_directory_is_not_synced_by_default(tmp_path, monkeypatch):
    synced = _synced_kinds(monkeypatch)
    atomic_write(tmp_path / "a.txt", "x")
    assert not any(stat.S_ISDIR(m) for m in synced)


def test_the_directory_is_synced_on_request(tmp_path, monkeypatch):
    synced = _synced_kinds(monkeypatch)
    atomic_write(tmp_path / "a.txt", "x", fsync_dir=True)
    assert any(stat.S_ISDIR(m) for m in synced)
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "x"
