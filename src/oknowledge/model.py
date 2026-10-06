"""The shapes that travel between layers."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Mention:
    """Something a video named, and a place to go about it.

    `url` is never empty: it is either a URL that appeared in the video or a
    search for the name. A mention with nowhere to go does not serve the one
    thing it exists for.
    """

    name: str
    url: str


@dataclass
class Note:
    """A saved link, as it ends up in the vault."""

    id: str
    url: str
    title: str
    category: str
    tags: list[str]
    type: str
    source: str
    saved: str                       # YYYY-MM-DD
    summary: str
    points: list[str] = field(default_factory=list)
    status: str = "ok"               # ok | partial | failed
    content: str = "full"            # full | summary
    author: str | None = None
    published: str | None = None     # YYYY-MM-DD
    cover: str | None = None         # path relative to the note
    body: str | None = None          # the extracted text, if content == "full"
    mentions: list[Mention] | None = None
    """Tri-state, on purpose. None: nobody asked this note for its mentions.
    []: it was asked and the video names nothing. A list: what it names. The
    difference between None and [] is what makes `oknowledge mentions`
    idempotent -- without it, a video that truly mentions nothing becomes a
    candidate again on every run and spends a model call to find nothing."""


@dataclass
class Extracted:
    """What was pulled out of a URL before the AI reads it."""

    title: str
    text: str
    type: str
    source: str
    author: str | None = None
    published: str | None = None     # YYYY-MM-DD
    cover_url: str | None = None


@dataclass
class QueueEntry:
    """The state of a link while it is processed, and after it fails."""

    id: str
    url: str
    content: str
    status: str                      # pending | ok | partial | failed
    updated: str                     # ISO 8601 UTC
    title: str | None = None
    error: str | None = None
