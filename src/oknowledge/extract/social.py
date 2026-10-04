"""Social media, best effort.

Reddit publishes its JSON and reads fine. X, Instagram and TikTok ask for a
login, but still serve OpenGraph and Twitter-card tags to anonymous clients (it
is how link previews work), so those give a title and a blurb without running
any JavaScript. A page with neither raises Unreadable, and the pipeline saves
the note anyway, with the URL and marked partial.
"""

from __future__ import annotations

import json
from html.parser import HTMLParser
from urllib.parse import urlsplit, urlunsplit

from ..model import Extracted
from ..net import NetworkError, fetch
from . import Unreadable, _host, _is

MAX_COMMENTS = 20
MAX_TITLE = 300
REMOVED = {"[removed]", "[deleted]"}


def _str(value) -> str:
    if value is not None and not isinstance(value, str):
        raise TypeError(f"expected text, got {type(value).__name__}")
    return (value or "").strip()


def from_reddit(data, url: str) -> Extracted:
    try:
        post = data[0]["data"]["children"][0]["data"]
        comments = data[1]["data"]["children"] if len(data) > 1 else []
        selftext = _str(post.get("selftext"))
        parts = [] if selftext in REMOVED else [selftext]
        for child in comments[:MAX_COMMENTS]:
            body = _str((child.get("data") or {}).get("body"))
            if body and body not in REMOVED:
                parts.append(f"- {body}")
        title = _str(post.get("title"))
        author = _str(post.get("author")) or None
        text = "\n\n".join(p for p in parts if p)
    except (KeyError, IndexError, TypeError, AttributeError) as error:
        raise Unreadable(
            f"unexpected reddit payload for {url}: {type(error).__name__}: {error}") from error

    if not title and not text:
        raise Unreadable(f"the thread has no title and no text: {url}")
    return Extracted(
        title=title or url,
        text=text,
        type="social",
        source=_host(url),
        author=author,
    )


def _reddit_json_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/") + ".json", "", ""))


class _Meta(HTMLParser):
    """Collects <meta> name/property -> content pairs and the document's <title>.

    Only the first <title> before the body counts (icons inside the page carry
    <title> too), and an unclosed one is cut off instead of eating the page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.title = ""
        self._state = "before"     # before -> inside -> done
        self._in_body = False

    def handle_starttag(self, tag, attrs):
        if tag == "body":
            self._in_body = True
            self._state = "done"
        elif self._in_body:
            return
        elif tag == "title" and self._state == "before":
            self._state = "inside"
        elif tag in ("meta", "head") and self._state == "inside":
            self._state = "done"       # an unclosed <title> ended here
        if tag == "meta" and not self._in_body:
            a = {k.lower(): (v or "") for k, v in attrs}
            key = (a.get("property") or a.get("name") or "").lower()
            if key and a.get("content", "").strip():
                self.meta.setdefault(key, a["content"].strip())

    def handle_endtag(self, tag):
        if tag in ("title", "head") and self._state == "inside":
            self._state = "done"

    def handle_data(self, data):
        if self._state != "inside":
            return
        if "<" in data:                # an unclosed <title>: the rest is page markup
            data, self._state = data.split("<", 1)[0], "done"
        self.title = (self.title + data)[:MAX_TITLE]


def from_preview_tags(html: str, url: str) -> Extracted:
    """Build a note from the link-preview tags of a page, as far as they go.

    A bare <title> is usually just the site name on a login wall ("Instagram"),
    so it only counts next to an og:/twitter: title or a description."""
    parser = _Meta()
    try:
        parser.feed(html)
        parser.close()
    except Exception as error:
        raise Unreadable(f"could not parse {url}: {type(error).__name__}") from error
    meta = parser.meta

    def first(*keys: str) -> str:
        return next((meta[k] for k in keys if k in meta), "")

    card_title = first("og:title", "twitter:title")
    description = first("og:description", "twitter:description", "description")
    if not card_title and not description:
        raise Unreadable(f"{_host(url)} shows no preview without logging in: {url}")
    return Extracted(
        title=card_title or " ".join(parser.title.split()) or url,
        text=description,
        type="social",
        source=_host(url),
        author=first("article:author", "author", "twitter:creator") or None,
        cover_url=first("og:image", "og:image:url", "twitter:image") or None,
    )


def from_url(url: str) -> Extracted:
    if _is(_host(url), {"reddit.com"}):
        try:
            return from_reddit(json.loads(fetch(_reddit_json_url(url)).text), url)
        except (NetworkError, ValueError) as error:
            raise Unreadable(f"could not read {url}: {error}") from error
    try:
        fetched = fetch(url)
    except NetworkError as error:
        raise Unreadable(f"{_host(url)} does not let us read it: {error}") from error
    return from_preview_tags(fetched.text, fetched.final_url)
