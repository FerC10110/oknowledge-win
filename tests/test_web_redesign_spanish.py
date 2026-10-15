"""Spec §5: the handoff's words, verbatim, on the three screens of this
delivery. One request per screen, every string looked for in it."""

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.model import Note
from oknowledge.vault import note_path, rebuild_indexes, write_note
from oknowledge.web.app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault, ui_language="es")    # the fork reads the language from the config
    write_note(cfg, Note(id="l00000000001", url="https://wireguard.com", title="WireGuard",
                         category="Redes", tags=["vpn"], type="article", source="wireguard.com",
                         saved="2026-10-10", summary="Una vpn."), "es")
    idea = new_idea("Una vpn para la familia.", "VPN familiar", "2026-10-13",
                    "2026-10-13T00:00:00.000001+00:00")
    idea.tags = ["vpn"]
    write_note(cfg, idea, "es", path=note_path(cfg, idea, shelf=cfg.ideas))
    for n, (kind, category) in enumerate((("movie", "Películas"), ("book", "Libros")), 1):
        card = Note(id=f"c{n:011d}", url=f"https://www.imdb.com/title/tt{n}", title=f"Ficha {n}",
                    category=category, tags=[], type=kind, source="imdb.com",
                    saved=f"2026-10-0{n}", summary="De qué va.", engine="")
        write_note(cfg, card, "es", path=note_path(cfg, card, shelf=cfg.ocio))
    for shelf in (cfg.links, cfg.ocio, cfg.ideas):
        rebuild_indexes(cfg, "es", shelf=shelf)
    client = TestClient(create_app(cfg))
    client.idea = idea.id
    return client


IDEA_SCREEN = ["← Ideas", "creada 13 oct", "Guardando…", "Guardado", "PEDILE A LA IA", "usando",
               "Links vinculados (0)", "Toda la biblioteca", "Sólo mi texto", "TU IDEA",
               "Escribila como te salga: la IA la ordena.", "se guarda sola", "Resumen",
               "¿Ya existe?", "Mejoras", "Ampliación", "Todavía no se lo pediste.",
               "Regenerar todo con la IA", "Borrar idea", "Links de esta idea",
               "Buscá en tus 1 links para sumar", "VINCULADOS", "PUEDEN SERVIR", "+ Sumar",
               "semilla", "en marcha"]

IDEAS_LIST = ["Nueva idea", "Buscá en tus ideas", "ESTADO", "descartada"]

OCIO = ["Buscá en Ocio o pegá un link de IMDb u Open Library",
        "2 fichas sin reescribir", "Reescribir", "Recientes", "Por ver", "Viendo", "Vista",
        "Reescribir la ficha", "Cambiar tipo", "Abrir en imdb.com",
        "La ficha está como vino de la fuente (en inglés).", "Reescribir en español",
        "DE QUÉ TRATA", "TU NOTA", "Qué te pareció", "Buscar en catálogos", "TIPO",
        "Películas", "Libros"]


@pytest.mark.parametrize("text", IDEA_SCREEN)
def test_the_idea_screen_says_it_as_the_handoff_does(client, text):
    assert text in client.get(f"/ideas/{client.idea}").text


@pytest.mark.parametrize("text", IDEAS_LIST)
def test_the_ideas_list_says_it_as_the_handoff_does(client, text):
    assert text in client.get("/ideas").text


@pytest.mark.parametrize("text", OCIO)
def test_ocio_says_it_as_the_handoff_does(client, text):
    assert text in client.get("/ocio?sel=c00000000001").text


def test_a_book_s_states_are_read(client):
    body = client.get("/ocio?tipo=book").text
    for text in ("Por leer", "Leyendo", "Leído"):
        assert text in body


def test_the_idea_screen_has_no_english_left(client):
    body = client.get(f"/ideas/{client.idea}").text
    for english in ("Saving…", "ASK THE AI", "YOUR IDEA", "Linked links", "Delete idea",
                    "+ Add", "LINKED", "MAY HELP"):
        assert english not in body
