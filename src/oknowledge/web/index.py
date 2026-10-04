"""The index the web serves: the vault's notes, in memory.

There is no database. refresh() is called on every request, so it must be
cheap: it stats the note files and re-parses the vault only when that
fingerprint changed. A stat per file is far cheaper than a read plus a YAML
parse, and it still picks up a note edited by hand in Obsidian a second ago.
"""

from __future__ import annotations

import os
import unicodedata
from dataclasses import dataclass

from ..config import Config
from ..model import Note
from ..vault import scan_notes

SNIPPET = 160


def fold(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return plain.lower()


@dataclass
class Hit:
    note: Note
    snippet: str


def fingerprint(cfg: Config) -> tuple:
    """One (name, mtime, size) per note file: a stat each, no reads. Raises
    OSError if the folder cannot be listed. A missing folder is an empty vault."""
    try:
        entries = [e for e in os.scandir(cfg.links_dir) if e.name.endswith(".md")]
    except FileNotFoundError:
        return ()
    stats = []
    for entry in entries:
        try:
            info = entry.stat()
        except FileNotFoundError:        # deleted between the listing and the stat
            continue
        stats.append((entry.name, info.st_mtime_ns, info.st_size))
    return tuple(sorted(stats))


class Library:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.notes: list[Note] = []
        self.unreadable = 0          # notes of ours that exist but could not be parsed
        self.error: str | None = None  # why the vault could not be read, if it could not
        self._fingerprint: tuple | None = None
        self.refresh()

    def refresh(self) -> None:
        try:
            current = fingerprint(self.cfg)
            if current == self._fingerprint:
                return
            notes, skipped = scan_notes(self.cfg)
        except OSError as exc:
            self.notes, self.unreadable, self._fingerprint = [], 0, None
            self.error = str(exc)
            return
        self.error = None
        self._fingerprint = current
        self.unreadable = len(skipped)
        self.notes = sorted(notes, key=lambda n: (n.saved, n.title), reverse=True)

    def by_id(self, link_id: str) -> Note | None:
        return next((n for n in self.notes if n.id == link_id), None)

    def filter(self, category: str | None = None, tag: str | None = None) -> list[Note]:
        found = self.notes
        if category:
            found = [n for n in found if n.category == category]
        if tag:
            found = [n for n in found if tag in n.tags]
        return found

    def categories(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for note in self.notes:
            counts[note.category] = counts.get(note.category, 0) + 1
        return dict(sorted(counts.items()))

    def tags(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for note in self.notes:
            for tag in note.tags:
                counts[tag] = counts.get(tag, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))

    def search(self, query: str) -> list[Hit]:
        needle = fold(query).strip()
        if not needle:
            return []
        hits = []
        for note in self.notes:
            haystacks = [note.title, note.summary, " ".join(note.points),
                         " ".join(note.tags), note.category, note.body or ""]
            for text in haystacks:
                position = fold(text).find(needle)
                if position != -1:
                    start = max(0, position - SNIPPET // 2)
                    piece = text[start:start + SNIPPET].strip()
                    hits.append(Hit(note=note, snippet=("…" if start else "") + piece + "…"))
                    break
        return hits
