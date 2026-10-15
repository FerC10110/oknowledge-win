"""A card in Ocio's right column (spec §3, "Panel derecho")."""

import re

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.vault import find_note, note_path, rebuild_indexes, write_note
from oknowledge.web.app import create_app


@pytest.fixture(autouse=True)
def state_tree(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr("oknowledge.web.app.CONFIG_PATH", tmp_path / "config" / "config.toml")


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


CARD = "c00000000001"


def put(cfg, **over):
    fields = dict(id=CARD, url="https://www.imdb.com/title/tt0088247", title="The Terminator",
                  category="Películas", tags=["acción"], type="movie", source="imdb.com",
                  saved="2026-10-11", summary="Un cyborg viaja al pasado.\n\nY no para.",
                  published="1984-10-26", length="108 min", rating="8.1", engine="fake",
                  state="doing", score=4, my_note="La vi dos veces.")
    fields.update(over)
    note = Note(**fields)
    write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ocio))
    return note


def panel(client, query=""):
    return client.get(f"/panel/{CARD}{query}").text


def test_the_panel_is_a_fragment_for_a_card(cfg, client):
    put(cfg)
    body = panel(client)
    assert "<html" not in body and f'data-panel="{CARD}"' in body


def test_ocio_draws_the_selected_card_s_panel(cfg, client):
    put(cfg)
    body = client.get("/ocio").text
    assert f'data-panel="{CARD}"' in body and 'class="detail-empty"' not in body


def test_the_top_bar_has_the_state_in_the_kind_s_words(cfg, client):
    put(cfg)
    seg = re.search(rf'<form[^>]*action="/item/{CARD}/mine/state"[^>]*>.*?</form>',
                    panel(client), re.S).group(0)
    assert "data-inline" in seg
    assert re.findall(r">(To watch|Watching|Watched)<", seg) == ["To watch", "Watching", "Watched"]
    assert re.search(r'value="doing" class="on"', seg)


def test_a_book_is_read(cfg, client):
    put(cfg, type="book", category="Libros", url="https://openlibrary.org/works/OL1W",
        source="openlibrary.org")
    body = panel(client)
    assert ">To read<" in body and ">Reading<" in body and ">To watch<" not in body


def test_the_current_star_takes_the_stars_off(cfg, client):
    put(cfg)
    stars = re.search(rf'<form[^>]*action="/item/{CARD}/mine/score"[^>]*>.*?</form>',
                      panel(client), re.S).group(0)
    assert re.findall(r'name="score" value="(\d)"', stars) == ["1", "2", "3", "0", "5"]


def test_the_more_menu(cfg, client):
    put(cfg)
    body = panel(client)
    assert f'action="/item/{CARD}/describe"' in body and "Rewrite the card" in body
    assert "Change type ▸" in body
    assert re.findall(rf'action="/item/{CARD}/kind".*?value="(\w+)"', body, re.S)[:1] == ["movie"]
    for kind in ("movie", "series", "anime", "book"):
        assert f'name="kind" value="{kind}"' in body
    assert f'action="/item/{CARD}/delete"' in body


def test_the_head_poster_kind_title_and_chips(cfg, client):
    put(cfg, cover="../attachments/t.jpg")
    body = panel(client)
    assert f'<img src="/cover/{CARD}"' in body
    assert "Movie · imdb.com" in body
    assert '<h1 dir="auto">The Terminator</h1>' in body
    for chip in ("1984", "108 min", "IMDb ★ 8.1"):
        assert f">{chip}<" in body


def test_a_card_without_a_cover_has_the_gradient(cfg, client):
    put(cfg)
    head = panel(client).split("<h1", 1)[0]
    assert "<img" not in head and "oklch(0.42 0.06 300)" in head


def test_open_in_its_site(cfg, client):
    put(cfg)
    assert re.search(r'<a class="btn primary" href="https://www.imdb.com/title/tt0088247" '
                     r'target="_blank" rel="noreferrer" data-open>Open in imdb.com ↗</a>', panel(client))


def test_a_url_that_is_not_the_web_is_never_a_link(cfg, client):
    put(cfg, url="javascript:alert(1)")
    body = panel(client)
    assert "data-panel=" in body             # the card was drawn: not a vacuous pass
    assert "javascript:" not in body


def test_a_rewritten_card_has_no_notice(cfg, client):
    put(cfg)
    assert "as the source gave it" not in panel(client)


def test_an_unrewritten_card_offers_the_rewrite(cfg, client):
    put(cfg, engine="")
    body = panel(client)
    assert "The card is as the source gave it (in English)." in body
    assert re.search(rf'<form[^>]*action="/item/{CARD}/describe"[^>]*data-inline[^>]*>\s*'
                     r'<button class="btn primary">Rewrite in Spanish</button>', body)


def test_while_it_is_rewritten_it_says_so_and_is_watched(cfg):
    put(cfg, engine="")
    app = create_app(cfg)
    app.state.rewriting.start(CARD, "describe")
    body = TestClient(app).get(f"/panel/{CARD}").text
    assert f'data-working="{CARD}"' in body and "Rewriting…" in body
    assert "Rewrite in Spanish" not in body


def test_a_failed_rewrite_says_why(cfg):
    put(cfg, engine="")
    app = create_app(cfg)
    app.state.rewriting.start(CARD, "describe")
    app.state.rewriting.finish(CARD, "describe", "opencode: 429")
    assert "Last time it failed: opencode: 429" in TestClient(app).get(f"/panel/{CARD}").text


def test_what_it_is_about_your_note_and_tags(cfg, client):
    put(cfg)
    body = panel(client)
    assert "WHAT IT IS ABOUT" in body and "Un cyborg viaja al pasado." in body
    area = re.search(r'<textarea[^>]*id="card-note"[^>]*>(.*?)</textarea>', body, re.S)
    assert area.group(1) == "La vi dos veces."
    assert f'data-autosave="/item/{CARD}/mine/note"' in area.group(0)
    assert 'placeholder="What you thought of it"' in area.group(0)
    assert "YOUR NOTE" in body and "saves itself" in body
    assert "#acción" in body and 'placeholder="+ tag"' in body


def test_no_save_buttons_marks_or_disks(cfg, client):
    put(cfg)
    body = panel(client)
    assert "data-panel=" in body             # the card was drawn: not a vacuous pass
    assert "💾" not in body and "Edit tags" not in body and "/mark" not in body
    saves = re.findall(r"<button[^>]*>Save</button>", body)
    assert all("data-nojs" in button for button in saves)


def test_the_state_route_speaks_for_a_rewrite(cfg):
    put(cfg, engine="")
    app = create_app(cfg)
    client = TestClient(app)
    app.state.rewriting.start(CARD, "describe")
    assert client.get(f"/item/{CARD}/state").json() == {"working": True, "status": "rewriting"}
    app.state.rewriting.finish(CARD, "describe", "boom")
    assert client.get(f"/item/{CARD}/state").json() == {"working": False, "status": "failed"}
    app.state.rewriting.start(CARD, "describe")
    app.state.rewriting.finish(CARD, "describe", None)
    assert client.get(f"/item/{CARD}/state").json() == {"working": False, "status": "ok"}


# --- the type -------------------------------------------------------------------------

def test_changing_the_type_changes_type_and_category(cfg, client):
    put(cfg)
    answer = client.post(f"/item/{CARD}/kind", data={"kind": "anime"}, follow_redirects=False)
    assert answer.headers["location"] == f"/ocio?sel={CARD}&notice=saved"
    after = find_note(cfg, CARD, shelf=cfg.ocio)[1]
    assert (after.type, after.category) == ("anime", "Anime")


def test_a_book_is_filed_under_books(cfg, client):
    put(cfg)
    client.post(f"/item/{CARD}/kind", data={"kind": "book"})
    assert find_note(cfg, CARD, shelf=cfg.ocio)[1].category == "Libros"


@pytest.mark.parametrize("kind", ["podcast", "", "idea"])
def test_an_unknown_type_changes_nothing(cfg, client, kind):
    put(cfg)
    answer = client.post(f"/item/{CARD}/kind", data={"kind": kind},
                         headers={"Accept": "application/json"})
    assert answer.status_code == 400 and answer.json()["ok"] is False
    assert find_note(cfg, CARD, shelf=cfg.ocio)[1].type == "movie"


def test_only_a_card_has_a_type_to_change(cfg, client):
    write_note(cfg, Note(id="l00000000001", url="https://e.com", title="E", category="Redes",
                         tags=[], type="article", source="e.com", saved="2026-10-10",
                         summary="s"), "es")
    rebuild_indexes(cfg, "es")
    assert client.post("/item/l00000000001/kind", data={"kind": "movie"}).status_code == 404


def test_the_type_by_script_answers_json(cfg, client):
    put(cfg)
    answer = client.post(f"/item/{CARD}/kind", data={"kind": "series"},
                         headers={"Accept": "application/json"})
    assert answer.json()["ok"] is True


# --- where a card lives now ----------------------------------------------------------

def test_a_card_s_old_address_opens_it_in_ocio(cfg, client):
    put(cfg)
    answer = client.get(f"/item/{CARD}?notice=saved", follow_redirects=False)
    assert answer.headers["location"] == f"/ocio?sel={CARD}&notice=saved"


def test_a_deleted_card_goes_back_to_ocio(cfg, client):
    put(cfg)
    answer = client.post(f"/item/{CARD}/delete", follow_redirects=False)
    assert answer.headers["location"].startswith("/ocio?notice=trashed&undo=")


def test_the_old_pages_and_scripts_are_gone(client):
    from importlib.resources import files
    templates = files("oknowledge.web").joinpath("templates")
    for name in ("item.html", "mine-buttons.html", "mark-picker.html", "icon-save.html"):
        assert not templates.joinpath(name).is_file()
    assert client.get("/static/redo.js").status_code == 404


# --- one series, several series ------------------------------------------------------

def test_one_series_is_a_serie_in_spanish(cfg):
    """In English the word is the same for one and for several, so the key
    cannot be: the chip and the panel name one card, the sidebar row the
    many."""
    client = TestClient(create_app(Config(vault=cfg.vault, ui_language="es")))    # the fork's language
    put(cfg, type="series", category="Series")
    assert "Serie · imdb.com" in panel(client)
    shelf = client.get("/ocio").text
    assert '<span class="chip kind">Serie</span>' in shelf
    assert ">Series<" in shelf
