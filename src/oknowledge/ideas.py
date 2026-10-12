"""Ideas: what you wrote, kept as a note on a shelf of its own.

An idea is a Note like any other, with three differences that all live
here: its id comes from the moment it was written and not from a URL, its
text is yours (`my_note`) and nothing rewrites it, and it carries the links
you added to it (`related`) -- inside the idea's own note, so it reads on
its own in Obsidian.
"""

from __future__ import annotations

from pathlib import Path

from .ai.base import MAX_IDEA_TITLE
from .config import Config
from .model import Note
from .urls import link_id
from .vault import MAX_RELATED, find_note, normalize_related, write_note

KIND = "idea"
CATEGORY = "Ideas"
"""Every idea's category, which only names its index file. Ideas are found
by state and by tag; a category a model picked would be a third way of
filing them that nobody asked for."""


class IdeaFull(Exception):
    """The idea already holds MAX_RELATED links. Said, not swallowed: a link
    that silently did not join is one you go looking for later."""


def idea_id(instant: str) -> str:
    """The id of an idea written at this instant: the same hash a link
    takes of its URL, over a uri of its own."""
    return link_id(f"idea:{instant}")


def clean_title(title: str) -> str:
    """One line, single spaces, at most MAX_IDEA_TITLE characters."""
    return " ".join(str(title).split())[:MAX_IDEA_TITLE].strip()


def new_idea(text: str, title: str, saved: str, instant: str) -> Note:
    """The note for what was just typed. Not written: the web writes it,
    the way it writes a card."""
    return Note(id=idea_id(instant), url="", title=clean_title(title),
                category=CATEGORY, tags=[], type=KIND, source="", saved=saved,
                summary="", my_note=text.strip())


def add_related(cfg: Config, idea: str, stem: str, language: str) -> Path | None:
    """Add one link to one idea.

    The idea is read here, so a caller holding its lock writes onto what is
    on disk now and not onto a copy it read earlier. None when there is no
    such idea. A link it already has is not an error.
    """
    found = find_note(cfg, idea, shelf=cfg.ideas)
    if found is None:
        return None
    path, note = found
    if stem in note.related:
        return path
    if len(note.related) >= MAX_RELATED:
        raise IdeaFull(idea)
    note.related = normalize_related([*note.related, stem])
    return write_note(cfg, note, language, path=path)


def drop_related(cfg: Config, idea: str, stem: str, language: str) -> Path | None:
    """Take one link off one idea, by the stem the idea holds."""
    found = find_note(cfg, idea, shelf=cfg.ideas)
    if found is None:
        return None
    path, note = found
    if stem not in note.related:
        return path
    note.related = [s for s in note.related if s != stem]
    return write_note(cfg, note, language, path=path)
