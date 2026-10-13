"""Marks: one emoji you put on a note, and nothing a model ever writes.

Its own module and not part of the vault's: the config reads the list of
marks to offer, and the config cannot import the vault (the vault imports
it). Nothing here touches a disk.
"""

from __future__ import annotations

import unicodedata

DEFAULT_MARKS = ("⭐", "🔥", "❤️", "📌", "✅", "❓", "💡", "⚠️", "🧪", "📚", "🎯", "👀")
"""What the picker offers until `[web] marks` says otherwise."""

MAX_MARK = 8
"""Code points, not characters: 👍🏽 is two and a family is five, joined."""

# What glues an emoji together: the joiner of 👨‍👩‍👧 and the selectors that
# turn ❤ into ❤️. They are format characters (Cf), which the rule below
# otherwise refuses along with every other invisible one.
_GLUE = frozenset({"‍", "️", "︎"})


def clean_mark(value) -> str | None:
    """The mark as it will be stored: "" for none, None when refused.

    Refused rather than repaired, like a category name: whoever typed "ok"
    into the box gets told no, not a mark they did not ask for. A symbol
    (So) is what every emoji is; letters, digits, spaces and invisible
    characters are what an emoji never needs.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return ""
    if len(text) > MAX_MARK:
        return None
    if not any(unicodedata.category(ch) == "So" for ch in text):
        return None
    for ch in text:
        if ch in _GLUE:
            continue
        if unicodedata.category(ch)[0] in "LNZC":
            return None
    return text


def rank_marks(notes, preferred) -> list[tuple[str, int]]:
    """(mark, how many notes carry it), most used first.

    A tie goes to the order of the picker's list, and after that to the
    note seen first: a filter that swapped places between two page loads
    for a reason nobody can see would be worse than no order at all.
    """
    counts: dict[str, int] = {}
    for note in notes:
        if note.mark:
            counts[note.mark] = counts.get(note.mark, 0) + 1
    listed = {mark: i for i, mark in enumerate(preferred)}
    seen = {mark: i for i, mark in enumerate(counts)}
    return sorted(counts.items(),
                  key=lambda kv: (-kv[1], listed.get(kv[0], len(listed)), seen[kv[0]]))
