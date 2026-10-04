"""The only module that touches the network. No test goes in here."""

from __future__ import annotations

import codecs
import re
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

MAX_BYTES = 8 * 1024 * 1024
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) oknowledge/0.1"
ACCEPT_LANGUAGE = "es,en;q=0.8"
MAX_REDIRECTS = 5

_HEADER_CHARSET = re.compile(r"charset\s*=\s*[\"']?([\w.:-]+)", re.I)
_META_CHARSET = re.compile(rb"<meta[^>]+charset\s*=\s*[\"']?([\w.:-]+)", re.I)


class NetworkError(Exception):
    """The page could not be fetched."""


def _known(name: str | None) -> str | None:
    if not name:
        return None
    try:
        codecs.lookup(name)
        "a".encode(name)   # raises LookupError for binary codecs (base64, zlib, ...)
    except (LookupError, ValueError):
        return None
    return name


@dataclass
class Fetched:
    status: int
    content_type: str
    content: bytes
    final_url: str

    @property
    def text(self) -> str:
        """Decode with the header's charset, else the page's own <meta>, else UTF-8.

        Servers often declare a legacy charset while sending UTF-8, so bytes that
        are valid UTF-8 and contain multibyte sequences are read as UTF-8.
        """
        match = _HEADER_CHARSET.search(self.content_type)
        encoding = _known(match.group(1)) if match else None
        if encoding is None:
            sniffed = _META_CHARSET.search(self.content[:4096])
            encoding = _known(sniffed.group(1).decode("ascii", "ignore")) if sniffed else None
        decoded = None
        if encoding and codecs.lookup(encoding).name != "utf-8" and not self.content.isascii():
            try:
                decoded = self.content.decode("utf-8")
            except UnicodeDecodeError:
                pass
        if decoded is None:
            decoded = self.content.decode(encoding or "utf-8", errors="replace")
        # Strip the BOM on every path: left in, U+FEFF leads the extracted text
        # and from there the note's title.
        return decoded.lstrip("\ufeff")


def fetch(url: str, timeout: float = 30.0, max_bytes: int | None = None) -> Fetched:
    """GET a URL, refusing anything over max_bytes (decoded) or slower than ~2x timeout."""
    if max_bytes is None:
        max_bytes = MAX_BYTES
    if urlsplit(url).scheme.lower() not in ("http", "https"):
        raise NetworkError(f"only http and https links can be fetched: {url}")
    headers = {"User-Agent": USER_AGENT, "Accept-Language": ACCEPT_LANGUAGE}
    deadline = time.monotonic() + 2 * timeout
    try:
        with httpx.Client(headers=headers, timeout=timeout, follow_redirects=True,
                          max_redirects=MAX_REDIRECTS) as client:
            with client.stream("GET", url) as response:
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
        # httpx timeouts and connect errors often have an empty message
        detail = f"{type(error).__name__}: {error}" if str(error) else type(error).__name__
        raise NetworkError(f"could not fetch {url}: {detail}") from error
