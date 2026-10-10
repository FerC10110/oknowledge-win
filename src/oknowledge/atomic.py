"""Atomic file writes, shared by the vault and the queue."""

from __future__ import annotations

import os
import secrets
from pathlib import Path

from . import places


def atomic_write(target: Path, text: str, fsync_dir: bool = False) -> None:
    """Write via a temp file in the same directory, then os.replace over target.

    The temp file is created with mode 0o666 so the umask applies to new notes;
    an existing note keeps its current mode. With fsync_dir the directory is
    synced too, so the new entry survives a power cut -- on POSIX. Windows has
    no handle for a directory at all (os.open on one raises PermissionError),
    so there the request is dropped: os.replace is still atomic, and what is
    lost is the promise about a power cut, not the write.
    """
    mode = target.stat().st_mode & 0o777 if target.exists() else None
    tmp = target.parent / f".oknowledge-{secrets.token_hex(8)}.tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, target)
        if fsync_dir and not places.WINDOWS:
            dir_fd = os.open(target.parent, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise
