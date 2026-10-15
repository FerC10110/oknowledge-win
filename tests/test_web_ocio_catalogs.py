"""Searching the catalogs from Ocio's field (spec §3, "Candidatos de catálogos").
No test reaches the network: both catalogs are the fake below."""

import re

import pytest
from fastapi.testclient import TestClient

from oknowledge.catalog import Candidate, Card
from oknowledge.config import Config
from oknowledge.vault import rebuild_indexes
from oknowledge.web.app import create_app


@pytest.fixture(autouse=True)
def state_tree(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr("oknowledge.web.app.CONFIG_PATH", tmp_path / "config" / "config.toml")


@pytest.fixture
def client(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    rebuild_indexes(cfg, "es")
    return TestClient(create_app(cfg))


@pytest.fixture
def asked(monkeypatch):
    calls = []

    def films(kind, query, via=""):
        calls.append((via or "movie", query))
        return [Candidate(ref="tt0088247", kind=kind, via=via or "movie", title="The Terminator",
                          year="1984", rating="8.1", poster="https://img/t.jpg",
                          people="James Cameron")], ""

    def books(kind, query, via=""):
        calls.append(("book", query))
        return [Candidate(ref="/works/OL1W", kind="book", via="book", title="Dune",
                          year="1965", people="Frank Herbert")], ""

    monkeypatch.setattr("oknowledge.catalog.cinemeta.search", films)
    monkeypatch.setattr("oknowledge.catalog.openlibrary.search", books)
    return calls


def stub_the_card(monkeypatch):
    """What Cinemeta's card() would answer for The Terminator, and no poster
    download and no model: saving must stay on this machine."""
    card = Card(url="https://www.imdb.com/title/tt0088247/", source="imdb.com",
                title="The Terminator", year="1984", people="James Cameron",
                released="1984-10-26", genres=["Action"], length="108 min", rating="8.1",
                synopsis="A cyborg assassin from the future.", poster="")
    monkeypatch.setattr("oknowledge.catalog.cinemeta.card", lambda candidate: card)
    monkeypatch.setattr("oknowledge.web.app.describe", lambda cfg, link_id, **rest: True)


def test_the_field_offers_the_catalogs(client):
    body = client.get("/ocio").text
    button = re.search(r'<button[^>]*id="catalog-search"[^>]*>(.*?)</button>', body, re.S)
    assert 'formaction="/ocio/buscar"' in button.group(0)
    assert "Search the catalogs ↵" in button.group(1)
    assert '<input type="hidden" name="en" value="ocio">' in body


def test_the_candidates_are_a_fragment(client, asked):
    body = client.get("/ocio/candidatos?q=terminator&tipo=movie").text
    assert "<html" not in body and 'data-search="terminator"' in body
    assert ">The Terminator<" in body and "1984" in body and "James Cameron" in body
    assert '<img src="https://img/t.jpg" alt="" loading="lazy" referrerpolicy="no-referrer">' in body


def test_each_candidate_saves_itself(client, asked):
    body = client.get("/ocio/candidatos?q=terminator&tipo=movie").text
    form = re.search(r'<form[^>]*action="/ocio/guardar".*?</form>', body, re.S).group(0)
    assert 'name="tipo" value="movie"' in form and 'name="ref" value="tt0088247"' in form
    assert 'name="via" value="movie"' in form and ">Save<" in form


def test_all_kinds_is_films(client, asked):
    client.get("/ocio/candidatos?q=x")
    client.get("/ocio/candidatos?q=x&tipo=ovni")
    assert asked == [("movie", "x"), ("movie", "x")]


def test_a_book_names_its_author(client, asked):
    body = client.get("/ocio/candidatos?q=dune&tipo=book").text
    assert asked == [("book", "dune")] and "Frank Herbert" in body


def test_a_switch_of_kind_on_top(client, asked):
    body = client.get("/ocio/candidatos?q=dune&tipo=book").text
    kinds = re.findall(r'data-kind="(\w+)"', body)
    assert kinds == ["movie", "series", "anime", "book"]
    assert re.search(r'href="/ocio\?buscar=dune&amp;catalogo=book" data-kind="book" class="on"', body)


def test_nothing_found_says_so(client, monkeypatch):
    monkeypatch.setattr("oknowledge.catalog.cinemeta.search", lambda *a, **k: ([], ""))
    assert "I found nothing in the catalogs" in client.get("/ocio/candidatos?q=zzz").text


def test_a_catalog_that_is_down_says_so(client, monkeypatch):
    monkeypatch.setattr("oknowledge.catalog.cinemeta.search",
                        lambda *a, **k: ([], "connection refused"))
    body = client.get("/ocio/candidatos?q=zzz").text
    assert "could not be reached" in body and "connection refused" in body


def test_no_words_no_search(client, asked):
    assert client.get("/ocio/candidatos?q=%20").status_code == 404
    assert asked == []


def test_without_javascript_ocio_draws_them_in_the_panel(client, asked):
    body = client.get("/ocio?buscar=terminator&tipo=series").text
    panel = body[body.index('id="panel"'):]
    assert ">The Terminator<" in panel
    assert asked == [("series", "terminator")]


def test_the_old_search_page_sends_you_to_the_panel(client):
    answer = client.get("/ocio/buscar?tipo=movie&q=Terminator&year=1984",
                        follow_redirects=False)
    assert answer.status_code == 303
    assert answer.headers["location"] == "/ocio?buscar=Terminator&catalogo=movie&tipo=movie&year=1984"


def test_the_button_without_words_is_just_ocio(client):
    answer = client.get("/ocio/buscar?q=&tipo=book", follow_redirects=False)
    assert answer.headers["location"] == "/ocio?tipo=book"


def test_a_saved_card_opens_in_ocio(client, monkeypatch):
    stub_the_card(monkeypatch)
    answer = client.post("/ocio/guardar", data={"tipo": "movie", "ref": "tt0088247",
                                                "via": "movie"}, follow_redirects=False)
    assert re.fullmatch(r"/ocio\?sel=[0-9a-f]{12}(&notice=\w[\w-]*)?", answer.headers["location"])


# --- the field on /ocio ------------------------------------------------------------

def test_plain_text_from_ocio_lists_candidates(client):
    answer = client.post("/add", data={"q": "terminator", "en": "ocio", "tipo": "series"},
                         follow_redirects=False)
    assert answer.headers["location"] == "/ocio?buscar=terminator&catalogo=series&tipo=series"


def test_a_prefix_lists_candidates_in_ocio(client):
    answer = client.post("/add", data={"q": "película:Terminator"}, follow_redirects=False)
    assert answer.headers["location"] == "/ocio?buscar=Terminator&catalogo=movie"


def test_an_imdb_link_from_ocio_is_saved_as_a_card(client, monkeypatch):
    stub_the_card(monkeypatch)
    answer = client.post("/add", data={"q": "https://www.imdb.com/title/tt0088247/",
                                       "en": "ocio"}, follow_redirects=False)
    assert answer.headers["location"].startswith("/ocio?sel=")


def test_an_imdb_link_the_catalog_does_not_know_lists_it(client, monkeypatch):
    monkeypatch.setattr("oknowledge.catalog.cinemeta.card", lambda candidate: None)
    monkeypatch.setattr("oknowledge.catalog.cinemeta.search", lambda *a, **k: ([], ""))
    answer = client.post("/add", data={"q": "https://www.imdb.com/title/tt0088247/",
                                       "en": "ocio"}, follow_redirects=False)
    assert answer.headers["location"] == "/ocio?buscar=tt0088247&catalogo=movie"


def test_another_link_from_ocio_is_not_a_card(client):
    answer = client.post("/add", data={"q": "https://myanimelist.net/anime/1", "en": "ocio"},
                         follow_redirects=False)
    assert answer.headers["location"] == "/ocio?notice=not-a-catalog-link"


def test_a_link_from_the_library_is_still_a_link(client, monkeypatch):
    taken = []
    monkeypatch.setattr("oknowledge.web.app.fetch",
                        lambda cfg, url, content, **rest: taken.append(url))
    client.post("/add", data={"q": "https://www.imdb.com/title/tt0088247/"})
    assert taken == ["https://imdb.com/title/tt0088247"]      # as normalize() writes it


# --- one kind for the grid, another for the candidates ------------------------------

def test_from_all_a_catalog_search_does_not_filter_the_grid(client, asked):
    body = client.get("/ocio?buscar=x").text
    assert asked == [("movie", "x")]
    assert not re.search(r'href="[^"]*tipo=movie[^"]*"[^>]*class="[^"]*\bon\b', body)
    field = body[body.index('id="unified"'):body.index("</form>")]
    assert 'name="tipo"' not in field             # the field form carries no grid filter


def test_the_grid_keeps_its_kind_and_the_candidates_follow_it(client, asked):
    body = client.get("/ocio?buscar=dune&tipo=book").text
    assert asked == [("book", "dune")]
    assert 'name="tipo" value="book"' in body


def test_a_catalog_kind_is_not_a_grid_filter(client, asked):
    body = client.get("/ocio?buscar=dune&catalogo=book").text
    assert asked == [("book", "dune")]
    assert 'name="tipo"' not in body[body.index('id="unified"'):body.index("</form>")]


def test_the_switch_changes_the_catalog_and_keeps_the_grid(client, asked):
    body = client.get("/ocio?buscar=dune&tipo=series&catalogo=book").text
    panel = body[body.index('id="panel"'):]
    links = re.findall(r'href="([^"]*)" data-kind="(\w+)"', panel)
    assert [k for _, k in links] == ["movie", "series", "anime", "book"]
    for href, kind in links:
        assert f"catalogo={kind}" in href and "tipo=series" in href


def test_the_field_keeps_the_grid_filter_in_what_it_redirects_to(client):
    answer = client.get("/ocio/buscar?q=dune&tipo=book", follow_redirects=False)
    assert answer.headers["location"] == "/ocio?buscar=dune&catalogo=book&tipo=book"


def test_a_scheme_less_imdb_link_is_saved(client, monkeypatch):
    stub_the_card(monkeypatch)
    answer = client.post("/add", data={"q": "www.imdb.com/title/tt0088247/", "en": "ocio"},
                         follow_redirects=False)
    assert answer.headers["location"].startswith("/ocio?sel=")
