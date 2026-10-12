"""Saving the one you picked.

A card is written at once, with no model in the way: the catalog already
answered and the synopsis it carries is text. What takes minutes -- the
rewrite in Spanish -- happens later and over a note that already exists.

Two tabs on the same button is the case this has to survive: the id comes
from the catalog's URL, so the second save finds the first one's note and
leaves it, score and all.
"""

import pytest
from fastapi.testclient import TestClient

from oknowledge.catalog import Candidate, Card
from oknowledge.config import Config
from oknowledge.net import Fetched, NetworkError
from oknowledge.urls import link_id
from oknowledge.vault import all_notes, find_note, read_note, rebuild_indexes, write_note
from oknowledge.web.app import create_app

IMDB_URL = "https://imdb.com/title/tt0088247"
SAVE = {"tipo": "movie", "ref": "tt0088247", "via": "movie"}


@pytest.fixture(autouse=True)
def state_tree(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr("oknowledge.web.app.CONFIG_PATH",
                        tmp_path / "config" / "config.toml")


def terminator_card() -> Card:
    return Card(url=IMDB_URL, source="imdb.com", title="The Terminator",
                year="1984", people="James Cameron", released="1984-10-26",
                genres=["Action", "Sci-Fi"], length="108 min", rating="8.1",
                synopsis="A cyborg assassin from the future.",
                poster="https://images.metahub.space/poster/tt0088247/img")


def terminator_1984() -> Candidate:
    return Candidate(ref="tt0088247", kind="movie", via="movie",
                     title="The Terminator", year="1984")


def terminator_1991() -> Candidate:
    return Candidate(ref="tt0103064", kind="movie", via="movie",
                     title="Terminator 2: Judgment Day", year="1991")


@pytest.fixture
def cfg(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    config = Config(vault=vault)
    rebuild_indexes(config, "es")
    return config


@pytest.fixture
def client(cfg):
    return TestClient(create_app(cfg))


@pytest.fixture
def fake_catalog(monkeypatch):
    """Both clients and the cover download, answering what the test says."""

    class Faker:
        def __init__(self):
            self.found: list[Candidate] = []
            self.the_card: Card | None = None
            self.poster: object = None
            self.asked_for: list[str] = []

        def __call__(self, search=None, card=None, poster=None):
            self.found = list(search or [])
            self.the_card = card
            self.poster = poster

        def search(self, kind, query, via=""):
            return list(self.found), ""

        def card(self, candidate):
            self.asked_for.append(candidate.ref)
            return self.the_card

        def fetch(self, url, timeout=30.0, max_bytes=None):
            if isinstance(self.poster, Exception):
                raise self.poster
            if self.poster is None:
                raise NetworkError("no poster in this test")
            return Fetched(200, "image/png", self.poster, url)

    faker = Faker()
    for where in ("cinemeta", "openlibrary"):
        monkeypatch.setattr(f"oknowledge.catalog.{where}.search", faker.search)
        monkeypatch.setattr(f"oknowledge.catalog.{where}.card", faker.card)
    monkeypatch.setattr("oknowledge.pipeline.fetch", faker.fetch)
    return faker


@pytest.fixture(autouse=True)
def asked(monkeypatch):
    """Which cards were handed to the rewrite. Autouse: saving a card now
    queues a model call, and a test that is about something else must not
    make one. The real one is a chain call; what the route owes it is the id."""
    calls = []
    monkeypatch.setattr("oknowledge.web.app.describe",
                        lambda cfg, link_id, **rest: calls.append(link_id))
    return calls


def test_the_card_lands_in_the_ocio_shelf(client, fake_catalog, cfg):
    fake_catalog(card=terminator_card())
    answer = client.post("/ocio/guardar", data=SAVE, follow_redirects=False)
    assert answer.status_code == 303
    assert "/item/" in answer.headers["location"]
    saved = all_notes(cfg, shelf=cfg.ocio)
    assert [n.title for n in saved] == ["The Terminator"]
    assert all_notes(cfg) == []                       # no entre los links


def test_the_note_carries_what_the_catalogue_said(client, fake_catalog, cfg):
    fake_catalog(card=terminator_card())
    client.post("/ocio/guardar", data=SAVE)
    note = all_notes(cfg, shelf=cfg.ocio)[0]
    assert (note.type, note.category) == ("movie", "Películas")
    assert (note.length, note.rating) == ("108 min", "8.1")
    assert note.status == "ok" and note.engine == ""


def test_the_poster_is_downloaded_beside_the_rest(client, fake_catalog, cfg):
    fake_catalog(card=terminator_card(), poster=b"\x89PNG...")
    client.post("/ocio/guardar", data=SAVE)
    note = all_notes(cfg, shelf=cfg.ocio)[0]
    assert note.cover == f"../attachments/{note.id}.png"
    assert (cfg.attachments_dir / f"{note.id}.png").exists()


def test_a_poster_that_does_not_download_is_not_a_lost_card(client, fake_catalog, cfg):
    fake_catalog(card=terminator_card(), poster=NetworkError("404"))
    client.post("/ocio/guardar", data=SAVE)
    assert all_notes(cfg, shelf=cfg.ocio)[0].cover is None


def test_saving_the_same_card_twice_leaves_one_note(client, fake_catalog, cfg):
    """Dos pestañas, el mismo botón. El id sale de la URL de IMDb."""
    fake_catalog(card=terminator_card())
    client.post("/ocio/guardar", data=SAVE)
    client.post("/ocio/guardar", data=SAVE)
    assert len(all_notes(cfg, shelf=cfg.ocio)) == 1


def test_the_second_save_does_not_wipe_your_score(client, fake_catalog, cfg):
    fake_catalog(card=terminator_card())
    client.post("/ocio/guardar", data=SAVE)
    path, note = find_note(cfg, link_id(IMDB_URL), shelf=cfg.ocio)
    note.score = 5                       # los botones son de la Tarea 12
    write_note(cfg, note, "es", path=path)
    client.post("/ocio/guardar", data=SAVE)
    assert read_note(path).score == 5


def test_the_card_opens_at_its_own_page(client, fake_catalog):
    """El 303 de arriba apunta a /item/{id}, y esa página busca en la
    biblioteca de links: sin esto, guardar una ficha termina en un 404."""
    fake_catalog(card=terminator_card())
    answer = client.post("/ocio/guardar", data=SAVE)
    assert answer.status_code == 200
    assert "The Terminator" in answer.text


def test_the_poster_is_served_from_the_shelf_too(client, fake_catalog, cfg):
    fake_catalog(card=terminator_card(), poster=b"\x89PNG...")
    client.post("/ocio/guardar", data=SAVE)
    assert client.get(f"/cover/{link_id(IMDB_URL)}").status_code == 200


def test_a_catalogue_that_fails_at_the_last_step_writes_nothing(client, fake_catalog, cfg):
    fake_catalog(card=None)
    answer = client.post("/ocio/guardar", data=SAVE, follow_redirects=False)
    assert "notice=" in answer.headers["location"]
    assert all_notes(cfg, shelf=cfg.ocio) == []


def test_an_unknown_kind_saves_nothing(client, fake_catalog, cfg):
    fake_catalog(card=terminator_card())
    answer = client.post("/ocio/guardar", data={**SAVE, "tipo": "ovni"},
                         follow_redirects=False)
    assert answer.status_code == 404
    assert all_notes(cfg, shelf=cfg.ocio) == []


def test_the_index_of_the_shelf_is_rebuilt(client, fake_catalog, cfg):
    fake_catalog(card=terminator_card())
    client.post("/ocio/guardar", data=SAVE)
    assert (cfg.root / "ocio" / "Películas.md").exists()


def test_the_links_indexes_are_not_touched_by_a_card(client, fake_catalog, cfg):
    """El reindex del ocio no puede borrar los índices de los links."""
    from oknowledge.model import Note
    link = Note(id="bbbbbbbbbbbb", url="https://example.com/x", title="Una página",
                category="Redes", tags=[], type="article", source="example.com",
                saved="2026-10-10", summary="Algo.")
    write_note(cfg, link, "es")
    rebuild_indexes(cfg, "es")
    fake_catalog(card=terminator_card())
    client.post("/ocio/guardar", data=SAVE)
    assert (cfg.root / "Redes.md").exists()


def test_a_year_that_names_one_candidate_skips_the_list(client, fake_catalog):
    fake_catalog(search=[terminator_1991(), terminator_1984()],
                 card=terminator_card())
    answer = client.post("/add", data={"url": "película:Terminator 1984"},
                         follow_redirects=False)
    # Va a la búsqueda, que al encontrar una sola para ese año guarda y sigue.
    assert answer.headers["location"].startswith("/ocio/buscar")
    body = client.post("/add", data={"url": "película:Terminator 1984"}).text
    assert "The Terminator" in body and "Terminator 2" not in body


def test_a_year_that_names_two_still_asks(client, fake_catalog):
    fake_catalog(search=[terminator_1984(),
                         Candidate(ref="tt9", kind="movie", via="movie",
                                   title="Otro Terminator", year="1984")],
                 card=terminator_card())
    body = client.post("/add", data={"url": "película:Terminator 1984"}).text
    assert "Otro Terminator" in body and "The Terminator" in body


def test_a_year_that_names_nobody_shows_the_whole_list(client, fake_catalog):
    """Mejor la lista entera que una página vacía por un año mal escrito."""
    fake_catalog(search=[terminator_1991()], card=terminator_card())
    body = client.post("/add", data={"url": "película:Terminator 1803"}).text
    assert "Terminator 2" in body


def test_an_id_goes_straight_to_the_card(client, fake_catalog):
    fake_catalog(card=terminator_card())
    answer = client.get("/ocio/buscar?tipo=movie&q=tt0088247", follow_redirects=False)
    assert answer.status_code == 303 and "/item/" in answer.headers["location"]
    assert fake_catalog.asked_for == ["tt0088247"]


def test_an_id_the_catalogue_does_not_know_is_a_page_and_not_a_crash(client, fake_catalog):
    fake_catalog(card=None)
    answer = client.get("/ocio/buscar?tipo=movie&q=tt0000000")
    assert answer.status_code == 200


def test_saving_a_card_asks_for_the_rewrite_afterwards(client, fake_catalog, asked):
    fake_catalog(card=terminator_card())
    client.post("/ocio/guardar", data=SAVE)
    assert asked == [link_id(IMDB_URL)]      # en segundo plano, no en la request


def test_a_card_that_was_not_written_is_not_rewritten(client, fake_catalog, asked):
    fake_catalog(card=None)
    client.post("/ocio/guardar", data=SAVE)
    assert asked == []


def test_saving_the_same_card_twice_does_not_rewrite_it_again(client, fake_catalog,
                                                              asked):
    """La segunda vez no se escribió nada: tampoco hay nada que mejorar."""
    fake_catalog(card=terminator_card())
    client.post("/ocio/guardar", data=SAVE)
    client.post("/ocio/guardar", data=SAVE)
    assert asked == [link_id(IMDB_URL)]


def test_the_button_asks_again(client, fake_catalog, cfg, asked):
    fake_catalog(card=terminator_card())
    client.post("/ocio/guardar", data=SAVE)
    asked.clear()
    answer = client.post(f"/item/{link_id(IMDB_URL)}/describe",
                         follow_redirects=False)
    assert answer.status_code == 303
    assert asked == [link_id(IMDB_URL)]


def test_the_button_is_only_for_cards(client, cfg, asked):
    from oknowledge.model import Note
    link = Note(id="bbbbbbbbbbbb", url="https://example.com/x", title="Página",
                category="Redes", tags=[], type="article", source="example.com",
                saved="2026-10-10", summary="Algo.")
    write_note(cfg, link, "es")
    assert client.post("/item/bbbbbbbbbbbb/describe").status_code == 404
    assert asked == []
