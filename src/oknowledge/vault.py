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
import secrets
import unicodedata
from dataclasses import dataclass, field
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


def note_path(cfg: Config, note: Note) -> Path:
    stem = f"{_safe(note.saved) or 'undated'}-{slug(note.title, note.id)}"
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
    """Resolve target (following symlinks) and require it strictly inside cfg.root."""
    resolved = target.resolve()
    root = cfg.root.resolve()
    if resolved == root or not resolved.parent.is_relative_to(root):
        raise ProtectedNote(f"refusing to write outside the managed folder: {target}")
    return resolved


def _atomic_write(target: Path, text: str) -> None:
    """Write via a temp file in the same directory, then os.replace over target.

    The temp file is created with mode 0o666 so the umask applies to new notes;
    an existing note keeps its current mode.
    """
    mode = target.stat().st_mode & 0o777 if target.exists() else None
    tmp = target.parent / f".oknowledge-{secrets.token_hex(8)}.tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
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
    return resolved


INDEX_NOTICE = "<!-- Generado por oknowledge. Los cambios a mano se pierden. -->"

_CLAIMS_MARKER = re.compile(rf"^{MARKER}:", re.MULTILINE)


@dataclass(frozen=True)
class RebuildResult:
    """What a reindex did: the indexes it wrote and the files it could not read."""

    written: list[Path] = field(default_factory=list)
    skipped: list[Path] = field(default_factory=list)


def _claims_marker(path: Path) -> bool:
    """True if the file's frontmatter text carries an `oknowledge:` key, even if
    the rest is too broken to parse. Lets a reindex tell a note of ours that the
    user hand-broke from a file that was never ours."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    if not text.startswith("---\n"):
        return False
    end = text.find("\n---", 4)
    return end != -1 and _CLAIMS_MARKER.search(text[4:end]) is not None


def _scan(cfg: Config) -> tuple[list[tuple[Path, Note]], list[Path]]:
    """Every readable note under links_dir, plus the files of ours it could not read."""
    if not cfg.links_dir.is_dir():
        return [], []
    found: list[tuple[Path, Note]] = []
    skipped: list[Path] = []
    for path in sorted(cfg.links_dir.glob("*.md")):
        note = read_note(path)
        if note is not None:
            found.append((path, note))
            continue
        front = read_front(path)
        is_index = front is not None and front.get("kind") == "index"
        if not is_index and _claims_marker(path):
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


def index_path(cfg: Config, category: str) -> Path:
    # The category name is written by a model: it can never leave our folder
    # or invent subdirectories.
    name = re.sub(r"[\\/:*?\"<>|]+", "-", category).strip(" .") or "Sin categoria"
    return cfg.root / f"{name}.md"


def write_index(cfg: Config, category: str, notes: list[Note]) -> Path:
    ordered = sorted(notes, key=lambda n: (n.saved, n.title), reverse=True)

    front = yaml.safe_dump(
        {MARKER: MARKER_VERSION, "kind": "index", "category": category},
        sort_keys=False, allow_unicode=True,
    ).strip()

    lines = [f"---\n{front}\n---\n", f"# {category} · {len(ordered)} links\n", f"{INDEX_NOTICE}\n"]
    for note in ordered:
        stem = note_path(cfg, note).stem
        tags = " ".join(f"#{t}" for t in note.tags)
        head = note.summary.strip().splitlines()[0] if note.summary.strip() else ""
        lines.append(f"- [[{stem}|{note.title}]]\n  `{tags}` — {head}")

    target = index_path(cfg, category)
    resolved = _ensure_inside_root(cfg, target)
    if resolved.exists() and read_front(resolved) is None:
        raise ProtectedNote(f"refusing to overwrite a file without the marker: {target}")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(resolved, "\n".join(lines) + "\n")
    return resolved


def rebuild_indexes(cfg: Config) -> RebuildResult:
    """Rewrite one index per category and delete the ones left without notes.

    Only reads notes; never rewrites them. Files of ours it could not read
    (hand-broken) are left alone and listed in `skipped`.
    """
    found, skipped = _scan(cfg)
    grouped: dict[str, list[Note]] = {}
    for _, note in found:
        grouped.setdefault(note.category, []).append(note)

    written = [write_index(cfg, category, notes) for category, notes in sorted(grouped.items())]

    keep = {p.name for p in written}
    if cfg.root.is_dir():
        for path in cfg.root.glob("*.md"):
            front = read_front(path)
            if front is not None and front.get("kind") == "index" and path.name not in keep:
                path.unlink()
    return RebuildResult(written=written, skipped=skipped)
