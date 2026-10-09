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
    engine: str = ""
    """Which engine produced the analysis below, and with which model. Written
    by the pipeline and nobody else: they say who wrote the content that is in
    the note right now, so a re-analysis replaces them rather than carrying
    them across the way `collections` and `mentions_extra` are carried. Empty
    on every note saved before this existed, and on every partial one -- a
    note nobody analysed has no engine to name."""
    model: str = ""

    collections: list[str] = field(default_factory=list)
    """The user's own grouping: a project they are working on, a list they are
    putting together. The only field here nobody but them writes -- the model
    never proposes one and a re-analysis carries them across untouched, the
    same promise mentions_extra has."""
    mentions_extra: list[str] = field(default_factory=list)
    """Lines of the mentions section that are not a bullet: a sentence the user
    typed there, a numbered item. Kept verbatim and written back after the
    bullets, because the user's own words are not ours to destroy. Parsed in
    vault._split_body and rendered in vault.render, nowhere else."""


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
    step: str = ""
    """What is being done to this link right now -- the pipeline's stage, and
    the engine after it when there is one ("analyze opencode") -- or "" when
    nothing is. The one field here that nobody keeps: it is written as the
    work moves and cleared when the link is settled, so a watcher can say
    what is happening instead of only that something is."""
