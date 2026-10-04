"""The only module that touches the network. No test goes in here."""

from __future__ import annotations

import codecs
import re
import time
from dataclasses import dataclass

import httpx

MAX_BYTES = 8 * 1024 * 1024
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) oknowledge/0.1"

_HEADER_CHARSET = re.compile(r"charset\s*=\s*[\"']?([\w.:-]+)", re.I)
_META_CHARSET = re.compile(rb"<meta[^>]+charset\s*=\s*[\"']?([\w.:-]+)", re.I)


class NetworkError(Exception):
    """The page could not be fetched."""


def _known(name: str | None) -> str | None:
    if not name:
        return None
    try:
        return codecs.lookup(name).name
    except LookupError:
        return None


@dataclass
class Fetched:
    status: int
    content_type: str
    content: bytes
    final_url: str

    @property
    def text(self) -> str:
        """Decode with the header's charset, else the page's own <meta>, else UTF-8."""
        match = _HEADER_CHARSET.search(self.content_type)
        encoding = _known(match.group(1)) if match else None
        if encoding is None:
            sniffed = _META_CHARSET.search(self.content[:4096])
            encoding = _known(sniffed.group(1).decode("ascii", "ignore")) if sniffed else None
        return self.content.decode(encoding or "utf-8", errors="replace")


def fetch(url: str, timeout: float = 30.0, max_bytes: int = MAX_BYTES) -> Fetched:
    """GET a URL, refusing anything over max_bytes (decoded) or slower than ~2x timeout."""
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "es,en;q=0.8"}
    deadline = time.monotonic() + 2 * timeout
    try:
        with httpx.stream("GET", url, headers=headers, timeout=timeout,
                          follow_redirects=True) as response:
            if response.status_code >= 400:
                raise NetworkError(f"{response.status_code} for {url}")
            declared = response.headers.get("content-length", "")
            if declared.isdigit() and int(declared) > max_bytes:
                raise NetworkError(f"page over {max_bytes} bytes: {url}")
            chunks, size = [], 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > max_bytes:
                    raise NetworkError(f"page over {max_bytes} bytes: {url}")
                if time.monotonic() > deadline:
                    raise NetworkError(f"download too slow: {url}")
                chunks.append(chunk)
            return Fetched(
                status=response.status_code,
                content_type=response.headers.get("content-type", ""),
                content=b"".join(chunks),
                final_url=str(response.url),
            )
    except NetworkError:
        raise
    except Exception as error:
        raise NetworkError(f"could not fetch {url}: {error}") from error
