"""The state of each link, in files, so the widget can read it.

Files and not a database for a concrete reason: the Omarchy plugin is QML and
can watch a folder with a FolderListModel, but it cannot open a database.
"""

from __future__ import annotations

import datetime as dt
import errno
import fcntl
import json
import os
import re
from contextlib import contextmanager
from pathlib import Path

from .atomic import atomic_write
from .model import QueueEntry

STATUSES = frozenset({"pending", "ok", "partial", "failed"})
UNFINISHED = ("partial", "failed")

_ID = re.compile(r"[A-Za-z0-9_-]+")


class Locked(Exception):
    """Another process is already working on this link."""


def state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME", "")
    if not base or not os.path.isabs(base):        # the XDG spec: relative means unset
        base = str(Path.home() / ".local" / "state")
    return Path(base) / "oknowledge"


def _now() -> str:
    # Milliseconds: links enqueued in the same second must still order.
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")


def _check_id(link_id: str) -> str:
    if not _ID.fullmatch(link_id):
        raise ValueError(f"invalid link id: {link_id!r}")
    return link_id


def _entry_from(link_id: str, data: object) -> QueueEntry | None:
    """Build an entry from decoded JSON, or None if it does not fit.

    The filename is the index, so the id comes from it and not from the file.
    """
    if not isinstance(data, dict):
        return None
    url, status = data.get("url"), data.get("status")
    if not isinstance(url, str) or not isinstance(status, str):
        return None
    fields = {key: data.get(key) for key in ("content", "updated", "title", "error")}
    if any(v is not None and not isinstance(v, str) for v in fields.values()):
        return None
    return QueueEntry(
        id=link_id,
        url=url,
        # A status we do not know (a hand edit) must stay retryable, not stranded.
        status=status if status in STATUSES else "failed",
        content=fields["content"] or "",
        updated=fields["updated"] or "",
        title=fields["title"],
        error=fields["error"],
    )


class Queue:
    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root else state_dir()

    @property
    def dir(self) -> Path:
        return self.root / "queue"

    def _path(self, link_id: str) -> Path:
        return self.dir / f"{_check_id(link_id)}.json"

    def _write(self, entry: QueueEntry) -> QueueEntry:
        self.dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "id": entry.id, "url": entry.url, "content": entry.content,
            "status": entry.status, "updated": entry.updated,
            "title": entry.title, "error": entry.error,
        }
        atomic_write(self._path(entry.id),
                     json.dumps(payload, ensure_ascii=False, indent=2), fsync_dir=True)
        return entry

    def enqueue(self, link_id: str, url: str, content: str) -> QueueEntry:
        return self._write(QueueEntry(
            id=link_id, url=url, content=content, status="pending", updated=_now(),
        ))

    def get(self, link_id: str) -> QueueEntry | None:
        # A lookup answers "no such entry" for a malformed id instead of raising:
        # the id reaches here straight from a web route, and "not found" is the
        # honest answer. The write paths below still reject it loudly.
        if not _ID.fullmatch(link_id):
            return None
        path = self._path(link_id)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, RecursionError):
            return None
        return _entry_from(link_id, data)

    def set_status(self, link_id: str, status: str, error: str | None = None,
                   title: str | None = None) -> QueueEntry | None:
        if status not in STATUSES:
            raise ValueError(f"unknown status {status!r}; expected one of {sorted(STATUSES)}")
        _check_id(link_id)
        entry = self.get(link_id)
        if entry is None:
            return None
        entry.status = status
        entry.updated = _now()
        if error is not None:
            entry.error = error
        if title is not None:
            entry.title = title
        return self._write(entry)

    def entries(self) -> list[QueueEntry]:
        if not self.dir.is_dir():
            return []
        found = [self.get(p.stem) for p in self.dir.glob("*.json") if _ID.fullmatch(p.stem)]
        alive = [e for e in found if e is not None]
        return sorted(alive, key=lambda e: (e.updated, e.id), reverse=True)

    def unfinished(self) -> list[QueueEntry]:
        return [e for e in self.entries() if e.status in UNFINISHED]

    def orphaned(self) -> list[QueueEntry]:
        """Pending entries that no live process holds a lock on.

        A process that died between enqueue and its final set_status leaves the
        entry pending forever; unfinished() would never retry it. A link that
        was enqueued a moment ago and not yet locked also shows up here.
        """
        return [e for e in self.entries()
                if e.status == "pending" and not self._held(e.id)]

    def _lock_path(self, link_id: str) -> Path:
        return self.root / "locks" / f"{_check_id(link_id)}.lock"

    def _held(self, link_id: str) -> bool:
        try:
            fd = os.open(self._lock_path(link_id), os.O_RDONLY)
        except FileNotFoundError:
            return False
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except OSError as err:
            if err.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
                return True
            raise
        finally:
            os.close(fd)                    # closing releases anything we took
        return False

    @contextmanager
    def lock(self, link_id: str):
        """Hold an exclusive advisory lock on a link for the with block.

        flock belongs to the open file, and the kernel drops it when the process
        dies, so there is no staleness to detect. The lock file is never
        deleted: unlinking it while another process opens it would let two
        processes hold "the" lock on different inodes.
        """
        path = self._lock_path(link_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o666)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as err:
                if err.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
                    raise Locked(f"{link_id} is already being processed") from None
                raise
            # Diagnostics only: nothing reads the pid to decide anything.
            os.ftruncate(fd, 0)
            os.write(fd, f"{os.getpid()}\n".encode())
            yield
        finally:
            os.close(fd)
