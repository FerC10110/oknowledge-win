"""Ordinary HTML pages, via trafilatura."""

from __future__ import annotations

import trafilatura

from ..model import Extracted
from ..net import Fetched, fetch
from . import Unreadable, _host

MIN_CHARS = 200
HTML_TYPES = ("text/html", "application/xhtml+xml", "text/plain")


class NotAWebPage(Unreadable):
    """The URL answered with something that is not HTML. Carries the response,
    so the dispatcher can hand it to the right extractor without a second fetch."""

    def __init__(self, message: str, fetched: Fetched):
        super().__init__(message)
        self.fetched = fetched


def from_html(html: str, url: str) -> Extracted:
    try:
        text = trafilatura.extract(
            html, url=url, include_comments=False, include_tables=True,
            favor_precision=True,
        )
        if not text or len(text.strip()) < MIN_CHARS:
            raise Unreadable(
                f"page returned too little text (it may need JavaScript or a login): {url}")
        meta = trafilatura.extract_metadata(html, default_url=url)
    except Unreadable:
        raise
    except Exception as error:
        raise Unreadable(f"could not parse {url}: {type(error).__name__}") from error

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
        raise NotAWebPage(f"{url} is {kind}, not a web page", fetched)
    return from_html(fetched.text, fetched.final_url)
