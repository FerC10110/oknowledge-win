"""`/`: the redesign's library column, driven by the URL."""

import re

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.vault import rebuild_indexes, write_note
from oknowledge.web.app import create_app


def note(id, title, category="Redes", tags=(), mark="", collections=(), saved="2026-10-03",
         summary="s"):
    return Note(id=id, url=f"https://e.com/{id}", title=title, category=category,
                tags=list(tags), type="article", source="e.com", saved=saved,
                summary=summary, mark=mark, collections=list(collections))


@pytest.fixture
def client(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    write_note(cfg, note("a1", "WireGuard simple", tags=["vpn"], mark="⭐",
                         collections=["Casa conectada"], saved="2026-10-04"), "es")
    write_note(cfg, note("b2", "Masa madre", category="Cocina", mark="📌",
                         saved="2026-09-20"), "es")
    write_note(cfg, note("c3", "Rutinas de fuerza", category="Salud", tags=["vpn"],
                         saved="2026-09-11"), "es")
    rebuild_indexes(cfg, "es")
    return TestClient(create_app(cfg))


@pytest.fixture
def big(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    for i in range(130):
        write_note(cfg, note(f"n{i:03d}", f"Nota {i:03d}", saved=f"2026-{1 + i % 12:02d}-01"), "es")
    rebuild_indexes(cfg, "es")
    return TestClient(create_app(cfg))


def items(body):
    return re.findall(r'<li class="item[^"]*" id="card-([^"]+)"', body)


def test_the_home_is_three_columns(client):
    body = client.get("/").text
    assert '<div class="app home">' in body
    assert '<section class="center"' in body
    assert '<section class="detail" id="panel"' in body


def test_everything_newest_first(client):
    assert items(client.get("/").text) == ["a1", "b2", "c3"]


@pytest.mark.parametrize("query,ids", [
    ("cat=Cocina", ["b2"]), ("tag=vpn", ["a1", "c3"]), ("mark=⭐", ["a1"]),
    ("mark=📌", ["b2"]), ("col=Casa conectada", ["a1"]), ("q=masa", ["b2"]),
    ("category=Salud", ["c3"]), ("collection=Casa conectada", ["a1"]),
])
def test_each_filter(client, query, ids):
    assert items(client.get("/?" + query).text) == ids


def test_the_header_names_the_view_and_counts_it(client):
    body = client.get("/?cat=Cocina").text
    assert re.search(r'class="list-head">\s*<span>Cocina · <b class="mono">1</b>', body)


def test_the_sidebar_lists_categories_marks_and_collections(client):
    side = re.search(r'<aside class="sidebar".*?</aside>', client.get("/").text, re.S).group(0)
    for text in ("Redes", "Cocina", "Salud", "Favorites", "📌", "Casa conectada"):
        assert text in side
    assert 'class="filter on"' in side          # "All" is the one on


def test_the_active_filter_is_marked(client):
    side = re.search(r'<aside class="sidebar".*?</aside>', client.get("/?cat=Salud").text, re.S).group(0)
    assert re.search(r'cat=Salud"[^>]*class="filter on"', side)


def test_cards_by_default_and_rows_on_request(client):
    assert '<ul class="items tiles"' in client.get("/").text
    assert '<ul class="items rows"' in client.get("/?vista=lista").text


def test_a_card_selects_its_note_without_leaving_the_view(client):
    body = client.get("/?cat=Redes").text
    assert 'href="/?cat=Redes&amp;sel=a1" data-sel="a1"' in body


def test_a_card_shows_category_colour_domain_and_favourite(client):
    body = client.get("/").text
    card = re.search(r'id="card-a1".*?</li>', body, re.S).group(0)
    assert "oklch(0.74 0.09 265)" in card       # the Redes dot
    assert "e.com" in card
    assert "★" in card
    assert "4 Oct" in card


def test_the_first_item_is_selected_when_none_is_asked(client):
    assert 'id="card-a1"' in client.get("/").text
    assert re.search(r'<li class="item on" id="card-a1"', client.get("/").text)


@pytest.mark.parametrize("sel", ["zzz", "../x", "b2"])
def test_a_selection_outside_the_view_falls_back_to_the_first(client, sel):
    body = client.get(f"/?cat=Salud&sel={sel}").text
    assert re.search(r'<li class="item on" id="card-c3"', body)


def test_a_search_with_no_hits_says_so(client):
    body = client.get("/?q=zanahoria").text
    assert "Nothing matches “zanahoria”" in body
    assert 'href="/">See everything</a>' in body


def test_an_empty_filter_says_so(client):
    body = client.get("/?tag=nada").text
    assert "There is nothing in #nada" in body


def test_a_query_of_punctuation_is_everything(client):
    assert items(client.get("/?q=!!!").text) == ["a1", "b2", "c3"]


def test_a_link_in_the_field_switches_it_to_saving(client):
    body = client.get("/?q=https://nuevo.com/x").text
    assert '<form class="unified saving"' in body
    assert items(body) == ["a1", "b2", "c3"]


def test_enter_without_javascript_searches(client):
    form = re.search(r'<form class="unified.*?</form>', client.get("/").text, re.S).group(0)
    first = re.search(r"<button[^>]*>", form).group(0)
    assert "formaction" not in first             # the default button is the GET one


def test_the_save_button_posts_to_add(client):
    form = re.search(r'<form class="unified.*?</form>', client.get("/").text, re.S).group(0)
    assert 'formaction="/add"' in form and 'formmethod="post"' in form
    assert 'name="content" value="full"' in form and 'name="content" value="summary"' in form


def test_add_takes_the_link_from_the_unified_field(client, monkeypatch):
    from oknowledge.web import app as module
    monkeypatch.setattr(module, "fetch", lambda *a, **k: None)
    answer = client.post("/add", data={"q": "https://nuevo.com/x", "content": "full"},
                         follow_redirects=False)
    assert answer.status_code == 303
    assert answer.headers["location"].endswith("&notice=reading")
    assert answer.headers["location"].startswith("/?sel=")


def test_the_list_fragment_is_the_column_alone(client):
    body = client.get("/lista?cat=Cocina").text
    assert "<html" not in body
    assert items(body) == ["b2"]


def test_sixty_at_first_and_a_way_to_more(big):
    body = big.get("/").text
    assert len(items(body)) == 60
    assert re.search(r'<a class="more" href="/\?hasta=120" data-more="/lista\?desde=60"', body)


def test_more_without_javascript_draws_the_longer_list(big):
    assert len(items(big.get("/?hasta=120").text)) == 120


def test_more_with_javascript_is_the_next_chunk_alone(big):
    body = big.get("/lista?desde=120").text
    assert len(items(body)) == 10
    assert 'class="more"' not in body


def test_search_and_marked_redirect_to_the_home(client):
    answer = client.get("/search?q=masa", follow_redirects=False)
    assert answer.status_code == 303 and answer.headers["location"] == "/?q=masa"
    answer = client.get("/marked?mark=⭐", follow_redirects=False)
    assert answer.headers["location"] == "/?mark=%E2%AD%90"


# --- fix round 1 ------------------------------------------------------------

def test_an_ocio_request_switches_the_field_to_saving(client):
    """Spec §6: `película:…` goes to /add like a link, so the field saves it
    and the list is not filtered by it."""
    body = client.get("/?q=película:Terminator").text
    assert '<form class="unified saving"' in body
    assert items(body) == ["a1", "b2", "c3"]


@pytest.mark.parametrize("q", ["masa", "nota: masa", "hola mundo"])
def test_ordinary_words_are_never_taken_for_an_ocio_request(client, q):
    body = client.get("/", params={"q": q}).text
    assert '<form class="unified saving"' not in body


def test_the_field_names_the_prefixes_it_saves(client):
    from oknowledge import cards
    form = re.search(r'<form class="unified[^>]*>', client.get("/").text).group(0)
    listed = re.search(r'data-save-prefixes="([^"]*)"', form).group(1).split()
    assert listed == sorted(cards.PREFIXES)


@pytest.fixture
def with_body(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    n = note("k1", "Uno")
    n.body = "solo el cuerpo dice zanahoriazul"
    write_note(cfg, n, "es")
    write_note(cfg, note("k2", "Dos"), "es")
    rebuild_indexes(cfg, "es")
    return TestClient(create_app(cfg))


def test_searching_the_list_reads_no_note_from_disk(with_body, monkeypatch):
    """The column draws no snippet, so a body hit must not cost a file read:
    live search asks for this at every pause in typing."""
    with_body.get("/")                       # the index is built before the trap
    monkeypatch.setattr("oknowledge.web.index.read_full",
                        lambda *a, **k: pytest.fail("read a note for a snippet"))
    assert items(with_body.get("/?q=zanahoriazul").text) == ["k1"]
    assert items(with_body.get("/lista?q=zanahoriazul").text) == ["k1"]


def test_the_next_chunk_is_the_one_after_the_first(big):
    first = items(big.get("/?hasta=120").text)
    body = big.get("/lista?desde=60").text
    assert items(body) == first[60:120]
    assert 'data-more="/lista?desde=120"' in body


def test_the_home_speaks_spanish(client, isolated_ui_language):
    isolated_ui_language.write_text('{"language": "es"}', encoding="utf-8")
    body = client.get("/").text
    for text in ("Buscá o pegá un link para guardarlo", "Biblioteca", "CATEGORÍAS",
                 "MARCAS", "COLECCIONES", "Tarjetas", "Lista", "★ Favoritos",
                 "Completo", "Resumen", "Abrir el original"):
        assert text in body
