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

import os
import re
import secrets
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .ai.base import MAX_CATEGORY_LENGTH, normalize_tags
from .atomic import atomic_write
from .config import Config
from .model import Note

MARKER = "oknowledge"
MARKER_VERSION = 1
TRASH = "trash"

HEADINGS = {
    "es": ("Puntos clave", "Contenido original"),
    "en": ("Key points", "Original content"),
}

FRONTMATTER_ORDER = (
    "url", "title", "category", "tags", "type", "source", "author",
    "published", "saved", "cover", "content", "status", "id", MARKER,
)


class ProtectedNote(Exception):
    """Refusing to write: the target is outside our folder or is not ours."""


class BadCategory(ValueError):
    """A category name we refuse to store, because it would not stay a name."""


def _safe(text: str) -> str:
    """Reduce text to [A-Za-z0-9-]: no separators, no dots, nothing that can escape."""
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-")


def slug(text: str, fallback: str) -> str:
    plain = unicodedata.normalize("NFKD", text)
    plain = plain.encode("ascii", "ignore").decode("ascii").lower()
    plain = re.sub(r"[^a-z0-9]+", "-", plain).strip("-")[:60].strip("-")
    return plain or _safe(fallback) or "note"


def render(note: Note, language: str) -> str:
    points_heading, content_heading = HEADINGS.get(language, HEADINGS["en"])

    front = {
        "url": note.url,
        "title": note.title,
        "category": note.category,
        "tags": list(note.tags),
        "type": note.type,
        "source": note.source,
        "author": note.author,
        "published": note.published,
        "saved": note.saved,
        "cover": note.cover,
        "content": note.content,
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
    if note.content == "full" and note.body:
        parts.append(f"## {content_heading}\n\n{note.body.strip()}\n")
    return "\n".join(parts)


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
_CONTENT_HEADINGS = {f"## {h[1]}" for h in HEADINGS.values()}


def _split_body(body: str) -> tuple[str, list[str], str | None]:
    """Return (summary, points, original content) from a body written by render().

    Sections are recognized by their heading text, not by position, so a missing
    section never shifts the others. The content section runs to end of file, so
    headings inside the extracted text survive.
    """
    lines = body.splitlines()
    start = next((i + 1 for i, line in enumerate(lines) if line.startswith("# ")), 0)
    summary: list[str] = []
    points: list[str] = []
    original: list[str] = []
    mode = "summary"
    for line in lines[start:]:
        marker = line.rstrip()
        if mode != "content" and marker in _CONTENT_HEADINGS:
            mode = "content"
        elif mode == "summary" and marker in _POINTS_HEADINGS:
            mode = "points"
        elif mode == "summary":
            summary.append(line)
        elif mode == "points":
            if line.startswith("- "):
                points.append(line[2:].strip())
        else:
            original.append(line)
    content = "\n".join(original).strip()
    return "\n".join(summary).strip(), points, content or None


_REQUIRED_TEXT = ("id", "url", "title", "category", "type", "source")


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
    if not isinstance(tags, list):
        return None
    for key in ("author", "cover"):
        if front.get(key) is not None and not isinstance(front[key], str):
            return None
    summary, points, body = _split_body(rest)
    return Note(
        id=required["id"],
        url=required["url"],
        title=required["title"],
        category=required["category"],
        tags=[str(t) for t in tags],
        type=required["type"],
        source=required["source"],
        saved=str(required["saved"]),
        summary=summary,
        points=points,
        status=str(front.get("status", "ok")),
        content=str(front.get("content", "full")),
        author=front.get("author"),
        published=str(front["published"]) if front.get("published") else None,
        cover=front.get("cover"),
        body=body,
    )


def note_stem(note: Note) -> str:
    """The file name a note earns from its date and title, before note_path()
    disambiguates it against what is already on disk."""
    return f"{_safe(note.saved) or 'undated'}-{slug(note.title, note.id)}"


def note_path(cfg: Config, note: Note) -> Path:
    stem = note_stem(note)
    candidate = cfg.links_dir / f"{stem}.md"
    n = 2
    while candidate.exists():
        existing = read_note(candidate)
        if existing is not None and existing.id == note.id:
            return candidate
        candidate = cfg.links_dir / f"{stem}-{n}.md"
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
    atomic_write(resolved, render(note, language))
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


def _scan(cfg: Config) -> tuple[list[tuple[Path, Note]], list[Path]]:
    """Every readable note under links_dir, plus the files of ours it could not read."""
    if not cfg.links_dir.is_dir():
        return [], []
    found: list[tuple[Path, Note]] = []
    skipped: list[Path] = []
    for path in sorted(cfg.links_dir.glob("*.md")):
        note, unreadable = scan_file(path)
        if note is not None:
            found.append((path, note))
        elif unreadable:
            skipped.append(path)
    return found, skipped


def all_notes(cfg: Config) -> list[Note]:
    return [note for _, note in _scan(cfg)[0]]


def find_note(cfg: Config, link_id: str) -> tuple[Path, Note] | None:
    for path, note in _scan(cfg)[0]:
        if note.id == link_id:
            return path, note
    return None


def categories(cfg: Config) -> dict[str, int]:
    counts: dict[str, int] = {}
    for note in all_notes(cfg):
        counts[note.category] = counts.get(note.category, 0) + 1
    return dict(sorted(counts.items()))


def _index_name(category: str) -> str:
    return re.sub(r"[\\/:*?\"<>|]+", "-", category).strip(" .")


def index_path(cfg: Config, category: str) -> Path:
    # The category name is written by a model: it can never leave our folder
    # or invent subdirectories. A pure function of the category, never of the language.
    name = _index_name(category) or INDEX_TEXT["es"][1]
    return cfg.root / f"{name}.md"


def _plain(text: str) -> str:
    """One line, no whitespace runs."""
    return " ".join(text.split())


def write_index(cfg: Config, category: str, entries: list[tuple[Path, Note]], language: str) -> Path:
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
        label = _plain(re.sub(r"[|\[\]]", " ", note.title))
        line = f"- [[{path.stem}|{label}]]"
        head = note.summary.strip().splitlines()[0] if note.summary.strip() else ""
        tags = " ".join(f"#{t}" for t in note.tags)
        detail = " — ".join(part for part in (f"`{tags}`" if tags else "", head) if part)
        if detail:
            line += f"\n  {detail}"
        lines.append(line)

    target = index_path(cfg, category)
    resolved = ensure_inside_root(cfg, target)
    if resolved.exists() and read_front(resolved) is None:
        raise ProtectedNote(f"refusing to overwrite a file without the marker: {target}")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(resolved, "\n".join(lines) + "\n")
    return resolved


def rebuild_indexes(cfg: Config, language: str) -> RebuildResult:
    """Rewrite one index per category and delete the ones left without notes.

    Only reads notes; never rewrites them. Files of ours it could not read
    (hand-broken) are left alone and listed in `skipped`; a category whose
    index path is held by a user file is listed in `blocked`. Never raises
    for either.
    """
    found, skipped = _scan(cfg)
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
        target = index_path(cfg, category)
        if target in claimed:
            # Two categories sanitize to the same file name. The first in sorted
            # order wins, so the winner is stable across rebuilds.
            blocked.append(target)
            continue
        claimed.add(target)
        try:
            written.append(write_index(cfg, category, entries, language))
        except ProtectedNote:
            # One category in the way must not stop the others from updating.
            blocked.append(target)

    keep = {p.name for p in claimed}
    if cfg.root.is_dir():
        for path in cfg.root.glob("*.md"):
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


def update_note(cfg: Config, link_id: str, language: str,
                category: str | None = None, tags=None) -> Path | None:
    """Change one of our notes' classification and rebuild the indexes.

    Returns the path written, or None if no note of ours has that id. Raises
    BadCategory for a category we refuse, before touching anything.
    """
    found = find_note(cfg, link_id)
    if found is None:
        return None
    path, note = found
    if category is not None:
        note.category = _checked_category(category)
    if tags is not None:
        note.tags = normalize_tags(tags)
    # In place: the name is a function of saved + title, which this never
    # changes, and an unlink here would be a note destroyed by a failed write.
    written = write_note(cfg, note, language, path=path)
    rebuild_indexes(cfg, language)
    return written


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


def delete_note(cfg: Config, link_id: str, language: str) -> Path | None:
    """Move one of our notes to trash/ and rebuild the indexes.

    Returns the new path, or None if no note of ours has that id. Deleting
    fires from a POST in a browser, so it has to be undoable: the file keeps
    its name and content and can be dragged back from Obsidian.
    """
    found = find_note(cfg, link_id)
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
    rebuild_indexes(cfg, language)
    return target


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


def rename_category(cfg: Config, old: str, new: str, language: str) -> RenameResult:
    """Rename a category; if `new` already exists, the two merge.

    Only touches notes of ours: _scan() already discards everything else.
    """
    target = _checked_category(new)
    moved = 0
    failed: list[tuple[Path, str]] = []
    for path, note in _scan(cfg)[0]:
        if note.category != old:
            continue
        note.category = target
        try:
            write_note(cfg, note, language, path=path)
        except (ProtectedNote, OSError) as error:
            failed.append((path, str(error)))
            continue
        moved += 1
    rebuild_indexes(cfg, language)
    return RenameResult(moved=moved, failed=failed)
