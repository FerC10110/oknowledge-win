"""Open Library: anything that was printed, without a key either.

Two calls per card, and that is not an accident: the search carries the
author, the year, the rating, the page count and the cover, and the
synopsis lives only on the work. The second call is the one allowed to
fail -- a book with no synopsis is still a card.

`description` comes back in two shapes, both real and both measured: Dune
answers a string, The Lord of the Rings answers an object with `value`, and
a work that is a redirect answers neither.
"""

import json
from pathlib import Path

import pytest

from oknowledge.catalog import Candidate
from oknowledge.catalog.openlibrary import card, search
from oknowledge.net import Fetched, NetworkError

FIXTURES = Path(__file__).parent / "fixtures" / "catalog"


def recorded(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def fake_fetch(monkeypatch):
    """Answer the calls in order, then raise if the test said to."""

    class Faker:
        url = ""

        def __init__(self):
            self.bodies: list[str] = []
            self.urls: list[str] = []
            self.error: Exception | None = None

        def __call__(self, *bodies: str, raises: Exception | None = None):
            self.bodies, self.error = list(bodies), raises

        def fetch(self, url, timeout=30.0, max_bytes=None):
            self.url = url
            self.urls.append(url)
            if not self.bodies:
                if self.error is not None:
                    raise self.error
                return Fetched(200, "application/json", b"{}", url)
            body = self.bodies.pop(0)
            return Fetched(status=200, content_type="application/json",
                           content=body.encode("utf-8"), final_url=url)

    faker = Faker()
    monkeypatch.setattr("oknowledge.catalog.openlibrary.net.fetch", faker.fetch)
    return faker


def a_dune_candidate() -> Candidate:
    return Candidate(ref="/works/OL893414W", kind="book", via="book", title="")


def a_lotr_candidate() -> Candidate:
    return Candidate(ref="/works/OL27448W", kind="book", via="book", title="")


def test_dune_comes_back_with_its_puntaje_sobre_cinco(fake_fetch):
    fake_fetch(recorded("openlibrary-search-dune.json"))
    found, error = search("book", "dune herbert")
    assert error == ""
    assert (found[0].title, found[0].year) == ("Dune", "1965")
    assert found[0].ref == "/works/OL893414W"
    assert found[0].rating == "4.3"           # redondeado de 4.303571
    assert found[0].poster.endswith("/11481354-L.jpg")


def test_the_card_joins_the_two_calls(fake_fetch):
    fake_fetch(recorded("openlibrary-search-dune.json"),
               recorded("openlibrary-work-dune.json"))
    card_ = card(a_dune_candidate())
    assert card_.url == "https://openlibrary.org/works/OL893414W"
    assert card_.source == "openlibrary.org"
    assert card_.people == "Frank Herbert"
    assert card_.length == "608 páginas"
    assert card_.rating == "4.3"
    assert card_.synopsis.startswith("Set on the desert planet Arrakis")


def test_the_other_shape_of_the_description(fake_fetch):
    """Medido: Dune la manda como string y El señor de los anillos como
    objeto con `value`. Las dos formas existen de verdad."""
    fake_fetch(recorded("openlibrary-search-lotr.json"),
               recorded("openlibrary-work-lotr.json"))
    assert card(a_lotr_candidate()).synopsis.startswith("Originally published")


def test_a_work_with_no_title_and_no_description_is_still_a_card(fake_fetch):
    """OL45883W contesta exactamente eso."""
    fake_fetch(recorded("openlibrary-search-dune.json"),
               recorded("openlibrary-work-untitled.json"))
    card_ = card(a_dune_candidate())
    assert card_.synopsis == ""
    assert card_.title == "Dune"        # el de la búsqueda, que sí está


def test_the_synopsis_is_optional_and_the_card_is_not(fake_fetch):
    """Si la segunda llamada falla, la ficha se guarda sin sinopsis."""
    fake_fetch(recorded("openlibrary-search-dune.json"),
               raises=NetworkError("timeout"))
    assert card(a_dune_candidate()).synopsis == ""


@pytest.mark.parametrize("answer", [
    "", "not json", "{}", '{"docs": "not a list"}', '{"docs": [{"no_key": 1}]}',
    # A row that is not an object at all: `.get` on a string is the one way
    # a catalog's nonsense could still reach somebody as a traceback.
    '{"docs": ["not an object"]}', '{"docs": [null]}',
])
def test_garbage_is_an_empty_answer_here_too(fake_fetch, answer):
    fake_fetch(answer)
    assert search("book", "x") == ([], "")
    assert card(a_dune_candidate()) is None


def test_a_catalogue_that_is_down_says_so(fake_fetch):
    fake_fetch(raises=NetworkError("connection refused"))
    found, error = search("book", "x")
    assert found == []
    assert error != ""


def test_an_id_is_looked_up_by_its_whole_key(fake_fetch):
    """Medido: q=OL893414W devuelve cero; q=key:/works/OL893414W devuelve uno."""
    fake_fetch("{}")
    search("book", "key:/works/OL893414W")
    assert "q=key%3A%2Fworks%2FOL893414W" in fake_fetch.url


def test_the_card_asks_for_the_work_by_its_olid(fake_fetch):
    fake_fetch(recorded("openlibrary-search-dune.json"),
               recorded("openlibrary-work-dune.json"))
    card(a_dune_candidate())
    assert fake_fetch.urls[1] == "https://openlibrary.org/works/OL893414W.json"
