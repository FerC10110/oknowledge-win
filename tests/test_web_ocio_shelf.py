"""/ocio (spec §3): sidebar TIPO/ESTADO, the poster grid, the panel column."""

import re

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.vault import note_path, rebuild_indexes, write_note
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


def put(cfg, n, title, kind="movie", **over):
    fields = dict(id=f"c{n:011d}", url=f"https://www.imdb.com/title/tt{n}", title=title,
                  category="Películas", tags=["drama"], type=kind, source="imdb.com",
                  saved=f"2026-10-{n:02d}", summary="Algo pasa.", engine="fake")
    fields.update(over)
    note = Note(**fields)
    write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ocio))
    return note


def grid(body):
    head = body.index('<ul class="posters"')
    return body[head:body.index("</ul>", head)]


def test_three_columns_with_the_panel(cfg, client):
    put(cfg, 1, "Alien")
    body = client.get("/ocio").text
    assert '<div class="app ocio">' in body
    assert 'id="list"' in body and 'data-source="/ocio/lista"' in body
    assert 'id="panel"' in body


def test_the_field_says_what_it_takes(client):
    body = client.get("/ocio").text
    form = re.search(r'<form[^>]*id="unified"[^>]*>', body).group(0)
    assert 'action="/ocio"' in form and 'data-mode="ocio"' in form
    assert ('placeholder="Search Leisure or paste a link from IMDb or Open Library"'
            in body)


def test_the_head_counts_and_offers_the_four_orders(cfg, client):
    put(cfg, 1, "Alien"), put(cfg, 2, "Brazil")
    body = client.get("/ocio").text
    assert re.search(r"Leisure · <b class=\"mono\">2</b>", body)
    for key, label in (("recientes", "Recent"), ("titulo", "Title"), ("anio", "Year"),
                       ("estrellas", "Your stars")):
        assert f">{label}<" in body
    assert 'href="/ocio?orden=titulo"' in body
    assert "Recent ▾" in body


def test_the_order_comes_from_the_url(cfg, client):
    put(cfg, 1, "Brazil"), put(cfg, 2, "Alien")
    body = client.get("/ocio?orden=titulo").text
    assert body.index(">Alien<") < body.index(">Brazil<")
    assert "Title ▾" in body


def test_a_poster_with_a_cover_and_its_chips(cfg, client):
    cfg.attachments_dir.mkdir(parents=True, exist_ok=True)      # a cover is drawn if its file is there
    (cfg.attachments_dir / "a.jpg").write_bytes(b"\xff\xd8\xff")
    note = put(cfg, 1, "Alien", cover="../attachments/a.jpg", state="done", score=4,
               published="1979-05-25", rating="8.5")
    item = grid(client.get("/ocio").text)
    assert f'<img src="/cover/{note.id}"' in item
    assert '<span class="chip kind">Movie</span>' in item
    assert '<span class="chip state"' in item and "Watched" in item
    assert "1979" in item and "IMDb 8.5" in item
    assert item.count('class="star on"') == 4


def test_a_poster_without_a_cover_is_the_gradient_with_the_title(cfg, client):
    """Review Focus 5: no <img>, no /cover request."""
    note = put(cfg, 1, "Alien")
    item = grid(client.get("/ocio").text)
    assert "<img" not in item and "/cover/" not in item
    assert "linear-gradient(160deg, oklch(0.42 0.06 300), oklch(0.18 0.03 300))" in item
    assert '<span class="fill-title" dir="auto">Alien</span>' in item


def test_a_kind_nobody_knows_gets_the_neutral_fill(cfg, client):
    """Review Focus 5: a hand-edited type."""
    put(cfg, 1, "Raro", kind="podcast")
    item = grid(client.get("/ocio").text)
    assert "linear-gradient(160deg, #2a2c34, #17181d)" in item
    assert '<span class="chip kind">' not in item


def test_no_state_no_state_chip(cfg, client):
    put(cfg, 1, "Alien")
    assert '<span class="chip state"' not in grid(client.get("/ocio").text)


def test_the_first_card_is_selected_and_an_unknown_sel_too(cfg, client):
    put(cfg, 1, "Alien"), put(cfg, 2, "Brazil")
    for query in ("", "?sel=nope"):
        body = client.get("/ocio" + query).text
        assert re.search(r'<li class="item poster on" id="card-c00000000002"', body)


def test_the_sidebar_has_type_and_state(cfg, client):
    put(cfg, 1, "Alien"), put(cfg, 2, "Dune", kind="book", category="Libros", state="doing")
    body = client.get("/ocio?tipo=book").text
    side = body[body.index('<aside class="sidebar"'):body.index("</aside>")]
    assert "TYPE" in side and "STATE" in side
    assert ">Movies<" in side and ">Books<" in side and ">Series<" not in side
    assert ">To read<" in side and ">Reading<" in side and ">To watch<" not in side


def test_kind_and_state_filter_the_grid(cfg, client):
    put(cfg, 1, "Alien", state="done"), put(cfg, 2, "Dune", kind="book", category="Libros")
    assert ">Dune<" not in client.get("/ocio?tipo=movie").text
    assert ">Dune<" not in client.get("/ocio?estado=done").text


def test_unknown_filters_show_everything(cfg, client):
    put(cfg, 1, "Alien")
    for query in ("?tipo=podcast", "?estado=dropped", "?orden=x"):
        assert ">Alien<" in client.get("/ocio" + query).text


def test_the_search_reads_title_author_and_tags(cfg, client):
    put(cfg, 1, "Dune", kind="book", category="Libros", author="Frank Herbert")
    put(cfg, 2, "Alien")
    column = client.get("/ocio/lista?q=herbert").text
    assert "<html" not in column and ">Dune<" in column and ">Alien<" not in column


def test_the_column_alone_comes_in_chunks(cfg, client):
    for n in range(1, 63):
        put(cfg, n, f"Película {n}", saved=f"2026-{1 + n // 28:02d}-{n % 28 + 1:02d}")
    body = client.get("/ocio").text
    assert grid(body).count('class="item poster') == 60
    assert 'data-more="/ocio/lista?desde=60"' in body
    assert client.get("/ocio/lista?desde=60").text.count('class="item poster') == 2


def test_the_unrewritten_notice_only_when_there_are_some(cfg, client):
    put(cfg, 1, "Alien")
    assert "not rewritten" not in client.get("/ocio").text
    put(cfg, 2, "Brazil", engine="")
    put(cfg, 3, "Cube", engine="")
    body = client.get("/ocio").text
    assert "2 cards not rewritten" in body
    assert 'action="/ocio/reescribir"' in body and ">Rewrite<" in body


def test_one_unrewritten_card_is_said_in_the_singular(cfg, client):
    put(cfg, 1, "Alien", engine="")
    assert "1 card not rewritten" in client.get("/ocio").text


def test_while_they_are_rewritten_the_notice_says_so(cfg, client):
    put(cfg, 1, "Alien", engine="")
    app = create_app(cfg)
    app.state.rewriting.start("c00000000001", "describe")
    body = TestClient(app).get("/ocio").text
    assert "Rewriting…" in body and 'action="/ocio/reescribir"' not in body


def test_an_empty_shelf_says_how_to_start(client):
    assert "Nothing in Leisure yet" in client.get("/ocio").text


def test_the_old_fragment_and_popup_are_gone(cfg, client):
    put(cfg, 1, "Alien")
    assert client.get("/embed/c00000000001").status_code == 404
    assert client.get("/static/popup.js").status_code == 404


# Moved unchanged from test_web_ocio_page.py (its page tests read the old
# ocio.html and are replaced above); the fixtures they need come with them.

def _terminator() -> Note:
    return Note(id=f"{abs(hash('The Terminator')):012d}"[:12],
                url="https://imdb.com/title/The Terminator", title="The Terminator",
                category="Películas", tags=["ciencia-ficcion"], type="movie",
                source="imdb.com", saved="2026-10-11", summary="Algo pasa.",
                length="108 min", rating="8.1")


@pytest.fixture
def a_card_in_the_shelf(cfg):
    note = _terminator()
    note.published = "1984-10-26"
    write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ocio))
    return note


@pytest.fixture
def a_link_in_the_library(cfg):
    note = Note(id="bbbbbbbbbbbb", url="https://wireguard.com", title="WireGuard",
                category="Redes", tags=[], type="article", source="wireguard.com",
                saved="2026-10-10", summary="Una vpn.")
    write_note(cfg, note, "es")
    return note


def test_the_nav_has_the_section(client):
    assert '/ocio"' in client.get("/").text


def test_the_library_does_not_show_the_cards(client, a_card_in_the_shelf):
    assert "The Terminator" not in client.get("/").text


def test_a_link_never_offers_it(client, a_link_in_the_library):
    assert "/describe" not in client.get(f"/item/{a_link_in_the_library.id}").text


def side_groups(html):
    """The sidebar's filter groups, as drawn."""
    return re.findall(r'<nav class="group".*?</nav>', html, re.S)


def test_the_column_brings_the_sidebar_of_its_filter(cfg, client):
    """Final review I-1: a filter changed without a reload redraws TIPO and
    ESTADO from the column's answer, the same as a full page load draws them."""
    put(cfg, 1, "Alien"), put(cfg, 2, "Dune", kind="book", category="Libros")
    column = client.get("/ocio/lista?tipo=book").text
    fresh = column[column.index('<template id="side-filters">'):column.index("</template>")]
    assert ">To read<" in fresh and ">Reading<" in fresh and ">To watch<" not in fresh
    # ESTADO keeps the kind, and the kind is the row lit.
    assert re.search(r'href="/ocio\?tipo=book&(amp;)?estado=pending"', fresh)
    assert re.search(r'class="filter on"><i[^>]*></i><span>Books<', fresh)
    page = client.get("/ocio?tipo=book").text
    side = page[page.index('<aside class="sidebar"'):page.index("</aside>")]
    assert side_groups(fresh) == side_groups(side) and len(side_groups(fresh)) == 2


def test_both_filters_stay_in_the_column_sidebar(cfg, client):
    put(cfg, 1, "Alien"), put(cfg, 2, "Dune", kind="book", category="Libros")
    column = client.get("/ocio/lista?tipo=book&estado=pending").text
    fresh = column[column.index('<template id="side-filters">'):column.index("</template>")]
    # TIPO keeps the state, as card_filters writes it; both rows are lit.
    assert re.search(r'href="/ocio\?tipo=movie&(amp;)?estado=pending"', fresh)
    assert re.search(r'class="filter on"><i[^>]*></i><span>Books<', fresh)
    assert re.search(r'class="filter on"><i[^>]*></i><span>To read<', fresh)


def test_more_of_the_column_does_not_bring_the_sidebar(cfg, client):
    put(cfg, 1, "Alien")
    assert "side-filters" not in client.get("/ocio/lista?desde=60").text


def test_the_page_draws_the_groups_once(cfg, client):
    put(cfg, 1, "Alien")
    assert "side-filters" not in client.get("/ocio").text


# --- polish (docs/2026-10-14-rediseno-ocio-ideas-pendientes.md, Ocio) -------------------

def test_the_state_chip_is_text_only(cfg, client):
    put(cfg, 1, "Alien", state="done")
    chip = re.search(r'<span class="chip state"[^>]*>(.*?)</span>', grid(client.get("/ocio").text)).group(1)
    assert chip == "Watched"


def test_under_the_poster_year_the_stars_given_and_the_rating(cfg, client):
    put(cfg, 1, "Alien", score=3, published="1979-05-25", rating="8.5")
    meta = re.search(r'<span class="meta">(.*?)</span>\s*</a>', grid(client.get("/ocio").text),
                     re.S).group(1)
    assert meta.index("1979") < meta.index("stars-shown") < meta.index("IMDb 8.5")
    # As the design: the stars given, not five with the rest dimmed.
    assert meta.count('class="star on"') == 3 and 'class="star"' not in meta
    assert '<span class="rating">IMDb 8.5</span>' in meta


def test_only_the_parts_that_exist_are_under_the_poster(cfg, client):
    put(cfg, 1, "Alien", score=0, published=None, rating="")
    meta = re.search(r'<span class="meta">(.*?)</span>\s*</a>', grid(client.get("/ocio").text),
                     re.S).group(1)
    assert meta.strip() == ""


def test_a_cover_whose_file_is_missing_is_the_gradient_with_the_title(cfg, client):
    put(cfg, 1, "Alien", cover="../attachments/gone.jpg")
    item = grid(client.get("/ocio").text)
    assert "<img" not in item
    assert '<span class="fill-title" dir="auto">Alien</span>' in item


def test_a_cover_whose_file_is_there_is_drawn(cfg, client):
    cfg.attachments_dir.mkdir(parents=True, exist_ok=True)
    (cfg.attachments_dir / "a.jpg").write_bytes(b"\xff\xd8\xff")
    note = put(cfg, 1, "Alien", cover="../attachments/a.jpg")
    item = grid(client.get("/ocio").text)
    assert f'<img src="/cover/{note.id}"' in item and "fill-title" not in item


def test_each_group_names_the_parameter_it_changes(cfg, client):
    """shell.js changes only that parameter over the newest list, so a click
    on ESTADO right after one on TIPO keeps the TIPO (polish)."""
    put(cfg, 1, "Alien")
    body = client.get("/ocio").text
    assert body.count('<nav class="group" data-apart data-param="tipo"') == 1
    assert body.count('<nav class="group" data-apart data-param="estado"') == 1
    assert body.count('class="chip-group" data-apart data-param="tipo"') == 1
    assert body.count('class="chip-group" data-apart data-param="estado"') == 1
    column = client.get("/ocio/lista").text
    assert 'data-apart data-param="tipo"' in column and 'data-apart data-param="estado"' in column


@pytest.mark.parametrize("state, color", [("done", "#8fc29a"), ("doing", "#a9b4de"),
                                          ("pending", "#c9cbd1")])
def test_the_state_chip_text_takes_the_state_s_colour(cfg, client, state, color):
    """Review M-3: Ocio.dc.html's statusColor, on the text."""
    put(cfg, 1, "Alien", state=state)
    assert f'<span class="chip state" style="color: {color}">' in grid(client.get("/ocio").text)
