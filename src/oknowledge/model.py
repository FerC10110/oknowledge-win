"""The shapes that travel between layers."""

from __future__ import annotations

from dataclasses import dataclass, field


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
