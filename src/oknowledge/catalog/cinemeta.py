"""Cinemeta: anything that was filmed, free and without a key.

The add-on Stremio runs on IMDb's data. Two endpoints, no registration, no
rate limit anyone has met, and IMDb ids as references -- which is why the
card's url can point at imdb.com, where a person expects to end up.

Anime goes through here too, as a series and as a movie. The specialist
catalog for it answers only over IPv6, which this machine has no route to.
"""

from __future__ import annotations

import json
from urllib.parse import quote

from .. import net
from . import Candidate, Card

BASE = "https://v3-cinemeta.strem.io"
MOST = 8
"""How many candidates a page shows. Cinemeta answers nineteen for
"terminator", and a list nobody scrolls is a list nobody reads."""
TIMEOUT = 8.0
"""Somebody is waiting in front of the page. Eight seconds is the point
where the answer stops being worth the wait."""
MAX_BYTES = 2_000_000


def _text(value) -> str:
    """A field as text. The catalog answers numbers for some of these and
    null for most of them, depending on the title."""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return ""


def _first(value) -> str:
    """The first name of a list of names, as the catalog writes them."""
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str) and item.strip():
                return item.strip()
    return _text(value).strip()


def _asked(url: str) -> dict | None:
    """The answer as a dict, or None for anything else that can happen.

    Anything: the endpoint down, a redirect to a login page, half a
    megabyte of HTML, an empty body, valid JSON that is a list. None of it
    is exceptional enough to raise at a person who typed a film's name.
    """
    try:
        answer = json.loads(net.fetch(url, timeout=TIMEOUT, max_bytes=MAX_BYTES).text)
    except Exception:
        return None
    return answer if isinstance(answer, dict) else None


def search(kind: str, query: str) -> tuple[list[Candidate], str]:
    """What the catalog thinks you might have meant, and why it could not say.

    The error is a string and not an exception because the only thing to do
    with it is show it: the page asks two catalogs for an anime, and one of
    them being down is not the end of the search.
    """
    via = "series" if kind in ("series", "anime") else "movie"
    url = f"{BASE}/catalog/{via}/top/search={quote(query, safe='')}.json"
    try:
        answer = json.loads(net.fetch(url, timeout=TIMEOUT, max_bytes=MAX_BYTES).text)
    except net.NetworkError as error:
        return [], str(error)
    except Exception:
        # Not an error worth showing: the catalog answered, with nonsense.
        return [], ""
    metas = answer.get("metas") if isinstance(answer, dict) else None
    if not isinstance(metas, list):
        return [], ""
    found: list[Candidate] = []
    for meta in metas:
        if not isinstance(meta, dict):
            continue
        ref, title = _text(meta.get("id")), _text(meta.get("name"))
        if not ref or not title:
            continue
        found.append(Candidate(
            ref=ref, kind=kind, via=via, title=title,
            year=_text(meta.get("releaseInfo") or meta.get("year")),
            rating=_text(meta.get("imdbRating")),
            poster=_text(meta.get("poster")),
        ))
        if len(found) == MOST:
            break
    return found, ""


def card(candidate: Candidate) -> Card | None:
    """The whole thing, or None if the catalog could not say."""
    answer = _asked(f"{BASE}/meta/{candidate.via}/{quote(candidate.ref, safe='')}.json")
    meta = answer.get("meta") if answer else None
    if not isinstance(meta, dict):
        return None
    title = _text(meta.get("name")) or candidate.title
    if not title:
        return None
    genres = meta.get("genres") or meta.get("genre") or []
    if candidate.via == "series":
        videos = meta.get("videos")
        count = len(videos) if isinstance(videos, list) else 0
        # The episode count, not the runtime: a series' runtime is one
        # episode's, which says nothing about the thing you are saving.
        length = f"{count} episodios" if count else ""
    else:
        length = _text(meta.get("runtime"))
    return Card(
        url=f"https://imdb.com/title/{candidate.ref}",
        source="imdb.com",
        title=title,
        year=_text(meta.get("year") or meta.get("releaseInfo")),
        # Most series have no director listed and every one has a writer.
        people=_first(meta.get("director")) or _first(meta.get("writer")),
        released=_text(meta.get("released"))[:10],
        genres=[g for g in genres if isinstance(g, str)] if isinstance(genres, list) else [],
        length=length,
        rating=_text(meta.get("imdbRating")),
        synopsis=_text(meta.get("description")).strip(),
        poster=_text(meta.get("poster")),
    )
