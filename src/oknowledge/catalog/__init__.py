"""The catalogs a card is built from, and the shapes they answer in.

Two of them, both free and neither asking for a key: Cinemeta for anything
that was filmed and Open Library for anything that was printed. They answer
in two steps, the same two in both cases -- a search that returns what might
be the thing, and a lookup that returns the thing -- because a title is not
an identifier and the first answer is not always the right one.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Candidate:
    """One row of a search: enough to tell two films of the same name apart,
    and the reference needed to ask for the rest."""

    ref: str            # "tt0088247" or "/works/OL893414W"
    kind: str           # what you asked for: movie | series | anime | book
    via: str            # how the catalog was asked: movie | series | book
    title: str
    year: str = ""      # "" when the catalog does not say
    rating: str = ""    # "8.1", "4.3", or ""
    poster: str = ""    # URL, or ""


@dataclass(frozen=True)
class Card:
    """A catalog's answer, already in the words a note uses."""

    url: str            # https://imdb.com/title/tt0088247
    source: str         # imdb.com | openlibrary.org
    title: str
    year: str = ""
    people: str = ""    # director or author; "" when unknown
    released: str = ""  # YYYY-MM-DD or YYYY; "" when unknown
    genres: list[str] = field(default_factory=list)  # as they came, in English
    length: str = ""    # "108 min" | "27 episodios" | "608 páginas" | ""
    rating: str = ""    # "8.1" | "4.3" | ""
    synopsis: str = ""  # "" when the catalog carries none
    poster: str = ""    # URL, or ""
