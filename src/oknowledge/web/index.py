"""The index the web serves: the vault's notes, in memory.

There is no database. refresh() is called on every request, so it is cheap:
it stats the note files and re-parses only those whose (mtime, size) changed.
A stat per file is far cheaper than a read plus a YAML parse, and it still
picks up a note edited by hand in Obsidian a second ago.

The entries held here are LIST VIEWS: their notes have `body=None`. Only a
pre-folded searchable string is kept per note, so search does no folding at
request time and the extracted article text is not held in memory. Anything
that needs the body (the item page, a snippet taken from it) reads that one
file fresh from disk with read_full().
"""

from __future__ import annotations

import os
import re
import threading
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from ..config import Config
from ..model import Note
from ..urls import is_search_url
from ..vault import read_note, scan_file

SNIPPET = 160
PER_PAGE = 100

# A note whose `saved` is not a date. The field is text in a file the user can
# edit, and a note nobody can date must still be somewhere you can get to: a
# link that no filter can reach is a link that is lost. The vault already
# names such a note undated-<title>.md.
UNDATED = "undated"
# The shape a date has to have. The month is checked against the twelve that
# exist, because the strip gives each one a name and there is no name for the
# thirteenth.
DATED = re.compile(r"\d{4}-(?:0[1-9]|1[0-2])-\d{2}\Z")


def period_of(saved: str, size: int = 4) -> str:
    """The year ("2021") or the month ("2021-11") a note belongs to.

    `size` is how much of the date to keep: 4 for the year, 7 for the month.
    A date that cannot be read belongs to no period and answers UNDATED for
    every size, so it never lands in a year it is not from.
    """
    return saved[:size] if DATED.match(saved or "") else UNDATED

# Latin letters that do not decompose under NFD, so accent-stripping alone
# would leave them unsearchable from a plain keyboard.
EXTRA = {"ø": "o", "ł": "l", "đ": "d", "ð": "d", "þ": "th", "ħ": "h", "ı": "i",
         "ß": "ss", "æ": "ae", "œ": "oe"}
# Japanese voicing marks are part of the letter, not an accent.
_KEEP_MARKS = {"゙", "゚"}


_FOLDED: dict[str, str] = {}


def _fold_char(char: str) -> str:
    """One character's folded form, memoised: a vault repeats few distinct characters."""
    piece = _FOLDED.get(char)
    if piece is None:
        if char.isspace():
            piece = " "
        else:
            piece = ""
            for lowered in char.casefold():
                lowered = EXTRA.get(lowered, lowered)
                decomposed = unicodedata.normalize("NFD", lowered)
                piece += decomposed[0] + "".join(
                    c for c in decomposed[1:]
                    if unicodedata.category(c) != "Mn" or c in _KEEP_MARKS)
            piece = unicodedata.normalize("NFC", piece)
        _FOLDED[char] = piece
    return piece


def fold_map(text: str) -> tuple[str, list[int]]:
    """(folded text, for each folded character the index it came from in `text`).

    Folding is case-insensitive and drops the accents a character decomposes
    into (a -> a, n -> n); every other script is left as it is. Whitespace of
    any kind, newlines included, becomes one space. Working character by
    character is what lets an offset in the folded text always map home.
    """
    out: list[str] = []
    home: list[int] = []
    for i, char in enumerate(text):
        piece = _fold_char(char)
        out.append(piece)
        home.extend([i] * len(piece))
    return "".join(out), home


_ASCII_SPACE = str.maketrans({c: " " for c in "\t\n\r\x0b\x0c\x1c\x1d\x1e\x1f\x85"})


def fold(text: str) -> str:
    if text.isascii():            # the common case, and the one worth being fast at
        return text.lower().translate(_ASCII_SPACE)
    return "".join(map(_fold_char, text))


def terms(query: str) -> list[str]:
    """The folded words of a query; a leading # (as tags are displayed) is dropped."""
    found = (word.lstrip("#") for word in fold(query).split())
    return [word for word in found if word]


def tally(notes) -> dict[str, int]:
    """How many of `notes` fall in each year and each month.

    Counted over the notes that passed the other filters, not over the whole
    library: with a collection chosen, the strip is meant to say which years
    that project lives in.
    """
    found: dict[str, int] = {}
    for note in notes:
        year = period_of(note.saved)
        found[year] = found.get(year, 0) + 1
        if year != UNDATED:
            month = period_of(note.saved, 7)
            found[month] = found.get(month, 0) + 1
    return found


@dataclass
class Hit:
    note: Note
    snippet: str


@dataclass
class Entry:
    note: Note                        # a list view: body is None
    path: Path
    mtime_ns: int
    tiers: tuple[str, str, str, str, str]  # folded: title+tags,
                                      # category+summary+points, mentions,
                                      # source+author+url, body


def _mention_text(note: Note) -> str:
    """What a video named, as one searchable block: every name, and the URLs
    that came out of the video itself.

    A name nobody gave a link to carries a search URL instead, and every one of
    those shares a host. Folding them in would make one query ("duckduckgo")
    return every video that ever named something without a link, so only a real
    URL goes in -- which is also the only kind worth searching by domain.
    """
    parts: list[str] = []
    for mention in note.mentions or []:
        parts.append(mention.name)
        if not is_search_url(mention.url):
            parts.append(mention.url)
    return "\n".join(parts)


def _entry(path: Path, note: Note, mtime_ns: int) -> Entry:
    tiers = (
        # The collections share the top tier with the title and the tags:
        # they are the only words in a note the user chose themselves.
        "\n".join([note.title, *note.tags, *note.collections]),
        "\n".join([note.category, note.summary, *note.points]),
        # What the video talked about: weaker than the summary, which says what
        # the note IS about, and stronger than one word passing by in a
        # transcript. A note with no mentions contributes "", which no term
        # matches, because terms() never yields an empty word.
        _mention_text(note),
        "\n".join(filter(None, [note.source, note.author, note.url])),
        note.body or "",
    )
    note.body = None
    return Entry(note=note, path=path, mtime_ns=mtime_ns,
                 tiers=tuple(fold(t) for t in tiers))


def read_full(entry: Entry) -> Note:
    """The note with its body, fresh from disk (the index does not hold bodies)."""
    return read_note(entry.path) or entry.note


def snippet_of(text: str, term: str) -> str | None:
    """A window of the ORIGINAL text around the first match of a folded term."""
    folded = fold(text)
    position = folded.find(term)
    if position == -1:
        return None
    if len(folded) == len(text):         # every character folded to one: offsets are identical
        match_start, match_end = position, position + len(term)
    else:
        home = fold_map(text)[1]
        match_start = home[position]
        match_end = home[position + len(term) - 1] + 1
    start = max(0, match_start - SNIPPET // 2)
    end = max(start + SNIPPET, match_end)
    piece = " ".join(text[start:end].split())
    return ("…" if start else "") + piece + "…"


def fingerprint(cfg: Config) -> dict[str, tuple[int, int]]:
    """name -> (mtime_ns, size) for every note file: a stat each, no reads.

    Raises OSError if the vault cannot be listed. A vault folder that has
    vanished is an error (it was moved or unmounted), not an empty library;
    only a missing links/ folder under an existing root means nothing is saved.
    """
    if not cfg.root.is_dir():
        raise FileNotFoundError(f"{cfg.root} does not exist")
    try:
        entries = [e for e in os.scandir(cfg.links_dir) if e.name.endswith(".md")]
    except FileNotFoundError:
        return {}
    stats = {}
    for entry in entries:
        try:
            info = entry.stat()
        except FileNotFoundError:        # deleted between the listing and the stat
            continue
        stats[entry.name] = (info.st_mtime_ns, info.st_size)
    return stats


class Library:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.entries: list[Entry] = []
        self.unreadable = 0              # notes of ours that exist but could not be parsed
        self.error: str | None = None    # why the vault could not be read, if it could not
        self._lock = threading.Lock()
        self._fingerprint: dict[str, tuple[int, int]] | None = None
        self._cache: dict[str, tuple[tuple[int, int], Entry | None]] = {}
        self._ids: dict[str, Entry] = {}
        self._categories: dict[str, int] = {}
        self._tags: dict[str, int] = {}
        self._tag_home: dict[str, str] = {}
        self._collections: dict[str, int] = {}
        self._years: dict[str, int] = {}
        self._months: dict[str, int] = {}
        self.refresh()

    @property
    def notes(self) -> list[Note]:
        """List views: `body` is None. Use read_full(entry) for the text."""
        return [e.note for e in self.entries]

    def refresh(self) -> None:
        with self._lock:          # sync routes run in a threadpool
            self._refresh()

    def _refresh(self) -> None:
        try:
            current = fingerprint(self.cfg)
            if current == self._fingerprint:
                return
            cache = {}
            for name, sig in current.items():
                old = self._cache.get(name)
                if old is not None and old[0] == sig:
                    cache[name] = old
                    continue
                path = self.cfg.links_dir / name
                note, _ = scan_file(path)
                cache[name] = (sig, _entry(path, note, sig[0]) if note else None)
        except OSError as exc:
            self.entries, self.unreadable = [], 0
            self._fingerprint, self._cache, self._ids = None, {}, {}
            self._categories, self._tags, self._tag_home = {}, {}, {}
            self._collections = {}
            self._years, self._months = {}, {}
            self.error = str(exc)
            return
        entries = [e for _, e in cache.values() if e is not None]
        # `saved` is date-only; the file time orders notes saved the same day.
        entries.sort(key=lambda e: (e.note.saved, e.mtime_ns, e.note.title), reverse=True)
        categories: dict[str, int] = {}
        tags: dict[str, int] = {}
        # Where each tag is used, so the chips can sit beside the ones they
        # are about instead of in one alphabetical wall.
        homes: dict[str, dict[str, int]] = {}
        collections: dict[str, int] = {}
        years: dict[str, int] = {}
        months: dict[str, int] = {}
        ids: dict[str, Entry] = {}
        for entry in entries:
            year = period_of(entry.note.saved)
            years[year] = years.get(year, 0) + 1
            if year != UNDATED:
                month = period_of(entry.note.saved, 7)
                months[month] = months.get(month, 0) + 1
            categories[entry.note.category] = categories.get(entry.note.category, 0) + 1
            for name in entry.note.collections:
                collections[name] = collections.get(name, 0) + 1
            for tag in entry.note.tags:
                tags[tag] = tags.get(tag, 0) + 1
                seen = homes.setdefault(tag, {})
                seen[entry.note.category] = seen.get(entry.note.category, 0) + 1
            ids.setdefault(entry.note.id, entry)
        # Publish everything together, after the work that can fail.
        self.error = None
        self._cache, self._fingerprint = cache, current
        self.unreadable = sum(1 for _, e in cache.values() if e is None)
        self.entries, self._ids = entries, ids
        self._categories = dict(sorted(categories.items()))
        # By name, like the categories: these are the user's own buckets, and
        # one that moved every time they filed something would be a bucket
        # they have to look for.
        self._collections = dict(sorted(collections.items()))
        # Newest first, like the notes themselves. Undated is not a year and
        # does not sort like one: it goes last, on its own, at the foot of
        # the strip.
        ordered = sorted((name for name in years if name != UNDATED), reverse=True)
        self._years = {name: years[name] for name in ordered + (
            [UNDATED] if UNDATED in years else [])}
        self._months = dict(sorted(months.items(), reverse=True))
        self._tags = dict(sorted(tags.items(), key=lambda kv: (-kv[1], kv[0])))
        # Most used wins, and the category name breaks a tie: a chip that moved
        # between groups on every reload, for a reason nobody could see, would
        # be worse than no grouping at all.
        self._tag_home = {tag: min(seen, key=lambda name: (-seen[name], name))
                          for tag, seen in homes.items()}

    def entry(self, link_id: str) -> Entry | None:
        return self._ids.get(link_id)

    def by_id(self, link_id: str) -> Note | None:
        entry = self.entry(link_id)
        return entry.note if entry else None

    def filter(self, category: str | None = None, tag: str | None = None,
               collection: str | None = None, when: str | None = None) -> list[Note]:
        found = self.notes
        if category:
            found = [n for n in found if n.category == category]
        if tag:
            found = [n for n in found if tag in n.tags]
        if collection:
            found = [n for n in found if collection in n.collections]
        if when:
            # Checked against the periods this library has, not matched as a
            # prefix: "2021-1" is not a month, and a prefix would quietly
            # hand back October to December as if it were one.
            if when not in self.periods():
                return []
            found = [n for n in found if period_of(n.saved, len(when)) == when]
        return found

    def categories(self) -> dict[str, int]:
        return self._categories

    def tags(self) -> dict[str, int]:
        return self._tags

    def collections(self) -> dict[str, int]:
        """The user's own groupings, and how many notes each one holds."""
        return self._collections

    def years(self) -> dict[str, int]:
        """Every year the library holds, newest first, undated last."""
        return self._years

    def months(self) -> dict[str, int]:
        """Every month the library holds, newest first."""
        return self._months

    def periods(self) -> set[str]:
        """What `when` is allowed to name."""
        return set(self._years) | set(self._months)

    def tag_home(self) -> dict[str, str]:
        """The category each tag is most used under."""
        return self._tag_home

    def search(self, query: str, page: int = 1, per_page: int = PER_PAGE
               ) -> tuple[list[Hit], int]:
        """(the hits on this page, the total number of hits).

        A note matches when every term of the query is somewhere in it. Hits
        rank by where the terms were found (title and tags, then category,
        summary and points, then what a video mentioned, then source, author
        and url, then body); entries are already newest first and the sort is
        stable, so date breaks ties.
        """
        words = terms(query)
        if not words:
            return [], 0
        ranked: list[tuple[int, Entry]] = []
        for entry in self.entries:
            score = 0
            for word in words:
                tier = next((i for i, text in enumerate(entry.tiers) if word in text), None)
                if tier is None:
                    break
                score += tier
            else:
                ranked.append((score, entry))
        ranked.sort(key=lambda pair: pair[0])
        start = (page - 1) * per_page
        return ([Hit(note=e.note, snippet=self._snippet(e, words))
                 for _, e in ranked[start:start + per_page]], len(ranked))

    def _snippet(self, entry: Entry, words: list[str]) -> str:
        note = entry.note
        fields = [note.title, " ".join(note.tags), note.category, note.summary,
                  "\n".join(note.points), _mention_text(note), note.source,
                  note.author or "", note.url]
        for word in words:                     # centred on the first term that matched
            for text in fields:
                found = snippet_of(text, word)
                if found:
                    return found
            body = read_full(entry).body or ""     # only a body hit costs a file read
            found = snippet_of(body, word)
            if found:
                return found
        return note.summary.strip().split("\n")[0][:SNIPPET]
