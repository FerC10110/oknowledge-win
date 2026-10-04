"""From a URL to text. One extractor per type, chosen by the URL."""

from __future__ import annotations

from urllib.parse import urlsplit

from ..model import Extracted
from ..urls import normalize

__all__ = ["Extracted", "Unreadable", "detect_type", "extract"]

SOCIAL_HOSTS = {
    "reddit.com", "x.com", "twitter.com", "instagram.com", "tiktok.com",
    "threads.net", "bsky.app",
}


YOUTUBE_HOSTS = {"youtube.com", "youtu.be", "youtube-nocookie.com"}


class Unreadable(Exception):
    """The page was reached but no text could be pulled out of it."""


def _host(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _is(host: str, domains: set[str]) -> bool:
    return any(host == d or host.endswith("." + d) for d in domains)


def detect_type(url: str) -> str:
    url = normalize(url)
    host = _host(url)
    path = urlsplit(url).path.lower()
    if _is(host, YOUTUBE_HOSTS):
        return "youtube"
    if _is(host, {"github.com"}):
        return "github"
    if path.endswith(".pdf"):
        return "pdf"
    if _is(host, SOCIAL_HOSTS):
        return "social"
    return "article"


def extract(url: str) -> Extracted:
    """Fetch the URL and turn it into text. This is the door the pipeline uses."""
    kind = detect_type(url)
    if kind == "youtube":
        from .youtube import from_url
        return from_url(url)
    if kind == "github":
        from .github import from_url
        return from_url(url)
    if kind == "pdf":
        from .pdf import from_url
        return from_url(url)
    if kind == "social":
        from .social import from_url
        return from_url(url)
    from .article import NotAWebPage, from_url
    try:
        return from_url(url)
    except NotAWebPage as error:
        # The URL gave no hint (arxiv.org/pdf/2301.12345) but the response is a PDF.
        fetched = error.fetched
        if fetched.content_type.split(";")[0].strip().lower() == "application/pdf":
            from .pdf import from_bytes
            return from_bytes(fetched.content, fetched.final_url)
        raise
