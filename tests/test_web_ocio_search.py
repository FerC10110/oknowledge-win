"""The page that asks which one you meant.

Cinemeta answers "terminator" with Judgment Day first and the 1984 one
second, which is why nothing is saved until somebody picks. Anime asks both
catalogs, series first: Cowboy Bebop is a series and a film, and whichever
one you meant, it is in one of the two answers.

Neither catalog being reachable is an ordinary afternoon and must be a page
that says so, never a 500.
"""

import pytest
from fastapi.testclient import TestClient

from oknowledge.catalog import Candidate
from oknowledge.config import Config
from oknowledge.net import NetworkError
from oknowledge.vault import rebuild_indexes
from oknowledge.web import app as module
from oknowledge.web.app import create_app


@pytest.fixture(autouse=True)
def state_tree(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr("oknowledge.web.app.CONFIG_PATH",
                        tmp_path / "config" / "config.toml")


@pytest.fixture
def taken(monkeypatch):
    calls = []
    monkeypatch.setattr(module, "fetch",
                        lambda cfg, url, content, **rest: calls.append(url))
    return calls


@pytest.fixture
def client(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    rebuild_indexes(cfg, "es")
    return TestClient(create_app(cfg))


def candidate(title, year="", rating="", via="movie", ref="tt0000001"):
    return Candidate(ref=ref, kind="movie", via=via, title=title,
                     year=year, rating=rating)


@pytest.fixture
def fake_catalog(monkeypatch):
    """Both clients, answering what the test says, remembering what was asked."""

    class Faker:
        def __init__(self):
            self.asked: list[tuple[str, str]] = []
            self.found: list[Candidate] = []
            self.error = ""
            self.failing: set[str] = set()

        def __call__(self, search=None, error=""):
            self.found = list(search or [])
            self.error = error

        def fail_on(self, via: str):
            self.failing.add(via)

        def search(self, kind, query, via=""):
            via = via or ("series" if kind in ("series", "anime") else "movie")
            self.asked.append((via, query))
            if via in self.failing:
                return [], "connection refused"
            if self.error:
                return [], self.error
            return [c for c in self.found], ""

        def books(self, kind, query, via=""):
            self.asked.append(("book", query))
            if self.error:
                return [], self.error
            return [c for c in self.found], ""

    faker = Faker()
    monkeypatch.setattr("oknowledge.catalog.cinemeta.search", faker.search)
    monkeypatch.setattr("oknowledge.catalog.openlibrary.search", faker.books)
    return faker


def test_a_prefix_in_the_paste_box_goes_to_the_candidates(client):
    answer = client.post("/add", data={"url": "película:Terminator"},
                         follow_redirects=False)
    assert answer.status_code == 303
    assert answer.headers["location"] == "/ocio?buscar=Terminator&tipo=movie"


def test_a_prefix_in_the_unified_field_goes_to_the_candidates(client):
    """The library's field sends its text as `q`; the Ocio path is the same."""
    answer = client.post("/add", data={"q": "película:Terminator"},
                         follow_redirects=False)
    assert answer.status_code == 303
    assert answer.headers["location"] == "/ocio?buscar=Terminator&tipo=movie"


def test_a_link_still_goes_where_it_always_went(client, taken):
    client.post("/add", data={"url": "https://example.com/x"})
    assert taken == ["https://example.com/x"]      # el camino de hoy, intacto


def test_a_prefix_with_no_title_says_what_is_missing(client, taken):
    """`película:` sin nada detrás no es un link ni una búsqueda."""
    body = client.post("/add", data={"url": "película:"}).text
    assert taken == []
    assert "título" in body or "title" in body.lower()
    assert "no es un link" not in body


def test_the_candidates_are_drawn_with_what_matters(client, fake_catalog):
    fake_catalog(search=[candidate("The Terminator", "1984", "8.1")])
    body = client.get("/ocio/candidatos?tipo=movie&q=Terminator").text
    assert "The Terminator" in body and "1984" in body
    assert 'action="/ocio/guardar"' in body


def test_the_form_carries_what_saving_needs(client, fake_catalog):
    fake_catalog(search=[candidate("The Terminator", ref="tt0088247")])
    body = client.get("/ocio/candidatos?tipo=movie&q=Terminator").text
    assert 'name="ref" value="tt0088247"' in body
    assert 'name="via" value="movie"' in body
    assert 'name="tipo" value="movie"' in body


def test_nothing_found_says_so_and_keeps_what_you_typed(client, fake_catalog):
    fake_catalog(search=[])
    body = client.get("/ocio/candidatos?tipo=movie&q=Zzz").text
    assert "Zzz" in body               # la caja no se vacía
    assert "no encontr" in body.lower() or "nothing" in body.lower()


def test_a_catalogue_that_is_down_is_a_page_and_not_a_500(client, fake_catalog):
    fake_catalog(error="connection refused")
    answer = client.get("/ocio/candidatos?tipo=movie&q=x")
    assert answer.status_code == 200
    body = answer.text.lower()
    # The sentence itself, not just the words "try again": the base template
    # carries a "Try again." of its own in a data attribute on every page.
    assert ("could not be reached" in body
            or "no se pudo consultar el catálogo" in body)
    assert "connection refused" in body       # qué dijo el catálogo


def test_nothing_found_is_not_dressed_up_as_a_failure(client, fake_catalog):
    """Zzz no existe: eso no es un catálogo caído."""
    fake_catalog(search=[])
    body = client.get("/ocio/candidatos?tipo=movie&q=Zzz").text.lower()
    assert "could not be reached" not in body
    assert "no se pudo consultar" not in body


def test_an_unknown_kind_searches_films(client, fake_catalog):
    client.get("/ocio/candidatos?tipo=ovni&q=x")
    assert fake_catalog.asked == [("movie", "x")]


def test_a_search_with_no_words_is_not_a_search(client):
    assert client.get("/ocio/candidatos?tipo=movie&q=").status_code == 404


def test_the_anime_asks_the_two_catalogues(client, fake_catalog):
    client.get("/ocio/candidatos?tipo=anime&q=bebop")
    assert fake_catalog.asked == [("series", "bebop"), ("movie", "bebop")]


def test_a_book_asks_open_library_and_nobody_else(client, fake_catalog):
    client.get("/ocio/candidatos?tipo=book&q=dune")
    assert fake_catalog.asked == [("book", "dune")]


def test_if_one_of_the_two_fails_the_other_still_shows(client, fake_catalog):
    fake_catalog(search=[candidate("Cowboy Bebop", via="series")])
    fake_catalog.fail_on("movie")
    body = client.get("/ocio/candidatos?tipo=anime&q=bebop").text
    assert "Cowboy Bebop" in body


def test_a_title_from_a_catalogue_cannot_inject_markup(client, fake_catalog):
    """El título es texto de internet y la página lo dibuja."""
    fake_catalog(search=[candidate("<script>alert(1)</script>")])
    body = client.get("/ocio/candidatos?tipo=movie&q=x").text
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;" in body
