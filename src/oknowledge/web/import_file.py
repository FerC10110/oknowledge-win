"""Getting a WhatsApp export out of a browser, and holding it between two steps.

Importing is two requests: one that reads the file and shows what it found, one
that writes. The file arrives in the first and is needed in the second, so the
text is staged under the state directory and named by a token.

Nothing here parses an export or writes a note. whatsapp.parse() and
pipeline.import_links() still do all of that, and the second request re-parses
the staged text rather than trusting anything the browser hands back: the token
names a file and carries no other meaning.
"""

from __future__ import annotations

import io
import re
import secrets
import time
import zipfile
from pathlib import Path

from ..atomic import atomic_write
from ..places import state_dir

# Six years of one busy group is 198 KB. Nothing near this cap is a real
# export, and the whole upload is held in memory to be parsed.
MAX_UPLOAD = 20 * 1024 * 1024
# What may come OUT of a zip. A kilobyte of zip can hold a gigabyte of zeroes,
# and the text is read into memory, so the bound is on the read and not on the
# size the archive declares -- a header can say anything.
MAX_TEXT = 32 * 1024 * 1024
# A staged upload left behind by a closed tab. It is the user's chat log: it
# does not get to sit on disk forever.
STALE_AFTER = 3600

ZIP_MAGIC = b"PK\x03\x04"
# Exactly what secrets.token_hex(16) produces, and nothing else. A traversal,
# an empty string and an upper-case spelling all fail here, before any path is
# built, which is what keeps the token from naming a file of its own choosing.
TOKEN = re.compile(r"[0-9a-f]{32}\Z")


class BadUpload(Exception):
    """What arrived is not a file this can read. The message is shown to the user."""


def _from_zip(data: bytes) -> str:
    try:
        bundle = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise BadUpload("that file starts like a zip but cannot be opened") from None
    with bundle:
        inside = [item for item in bundle.infolist()
                  if not item.is_dir() and item.filename.lower().endswith(".txt")]
        if not inside:
            raise BadUpload("the zip holds no .txt file; a WhatsApp export is one")
        try:
            with bundle.open(inside[0]) as stream:
                # One byte past the cap, so a file exactly at it still reads.
                raw = stream.read(MAX_TEXT + 1)
        except (OSError, zipfile.BadZipFile, EOFError) as error:
            raise BadUpload(f"the zip could not be read ({type(error).__name__})") from None
    if len(raw) > MAX_TEXT:
        raise BadUpload("the text inside that zip is far larger than any chat export")
    return raw.decode("utf-8", errors="replace")


def text_of(data: bytes) -> str:
    """The export's text, from a .txt or from the .zip WhatsApp hands you.

    The kind is decided by the bytes, not by the name: a browser sends whatever
    the file was called on disk, and a chat export renamed .txt is still a zip.

    errors="replace" for the same reason the CLI uses it: six years of chat can
    hold one byte that is not UTF-8, and losing a thousand links over it is the
    kind of silent loss this project does not allow.
    """
    if not data:
        raise BadUpload("that file is empty")
    if len(data) > MAX_UPLOAD:
        raise BadUpload("that file is far larger than any chat export")
    if data.startswith(ZIP_MAGIC):
        return _from_zip(data)
    return data.decode("utf-8", errors="replace")


def staging_dir() -> Path:
    return state_dir() / "import"


def _path(token: str) -> Path | None:
    """Where a token's text lives, or None if the token is not one of ours."""
    return staging_dir() / f"{token}.txt" if TOKEN.match(token or "") else None


def sweep(now: float | None = None) -> None:
    """Drop the uploads nobody confirmed. Never raises: this is housekeeping."""
    cutoff = (now if now is not None else time.time()) - STALE_AFTER
    try:
        entries = list(staging_dir().iterdir())
    except OSError:
        return
    for entry in entries:
        try:
            if entry.is_file() and entry.stat().st_mtime < cutoff:
                entry.unlink()
        except OSError:
            continue


def stage(text: str) -> str:
    """Hold `text` for the request that confirms it, and return its token."""
    sweep()
    folder = staging_dir()
    folder.mkdir(parents=True, exist_ok=True)
    token = secrets.token_hex(16)
    atomic_write(folder / f"{token}.txt", text, fsync_dir=True)
    return token


def staged(token: str) -> str | None:
    """The text a token names, or None -- which is also the answer for a token
    that is not one, for one already confirmed, and for one that was swept."""
    path = _path(token)
    if path is None:
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def drop(token: str) -> None:
    """Forget a staged upload. A token that names nothing is already forgotten."""
    path = _path(token)
    if path is None:
        return
    try:
        path.unlink()
    except OSError:
        pass
