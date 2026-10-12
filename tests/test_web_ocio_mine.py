"""Your part of a card: a state, five stars and a comment.

Three buttons and a box, each a POST that rewrites the frontmatter and
nothing else. None of it is ever written by the model: a re-analysis
replaces the summary, the points and who wrote them, and carries the rest
across -- the promise collections already has.

The words depend on what the thing is. A book is read, not watched.
"""

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.vault import find_note, note_path, rebuild_indexes, write_note
from oknowledge.web.app import create_app

CARD = "aaaaaaaaaaaa"
BOOK = "cccccccccccc"
LINK = "bbbbbbbbbbbb"


@pytest.fixture(autouse=True)
def state_tree(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr("oknowledge.web.app.CONFIG_PATH",
                        tmp_path / "config" / "config.toml")


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


def put_card(cfg, note):
    write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ocio))


@pytest.fixture
def a_card_in_the_shelf(cfg):
    note = Note(id=CARD, url="https://imdb.com/title/tt0088247",
                title="The Terminator", category="Películas", tags=[],
                type="movie", source="imdb.com", saved="2026-10-11",
                summary="Un cyborg.")
    put_card(cfg, note)
    return note


@pytest.fixture
def a_book_in_the_shelf(cfg):
    note = Note(id=BOOK, url="https://openlibrary.org/works/OL893414W",
                title="Dune", category="Libros", tags=[], type="book",
                source="openlibrary.org", saved="2026-10-11", summary="Arrakis.")
    put_card(cfg, note)
    return note


@pytest.fixture
def a_link_in_the_library(cfg):
    note = Note(id=LINK, url="https://wireguard.com", title="WireGuard",
                category="Redes", tags=[], type="article",
                source="wireguard.com", saved="2026-10-10", summary="Una vpn.")
    write_note(cfg, note, "es")
    rebuild_indexes(cfg, "es")
    return note


def note_now(cfg, link_id=CARD):
    return find_note(cfg, link_id, shelf=cfg.ocio)[1]


def card_file(cfg):
    return next(cfg.ocio.dir.glob("*the-terminator*.md"))


def test_the_three_buttons_set_the_state(client, a_card_in_the_shelf, cfg):
    client.post(f"/item/{CARD}/mine/state", data={"state": "done"})
    assert note_now(cfg).state == "done"


def test_the_stars_set_the_score(client, a_card_in_the_shelf, cfg):
    client.post(f"/item/{CARD}/mine/score", data={"score": "4"})
    assert note_now(cfg).score == 4


@pytest.mark.parametrize("bad", ["9", "0", "-1", "cinco", "", "4.5"])
def test_a_score_that_is_not_one_to_five_writes_nothing(client, a_card_in_the_shelf,
                                                        cfg, bad):
    before = card_file(cfg).read_text(encoding="utf-8")
    client.post(f"/item/{CARD}/mine/score", data={"score": bad})
    assert card_file(cfg).read_text(encoding="utf-8") == before


def test_a_state_nobody_invented(client, a_card_in_the_shelf, cfg):
    client.post(f"/item/{CARD}/mine/state", data={"state": "abandonada"})
    assert note_now(cfg).state == ""


def test_your_note_is_saved_as_you_typed_it(client, a_card_in_the_shelf, cfg):
    client.post(f"/item/{CARD}/mine/note",
                data={"my_note": "La vi en el cine.\n\nMuy buena."})
    assert note_now(cfg).my_note == "La vi en el cine.\n\nMuy buena."


@pytest.mark.parametrize("cleared", ["", "  ", "\n"])
def test_an_empty_box_clears_your_note(client, a_card_in_the_shelf, cfg, cleared):
    """Borrar lo que escribiste es una edición como cualquier otra."""
    client.post(f"/item/{CARD}/mine/note", data={"my_note": "Algo"})
    assert note_now(cfg).my_note == "Algo"
    client.post(f"/item/{CARD}/mine/note", data={"my_note": cleared})
    assert note_now(cfg).my_note == ""


def test_your_part_survives_what_the_model_writes(client, a_card_in_the_shelf, cfg):
    """La promesa del diseño, probada donde se rompe."""
    client.post(f"/item/{CARD}/mine/state", data={"state": "done"})
    client.post(f"/item/{CARD}/mine/score", data={"score": "5"})
    client.post(f"/item/{CARD}/mine/note", data={"my_note": "Mía"})
    path, note = find_note(cfg, CARD, shelf=cfg.ocio)
    note.summary, note.points, note.engine = "Reescrita", ["uno"], "opencode"
    write_note(cfg, note, "es", path=path)
    back = note_now(cfg)
    assert (back.state, back.score, back.my_note) == ("done", 5, "Mía")
    assert back.summary == "Reescrita"


def test_the_words_depend_on_what_it_is(client, a_book_in_the_shelf):
    body = client.get(f"/item/{BOOK}").text
    assert "to read" in body or "por leer" in body
    assert "to watch" not in body and "por ver" not in body


def test_a_film_is_watched_and_not_read(client, a_card_in_the_shelf):
    body = client.get(f"/item/{CARD}").text
    assert "to watch" in body or "por ver" in body
    assert "to read" not in body and "por leer" not in body


def test_a_link_has_no_stars(client, a_link_in_the_library):
    body = client.get(f"/item/{LINK}").text
    assert 'action="/item/' in body          # sus propios botones siguen
    assert "/mine/score" not in body


def test_none_of_this_reaches_the_links_shelf(client, a_link_in_the_library, cfg):
    answer = client.post(f"/item/{LINK}/mine/score", data={"score": "4"})
    assert answer.status_code == 404


@pytest.mark.parametrize("what, data", [
    ("state", {"state": "done"}), ("score", {"score": "4"}),
    ("note", {"my_note": "x"}),
])
def test_a_card_that_is_not_there(client, what, data):
    assert client.post(f"/item/zzzzzzzzzzzz/mine/{what}", data=data).status_code == 404


# --- what the card page offers, and what it does when clicked --------------

def test_a_card_can_be_thrown_away(client, cfg, a_card_in_the_shelf):
    """El botón está dibujado en la ficha: tiene que hacer lo que dice."""
    answer = client.post(f"/item/{CARD}/delete", follow_redirects=False)
    assert answer.status_code == 303
    assert find_note(cfg, CARD, shelf=cfg.ocio) is None
    assert (cfg.root / "trash" / "2026-10-11-the-terminator.md").exists()


def test_a_cards_tags_can_be_edited_by_hand(client, cfg, a_card_in_the_shelf):
    """Las etiquetas son los géneros del catálogo; corregirlas a mano es
    parte del diseño y el modelo nunca las pisa."""
    client.post(f"/item/{CARD}/tags", data={"tags": "ciencia-ficcion, culto"})
    assert find_note(cfg, CARD, shelf=cfg.ocio)[1].tags == ["ciencia-ficcion", "culto"]


def test_the_card_page_offers_nothing_that_answers_404(client, a_card_in_the_shelf):
    """Una ficha no se mueve de categoría (la categoría es el tipo), no se
    reanaliza (no hay página que volver a leer: eso es reescribir el
    resumen) y no entra en una colección de links. Lo que no se puede
    hacer no se dibuja."""
    body = client.get(f"/item/{CARD}").text
    assert f"/item/{CARD}/delete" in body and f"/item/{CARD}/tags" in body
    for path in ("category", "reprocess", "collections"):
        assert f"/item/{CARD}/{path}" not in body


def test_a_link_still_offers_all_of_it(client, cfg, a_link_in_the_library):
    body = client.get(f"/item/{LINK}").text
    for path in ("category", "reprocess", "collections", "tags", "delete"):
        assert f"/item/{LINK}/{path}" in body


def test_the_popup_of_a_card_opens(client, a_card_in_the_shelf):
    """La grilla de ocio apunta cada ficha a /embed, que es lo que el
    popup carga. Un 404 ahí es una tarjeta que no se abre sin salir de la
    grilla, que es para lo que el popup existe."""
    answer = client.get(f"/embed/{CARD}")
    assert answer.status_code == 200
    assert "The Terminator" in answer.text
