"""The only module that writes Markdown.

Two rules, and both live here for a reason: the vault belongs to the user.

1. Only write inside <vault>/<folder>/.
2. Only touch files whose frontmatter has `oknowledge: 1`. A file without that
   marker is never modified or deleted, even if it sits in our folder and is
   named exactly like the one we were about to write.
"""

from __future__ import annotations

import os
import re
import tempfile
import unicodedata
from pathlib import Path

import yaml

from .config import Config
from .model import Note

MARKER = "oknowledge"
MARKER_VERSION = 1

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


def slug(text: str, fallback: str) -> str:
    plain = unicodedata.normalize("NFKD", text)
    plain = plain.encode("ascii", "ignore").decode("ascii").lower()
    plain = re.sub(r"[^a-z0-9]+", "-", plain).strip("-")[:60].strip("-")
    return plain or fallback


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


def read_front(path: Path) -> dict | None:
    """The frontmatter, only if the file is ours. Otherwise None."""
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
    except yaml.YAMLError:
        return None
    if not isinstance(front, dict) or front.get(MARKER) != MARKER_VERSION:
        return None
    return front


def _split_body(text: str) -> tuple[str, list[str], str | None]:
    """Return (summary, points, original content) from a body written by render()."""
    body = text.split("\n---", 1)[1]          # everything after the frontmatter
    lines = body.splitlines()
    # Skip past the H1.
    start = next((i + 1 for i, line in enumerate(lines) if line.startswith("# ")), 0)
    sections: list[list[str]] = [[]]
    for line in lines[start:]:
        if line.startswith("## "):
            sections.append([])
        else:
            sections[-1].append(line)
    summary = "\n".join(sections[0]).strip()
    points = [line[2:].strip() for line in sections[1] if line.startswith("- ")] if len(sections) > 1 else []
    original = "\n".join(sections[2]).strip() if len(sections) > 2 else None
    return summary, points, original or None


_REQUIRED_TEXT = ("id", "url", "title", "category", "type", "source")


def read_note(path: Path) -> Note | None:
    """The note, if the file is ours and parseable. Never modifies the file.

    A marked file that is missing a required key, or has a value of the wrong
    type (the user hand-edits these), reads as None, same as an unmarked one.
    """
    front = read_front(path)
    if front is None or front.get("kind") == "index":
        return None
    try:
        if not all(isinstance(front[k], str) for k in _REQUIRED_TEXT):
            return None
        tags = front.get("tags") or []
        if not isinstance(tags, list):
            return None
        for key in ("author", "cover"):
            if front.get(key) is not None and not isinstance(front[key], str):
                return None
        summary, points, body = _split_body(path.read_text(encoding="utf-8"))
        return Note(
            id=front["id"],
            url=front["url"],
            title=front["title"],
            category=front["category"],
            tags=[str(t) for t in tags],
            type=front["type"],
            source=front["source"],
            saved=str(front["saved"]),
            summary=summary,
            points=points,
            status=str(front.get("status", "ok")),
            content=str(front.get("content", "full")),
            author=front.get("author"),
            published=str(front["published"]) if front.get("published") else None,
            cover=front.get("cover"),
            body=body,
        )
    except (KeyError, IndexError, TypeError, ValueError, OSError):
        return None


def note_path(cfg: Config, note: Note) -> Path:
    stem = f"{note.saved}-{slug(note.title, note.id)}"
    candidate = cfg.links_dir / f"{stem}.md"
    n = 2
    while candidate.exists():
        existing = read_note(candidate)
        if existing is not None and existing.id == note.id:
            return candidate
        candidate = cfg.links_dir / f"{stem}-{n}.md"
        n += 1
    return candidate


def _ensure_inside_root(cfg: Config, target: Path) -> Path:
    """Resolve target (following symlinks) and require it inside cfg.root."""
    resolved = target.resolve()
    if not resolved.is_relative_to(cfg.root.resolve()):
        raise ProtectedNote(f"refusing to write outside the managed folder: {target}")
    return resolved


def _atomic_write(target: Path, text: str) -> None:
    """Write via a temp file in the same directory, then os.replace over target."""
    mode = target.stat().st_mode & 0o777 if target.exists() else 0o644
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=".oknowledge-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.chmod(tmp_name, mode)
        os.replace(tmp_name, target)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def write_note(cfg: Config, note: Note, language: str, path: Path | None = None) -> Path:
    target = path or note_path(cfg, note)
    resolved = _ensure_inside_root(cfg, target)       # location first, before any write
    if resolved.exists() and read_front(resolved) is None:
        raise ProtectedNote(f"refusing to overwrite a file without the marker: {target}")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(resolved, render(note, language))
    return target
