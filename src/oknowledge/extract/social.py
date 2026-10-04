"""Social media, best effort.

Reddit publishes its JSON and reads fine. X, Instagram and TikTok ask for a
login or block automated readers: when that happens, Unreadable is raised and
the pipeline saves the note anyway, with the URL and marked partial.
"""

from __future__ import annotations

import json
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


def from_url(url: str) -> Extracted:
    if _is(_host(url), {"reddit.com"}):
        try:
            return from_reddit(json.loads(fetch(_reddit_json_url(url)).text), url)
        except (NetworkError, ValueError) as error:
            raise Unreadable(f"could not read {url}: {error}") from error
    try:
        fetch(url)
    except NetworkError as error:
        raise Unreadable(f"{_host(url)} does not let us read it: {error}") from error
    raise Unreadable(f"{_host(url)} needs a logged-in browser to read")
