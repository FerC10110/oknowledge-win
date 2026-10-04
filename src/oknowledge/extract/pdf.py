"""PDFs, via pypdf. Only the text the PDF already carries: there is no OCR."""

from __future__ import annotations

import io
from urllib.parse import unquote, urlsplit

from pypdf import PdfReader

from ..model import Extracted
from ..net import NetworkError, fetch
from . import Unreadable, _host

MAX_PAGES = 20
# A PDF cannot be cut short (pypdf needs the cross-reference table at the end),
# so it gets a higher ceiling than a web page instead of being truncated.
PDF_MAX_BYTES = 32 * 1024 * 1024
PLACEHOLDER_TITLES = {"untitled"}   # what PDF generators (reportlab, ...) write when nobody set one


def from_bytes(data: bytes, url: str) -> Extracted:
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise Unreadable(f"the PDF at {url} is protected by a password")
        pages = [page.extract_text() or "" for page in reader.pages[:MAX_PAGES]]
        meta = reader.metadata
        meta_title, meta_author = (meta.title, meta.author) if meta else (None, None)
    except Unreadable:
        raise
    except Exception as error:
        raise Unreadable(
            f"could not read the PDF at {url}: {type(error).__name__}: {error}") from error

    text = "\n\n".join(p.strip() for p in pages if p.strip()).strip()
    if not text:
        raise Unreadable(f"the PDF at {url} has no text layer (a scan needs OCR)")

    name = unquote(urlsplit(url).path.rsplit("/", 1)[-1]) or url
    title = (meta_title or "").strip()
    if title.lower() in PLACEHOLDER_TITLES:
        title = ""
    title = title or name
    return Extracted(
        title=title,
        text=text,
        type="pdf",
        source=_host(url),
        author=meta_author or None,
    )


def from_url(url: str) -> Extracted:
    try:
        fetched = fetch(url, max_bytes=PDF_MAX_BYTES)
    except NetworkError as error:
        if error.too_large:
            raise Unreadable(
                f"the PDF is too big to read (limit {PDF_MAX_BYTES // 2**20} MiB): {error}"
            ) from error
        raise Unreadable(f"could not download the PDF: {error}") from error
    return from_bytes(fetched.content, fetched.final_url)
