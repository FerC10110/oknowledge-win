"""The only module that writes Markdown.

Three rules, and they all live here for a reason: the vault belongs to the user.

1. Only write inside <vault>/<folder>/.
2. Only touch files whose frontmatter has `oknowledge: 1`. A file without that
   marker is never modified or deleted, even if it sits in our folder and is
   named exactly like the one we were about to write.
3. Nothing is destroyed. A note is written in place, never unlinked and
   rewritten; a deleted note is moved to <vault>/<folder>/trash/, where
   Obsidian can still open it and the user can drag it back.
"""

from __future__ import annotations

import contextlib
import os
import re
import secrets
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .ai.base import (
    MAX_CATEGORY_LENGTH, MAX_COLLECTIONS, UNSAFE_IN_A_NAME, normalize_collections, normalize_tags,
)
from .atomic import atomic_write
from .config import Config, Shelf
from .marks import clean_mark
from .model import Mention, Note
from .queue import Locked
from .urls import search_url

MARKER = "oknowledge"
MARKER_VERSION = 1
TRASH = "trash"

HEADINGS = {
    "es": ("Puntos clave", "Menciones", "Contenido original", "Mi nota"),
    "en": ("Key points", "Mentions", "Original content", "My note"),
}

ACTIONS = ("exists", "improve", "expand", "links")
"""What can be asked about an idea, in the order its sections are written."""

ACTION_HEADINGS = {
    "es": {"exists": "Ya existe", "improve": "Mejoras", "expand": "Ampliación",
           "links": "Links que pueden servir"},
    "en": {"exists": "Already out there", "improve": "Improvements",
           "expand": "Expansion", "links": "Links that may help"},
}

FRONTMATTER_ORDER = (
    "url", "title", "category", "tags", "collections", "related", "type", "source",
    "author", "published", "saved", "cover", "length", "rating", "score",
    "state", "mark", "content", "engine", "model", "status", "id", MARKER,
)


class ProtectedNote(Exception):
    """Refusing to write: the target is outside our folder or is not ours."""


class BadCategory(ValueError):
    """A category name we refuse to store, because it would not stay a name."""


class IndexesStale(Exception):
    """The change is on disk; rebuilding the indexes after it failed.

    Its own exception because the two need opposite words to the user. A
    failed write means nothing happened and the note is untouched. This means
    the note is already saved, or already in trash/, and only the indexes are
    behind -- which `oknowledge reindex` fixes. Telling the user nothing
    happened when their note has moved is worse than the error itself.

    `done` is whatever the function would have returned had the rebuild
    worked, so a caller can report what really did happen.
    """

    def __init__(self, done, error: BaseException):
        super().__init__(f"the change was saved, but the indexes are stale: {error}")
        self.done = done
        self.error = error


@dataclass(frozen=True)
class Trashed:
    """Where a deleted note was, and the file it is now in trash/. The pair
    is what a Deshacer needs to put it back (spec §6.2)."""

    source: Path
    target: Path


def _safe(text: str) -> str:
    """Reduce text to [A-Za-z0-9-]: no separators, no dots, nothing that can escape."""
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-")


def slug(text: str, fallback: str) -> str:
    plain = unicodedata.normalize("NFKD", text)
    plain = plain.encode("ascii", "ignore").decode("ascii").lower()
    plain = re.sub(r"[^a-z0-9]+", "-", plain).strip("-")[:60].strip("-")
    return plain or _safe(fallback) or "note"


def render(note: Note, language: str) -> str:
    points_heading, mentions_heading, content_heading, mine_heading = HEADINGS.get(
        language, HEADINGS["en"])

    front = {
        "url": note.url,
        "title": note.title,
        "category": note.category,
        "tags": list(note.tags),
        # None rather than []: FRONTMATTER_ORDER drops what is None, and a
        # thousand notes that are in no collection should not each carry a
        # line saying so.
        "collections": list(note.collections) or None,
        # As wikilinks, so Obsidian draws them as links; stems everywhere
        # else. None and not [] for the reason collections has it.
        "related": [f"[[{stem}]]" for stem in note.related] or None,
        "type": note.type,
        "source": note.source,
        "author": note.author,
        "published": note.published,
        "saved": note.saved,
        "cover": note.cover,
        # `or None` for the same reason collections and engine have it: a
        # link has none of these and must not carry four empty lines.
        "length": note.length or None,
        "rating": note.rating or None,
        "score": note.score or None,
        "state": note.state or None,
        "mark": note.mark or None,
        "content": note.content,
        # `or None` for the same reason collections has it: a thousand notes
        # that nobody analysed should not each carry two empty lines.
        "engine": note.engine or None,
        "model": note.model or None,
        "status": note.status,
        "id": note.id,
        MARKER: MARKER_VERSION,
    }
    front = {k: front[k] for k in FRONTMATTER_ORDER if front.get(k) is not None}
    head = yaml.safe_dump(front, sort_keys=False, allow_unicode=True).strip()

    parts = [f"---\n{head}\n---\n", f"# {note.title}\n", f"{note.summary.strip()}\n"]
    if note.points:
        bullets = "\n".join(f"- {p}" for p in note.points)
        parts.append(f"## {points_heading}\n\n{bullets}\n")
    # Before Mi nota: in an idea that section runs to the end of the file.
    named = ACTION_HEADINGS.get(language, ACTION_HEADINGS["en"])
    for action in ACTIONS:
        text = note.actions.get(action, "").strip()
        if text:
            parts.append(f"## {named[action]}\n\n{text}\n")
    if note.mentions is not None:
        bullets = "\n".join(f"- [{_escape_name(m.name)}]({m.url})"
                            for m in note.mentions)
        # The heading alone when there is nothing: the section's presence is
        # what says this note was already asked.
        lines = bullets.splitlines() + list(note.mentions_extra)
        parts.append(f"## {mentions_heading}\n\n" + "\n".join(lines) + "\n" if lines
                     else f"## {mentions_heading}\n")
    if note.my_note:
        # Before the original content, which runs to end of file: a section
        # after that one is text the reader meant to keep, not a section.
        parts.append(f"## {mine_heading}\n\n{note.my_note.strip()}\n")
    if note.content == "full" and note.body:
        parts.append(f"## {content_heading}\n\n{note.body.strip()}\n")
    return "\n".join(parts)


def _escape_name(name: str) -> str:
    """So a bracket in a name cannot break the link it sits in."""
    return name.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def _unescape_name(name: str) -> str:
    return re.sub(r"\\([\[\]\\])", r"\1", name)


def _read_marked(path: Path) -> tuple[dict, str] | None:
    """(frontmatter, text after the frontmatter) if the file is ours, else None."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end == -1:
        return None
    try:
        front = yaml.safe_load(text[4:end])
    except (yaml.YAMLError, ValueError):
        return None
    if not isinstance(front, dict) or front.get(MARKER) != MARKER_VERSION:
        return None
    return front, text[end + 4:]


def read_front(path: Path) -> dict | None:
    """The frontmatter, only if the file is ours. Otherwise None."""
    marked = _read_marked(path)
    return marked[0] if marked else None


_POINTS_HEADINGS = {f"## {h[0]}" for h in HEADINGS.values()}
_MENTIONS_HEADINGS = {f"## {h[1]}" for h in HEADINGS.values()}
_CONTENT_HEADINGS = {f"## {h[2]}" for h in HEADINGS.values()}
_MINE_HEADINGS = {f"## {h[3]}" for h in HEADINGS.values()}
_ACTION_HEADINGS = {f"## {heading}": action for table in ACTION_HEADINGS.values()
                    for action, heading in table.items()}
# Any bullet a person types: -, * or +, indented or not.
_LIST_ITEM = re.compile(r"^\s*[-*+]\s+(?P<text>\S.*)$")
_BULLET = re.compile(r"^\[(?P<name>.*)\]\((?P<url>.*)\)$")


def _mention(text: str) -> Mention:
    """One bullet, however it was written.

    The generated form first; then a bare name, which is what a hand-edit
    leaves; and anything else is kept verbatim as the name. A line in this
    section is never dropped -- the user's own words are not ours to delete.
    """
    match = _BULLET.match(text)
    if match:
        name = _unescape_name(match.group("name")).strip()
        url = match.group("url").strip()
        if name and url:
            return Mention(name=name, url=url)
    return Mention(name=text, url=search_url(text))


def _split_body(
    body: str, mine_to_end: bool = False, actions: bool = False,
) -> tuple[str, list[str], list[Mention] | None, list[str], str, str | None,
           dict[str, str]]:
    """Return (summary, points, mentions, mentions_extra, my note, content).

    From a body written by render(), or edited by hand. Lines in the mentions
    section that are not bullets come back verbatim as mentions_extra.

    Sections are recognized by their heading text, not by position, so a missing
    section never shifts the others. The content section runs to end of file, so
    headings inside the extracted text survive.

    `mine_to_end` does the same for your own section, for an idea: there it
    is the idea itself, written by you, and a line of it that happens to
    read like one of the app's headings is still a line of yours.

    `actions` reads an idea's action sections; anywhere else those headings
    are just text.
    """
    lines = body.splitlines()
    start = next((i + 1 for i, line in enumerate(lines) if line.startswith("# ")), 0)
    summary: list[str] = []
    points: list[str] = []
    mentions: list[Mention] | None = None
    extra: list[str] = []
    mine: list[str] = []
    original: list[str] = []
    found: dict[str, list[str]] = {}
    current: list[str] = []
    # A heading of yours after an action section: yours, not the section's,
    # or asking again would delete it. It joins your note.
    loose: list[str] = []
    mode = "summary"
    for line in lines[start:]:
        marker = line.rstrip()
        if mode == "mine" and mine_to_end:
            mine.append(line)
        elif actions and mode != "content" and marker in _ACTION_HEADINGS:
            mode = "action"
            current = found.setdefault(_ACTION_HEADINGS[marker], [])
        elif mode != "content" and marker in _CONTENT_HEADINGS:
            mode = "content"
        elif mode != "content" and marker in _MENTIONS_HEADINGS:
            # Accumulates, like the points section: a second heading adds to
            # the list instead of discarding what the first one held.
            mode = "mentions"
            if mentions is None:
                mentions = []
        elif mode != "content" and marker in _MINE_HEADINGS:
            mode = "mine"
        elif mode == "summary" and marker in _POINTS_HEADINGS:
            mode = "points"
        elif mode == "summary":
            summary.append(line)
        elif mode == "points":
            if line.startswith("- "):
                points.append(line[2:].strip())
        elif mode == "mine":
            # Verbatim, every line: what you typed there is prose as often as
            # it is a list, and a bullet filter would eat the prose.
            mine.append(line)
        elif mode == "mentions":
            item = _LIST_ITEM.match(line)
            if item:
                mentions.append(_mention(item.group("text").strip()))
            elif line.strip() and not re.fullmatch(r"\s*[-*+]\s*", line):
                extra.append(line.rstrip())
        elif mode == "action" and marker.startswith("## "):
            mode = "loose"
            loose.append(line)
        elif mode == "action":
            current.append(line)
        elif mode == "loose":
            loose.append(line)
        else:
            original.append(line)
    content = "\n".join(original).strip()
    sections = {action: "\n".join(lines).strip() for action, lines in found.items()}
    yours = "\n\n".join(text for text in ("\n".join(loose).strip(),
                                            "\n".join(mine).strip()) if text)
    return ("\n".join(summary).strip(), points, mentions, extra,
            yours, content or None,
            {action: text for action, text in sections.items() if text})


_REQUIRED_TEXT = ("id", "url", "title", "category", "type", "source")


def _as_text(value) -> str:
    """A frontmatter value that has to be text, as a hand-edit leaves it.

    `rating: 8.1` typed in Obsidian parses as a number and means what it
    looks like; a list or a date in one of these does not, and reads as
    nothing rather than as its repr."""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return ""


def _as_score(value) -> int:
    """Your stars, as a whole number. `score: muchísimo` is somebody typing
    in Obsidian, not a note we refuse to read."""
    if isinstance(value, bool):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


MAX_RELATED = MAX_COLLECTIONS
"""The same cap as the collections, for the same reason: a frontmatter that
grows without end is a note that one day cannot be read."""

_WIKILINK = re.compile(r"^\[\[(?P<target>[^\]|]*)(?:\|[^\]]*)?\]\]$")


def normalize_related(values) -> list[str]:
    """The stems an idea points at, however Obsidian or a hand left them.

    `[[stem]]`, `[[stem|alias]]`, `[[folder/stem]]`, `stem.md` and a bare
    `stem` all name the same note. Anything that is not text is dropped
    rather than refusing the note: the idea is the user's either way. In
    order, once each, at most MAX_RELATED.

    YAML has its own opinion of a wikilink: unquoted, `- [[stem]]` is a
    list inside a list, and `related: [[stem]]` on one line is the same
    shape again; a bare `related: stem` is one string. All of them are a
    link somebody wrote, so all of them are read.
    """
    if isinstance(values, str):
        values = [values]
    elif not isinstance(values, list):
        values = []
    flat = []
    for value in values:
        while isinstance(value, list) and len(value) == 1:
            value = value[0]
        flat.append(value)
    out: list[str] = []
    for value in flat:
        if not isinstance(value, str):
            continue
        text = value.strip()
        match = _WIKILINK.match(text)
        stem = (match.group("target") if match else text).strip()
        stem = stem.rsplit("/", 1)[-1]
        if stem.endswith(".md"):
            stem = stem[:-3]
        if stem and stem not in out:
            out.append(stem)
    return out[:MAX_RELATED]


def read_note(path: Path) -> Note | None:
    """The note, if the file is ours and parseable. Never modifies the file.

    A marked file that is missing a required key, or has a value of the wrong
    type (the user hand-edits these), reads as None, same as an unmarked one.
    """
    marked = _read_marked(path)
    if marked is None:
        return None
    front, rest = marked
    if front.get("kind") == "index":
        return None
    try:
        required = {k: front[k] for k in (*_REQUIRED_TEXT, "saved")}
    except KeyError:
        return None
    if not all(isinstance(required[k], str) for k in _REQUIRED_TEXT):
        return None
    tags = front.get("tags") or []
    collections = front.get("collections") or []
    if not isinstance(tags, list) or not isinstance(collections, list):
        return None
    for key in ("author", "cover"):
        if front.get(key) is not None and not isinstance(front[key], str):
            return None
    # A hand-edited `engine:` comes back as whatever was typed -- a list, a
    # number, a date. It picks an icon, so anything that is not text is nobody.
    # The note is not refused over it: it is the user's note either way.
    made = {key: front.get(key) for key in ("engine", "model")}
    made = {key: value if isinstance(value, str) else "" for key, value in made.items()}
    related = front.get("related")
    is_idea = required["type"] == "idea"
    summary, points, mentions, extra, mine, body, actions = _split_body(
        rest, mine_to_end=is_idea, actions=is_idea)
    return Note(
        id=required["id"],
        url=required["url"],
        title=required["title"],
        category=required["category"],
        tags=[str(t) for t in tags],
        collections=[str(c) for c in collections],
        related=normalize_related(related),
        type=required["type"],
        source=required["source"],
        saved=str(required["saved"]),
        summary=summary,
        points=points,
        status=str(front.get("status", "ok")),
        content=str(front.get("content", "full")),
        engine=made["engine"],
        model=made["model"],
        author=front.get("author"),
        published=str(front["published"]) if front.get("published") else None,
        cover=front.get("cover"),
        body=body,
        mentions=mentions,
        mentions_extra=extra,
        length=_as_text(front.get("length")),
        rating=_as_text(front.get("rating")),
        score=_as_score(front.get("score")),
        state=_as_text(front.get("state")),
        mark=clean_mark(front.get("mark")) or "",
        my_note=mine,
        actions=actions,
    )


def note_stem(note: Note) -> str:
    """The file name a note earns from its date and title, before note_path()
    disambiguates it against what is already on disk."""
    return f"{_safe(note.saved) or 'undated'}-{slug(note.title, note.id)}"


def note_path(cfg: Config, note: Note, shelf: Shelf | None = None) -> Path:
    shelf = shelf or cfg.links
    stem = note_stem(note)
    candidate = shelf.dir / f"{stem}.md"
    n = 2
    while candidate.exists():
        existing = read_note(candidate)
        if existing is not None and existing.id == note.id:
            return candidate
        candidate = shelf.dir / f"{stem}-{n}.md"
        n += 1
    return candidate


def ensure_inside_root(cfg: Config, target: Path) -> Path:
    """Resolve target (following symlinks) and require it strictly inside cfg.root.

    Public because every write to the vault has to pass it, including the ones
    made outside this module: one containment rule, in one place.
    """
    resolved = target.resolve()
    root = cfg.root.resolve()
    if resolved == root or not resolved.parent.is_relative_to(root):
        raise ProtectedNote(f"refusing to write outside the managed folder: {target}")
    return resolved


def write_note(cfg: Config, note: Note, language: str, path: Path | None = None) -> Path:
    target = path or note_path(cfg, note)
    resolved = ensure_inside_root(cfg, target)        # location first, before any write
    if resolved.exists() and read_front(resolved) is None:
        raise ProtectedNote(f"refusing to overwrite a file without the marker: {target}")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    # fsync_dir, like the queue entry that describes this note: the entry must
    # never be the more durable of the two. An `ok` entry whose note did not
    # survive a power cut is in neither unfinished() nor orphaned(), so nothing
    # would ever look at that link again.
    atomic_write(resolved, render(note, language), fsync_dir=True)
    return resolved


# Index boilerplate follows the content language, like HEADINGS: (notice, label
# for a note with no category).
INDEX_TEXT = {
    "es": ("<!-- Generado por oknowledge. Los cambios a mano se pierden. -->", "Sin categoria"),
    "en": ("<!-- Generated by oknowledge. Manual changes are lost. -->", "Uncategorized"),
}

_CLAIMS_MARKER = re.compile(rf"^{MARKER}:", re.MULTILINE)


@dataclass(frozen=True)
class RebuildResult:
    """What a reindex did.

    written: indexes we wrote.
    skipped: marked notes of ours that could not be parsed (left untouched).
    blocked: category indexes we refused to write because a file of the
        user's, without the marker, is in the way (left untouched).
    """

    written: list[Path] = field(default_factory=list)
    skipped: list[Path] = field(default_factory=list)
    blocked: list[Path] = field(default_factory=list)


def _claims_marker(path: Path) -> bool:
    """True if the file's frontmatter text carries an `oknowledge:` key, even if
    the rest is too broken to parse. Raises OSError if the file cannot be read
    at all (the caller reports it). Lets a reindex tell a note of ours that the
    user hand-broke from a file that was never ours."""
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return False
    if not text.startswith("---\n"):
        return False
    end = text.find("\n---", 4)
    return end != -1 and _CLAIMS_MARKER.search(text[4:end]) is not None


def scan_file(path: Path) -> tuple[Note | None, bool]:
    """(note, False) if the file is a readable note of ours; (None, True) if it
    is a file of ours that could not be read; (None, False) if it is not a note
    (an index, or not ours at all)."""
    note = read_note(path)
    if note is not None:
        return note, False
    front = read_front(path)
    if front is not None and front.get("kind") == "index":
        return None, False
    try:
        return None, _claims_marker(path)
    except OSError:
        # Cannot tell whether it is ours, but we failed to index it: say so.
        return None, True


def _scan(cfg: Config, shelf: Shelf | None = None) -> tuple[list[tuple[Path, Note]], list[Path]]:
    """Every readable note on the shelf, plus the files of ours it could not read."""
    shelf = shelf or cfg.links
    if not shelf.dir.is_dir():
        return [], []
    found: list[tuple[Path, Note]] = []
    skipped: list[Path] = []
    for path in sorted(shelf.dir.glob("*.md")):
        note, unreadable = scan_file(path)
        if note is not None:
            found.append((path, note))
        elif unreadable:
            skipped.append(path)
    return found, skipped


def all_notes(cfg: Config, shelf: Shelf | None = None) -> list[Note]:
    return [note for _, note in _scan(cfg, shelf)[0]]


def all_entries(cfg: Config, shelf: Shelf | None = None) -> list[tuple[Path, Note]]:
    """Every readable note on the shelf with the file it is in: the file
    name is what a wikilink to it says."""
    return _scan(cfg, shelf)[0]


def find_note(cfg: Config, link_id: str, shelf: Shelf | None = None) -> tuple[Path, Note] | None:
    for path, note in _scan(cfg, shelf)[0]:
        if note.id == link_id:
            return path, note
    return None


def categories(cfg: Config) -> dict[str, int]:
    counts: dict[str, int] = {}
    for note in all_notes(cfg):
        counts[note.category] = counts.get(note.category, 0) + 1
    return dict(sorted(counts.items()))


def _index_name(category: str) -> str:
    # The same list ai.base._clean_category() cleans against, so what the
    # model invents and what an index file can be called cannot drift apart.
    return re.sub(f"[{re.escape(UNSAFE_IN_A_NAME)}]+", "-", category).strip(" .")


def index_path(cfg: Config, category: str, shelf: Shelf | None = None) -> Path:
    # The category name is written by a model: it can never leave our folder
    # or invent subdirectories. A pure function of the category, never of the language.
    shelf = shelf or cfg.links
    name = _index_name(category) or INDEX_TEXT["es"][1]
    return shelf.index_dir / f"{name}.md"


def _plain(text: str) -> str:
    """One line, no whitespace runs."""
    return " ".join(text.split())


def write_index(cfg: Config, category: str, entries: list[tuple[Path, Note]], language: str,
                shelf: Shelf | None = None) -> Path:
    """Write the index for one category. `entries` are (real path on disk, note)
    pairs, so every wikilink names the file that actually exists."""
    notice = INDEX_TEXT.get(language, INDEX_TEXT["en"])[0]
    ordered = sorted(entries, key=lambda e: (e[1].saved, e[1].title, e[0].name), reverse=True)

    front = yaml.safe_dump(
        {MARKER: MARKER_VERSION, "kind": "index", "category": category},
        sort_keys=False, allow_unicode=True,
    ).strip()

    count = f"{len(ordered)} link" + ("" if len(ordered) == 1 else "s")
    lines = [f"---\n{front}\n---\n", f"# {_plain(category)} · {count}\n", f"{notice}\n"]
    for path, note in ordered:
        label = _plain(re.sub(r"[|\[\]]", " ", note.title)) or path.stem
        line = f"- [[{path.stem}|{label}]]"
        head = note.summary.strip().splitlines()[0] if note.summary.strip() else ""
        tags = " ".join(f"#{t}" for t in note.tags)
        detail = " — ".join(part for part in (f"`{tags}`" if tags else "", head) if part)
        if detail:
            line += f"\n  {detail}"
        lines.append(line)

    target = index_path(cfg, category, shelf)
    resolved = ensure_inside_root(cfg, target)
    if resolved.exists() and read_front(resolved) is None:
        raise ProtectedNote(f"refusing to overwrite a file without the marker: {target}")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(resolved, "\n".join(lines) + "\n")
    return resolved


def rebuild_indexes(cfg: Config, language: str, shelf: Shelf | None = None) -> RebuildResult:
    """Rewrite one index per category and delete the ones left without notes.

    Only reads notes; never rewrites them. Files of ours it could not read
    (hand-broken) are left alone and listed in `skipped`; a category whose
    index path is held by a user file is listed in `blocked`. Never raises
    for either.
    """
    shelf = shelf or cfg.links
    found, skipped = _scan(cfg, shelf)
    grouped: dict[str, list[tuple[Path, Note]]] = {}
    for path, note in found:
        grouped.setdefault(note.category, []).append((path, note))

    written: list[Path] = []
    blocked: list[Path] = []
    claimed: set[Path] = set()
    fallback = INDEX_TEXT.get(language, INDEX_TEXT["en"])[1]
    for category, entries in sorted(grouped.items()):
        if not _index_name(category):
            category = fallback          # nameless category: use the localized label
        target = index_path(cfg, category, shelf)
        if target in claimed:
            # Two categories sanitize to the same file name. The first in sorted
            # order wins, so the winner is stable across rebuilds.
            blocked.append(target)
            continue
        claimed.add(target)
        try:
            written.append(write_index(cfg, category, entries, language, shelf))
        except ProtectedNote:
            # One category in the way must not stop the others from updating.
            blocked.append(target)

    keep = {p.name for p in claimed}
    # Only this shelf's own index folder: the sweep deletes indexes left
    # without notes, and the other shelf's notes are not in `found`.
    if shelf.index_dir.is_dir():
        for path in shelf.index_dir.glob("*.md"):
            front = read_front(path)
            if front is not None and front.get("kind") == "index" and path.name not in keep:
                path.unlink()
    return RebuildResult(written=written, skipped=skipped, blocked=blocked)


# --- editing what is already saved -------------------------------------------
#
# Everything below changes or removes a file the user already has. Two habits
# make that safe, and both are deliberate:
#
# * a note is rewritten in place with write_note(..., path=path), which is an
#   atomic replace underneath. The file name comes from the saved date and the
#   title, and nothing here edits either, so the name never has to change. A
#   failed write costs the edit and leaves the note exactly as it was.
# * nothing is unlinked. Deleting moves the file into trash/, a sibling of
#   links/, which every scan already ignores because _scan() globs
#   links_dir/*.md and never recurses.


def clean_category(name) -> str | None:
    """The category as it will be stored, or None if we refuse it.

    Category names arrive from a browser form and end up in frontmatter and in
    an index file name, so they are refused rather than sanitized: a user who
    types `../../etc` gets told no, instead of silently getting a category
    named something else. The test is simply that the name survives
    _index_name() unchanged and carries no control characters, which rules out
    path separators, leading dots and the characters a file name cannot hold.
    """
    text = str(name).strip()
    if not text or len(text) > MAX_CATEGORY_LENGTH:
        return None
    if any(unicodedata.category(char).startswith("C") for char in text):
        return None
    return text if _index_name(text) == text else None


def _checked_category(name) -> str:
    clean = clean_category(name)
    if clean is None:
        raise BadCategory(f"not a usable category name: {name!r}")
    return clean


def _finish(cfg: Config, language: str, done, shelf: Shelf | None = None):
    """Rebuild the indexes after a change that has already landed on disk."""
    try:
        rebuild_indexes(cfg, language, shelf)
    except OSError as error:
        raise IndexesStale(done, error) from error
    return done


def update_note(cfg: Config, link_id: str, language: str,
                category: str | None = None, tags=None, mentions=None,
                drop_mention: str | None = None,
                add_collection: str | None = None,
                drop_collection: str | None = None,
                found: tuple[Path, Note] | None = None,
                state: str | None = None, score: str | int | None = None,
                my_note: str | None = None,
                mark: str | None = None,
                kind: str | None = None,
                shelf: Shelf | None = None,
                rebuild: bool = True) -> Path | None:
    """Change one of our notes' classification and rebuild the indexes.

    `mentions` replaces the whole list. `drop_mention` removes the entries of
    that name, inside the same scan, so a caller never has to read the note
    itself (which would cost a second vault scan, and race with a re-analysis).

    `add_collection` and `drop_collection` change one collection, for the same
    reason `drop_mention` exists: a caller putting thirty notes into a project
    should not have to read each of them twice.
    The name arrives already spelled the way the library spells it -- which
    collections exist is the index's business, not this module's.

    `found` is a (path, note) the caller already read, under its own lock, so
    this does not scan the vault a second time. Without it the note is looked up.

    `rebuild=False` writes the note and leaves the indexes to the caller: a
    bulk move of thirty notes rebuilds once at the end, not thirty times.

    Returns the path written, or None if no note of ours has that id. Raises
    BadCategory for a category we refuse, before touching anything.
    """
    if found is None:
        found = find_note(cfg, link_id, shelf)
    if found is None:
        return None
    path, note = found
    if category is not None:
        note.category = _checked_category(category)
    if kind is not None:
        note.type = kind
    if tags is not None:
        note.tags = normalize_tags(tags)
    if mentions is not None:
        note.mentions = list(mentions)
    if add_collection:
        note.collections = normalize_collections([*note.collections, add_collection])
    if drop_collection:
        # By the exact name: every button that sends one carries the spelling
        # the note itself holds.
        note.collections = [c for c in note.collections if c != drop_collection]
    # Yours, and checked before anything is touched: a score out of range or
    # a state nobody defined leaves the note exactly as it was. Both arrive
    # from a form, which means they can arrive as anything.
    if state is not None:
        note.state = state if state in states_for(note.type) else note.state
    if score is not None:
        # "0" is the stars taken off (clicking the one you had, spec §2);
        # anything else that is not one to five leaves them as they were.
        picked = _stars(score)
        if picked or str(score).strip() == "0":
            note.score = picked
    if my_note is not None:
        note.my_note = my_note.strip()
    if mark is not None:
        picked = clean_mark(mark)
        note.mark = note.mark if picked is None else picked
    if drop_mention is not None and note.mentions is not None:
        # `is not None`, not a truthiness test: a note nobody asked has None
        # here, and turning that into [] would tell the backfill this video
        # was already asked, for good.
        note.mentions = [m for m in note.mentions if m.name != drop_mention]
    # In place: the name is a function of saved + title, which this never
    # changes, and an unlink here would be a note destroyed by a failed write.
    written = write_note(cfg, note, language, path=path)
    # A change to mentions or collections skips the rebuild: no index names
    # either, and rebuilding the whole library on a delete click -- or once
    # per note while thirty of them join a project -- buys nothing.
    if (category is None and tags is None) or not rebuild:
        return written
    return _finish(cfg, language, written, shelf)


STATES = ("pending", "doing", "done")
"""What a card can be: not started, started, finished. Three and not four --
a list of things you gave up on is a list nobody opens."""

IDEA_STATES = (*STATES, "dropped")
"""An idea can be given up on, and remembering that you did -- and why -- is
the reason to write it down. A film you dropped is a list nobody opens; an
idea you dropped is one you will not have to have twice."""


def states_for(kind: str) -> tuple[str, ...]:
    """The states a note of this type can be in."""
    return IDEA_STATES if kind == "idea" else STATES


def _stars(value) -> int:
    """One to five, or 0 for anything else. The box is five buttons, so
    anything else is somebody typing into the URL."""
    try:
        picked = int(str(value).strip())
    except (TypeError, ValueError):
        return 0
    return picked if 1 <= picked <= 5 else 0


def trash_dir(cfg: Config) -> Path:
    """Where deleted notes go: a sibling of links/, so no scan ever sees them."""
    return cfg.root / TRASH


def _free_name(folder: Path, name: str) -> Path:
    """Claim an unused name in `folder`, creating the file to reserve it.

    Two notes deleted on the same day with the same title have the same file
    name; the second must not overwrite the first.
    """
    stem, suffix = (name[:-3], ".md") if name.endswith(".md") else (name, "")
    for attempt in range(1, 100):
        candidate = folder / (name if attempt == 1 else f"{stem}-{attempt}{suffix}")
        try:
            os.close(os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o666))
        except FileExistsError:
            continue
        return candidate
    return folder / f"{stem}-{secrets.token_hex(4)}{suffix}"


def delete_note(cfg: Config, link_id: str, language: str,
                shelf: Shelf | None = None, rebuild: bool = True) -> Trashed | None:
    """Move one of our notes to trash/ and rebuild the indexes.

    Returns where it was and where it went, or None if no note of ours has
    that id. Deleting fires from a POST in a browser, so it has to be
    undoable: the file keeps its name and content, can be dragged back from
    Obsidian, and restore_note() puts it back from a Deshacer.
    """
    found = find_note(cfg, link_id, shelf)
    if found is None:
        return None
    path, _ = found
    # Location first, before anything is created: a trash/ symlinked out of
    # the vault has to be refused, not followed.
    folder = ensure_inside_root(cfg, trash_dir(cfg) / "note.md").parent
    folder.mkdir(parents=True, exist_ok=True)
    target = _free_name(folder, path.name)
    try:
        os.replace(path, target)                 # same filesystem: atomic
    except OSError:
        target.unlink(missing_ok=True)           # no empty placeholder left behind
        raise
    done = Trashed(source=path, target=target)
    if not rebuild:
        return done
    return _finish(cfg, language, done, shelf)


def restore_note(cfg: Config, link_id: str, source: Path, target: Path, language: str,
                 shelf: Shelf | None = None, rebuild: bool = True) -> bool:
    """Put a deleted note back at its old address, and rebuild its shelf.

    False, with nothing touched, unless all of this holds: `target` is a file
    directly in trash/, still ours and still this id (Obsidian can edit,
    unmark or move it in the meantime); `source` is a free name directly in
    the shelf's folder; and no note on the shelf has the id (the link was
    pasted again since). The move never overwrites: a file that appears at
    `source` between the check and the move wins, and the note stays in
    trash/.
    """
    shelf = shelf or cfg.links
    try:
        trashed = ensure_inside_root(cfg, Path(target))
        back = ensure_inside_root(cfg, Path(source))
    except ProtectedNote:
        return False
    if trashed.parent != trash_dir(cfg).resolve() or back.parent != shelf.dir.resolve():
        return False
    if not trashed.is_file() or not back.parent.is_dir():
        return False
    found = read_note(trashed)
    if found is None or found.id != link_id:
        return False
    if back.exists() or back.is_symlink() or find_note(cfg, link_id, shelf) is not None:
        return False
    try:
        os.link(trashed, back)                   # fails, not overwrites, if the name appeared
    except (FileExistsError, FileNotFoundError):
        return False                             # name taken, or the trash file vanished
    except OSError:
        # A filesystem without hard links: reserve the name, then move onto
        # our own empty placeholder.
        try:
            os.close(os.open(back, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o666))
        except FileExistsError:
            return False
        try:
            os.replace(trashed, back)
        except OSError:
            back.unlink(missing_ok=True)
            raise
    else:
        trashed.unlink()
    if rebuild:
        _finish(cfg, language, True, shelf)
    return True


@dataclass(frozen=True)
class RenameResult:
    """What a rename did.

    moved: notes rewritten under the new category.
    failed: (path, why) for each note that could not be written. A rename
        touches many files, so one bad note must neither abort the rest nor
        pass unreported: a half-renamed vault with no word to the user is the
        worst outcome of the three.
    """

    moved: int = 0
    failed: list[tuple[Path, str]] = field(default_factory=list)


BUSY = "an analysis is running on this link"


@contextlib.contextmanager
def _unlocked(link_id: str):
    yield


def rename_category(cfg: Config, old: str, new: str, language: str,
                    lock=None) -> RenameResult:
    """Rename a category; if `new` already exists, the two merge.

    Only touches notes of ours: _scan() already discards everything else.

    `lock(link_id)` is a context manager held while one note is rewritten, and
    the reason the note is read again inside it. This is the most destructive
    operation in the project -- it writes many notes at once -- and the scan it
    walks is already old by the time the first write happens, so a re-analysis
    that finished in between would be silently overwritten by the scanned
    copy. Under the lock the note is re-read, which is what makes the rewrite
    a change to the current note and not to a remembered one. A note that
    cannot be locked costs its own rename and is reported; it never stops the
    others.

    The vault does not reach for the queue itself: the caller that knows about
    re-analysis (the web) passes the lock in, and without it this behaves as
    it always did.
    """
    target = _checked_category(new)
    hold = lock or _unlocked
    moved = 0
    failed: list[tuple[Path, str]] = []
    for path, scanned in _scan(cfg)[0]:
        if scanned.category != old:
            continue
        try:
            with hold(scanned.id):
                note = read_note(path)
                if note is None or note.category != old:
                    # It changed under us (a re-analysis, a hand edit). Not
                    # ours to move any more, and not a failure either.
                    continue
                note.category = target
                write_note(cfg, note, language, path=path)
        except Locked:
            failed.append((path, BUSY))
            continue
        except (ProtectedNote, OSError) as error:
            failed.append((path, str(error)))
            continue
        moved += 1
    return _finish(cfg, language, RenameResult(moved=moved, failed=failed))


def repoint_related(cfg: Config, old: str, new: str, language: str,
                    lock=None) -> RenameResult:
    """Point every idea that names the file `old` at `new` instead.

    The pipeline renames a link's file when the model finally gives it a
    real title, and the ideas name their links by file name -- that is
    what a wikilink is. Shaped like rename_category, for the same reasons:
    each idea is read again under its own lock, and one that cannot be
    written is reported and never stops the others. No index names an
    idea's links, so there is nothing to rebuild.
    """
    hold = lock or _unlocked
    moved = 0
    failed: list[tuple[Path, str]] = []
    for path, scanned in _scan(cfg, cfg.ideas)[0]:
        if old not in scanned.related:
            continue
        try:
            with hold(scanned.id):
                note = read_note(path)
                if note is None or old not in note.related:
                    continue
                note.related = normalize_related(
                    [new if stem == old else stem for stem in note.related])
                write_note(cfg, note, language, path=path)
        except Locked:
            failed.append((path, BUSY))
            continue
        except (ProtectedNote, OSError) as error:
            failed.append((path, str(error)))
            continue
        moved += 1
    return RenameResult(moved=moved, failed=failed)
