"""The genres a catalog names, as tags.

A table and not a model call: these are twenty-five words that have not
changed in forty years, and a card should not wait seconds -- or risk an
invention -- for a translation that fits in a dict.

What comes out is still raw text. normalize_tags() is what writes tags into
a note, and it is what turns "ciencia ficción" into "ciencia-ficcion".
"""

from __future__ import annotations

MOST = 6
"""How many survive. A film has three; an Open Library book can carry forty
subjects, and forty tags on one note is a wall nobody reads."""

SPANISH = {
    # IMDb's list, which is what Cinemeta answers with.
    "action": "acción",
    "adventure": "aventura",
    "animation": "animación",
    "biography": "biografía",
    "comedy": "comedia",
    "crime": "crimen",
    "documentary": "documental",
    "drama": "drama",
    "family": "familia",
    "fantasy": "fantasía",
    "film-noir": "cine negro",
    "game-show": "concurso",
    "history": "historia",
    "horror": "terror",
    "music": "música",
    "musical": "musical",
    "mystery": "misterio",
    "news": "noticias",
    "romance": "romance",
    "sci-fi": "ciencia ficción",
    "science fiction": "ciencia ficción",
    "short": "cortometraje",
    "sport": "deporte",
    "talk-show": "entrevistas",
    "thriller": "suspenso",
    "war": "guerra",
    "western": "western",
    # The subjects Open Library puts first, over and over.
    "fiction": "ficción",
    "juvenile fiction": "literatura juvenil",
    "literature": "literatura",
    "poetry": "poesía",
    "biography & autobiography": "biografía",
}


def as_tags(names, language: str) -> list[str]:
    """The genres as tags: folded, translated into Spanish when the word is
    in the table, deduplicated in the order they came, six at most.

    A genre nobody translated comes through as it was written. The catalogs
    invent names -- "Reality-TV", a subject typed by a librarian -- and
    dropping one for not being in a dict loses the only word that described
    it.
    """
    out: list[str] = []
    for name in names or ():
        if not isinstance(name, str):
            continue
        folded = " ".join(name.split()).lower()
        if not folded:
            continue
        if language == "es":
            folded = SPANISH.get(folded, folded)
        if folded not in out:
            out.append(folded)
    return out[:MOST]
