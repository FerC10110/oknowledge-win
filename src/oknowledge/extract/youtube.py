"""YouTube, via the system's yt-dlp.

It is not installed in the venv on purpose: yt-dlp breaks every time YouTube
changes something, and the system one is updated along with Omarchy.
"""

from __future__ import annotations

import html
import json
import re
import subprocess

from ..model import Extracted
from ..net import NetworkError, fetch
from . import Unreadable, _host

CAPTION_LANGS = ("es", "es-419", "en", "en-US")
YTDLP_TIMEOUT = 120


def vtt_to_text(vtt: str) -> str:
    """Spoken text of a WebVTT file: no header, cue ids, timings, notes or tags."""
    lines: list[str] = []
    for block in re.split(r"\n\s*\n", vtt.replace("\r\n", "\n")):
        rows = [r.strip() for r in block.strip().splitlines()]
        if not rows or rows[0].startswith(("WEBVTT", "NOTE", "STYLE", "REGION")):
            continue
        timing = next((i for i, r in enumerate(rows) if "-->" in r), None)
        if timing is None:
            continue
        for row in rows[timing + 1:]:
            row = html.unescape(re.sub(r"<[^>]+>", "", row)).strip()
            if row and (not lines or lines[-1] != row):
                lines.append(row)
    return " ".join(lines)


def _caption_url(data: dict) -> str | None:
    """A VTT track, preferring creator-made captions over automatic ones per language."""
    try:
        for lang in CAPTION_LANGS:
            for kind in ("subtitles", "automatic_captions"):
                for track in (data.get(kind) or {}).get(lang) or []:
                    if track.get("ext") == "vtt" and isinstance(track.get("url"), str):
                        return track["url"]
    except (AttributeError, TypeError):
        pass
    return None


def _str(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def from_ytdlp(data: dict, url: str, captions: str | None) -> Extracted:
    try:
        parts = [_str(data.get("description"))]
        if captions:
            parts.append(vtt_to_text(captions))
        text = "\n\n".join(p for p in parts if p)
        if not text:
            raise Unreadable(f"the video has neither description nor captions: {url}")

        date = str(data.get("upload_date") or "")
        published = f"{date[:4]}-{date[4:6]}-{date[6:8]}" if len(date) == 8 else None
        return Extracted(
            title=_str(data.get("title")) or url,
            text=text,
            type="youtube",
            source=_host(url),
            author=_str(data.get("channel")) or _str(data.get("uploader")) or None,
            published=published,
            cover_url=_str(data.get("thumbnail")) or None,
        )
    except (AttributeError, TypeError) as error:
        raise Unreadable(f"unexpected yt-dlp data for {url}: {error}") from error


def from_url(url: str) -> Extracted:
    try:
        proc = subprocess.run(
            ["yt-dlp", "--dump-json", "--no-warnings", "--skip-download", "--no-playlist",
             "--playlist-items", "1", "--", url],
            capture_output=True, text=True, timeout=YTDLP_TIMEOUT,
        )
    except FileNotFoundError as error:
        raise Unreadable(f"yt-dlp is not installed, so {url} cannot be read") from error
    except subprocess.TimeoutExpired as error:
        raise Unreadable(f"yt-dlp took over {YTDLP_TIMEOUT}s on {url}") from error
    if proc.returncode != 0:
        raise Unreadable(f"yt-dlp failed on {url}: {proc.stderr.strip()[:200]}")

    try:
        data = json.loads(proc.stdout)
    except ValueError as error:
        if proc.stdout.count("\n{") or proc.stdout.strip().count("\n"):
            raise Unreadable(f"{url} looks like a playlist, not a single video") from error
        raise Unreadable(f"yt-dlp gave unreadable output for {url}") from error
    if not isinstance(data, dict):
        raise Unreadable(f"yt-dlp gave unexpected output for {url}")

    captions = None
    track = _caption_url(data)
    if track:
        try:
            captions = fetch(track).text
        except NetworkError:
            captions = None
        # A consent or error page is not a transcript.
        if captions is not None and not captions.lstrip().startswith("WEBVTT"):
            captions = None
    return from_ytdlp(data, url, captions)
