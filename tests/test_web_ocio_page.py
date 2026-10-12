"""The section the cards live in.

A second shelf, a second index, and the two never mix: a film does not
belong among the links about Docker, and a link does not belong among the
films. Everything a note page can do, a card gets for free -- this page is
only the list.

Until the first card is saved there is no ocio/ folder at all, which is the
state every vault is in right now.
"""

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.vault import note_path, rebuild_indexes, write_note
from oknowledge.web.app import create_app


@pytest.fixture(autouse=True)
def state_tree(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr("oknowledge.web.app.CONFIG_PATH",
                        tmp_path / "config" / "config.toml")


def card(title, kind="movie", category="Películas", **over) -> Note:
    fields = dict(
        id=f"{abs(hash(title)):012d}"[:12], url=f"https://imdb.com/title/{title}",
        title=title, category=category, tags=["ciencia-ficcion"], type=kind,
        source="imdb.com", saved="2026-10-11", summary="Algo pasa.",
    )
    fields.update(over)
    return Note(**fields)


def dune() -> Note:
    return card("Dune", kind="book", category="Libros", state="pending",
                length="608 páginas", rating="4.3")


def terminator() -> Note:
    return card("The Terminator", length="108 min", rating="8.1")


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


def put(cfg, note):
    write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ocio))


@pytest.fixture
def a_card_in_the_shelf(cfg):
    note = terminator()
    note.published = "1984-10-26"
    put(cfg, note)
    return note


@pytest.fixture
def a_link_in_the_library(cfg):
    note = Note(id="bbbbbbbbbbbb", url="https://wireguard.com", title="WireGuard",
                category="Redes", tags=[], type="article", source="wireguard.com",
                saved="2026-10-10", summary="Una vpn.")
    write_note(cfg, note, "es")
    return note


@pytest.fixture
def cards_of_every_kind(cfg):
    put(cfg, terminator())
    put(cfg, dune())
    put(cfg, card("Cowboy Bebop", kind="anime", category="Anime"))


def test_the_nav_has_the_section(client):
    assert '/ocio"' in client.get("/").text


def test_an_empty_shelf_is_a_page_and_not_a_500(client):
    """El caso de todos los días hasta que guardes la primera: la carpeta
    ocio/ todavía no existe."""
    answer = client.get("/ocio")
    assert answer.status_code == 200
    assert "todavía" in answer.text.lower() or "nothing" in answer.text.lower()


def test_the_cards_are_there_and_the_links_are_not(client, a_card_in_the_shelf,
                                                   a_link_in_the_library):
    body = client.get("/ocio").text
    assert "The Terminator" in body
    assert "WireGuard" not in body


def test_the_library_does_not_show_the_cards(client, a_card_in_the_shelf):
    assert "The Terminator" not in client.get("/").text


def test_a_card_shows_what_a_card_has(client, a_card_in_the_shelf):
    body = client.get("/ocio").text
    assert "8.1" in body and "1984" in body and "108 min" in body


def test_the_four_kinds_filter(client, cards_of_every_kind):
    body = client.get("/ocio?tipo=book").text
    assert "Dune" in body and "The Terminator" not in body


def test_an_unknown_kind_shows_everything_rather_than_nothing(client,
                                                              cards_of_every_kind):
    body = client.get("/ocio?tipo=ovni").text
    assert "Dune" in body and "The Terminator" in body


def test_the_state_filters(client, cfg):
    put(cfg, dune())                       # pending
    seen = terminator()
    seen.state = "done"
    put(cfg, seen)
    body = client.get("/ocio?estado=pending").text
    assert "Dune" in body and "The Terminator" not in body


@pytest.mark.parametrize("estado", ["ovni", "dropped"])
def test_an_unknown_state_shows_everything_rather_than_nothing(client, cfg, estado):
    """Un estado que ninguna ficha puede tener filtra a cero y la página
    queda igual que un estante vacío. Son tres estados y nada más: lo que
    no es uno de ellos no filtra."""
    put(cfg, dune())                       # pending
    seen = terminator()
    seen.state = "done"
    put(cfg, seen)
    body = client.get(f"/ocio?estado={estado}").text
    assert "Dune" in body and "The Terminator" in body


def test_a_state_nobody_knows_does_not_take_the_page_down(client, cfg):
    """Un `state:` escrito a mano en Obsidian —o escrito por una versión
    anterior del programa— es un valor como cualquier otro: la sección lo
    muestra tal cual y sigue en pie. Un 500 acá se lleva todas las fichas
    por una palabra en una."""
    note = terminator()
    note.state = "abandonada"
    put(cfg, note)
    answer = client.get("/ocio")
    assert answer.status_code == 200
    assert "The Terminator" in answer.text and "abandonada" in answer.text


def test_a_card_nobody_rewrote_is_marked(client, a_card_in_the_shelf):
    body = client.get("/ocio").text.lower()
    assert "not rewritten" in body or "sin reescribir" in body


def test_a_card_the_model_rewrote_is_not_marked(client, cfg):
    note = terminator()
    note.engine, note.model = "opencode", "sonnet"
    put(cfg, note)
    body = client.get("/ocio").text.lower()
    assert "not rewritten" not in body and "sin reescribir" not in body


def test_the_shelf_notices_a_card_written_while_the_server_runs(client, cfg):
    """La Library cachea por mtime: la segunda instancia tiene que refrescar
    igual que la primera."""
    assert "Dune" not in client.get("/ocio").text
    put(cfg, dune())
    assert "Dune" in client.get("/ocio").text


def test_a_card_opens_from_the_section(client, a_card_in_the_shelf):
    answer = client.get(f"/item/{a_card_in_the_shelf.id}")
    assert answer.status_code == 200
    assert "The Terminator" in answer.text


def test_the_shelf_does_not_count_its_own_indexes_as_broken(client, cfg):
    """El estante de ocio guarda sus índices adentro, al lado de las fichas:
    un índice no es una nota rota, es un índice."""
    from oknowledge.vault import rebuild_indexes as rebuild
    put(cfg, terminator())
    rebuild(cfg, "es", shelf=cfg.ocio)
    body = client.get("/ocio").text.lower()
    assert "could not be read" not in body
    assert "no se pudieron leer" not in body
    assert "the terminator" in body


def test_a_card_nobody_rewrote_offers_the_button(client, a_card_in_the_shelf):
    body = client.get(f"/item/{a_card_in_the_shelf.id}").text
    assert f'/item/{a_card_in_the_shelf.id}/describe' in body


def test_a_card_the_model_already_wrote_does_not_offer_it(client, cfg):
    note = terminator()
    note.engine, note.model = "opencode", "sonnet"
    put(cfg, note)
    assert "/describe" not in client.get(f"/item/{note.id}").text


def test_a_link_never_offers_it(client, a_link_in_the_library):
    assert "/describe" not in client.get(f"/item/{a_link_in_the_library.id}").text
