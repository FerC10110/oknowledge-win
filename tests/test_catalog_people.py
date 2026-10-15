"""Who made it, on a candidate (spec §3, "autor o director")."""

from oknowledge.catalog import openlibrary, cinemeta


def test_a_book_names_its_first_author():
    found = openlibrary._candidate({"key": "/works/OL1W", "title": "Dune",
                                    "author_name": ["Frank Herbert", "Otro"]}, "book")
    assert found.people == "Frank Herbert"


def test_a_book_without_authors_names_nobody():
    assert openlibrary._candidate({"key": "/works/OL1W", "title": "Dune"}, "book").people == ""


def test_a_film_names_its_director_when_the_search_says(monkeypatch):
    answer = '{"metas": [{"id": "tt1", "name": "Alien", "director": ["Ridley Scott"]}, ' \
             '{"id": "tt2", "name": "Brazil"}]}'
    monkeypatch.setattr(cinemeta.net, "fetch",
                        lambda url, **kw: type("R", (), {"text": answer})())
    found, _ = cinemeta.search("movie", "x")
    assert [c.people for c in found] == ["Ridley Scott", ""]
