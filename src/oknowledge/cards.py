"""A line that asks for a card instead of saving a link.

`película:Terminator` in the box the links go in. Nine words, four kinds,
and everything else falls through to the link the box is for -- which is
what makes this cheap: nothing is fetched, saved or shown until the line
has been recognized here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .ai.base import normalize_tags
from .catalog import Card
from .catalog.genres import as_tags
from .model import Note
from .urls import link_id
from .web.index import fold

PREFIXES = {
    # Folded keys: fold() lowercases and drops accents, so "PELÍCULA" and
    # "pelicula" are the same word before they get here.
    "pelicula": "movie",
    "peli": "movie",
    "movie": "movie",
    "serie": "series",
    "series": "series",
    "anime": "anime",
    "libro": "book",
    "book": "book",
}

LONGEST = 120
"""A title nobody typed on purpose. The box takes 2048 characters because a
link can be that long; a film's name cannot."""

_YEAR = re.compile(r"\s+(1[89]\d\d|20\d\d)$")
"""Only at the end, and only a plausible one: "Fahrenheit 451" keeps its
number and "1984 de Orwell" keeps its year, because neither is at the end
as a four-digit word."""
_IMDB = re.compile(r"^tt\d{7,8}$")
_OPENLIBRARY = re.compile(r"^OL\d+W$", re.IGNORECASE)


@dataclass(frozen=True)
class Wanted:
    """A card somebody asked for, before any catalog has been asked."""

    kind: str           # movie | series | anime | book
    query: str          # what to search for, without the year
    year: str = ""      # "" unless the line ended in one
    ref: str = ""       # an id typed instead of a title, in catalog form


def wanted(raw: str) -> Wanted | None:
    """The card this line asks for, or None if it does not ask for one.

    None is the answer for every link, every empty title, and every word
    that is not one of the nine -- the caller then treats the line as what
    the box is for.
    """
    head, colon, rest = (raw or "").partition(":")
    if not colon:
        return None
    kind = PREFIXES.get(fold(head).strip())
    if kind is None:
        return None
    query = " ".join(rest.split())[:LONGEST]
    if not query:
        return None

    ref = ""
    if _IMDB.match(query):
        ref = query
    elif _OPENLIBRARY.match(query):
        # The catalog knows a book by its whole key, never by the id alone.
        ref = f"/works/{query.upper()}"

    # An id can never also carry a year: _YEAR needs a space in front of it
    # and neither id pattern has one.
    year = ""
    found = _YEAR.search(query)
    if found:
        year = found.group(1)
        query = query[:found.start()].strip()
    return Wanted(kind=kind, query=query, year=year, ref=ref)


CATEGORIES = {
    "es": {"movie": "Películas", "series": "Series",
           "anime": "Anime", "book": "Libros"},
    "en": {"movie": "Movies", "series": "Series",
           "anime": "Anime", "book": "Books"},
}
"""The category a card lands in, which is its kind and nothing else. A model
classifies a link because nobody knows what a link is until it is read; a
film is a film before anybody asks."""


def note_from_card(card: Card, kind: str, language: str, saved: str) -> Note:
    """A catalog's answer as a note of ours. Pure: no disk, no network.

    The poster is not downloaded here. `cover` is filled in by whoever
    saves the note, because that is the step that has a folder to put a
    file in.

    `status` is "ok" from the start: a card is complete the moment the
    catalog answers, and nothing is owed. `engine` stays empty, which is
    what says no model has rewritten it yet -- and what keeps retry from
    ever trying to scrape imdb.com.
    """
    names = CATEGORIES.get(language, CATEGORIES["en"])
    return Note(
        id=link_id(card.url),
        url=card.url,
        title=card.title,
        category=names.get(kind, names["movie"]),
        tags=normalize_tags(as_tags(card.genres, language)),
        type=kind,
        source=card.source,
        saved=saved,
        summary=card.synopsis,
        points=[],
        status="ok",
        # The catalog's synopsis is the whole text there is: there is no page
        # to extract, so there is no original content section to promise.
        content="summary",
        author=card.people or None,
        published=card.released or None,
        length=card.length,
        rating=card.rating,
    )
