"""YouTube, via the system's yt-dlp.

It is not installed in the venv on purpose: yt-dlp breaks every time YouTube
changes something, and the system one is updated along with Omarchy.
"""

from __future__ import annotations

import json
import re
import subprocess

from ..model import Extracted
from ..net import NetworkError, fetch
from . import Unreadable, _host

CAPTION_LANGS = ("es", "es-419", "en", "en-US")
YTDLP_TIMEOUT = 120


def vtt_to_text(vtt: str) -> str:
    lines: list[str] = []
    for raw in vtt.splitlines():
        line = raw.strip()
        if not line or "-->" in line or line.startswith(("WEBVTT", "Kind:", "Language:")):
            continue
        line = re.sub(r"<[^>]+>", "", line)
        if line and (not lines or lines[-1] != line):
            lines.append(line)
    return " ".join(lines)


def _caption_url(data: dict) -> str | None:
    tracks = {**(data.get("subtitles") or {}), **(data.get("automatic_captions") or {})}
    for lang in CAPTION_LANGS:
        for track in tracks.get(lang, []):
            if track.get("ext") == "vtt" and track.get("url"):
                return track["url"]
    return None


def from_ytdlp(data: dict, url: str, captions: str | None) -> Extracted:
    parts = [data.get("description") or ""]
    if captions:
        parts.append(vtt_to_text(captions))
    text = "\n\n".join(p.strip() for p in parts if p.strip())
    if not text:
        raise Unreadable(f"the video has neither description nor captions: {url}")

    date = str(data.get("upload_date") or "")
    published = f"{date[:4]}-{date[4:6]}-{date[6:8]}" if len(date) == 8 else None
    return Extracted(
        title=(data.get("title") or url).strip(),
        text=text,
        type="youtube",
        source=_host(url),
        author=(data.get("channel") or data.get("uploader") or None),
        published=published,
        cover_url=data.get("thumbnail"),
    )


def from_url(url: str) -> Extracted:
    try:
        proc = subprocess.run(
            ["yt-dlp", "--dump-json", "--no-warnings", "--skip-download", "--no-playlist",
             "--", url],
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
    return from_ytdlp(data, url, captions)
