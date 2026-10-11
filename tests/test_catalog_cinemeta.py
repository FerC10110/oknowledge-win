"""Cinemeta: anything that was filmed, without a key.

Recorded answers, never the network: the fixtures in tests/fixtures/catalog
were taken by hand once, and a catalog that changes its mind about a field
has to break a test here rather than a card in somebody's vault.

The promise this file exists for is that neither function ever raises. A
catalog answering nonsense -- or nothing, or ten thousand rows -- is an
ordinary Tuesday for an endpoint nobody runs, and the page that calls these
has a person waiting in front of it.
"""

import json
from pathlib import Path

import pytest

from oknowledge.catalog import Candidate
from oknowledge.catalog.cinemeta import card, search
from oknowledge.net import Fetched, NetworkError

FIXTURES = Path(__file__).parent / "fixtures" / "catalog"


def recorded(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def fake_fetch(monkeypatch):
    """Answer every fetch with one body, and remember the URL it was asked."""

    class Faker:
        url = ""
        body = ""
        error: Exception | None = None

        def __call__(self, body: str = "", raises: Exception | None = None):
            self.body, self.error = body, raises

        def fetch(self, url, timeout=30.0, max_bytes=None):
            self.url = url
            if self.error is not None:
                raise self.error
            return Fetched(status=200, content_type="application/json",
                           content=self.body.encode("utf-8"), final_url=url)

    faker = Faker()
    monkeypatch.setattr("oknowledge.catalog.cinemeta.net.fetch", faker.fetch)
    return faker


def a_candidate() -> Candidate:
    return Candidate(ref="tt0088247", kind="movie", via="movie", title="")


def test_the_six_terminators_come_back_in_order(fake_fetch):
    fake_fetch(recorded("cinemeta-search-terminator.json"))
    found, error = search("movie", "terminator")
    assert error == ""
    assert [(c.title, c.year) for c in found[:2]] == [
        ("Terminator 2: Judgment Day", "1991"), ("The Terminator", "1984")]
    assert found[0].ref == "tt0103064"
    assert found[0].via == "movie"


def test_eight_at_most(fake_fetch):
    fake_fetch(json.dumps({"metas": [{"id": f"tt{n:07}", "name": str(n)}
                                     for n in range(10_000)]}))
    assert len(search("movie", "x")[0]) == 8


def test_the_card_of_terminator_is_the_whole_ficha(fake_fetch):
    fake_fetch(recorded("cinemeta-meta-terminator.json"))
    card_ = card(Candidate(ref="tt0088247", kind="movie", via="movie",
                           title="", year="", rating="", poster=""))
    assert card_.url == "https://imdb.com/title/tt0088247"
    assert card_.source == "imdb.com"
    assert card_.title == "The Terminator"
    assert card_.year == "1984"
    assert card_.people == "James Cameron"
    assert card_.released == "1984-10-26"
    assert card_.genres == ["Action", "Adventure", "Sci-Fi"]
    assert card_.length == "108 min"
    assert card_.rating == "8.1"
    assert "cyborg assassin" in card_.synopsis
    assert card_.poster.startswith("https://")


def test_a_series_counts_its_episodes(fake_fetch):
    fake_fetch(recorded("cinemeta-meta-bebop.json"))
    card_ = card(Candidate(ref="tt0213338", kind="anime", via="series",
                           title="Cowboy Bebop"))
    assert card_.length == "27 episodios"


def test_a_series_with_no_director_is_signed_by_its_writer(fake_fetch):
    """Cinemeta leaves `director` out of most series; the name is still known."""
    fake_fetch(recorded("cinemeta-meta-bebop.json"))
    card_ = card(Candidate(ref="tt0213338", kind="anime", via="series",
                           title="Cowboy Bebop"))
    assert card_.people == "Shin'ichirô Watanabe"


@pytest.mark.parametrize("answer", [
    "", "no json at all", "{}", '{"metas": "not a list"}',
    '{"metas": [{"no_id": 1}]}', '{"meta": null}',
    # A row that is not an object at all: `.get` on a string is the one way
    # a catalog's nonsense could still reach somebody as a traceback.
    '{"metas": ["not an object"]}', '{"metas": [null]}', '{"meta": "a string"}',
    "[]", "null",
])
def test_garbage_is_an_empty_answer_and_never_a_traceback(fake_fetch, answer):
    fake_fetch(answer)
    assert search("movie", "x") == ([], "")
    assert card(a_candidate()) is None


def test_a_catalogue_that_is_down_says_so(fake_fetch):
    fake_fetch(raises=NetworkError("connection refused"))
    found, error = search("movie", "x")
    assert found == []
    assert error != ""          # la página lo muestra; no es una excepción


def test_a_catalogue_that_is_down_has_no_card_either(fake_fetch):
    fake_fetch(raises=NetworkError("connection refused"))
    assert card(a_candidate()) is None


def test_the_query_is_escaped(fake_fetch):
    """Un título con / o ? no puede partir la dirección."""
    fake_fetch("{}")
    search("movie", "9 1/2 weeks?")
    assert "9%201%2F2%20weeks%3F" in fake_fetch.url


def test_an_anime_can_be_looked_for_among_the_films(fake_fetch):
    """Cowboy Bebop is a series and a film; what it is saved as is what you
    asked for, not which catalog answered."""
    fake_fetch(recorded("cinemeta-search-terminator.json"))
    found, _ = search("anime", "bebop", via="movie")
    assert "/catalog/movie/" in fake_fetch.url
    assert (found[0].kind, found[0].via) == ("anime", "movie")


def test_without_an_override_an_anime_is_a_series(fake_fetch):
    fake_fetch("{}")
    search("anime", "bebop")
    assert "/catalog/series/" in fake_fetch.url
