"""From a URL to text. One extractor per type, chosen by the URL."""

from __future__ import annotations

from urllib.parse import urlsplit

from ..model import Extracted

__all__ = ["Extracted", "Unreadable", "detect_type", "extract"]

SOCIAL_HOSTS = {
    "reddit.com", "x.com", "twitter.com", "instagram.com", "tiktok.com",
    "threads.net", "bsky.app",
}


class Unreadable(Exception):
    """The page was reached but no text could be pulled out of it."""


def _host(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def detect_type(url: str) -> str:
    host = _host(url)
    path = urlsplit(url).path.lower()
    if host in {"youtube.com", "youtu.be", "m.youtube.com"}:
        return "youtube"
    if host == "github.com":
        return "github"
    if path.endswith(".pdf"):
        return "pdf"
    if host in SOCIAL_HOSTS or host.endswith(".reddit.com"):
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
    from .article import from_url
    return from_url(url)
