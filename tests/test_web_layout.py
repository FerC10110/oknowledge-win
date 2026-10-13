"""The pages at phone width: what has to be in the HTML and the CSS for it."""

import re

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.vault import rebuild_indexes, write_note
from oknowledge.web.app import WEB, create_app

LINK = "aaaaaaaaaaaa"


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
    write_note(config, Note(id=LINK, url="https://wireguard.com", title="WireGuard",
                            category="Redes", tags=["vpn"], type="article",
                            source="wireguard.com", saved="2026-10-10",
                            summary="Una vpn."), "es")
    rebuild_indexes(config, "es")
    return config


@pytest.fixture
def client(cfg):
    return TestClient(create_app(cfg))


def css():
    return WEB.joinpath("static", "style.css").read_text(encoding="utf-8")


# --- the header -------------------------------------------------------------

def test_the_paste_box_folds_into_a_plus(client):
    body = client.get("/").text
    assert re.search(r'<details class="paste" open>\s*<summary[^>]*>＋</summary>', body)
    assert 'action="/add"' in body


def test_saving_everything_is_called_complete_not_all():
    from oknowledge.i18n import STRINGS
    assert STRINGS["es"]["Full"] == "Completo"


def test_every_page_loads_the_layout_script(client):
    assert '<script src="/static/layout.js"></script>' in client.get("/").text


def test_the_layout_script_closes_and_unfocuses_on_a_phone():
    js = WEB.joinpath("static", "layout.js").read_text(encoding="utf-8")
    assert "(max-width: 42rem)" in js
    assert "details.filters" in js and "details.paste" in js and "blur" in js


# --- the filters ------------------------------------------------------------

def filters_summary(body):
    return re.search(r'<details class="filters" open>\s*<summary[^>]*>(.*?)</summary>',
                     body, re.S)


@pytest.mark.parametrize("path", ["/", "/ocio", "/ideas"])
def test_the_filters_fold_into_one_line(client, path):
    assert filters_summary(client.get(path).text)


def test_the_summary_says_what_is_on(client):
    assert "Redes" in filters_summary(client.get("/?category=Redes").text).group(1)


def test_the_summary_says_all_when_nothing_is_on(client):
    assert "All" in filters_summary(client.get("/").text).group(1)


def test_select_moved_into_the_summary(client):
    assert "pick-mode" in filters_summary(client.get("/").text).group(1)


# --- the strip of time and the cards ----------------------------------------

def timeline(body):
    return re.search(r'<nav class="timeline".*?</nav>', body, re.S).group(0)


def test_a_break_comes_before_the_first_month_only(client):
    nav = timeline(client.get("/?when=2026").text)
    assert nav.count('<i class="break"') == 1
    assert nav.index('<i class="break"') < nav.index('class="month')


def test_no_year_open_no_break(client):
    assert '<i class="break"' not in timeline(client.get("/").text)


def test_the_phone_css_puts_the_months_on_their_own_row():
    assert ".timeline .break" in css() and "order: 1" in css()
    assert "-webkit-line-clamp: 4" in css()


def test_while_picking_the_mark_gives_its_corner_to_the_checkbox():
    assert re.search(r"body\.picking \.card > \.mark\s*\{\s*display: none", css())


# --- the categories page ----------------------------------------------------

def test_categories_are_a_grid_not_rows(client):
    body = client.get("/categories").text
    assert '<ul class="cat-grid">' in body and 'class="hits"' not in body


def test_each_category_renames_from_its_own_card(client):
    body = client.get("/categories").text
    card = re.search(r'<li class="cat-card">.*?</li>', body, re.S).group(0)
    assert 'href="/?category=Redes"' in card
    assert re.search(r"<details>\s*<summary[^>]*>✎</summary>", card)
    assert 'name="old" value="Redes"' in card and 'list="known"' in card


# --- touch, focus, notices --------------------------------------------------

def test_on_a_touch_screen_the_actions_are_always_there():
    assert re.search(r"@media \(hover: none\)\s*\{\s*\.actions\s*\{\s*opacity: 1", css())


def test_focus_is_always_visible():
    assert ":focus-visible" in css() and "outline: 2px solid var(--focus)" in css()
    assert css().count("--focus:") >= 2                       # light and dark


def test_the_unreadable_notice_keeps_the_path_out_of_sight(client, cfg):
    (cfg.links_dir / "roto.md").write_text("---\noknowledge: 1\n---\n", encoding="utf-8")
    body = client.get("/").text
    notice = re.search(r'<p class="quiet"[^>]*>(.*?)</p>', body, re.S)
    assert "could not be read" in notice.group(1)
    assert str(cfg.links_dir) not in notice.group(1)
    assert f'title="{cfg.links_dir}"' in notice.group(0)


def test_each_engine_is_one_compact_row(client):
    body = client.get("/settings").text
    assert body.count('class="row engine-row"') == 3


def test_a_card_title_leaves_room_for_the_mark_in_its_corner():
    assert re.search(r"\.card h2 \{[^}]*padding-right: 2\.4rem", css())


def test_an_empty_mark_draws_no_circle_until_it_is_opened():
    assert re.search(r"\.card > \.mark:not\(\[open\]\) > summary \{[^}]*border-color: transparent",
                     css())


def test_on_a_phone_an_empty_mark_still_shows_its_plus():
    assert re.search(r"\(max-width: 42rem\)\s*\{\s*\.card > \.mark:not\(\[open\]\) \.none"
                     r"\s*\{\s*opacity: 0\.6", css())


def test_the_search_box_is_let_go_after_the_browser_focuses_it():
    js = WEB.joinpath("static", "layout.js").read_text(encoding="utf-8")
    assert 'addEventListener("load"' in js


def test_a_focus_nobody_asked_for_is_dropped_but_a_tap_is_not():
    js = WEB.joinpath("static", "layout.js").read_text(encoding="utf-8")
    assert '"pointerdown"' in js and '"focus"' in js
