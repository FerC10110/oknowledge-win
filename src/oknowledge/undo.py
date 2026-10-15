"""What a delete can still take back (spec §6.2).

The notes stay where delete_note() put them, in the vault's trash/: moving
them out of the vault would make the 24-hour expiry a real deletion, and
nothing in this project destroys a note. What lives here is one small JSON
per delete -- which file came from where -- so a Deshacer can put them back.
Forgetting a lot deletes that JSON and never a note.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import re
import secrets
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path

from .atomic import atomic_write
from .config import Config
from .queue import Locked, state_dir
from .vault import ProtectedNote, Trashed, rebuild_indexes, restore_note

log = logging.getLogger(__name__)

LIFETIME = dt.timedelta(hours=24)
"""How long a lot can be used. The toast offers it for 5 s; the rest is for
the no-JS form left open in a tab, and for nothing else."""

TOKEN = re.compile(r"[A-Za-z0-9_-]{22}")
"""secrets.token_urlsafe(16): the only thing that ever names a file here."""

SHELVES = ("links", "ocio", "ideas")


@dataclass(frozen=True)
class UndoResult:
    restored: list[str]
    skipped: list[str]
    shelf: str
    stale: bool = False


def _now(now: dt.datetime | None) -> dt.datetime:
    return now or dt.datetime.now(dt.timezone.utc)


def folder() -> Path:
    return state_dir() / "undo"


def _path(token) -> Path | None:
    if not isinstance(token, str) or not TOKEN.fullmatch(token):
        return None
    return folder() / f"{token}.json"


def _read(path: Path) -> dict | None:
    try:
        lot = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(lot, dict) or not isinstance(lot.get("items"), list):
        return None
    return lot


def _at(lot: dict) -> dt.datetime | None:
    try:
        at = dt.datetime.fromisoformat(str(lot.get("at", "")))
    except ValueError:
        return None
    return at if at.tzinfo is not None else None


def _young(at: dt.datetime, now: dt.datetime) -> bool:
    """Within LIFETIME of `now`, and not after it. A date in the future
    means the clock went back since: no age can be told, and a lot that
    counted as fresh would never expire, so it counts as expired."""
    return dt.timedelta(0) <= now - at <= LIFETIME


def _fresh(lot: dict | None, now: dt.datetime) -> bool:
    at = _at(lot) if lot else None
    return at is not None and _young(at, now)


def remember(cfg: Config, items: list[tuple[str, str, Trashed]],
             now: dt.datetime | None = None) -> str:
    """Write the lot for one delete and return its token. Raises OSError
    when the state dir cannot be written; the delete itself has landed."""
    now = _now(now)
    purge(now)
    root = cfg.root.resolve()
    lot = {"at": now.isoformat(), "items": [
        {"id": link, "shelf": shelf,
         "source": trashed.source.resolve().relative_to(root).as_posix(),
         "target": trashed.target.resolve().relative_to(root).as_posix()}
        for link, shelf, trashed in items]}
    token = secrets.token_urlsafe(16)
    where = folder()
    where.mkdir(parents=True, exist_ok=True)
    atomic_write(where / f"{token}.json", json.dumps(lot, ensure_ascii=False))
    return token


def alive(token, now: dt.datetime | None = None) -> bool:
    """Whether a page may offer Deshacer for this token."""
    path = _path(token)
    return path is not None and _fresh(_read(path), _now(now))


def restore(cfg: Config, token, language: str,
            lock: Callable[[str], AbstractContextManager],
            now: dt.datetime | None = None) -> UndoResult | None:
    """Put a lot's notes back. None if the token names no lot that can be used.

    The JSON is claimed -- deleted -- before anything moves: a second
    Deshacer, from a double click or from the form and the script at once,
    finds nothing instead of racing the first.
    """
    path = _path(token)
    if path is None:
        return None
    lot = _read(path)
    if not _fresh(lot, _now(now)):
        return None
    try:
        path.unlink()
    except FileNotFoundError:
        return None
    restored: list[str] = []
    skipped: list[str] = []
    touched: dict[str, object] = {}
    items = [item for item in lot["items"] if isinstance(item, dict)]
    for item in items:
        link = str(item.get("id", ""))
        name = str(item.get("shelf", ""))
        back = False
        if name in SHELVES and link:
            shelf = cfg.shelf(name)
            try:
                with lock(link):
                    back = restore_note(cfg, link, cfg.root / str(item.get("source", "")),
                                        cfg.root / str(item.get("target", "")),
                                        language, shelf, rebuild=False)
            except (Locked, OSError, ProtectedNote, ValueError) as error:
                log.warning("could not restore %s: %s", link, error)
            except Exception:
                # One note's surprise must not strand the rest of the lot in
                # trash/, nor keep the shelves already back from a rebuild.
                log.exception("could not restore %s", link)
            if back:
                touched[name] = shelf
        (restored if back else skipped).append(link)
    stale = False
    for shelf in touched.values():
        try:
            rebuild_indexes(cfg, language, shelf)
        except OSError as error:
            log.warning("the indexes could not be rebuilt after a restore: %s", error)
            stale = True
        except Exception:
            log.exception("the indexes could not be rebuilt after a restore")
            stale = True
    first = str(items[0].get("shelf", "")) if items else ""
    return UndoResult(restored, skipped, first if first in SHELVES else "links", stale)


def purge(now: dt.datetime | None = None) -> int:
    """Delete the lots older than LIFETIME. Only `<token>.json` files in
    folder(), never a note; a lot that cannot be read goes by its mtime."""
    now = _now(now)
    gone = 0
    try:
        paths = list(folder().glob("*.json"))
    except OSError:
        return 0
    for path in paths:
        if not TOKEN.fullmatch(path.stem):
            continue
        lot = _read(path)
        if lot is not None and _at(lot) is not None:
            if _fresh(lot, now):
                continue
        else:
            try:
                written = dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc)
            except OSError:
                continue
            if _young(written, now):
                continue
        try:
            path.unlink()
            gone += 1
        except FileNotFoundError:
            pass
    return gone
