"""From a URL to text. One extractor per type, chosen by the URL."""

from __future__ import annotations

from urllib.parse import urlsplit

from ..model import Extracted
from ..net import NetworkError
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


def _content_type(header: str) -> str:
    return header.split(";")[0].strip().lower()


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
    """Fetch the URL and turn it into text. This is the door the pipeline uses.

    The only exception that leaves here is Unreadable."""
    try:
        return _extract(url)
    except NetworkError as error:
        raise Unreadable(str(error)) from error
    except (AttributeError, TypeError, KeyError, ValueError) as error:
        # Backstop for a payload shape no extractor foresaw. The type stays in
        # the message so a bug of ours is not disguised as "the page is unreadable".
        raise Unreadable(
            f"could not read {url}: {type(error).__name__}: {error}") from error


def _extract(url: str) -> Extracted:
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
    except NetworkError as error:
        # A big PDF behind an extensionless URL trips the web-page size cap
        # before we can see what it is; the headers still say. Fetch it again
        # under the PDF ceiling (pdf.from_url explains if it is over that too).
        if error.too_large and _content_type(error.headers.get("content-type", "")) == "application/pdf":
            from .pdf import from_url as pdf_from_url
            return pdf_from_url(url)
        raise
    except NotAWebPage as error:
        # The URL gave no hint (arxiv.org/pdf/2301.12345) but the response is a PDF.
        fetched = error.fetched
        if _content_type(fetched.content_type) == "application/pdf":
            from .pdf import from_bytes
            return from_bytes(fetched.content, fetched.final_url)
        raise
