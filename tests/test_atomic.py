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


def test_an_existing_files_mode_survives_a_rewrite(tmp_path):
    """The docstring promises it and config.save's 0600 depends on nothing else
    loosening it. The temp file is created 0o666 minus the umask, so without
    the chmod the rewrite would widen a 0600 file."""
    target = tmp_path / "a.txt"
    atomic_write(target, "first")
    target.chmod(0o600)

    atomic_write(target, "second")

    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert target.read_text(encoding="utf-8") == "second"


def test_a_new_file_is_left_to_the_umask(tmp_path):
    """The other half of the same line: nothing is chmodded on a first write."""
    target = tmp_path / "b.txt"
    atomic_write(target, "x")
    expected = 0o666 & ~_umask()
    assert stat.S_IMODE(target.stat().st_mode) == expected


def _umask():
    current = os.umask(0o022)
    os.umask(current)
    return current
