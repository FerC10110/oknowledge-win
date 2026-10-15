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


# --- delivery 3 (docs/2026-10-14-rediseno-modales-teclado-design.md §10) ----------

SETTINGS = ["Ajustes", "Los cambios se guardan solos", "Motores", "Idioma y guardado", "Importar",
            "Categorías", "Buscar modelos",
            "Se usan en orden, de arriba hacia abajo. Podés poner varios modelos separados por coma.",
            "¿Dónde se guarda esto?", "Idioma de los resúmenes", "Idioma de la interfaz",
            "Compartido con tus otros plugins de Omarchy", "Cambiarlo recarga la página",
            "Guardar por defecto", "Lo que se marca al pegar un link", "Menciones de un video",
            "Qué nombres se extraen",
            "Links a analizar por vez", "Cuántos procesa cada tanda",
            "Soltá acá el export de WhatsApp", "Elegir archivo", "Links esperando análisis: 0",
            "Ver actividad", "Si renombrás a una que ya existe, se unen.",
            "¿Unir «%1» con «%2»?"]

EVERY_PAGE = ["Atajos", "Atajos de teclado", "Buscar o pegar un link", "Biblioteca · Ocio · Ideas",
              "Anterior / siguiente", "Fila arriba / abajo", "Abrir original", "Favorito",
              "Agregar etiqueta", "Seleccionar", "Borrar seleccionados", "Lista / tarjetas",
              "Cerrar / deseleccionar", 'data-undo="Deshacer"', 'data-opening="Abriendo %1…"',
              "No se pudieron cargar los ajustes. Fijate que oknowledge siga andando."]

BULK = ['data-one="1 seleccionado"', 'data-many="%1 seleccionados"', "Mover a",
        "Nueva categoría", "★ Favorito", "Borrar", "Limpiar la selección",
        "Seleccionar WireGuard"]


@pytest.mark.parametrize("text", SETTINGS)
def test_settings_says_it_as_the_handoff_does(client, text):
    assert text in client.get("/settings/panel").text


@pytest.mark.parametrize("text", EVERY_PAGE)
def test_every_page_says_the_shortcuts_as_the_handoff_does(client, text):
    assert text in client.get("/").text


@pytest.mark.parametrize("text", BULK)
def test_the_selection_says_it_as_the_handoff_does(client, text):
    assert text in client.get("/").text


def test_deleting_and_undoing_say_it_as_the_spec_does(client):
    json = {"Accept": "application/json"}
    deleted = client.post("/item/l00000000001/delete", headers=json).json()
    assert deleted["notice"] == "Borrado"
    back = client.post(f"/undo/{deleted['undo']}", headers=json).json()
    assert back["notice"] == "Restaurado"
    again = client.post(f"/undo/{deleted['undo']}", headers=json)
    assert again.json()["error"] == "Ya no se puede deshacer"


# --- delivery 4 (docs/2026-10-15-rediseno-celular-design.md §15) --------------------------

PHONE = ['<nav class="tabbar" aria-label="Secciones">', ">Biblioteca</a>", ">Ocio</a>",
         ">Ideas</a>", ">Favoritos</a>",
         'class="topbar-settings" data-modal="settings">Ajustes',
         '<nav class="chip-row" aria-label="Filtros">', ">Todo</a>",
         'data-on="Cancelar"', ">Seleccionar</button>"]


@pytest.mark.parametrize("text", PHONE)
def test_the_phone_says_it_as_the_spec_does(client, text):
    assert text in client.get("/").text


def test_the_way_back_says_where_it_goes(client):
    assert 'aria-label="Volver a Biblioteca">← Biblioteca</a>' in client.get("/?sel=l00000000001").text
    assert 'aria-label="Volver a Ocio">← Ocio</a>' in client.get("/ocio?sel=c00000000001").text
