"""Ordinary HTML pages, via trafilatura."""

from __future__ import annotations

import trafilatura

from ..model import Extracted
from ..net import fetch
from . import Unreadable, _host

MIN_CHARS = 200
HTML_TYPES = ("text/html", "application/xhtml+xml", "text/plain")


def from_html(html: str, url: str) -> Extracted:
    text = trafilatura.extract(
        html, url=url, include_comments=False, include_tables=True, favor_precision=True,
    )
    if not text or len(text.strip()) < MIN_CHARS:
        raise Unreadable(f"no readable text in {url}")

    meta = trafilatura.extract_metadata(html, default_url=url)
    published = (meta.date or "")[:10] if meta and meta.date else None
    return Extracted(
        title=(meta.title if meta and meta.title else url).strip(),
        text=text.strip(),
        type="article",
        source=_host(url),
        author=(meta.author.strip() if meta and meta.author else None),
        published=published or None,
        cover_url=(meta.image if meta and meta.image else None),
    )


def from_url(url: str) -> Extracted:
    fetched = fetch(url)
    kind = fetched.content_type.split(";")[0].strip().lower()
    if kind and kind not in HTML_TYPES:
        raise Unreadable(f"{url} is {kind}, not a web page")
    return from_html(fetched.text, url)
