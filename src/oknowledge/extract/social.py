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


def from_reddit(data, url: str) -> Extracted:
    try:
        post = data[0]["data"]["children"][0]["data"]
        comments = data[1]["data"]["children"] if len(data) > 1 else []
        parts = [post.get("selftext") or ""]
        for child in comments[:MAX_COMMENTS]:
            body = (child.get("data") or {}).get("body")
            if body:
                parts.append(f"- {body}")
    except (KeyError, IndexError, TypeError, AttributeError) as error:
        raise Unreadable(f"unexpected reddit payload for {url}") from error

    text = "\n\n".join(p.strip() for p in parts if p.strip())
    if not text:
        raise Unreadable(f"the thread has no text: {url}")

    return Extracted(
        title=post.get("title") or url,
        text=text,
        type="social",
        source=_host(url),
        author=post.get("author"),
    )


def _reddit_json_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/") + ".json", "", ""))


class _Meta(HTMLParser):
    """Collects <meta> name/property -> content pairs and the <title>."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            a = {k.lower(): (v or "") for k, v in attrs}
            key = (a.get("property") or a.get("name") or "").lower()
            if key and a.get("content", "").strip():
                self.meta.setdefault(key, a["content"].strip())

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data


def from_preview_tags(html: str, url: str) -> Extracted:
    """Build a note from the link-preview tags of a page, as far as they go."""
    parser = _Meta()
    try:
        parser.feed(html)
        parser.close()
    except Exception as error:
        raise Unreadable(f"could not parse {url}: {type(error).__name__}") from error
    meta = parser.meta

    def first(*keys: str) -> str:
        return next((meta[k] for k in keys if k in meta), "")

    title = first("og:title", "twitter:title") or " ".join(parser.title.split())
    description = first("og:description", "twitter:description", "description")
    if not title and not description:
        raise Unreadable(f"{_host(url)} shows no preview without logging in: {url}")
    return Extracted(
        title=title or url,
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
