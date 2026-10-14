"""The state of each link, in files.

Files and not a database because the state has to outlive every process that
touches it, be readable while a run is going, and survive a crash with no
recovery step. A folder of small JSON files does all three, and the lock that
keeps two processes off one link is a lock on a file too -- see locking.py,
which is where the two operating systems differ.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
from contextlib import contextmanager
from pathlib import Path

from . import locking
from .atomic import atomic_write
from .model import QueueEntry
from .places import state_dir

# Room for a pid, so a shorter one written over a longer one leaves no tail.
PID_ROOM = 16

STATUSES = frozenset({"pending", "ok", "partial", "failed"})
UNFINISHED = ("partial", "failed")

_ID = re.compile(r"[A-Za-z0-9_-]+")


class Locked(Exception):
    """Another process is already working on this link."""


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
    # Not held to that rule: the step is a transient a watcher reads, not
    # something that describes the link. A hand-edited one that is not text
    # reads as no step at all rather than stranding the link, which rejecting
    # the entry would do -- and a link `retry` can never see again is the one
    # thing this module does not allow.
    step = data.get("step")
    return QueueEntry(
        id=link_id,
        url=url,
        # A status we do not know (a hand edit) must stay retryable, not stranded.
        status=status if status in STATUSES else "failed",
        content=fields["content"] or "",
        updated=fields["updated"] or "",
        title=fields["title"],
        error=fields["error"],
        step=step if isinstance(step, str) else "",
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
            "title": entry.title, "error": entry.error, "step": entry.step,
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
        # A status is where a link stops being worked on, so whatever it was
        # in the middle of, it is not any more.
        entry.step = ""
        if error is not None:
            entry.error = error
        if title is not None:
            entry.title = title
        return self._write(entry)

    def set_step(self, link_id: str, step: str) -> None:
        """Say what is being done to this link right now, for whoever watches.

        Never raises, and never returns a problem either: this is told between
        the stages of a run that is holding a model open, and nothing about it
        may reach the link. A link with no entry yet -- the first stage runs
        before `add()` has written one -- is simply not told about.

        It also keeps `updated` moving, which is what lets a watcher tell a
        thirty-second analysis from a run that died: the panel calls an entry
        "working" only while its clock is fresh.
        """
        try:
            entry = self.get(link_id)
            if entry is None:
                return
            entry.step = step
            entry.updated = _now()
            self._write(entry)
        except (OSError, ValueError):
            return

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
        orphans = []
        for entry in self.entries():
            if entry.status != "pending":
                continue
            try:
                held = self.held(entry.id)
            except OSError:
                # A lock file we cannot probe (root-owned after a sudo run, say)
                # leaves us not knowing whether a process holds it. Calling it
                # free risks two processes writing one note; calling it held
                # costs this one link a retry cycle. So: held, and carry on.
                held = True
            if not held:
                orphans.append(entry)
        return orphans

    def _lock_path(self, link_id: str) -> Path:
        return self.root / "locks" / f"{_check_id(link_id)}.lock"

    def held(self, link_id: str) -> bool:
        """Whether some live process is working on this link right now.

        The lock belongs to the open file and the system drops it when the
        holder dies, so a true here is never stale: there is no timeout to
        guess at and no crashed run left looking busy forever.

        Opened for writing even though nothing is written: Windows cannot lock
        a read-only handle, and the probe there has to take the lock for an
        instant because msvcrt has no shared mode.
        """
        try:
            fd = os.open(self._lock_path(link_id), os.O_RDWR)
        except FileNotFoundError:
            return False
        try:
            return locking.probe(fd)
        finally:
            os.close(fd)                    # closing releases anything we took

    def busy(self) -> list[QueueEntry]:
        """Pending entries some live process holds now: the ones really being
        worked on. A pending entry nobody holds is owed work, not work."""
        locks = self.root / "locks"
        if not locks.is_dir():
            return []
        found = []
        # Probe the lock files, not the entries: entries are never pruned, so
        # reading them all would cost the whole library on every request.
        for path in locks.glob("*.lock"):
            if not _ID.fullmatch(path.stem):
                continue
            try:
                if not self.held(path.stem):
                    continue
            except OSError:
                continue
            entry = self.get(path.stem)
            if entry is not None and entry.status == "pending":
                found.append(entry)
        found.sort(key=lambda e: (e.updated, e.id), reverse=True)
        return found

    @contextmanager
    def lock(self, link_id: str):
        """Hold an exclusive lock on a link for the with block.

        The lock belongs to the open file, and the system drops it when the
        process dies, so there is no staleness to detect. The lock file is
        never deleted: unlinking it while another process has it open would let
        two processes hold "the" lock on two different files.
        """
        path = self._lock_path(link_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o666)
        try:
            if not locking.take(fd):
                raise Locked(f"{link_id} is already being processed")
            # Diagnostics only: nothing reads the pid to decide anything.
            # Padded to a fixed width instead of truncating the file, because
            # the lock on Windows is on byte 0 and shortening a file under a
            # lock is a thing that can fail. Writing over a byte we hold the
            # lock on is not. The handle is fresh and neither lock takes a
            # position with it, so this writes at byte 0 with no seek.
            os.write(fd, f"{os.getpid()}".ljust(PID_ROOM).encode() + b"\n")
            yield
        finally:
            os.close(fd)
