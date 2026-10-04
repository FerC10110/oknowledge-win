"""The state of each link, in files, so the widget can read it.

Files and not a database for a concrete reason: the Omarchy plugin is QML and
can watch a folder with a FolderListModel, but it cannot open a database.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import time
from contextlib import contextmanager
from pathlib import Path

from .atomic import atomic_write
from .model import QueueEntry

STATUSES = frozenset({"pending", "ok", "partial", "failed"})
UNFINISHED = ("partial", "failed")


class Locked(Exception):
    """Another process is already working on this link."""


def state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local" / "state")
    return Path(base) / "oknowledge"


def _now() -> str:
    # Milliseconds: links enqueued in the same second must still order.
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")


def _optional_text(value: object) -> str | None:
    return None if value is None else str(value)


def _entry_from(data: object) -> QueueEntry | None:
    """Build an entry from decoded JSON, or None if it does not fit."""
    if not isinstance(data, dict):
        return None
    required = [data.get(key) for key in ("id", "url", "status")]
    if not all(isinstance(value, str) for value in required):
        return None
    link_id, url, status = required
    return QueueEntry(
        id=link_id,
        url=url,
        content=_optional_text(data.get("content")) or "",
        status=status,
        updated=_optional_text(data.get("updated")) or "",
        title=_optional_text(data.get("title")),
        error=_optional_text(data.get("error")),
    )


class Queue:
    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root else state_dir()

    @property
    def dir(self) -> Path:
        return self.root / "queue"

    def _path(self, link_id: str) -> Path:
        return self.dir / f"{link_id}.json"

    def _write(self, entry: QueueEntry) -> QueueEntry:
        self.dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "id": entry.id, "url": entry.url, "content": entry.content,
            "status": entry.status, "updated": entry.updated,
            "title": entry.title, "error": entry.error,
        }
        atomic_write(self._path(entry.id), json.dumps(payload, ensure_ascii=False, indent=2))
        return entry

    def enqueue(self, link_id: str, url: str, content: str) -> QueueEntry:
        return self._write(QueueEntry(
            id=link_id, url=url, content=content, status="pending", updated=_now(),
        ))

    def get(self, link_id: str) -> QueueEntry | None:
        try:
            data = json.loads(self._path(link_id).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return _entry_from(data)

    def set_status(self, link_id: str, status: str, error: str | None = None,
                   title: str | None = None) -> QueueEntry | None:
        if status not in STATUSES:
            raise ValueError(f"unknown status {status!r}; expected one of {sorted(STATUSES)}")
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
        found = [self.get(p.stem) for p in self.dir.glob("*.json")]
        alive = [e for e in found if e is not None]
        return sorted(alive, key=lambda e: (e.updated, e.id), reverse=True)

    def unfinished(self) -> list[QueueEntry]:
        return [e for e in self.entries() if e.status in UNFINISHED]

    @contextmanager
    def lock(self, link_id: str, stale_after: int = 900):
        path = self.root / "locks" / f"{link_id}.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        self._acquire(path, link_id, stale_after)
        try:
            yield
        finally:
            # Only release a lock that is still ours: if the work outran
            # stale_after, another process may have legitimately taken over.
            try:
                if path.read_text(encoding="utf-8").strip() == str(os.getpid()):
                    path.unlink(missing_ok=True)
            except OSError:
                pass

    @staticmethod
    def _acquire(path: Path, link_id: str, stale_after: int) -> None:
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        try:
            handle = os.open(path, flags)
        except FileExistsError:
            try:
                age = time.time() - path.stat().st_mtime
            except FileNotFoundError:
                age = stale_after              # released in between: it is free
            if age < stale_after:
                raise Locked(f"{link_id} is already being processed") from None
            path.unlink(missing_ok=True)       # left behind by a process that is gone
            try:
                handle = os.open(path, flags)
            except FileExistsError:
                raise Locked(f"{link_id} is already being processed") from None
        try:
            os.write(handle, f"{os.getpid()}\n".encode())
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        finally:
            os.close(handle)
