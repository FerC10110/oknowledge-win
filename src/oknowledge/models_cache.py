"""What each engine answered last time it was asked what models it has.

A list from a month ago is a list, not a lie, as long as it says it is from a
month ago -- so the date is kept beside the names and shown next to the
button. The alternative is asking three engines every time the page opens,
which is up to twelve seconds of waiting for somebody who only wanted to
change the batch size.

It lives in the state dir, outside the vault: it is derived, it is
throwaway, and losing it costs one button press. Which also means a person
can edit it and another tool can write over it, so everything read back here
is checked rather than believed.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from .ai.base import clean_models
from .atomic import atomic_write
from .places import state_dir

FILE = "models.json"


def path() -> Path:
    """Where the cache lives. A function and not a constant: the state dir
    comes from the environment, and a test moves it."""
    return state_dir() / FILE


def _entry(value: object) -> dict | None:
    """One engine's entry, or None if it is not one.

    `found` goes back through the same filter the engines use, so a name
    hand-written into the file is held to what a model name can look like.
    """
    if not isinstance(value, dict):
        return None
    found = value.get("found")
    at = value.get("at")
    return {"found": clean_models(found if isinstance(found, list) else []),
            "at": at if isinstance(at, str) else ""}


def read() -> dict[str, dict]:
    """The whole table: {engine: {"found": [...], "at": "<date>"}}.

    Never raises. A file that is missing, unreadable or not an object is an
    empty table: the box it fills is typable either way.
    """
    try:
        data = json.loads(path().read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, RecursionError):
        return {}
    if not isinstance(data, dict):
        return {}
    kept = {}
    for name, value in data.items():
        entry = _entry(value)
        if isinstance(name, str) and entry is not None:
            kept[name] = entry
    return kept


def remember(engine: str, found: list[str]) -> dict[str, dict]:
    """Write down what `engine` just answered, and give the new table back.

    The other engines' entries are kept: the button asks one engine, and
    rewriting the file wholesale would throw away the answers of the two it
    did not ask. An empty answer is still an answer and is written as one --
    "asked today, found nothing" is worth more than silence.

    Never raises; an empty table means it could not be written.
    """
    table = read()
    table[engine] = {
        "found": clean_models(found),
        "at": dt.datetime.now(dt.timezone.utc).date().isoformat(),
    }
    try:
        path().parent.mkdir(parents=True, exist_ok=True)
        atomic_write(path(), json.dumps(table, ensure_ascii=False, indent=2) + "\n")
    except OSError:
        return {}
    return table
