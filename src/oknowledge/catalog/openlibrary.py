"""Open Library: anything that was printed, free and without a key.

Two calls per card, measured rather than assumed: the search carries the
author, the year, the rating out of five, the page count and the cover, and
the synopsis lives only on the work. The second call is the one allowed to
fail -- a book with no synopsis is still a book.

An id is looked up by its whole key. `q=OL893414W` finds nothing;
`q=key:/works/OL893414W` finds the one.
"""

from __future__ import annotations

import json
from urllib.parse import quote

from .. import net
from . import Candidate, Card

BASE = "https://openlibrary.org"
COVERS = "https://covers.openlibrary.org/b/id"
FIELDS = ("key,title,author_name,first_publish_year,ratings_average,"
          "number_of_pages_median,subject,cover_i")
"""Only what a card shows. The default answer carries every edition of
every printing, which for Dune is half a megabyte of nothing we use."""
MOST = 8
TIMEOUT = 8.0
MAX_BYTES = 2_000_000


def _text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return ""


def _first(value) -> str:
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str) and item.strip():
                return item.strip()
    return _text(value).strip()


def _rating(value) -> str:
    """Out of five, to one decimal. The catalog answers 4.303571, which is
    an average of votes and not a number anybody wants to read."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return ""
    return f"{round(float(value), 1)}"


def _docs(query: str) -> tuple[list[dict], str]:
    """The search rows, and the reason there are none if the catalog said."""
    url = f"{BASE}/search.json?q={quote(query, safe='')}&limit={MOST}&fields={FIELDS}"
    try:
        answer = json.loads(net.fetch(url, timeout=TIMEOUT, max_bytes=MAX_BYTES).text)
    except net.NetworkError as error:
        return [], str(error)
    except Exception:
        return [], ""
    docs = answer.get("docs") if isinstance(answer, dict) else None
    if not isinstance(docs, list):
        return [], ""
    return [d for d in docs if isinstance(d, dict)], ""


def _candidate(doc: dict, kind: str) -> Candidate | None:
    ref, title = _text(doc.get("key")), _text(doc.get("title"))
    if not ref or not title:
        return None
    cover = doc.get("cover_i")
    return Candidate(
        ref=ref, kind=kind, via="book", title=title,
        year=_text(doc.get("first_publish_year")),
        rating=_rating(doc.get("ratings_average")),
        poster=f"{COVERS}/{cover}-L.jpg" if isinstance(cover, int) else "",
    )


def search(kind: str, query: str, via: str = "") -> tuple[list[Candidate], str]:
    # `via` is here so both clients answer the same call. A book has one
    # catalog and one shelf in it; there is nothing to override.
    docs, error = _docs(query)
    found = [c for c in (_candidate(d, kind) for d in docs) if c is not None]
    return found[:MOST], error


def _synopsis(ref: str) -> str:
    """The work's own description, in either shape it comes in, or nothing.

    Nothing covers every way this call can go wrong, on purpose: it is the
    second of two, and losing a synopsis must never lose the card.
    """
    url = f"{BASE}{quote(ref, safe='/')}.json"
    try:
        work = json.loads(net.fetch(url, timeout=TIMEOUT, max_bytes=MAX_BYTES).text)
    except Exception:
        return ""
    if not isinstance(work, dict):
        return ""
    described = work.get("description")
    if isinstance(described, dict):
        described = described.get("value")
    return _text(described).strip()


def card(candidate: Candidate) -> Card | None:
    """The whole thing, or None if the search cannot find it by its key."""
    docs, _ = _docs(f"key:{candidate.ref}")
    doc = docs[0] if docs else None
    if not isinstance(doc, dict):
        return None
    title = _text(doc.get("title")) or candidate.title
    if not title:
        return None
    pages = doc.get("number_of_pages_median")
    year = _text(doc.get("first_publish_year"))
    subjects = doc.get("subject")
    cover = doc.get("cover_i")
    return Card(
        url=f"{BASE}{candidate.ref}",
        source="openlibrary.org",
        title=title,
        year=year,
        people=_first(doc.get("author_name")),
        # A book's day of publication is not a fact Open Library keeps for
        # the work, only for an edition. The year is what there is.
        released=year,
        genres=[s for s in subjects if isinstance(s, str)] if isinstance(subjects, list) else [],
        length=f"{pages} páginas" if isinstance(pages, int) else "",
        rating=_rating(doc.get("ratings_average")),
        synopsis=_synopsis(candidate.ref),
        poster=f"{COVERS}/{cover}-L.jpg" if isinstance(cover, int) else "",
    )
