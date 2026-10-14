"""The detail panel of a link: read, and edit in place."""

import re

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.model import Mention, Note
from oknowledge.vault import note_path, rebuild_indexes, write_note
from oknowledge.web.app import create_app


def note(id, title="WireGuard simple", **extra):
    base = dict(id=id, url=f"https://wireguard.com/{id}", title=title, category="Redes",
                tags=["vpn", "redes"], type="article", source="wireguard.com",
                saved="2026-10-04", summary="Uno dos tres.\n\nCuatro cinco.",
                points=["Rápido", "Simple", "Seguro"], collections=["Casa conectada"])
    base.update(extra)
    return Note(**base)


@pytest.fixture
def cfg(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    write_note(cfg, note("a1", mark="⭐",
                         mentions=[Mention(name="Pi-hole", url="https://pi-hole.net")]), "es")
    write_note(cfg, note("b2", title="Masa madre", mark="", collections=[]), "es")
    rebuild_indexes(cfg, "es")
    return cfg


@pytest.fixture
def client(cfg):
    return TestClient(create_app(cfg))


def panel(client, id, query=""):
    answer = client.get(f"/panel/{id}{query}")
    assert answer.status_code == 200
    return answer.text


def test_the_panel_is_a_fragment(client):
    body = panel(client, "a1")
    assert "<html" not in body
    assert '<h1 dir="auto">WireGuard simple</h1>' in body


def test_an_unknown_link_has_no_panel(client):
    assert client.get("/panel/nope").status_code == 404


def test_the_home_draws_the_selected_panel(client):
    body = client.get("/?sel=b2").text
    assert '<h1 dir="auto">Masa madre</h1>' in body


def test_the_meta_row_has_the_category_chip_with_its_menu(client):
    body = panel(client, "a1")
    chip = re.search(r'<details class="menu chip-menu">.*?</details>', body, re.S).group(0)
    assert "Redes" in chip and "oklch(0.74 0.09 265)" in chip
    assert 'action="/item/a1/category"' in chip and "data-inline" in chip
    assert 'name="category" value="Redes"' in chip
    assert "wireguard.com · 4 Oct" in body


def test_summary_in_paragraphs_with_reading_time(client):
    body = panel(client, "a1")
    assert '<p class="body" dir="auto">Uno dos tres.</p>' in body
    assert '<p class="body" dir="auto">Cuatro cinco.</p>' in body
    assert "1 min read of the summary" in body


def test_the_points_box(client):
    body = panel(client, "a1")
    box = re.search(r'<section class="points">.*?</section>', body, re.S).group(0)
    assert "IN THREE LINES" in box
    assert box.count("<li") == 3


def test_mentions_and_collections_keep_their_x(client):
    body = panel(client, "a1")
    assert "Pi-hole" in body and 'action="/item/a1/mentions/delete"' in body
    assert re.search(r'action="/item/a1/collections".*?name="drop" value="Casa conectada"', body, re.S)


def test_tags_are_links_with_an_x_and_a_box_to_add(client):
    body = panel(client, "a1", "?cat=Redes")
    assert 'href="/?tag=vpn"' in body
    assert re.search(r'name="tags" value="redes"', body)          # x on vpn leaves redes
    assert 'name="add"' in body and "+ tag" in body


def test_adding_a_tag_keeps_the_others(client, cfg):
    client.post("/item/b2/tags", data={"tags": "vpn redes", "add": "nuevo"})
    assert "#nuevo" in panel(client, "b2")
    assert "#vpn" in panel(client, "b2")


def test_the_star_toggles_the_favourite_mark(client):
    on = re.search(r'<form[^>]*action="/item/a1/mark".*?</form>', panel(client, "a1"), re.S).group(0)
    assert 'name="mark" value=""' in on and "star on" in on
    off = re.search(r'<form[^>]*action="/item/b2/mark".*?</form>', panel(client, "b2"), re.S).group(0)
    assert 'name="mark" value="⭐"' in off


def test_the_more_menu(client):
    body = panel(client, "a1")
    more = re.search(r'<details class="menu up more">.*?</details>', body, re.S).group(0)
    assert more.count('action="/item/a1/mark"') == 1 and "🔥" in more
    assert 'action="/item/a1/collections"' in more and 'name="add"' in more
    assert 'action="/item/a1/reprocess"' in more
    assert 'action="/item/a1/delete"' in more


def test_to_an_idea_only_with_ideas(client, cfg):
    assert "To an idea" not in panel(client, "a1")
    # new_idea builds the note and does not write it: the web writes it.
    idea = new_idea("texto", "VPN familiar propia", "2026-10-12", "2026-10-12T00:00:00.000001+00:00")
    write_note(cfg, idea, "es", path=note_path(cfg, idea, shelf=cfg.ideas))
    rebuild_indexes(cfg, "es", shelf=cfg.ideas)
    body = panel(client, "a1")
    assert "To an idea" in body and "VPN familiar propia" in body
    assert 'action="/item/a1/ideas"' in body


def test_the_original_opens_in_a_new_tab(client):
    assert re.search(r'<a class="btn primary" href="https://wireguard.com/a1" target="_blank"', panel(client, "a1"))


def test_the_item_page_of_a_link_is_the_home_with_it_selected(client):
    answer = client.get("/item/a1?notice=saved", follow_redirects=False)
    assert answer.status_code == 303
    assert answer.headers["location"] == "/?sel=a1&notice=saved"


def test_a_write_lands_on_the_panel_with_a_toast(client):
    body = client.post("/item/b2/category", data={"category": "Cocina"}).text
    assert '<p class="notice toast" role="status">' in body
    assert re.search(r'<li class="item on" id="card-b2"', body)


def test_the_more_menu_lists_every_mark_with_the_current_one_on(client, cfg):
    more = re.search(r'<details class="menu up more">.*?</details>', panel(client, "a1"), re.S).group(0)
    for mark in cfg.marks:
        assert f'value="{mark}"' in more
    assert re.search(r'<button name="mark" value="⭐" class="on"', more)


def test_while_the_ai_reads_it_the_panel_holds_only_the_title(client, monkeypatch):
    # The seam the queue fills in (Task 6): {id: url} of the links being read.
    monkeypatch.setattr("oknowledge.web.app.links_in_analysis",
                        lambda: {"a1": "https://wireguard.com/a1"})
    body = panel(client, "a1")
    assert '<h1 dir="auto">WireGuard simple</h1>' in body
    assert "The AI is reading the link…" in body and '<div class="skeleton">' in body
    assert 'name="add"' not in body.split('<div class="detail-bar">')[0]
    assert "#vpn" not in body and "chip-menu" not in body
    assert "Casa conectada" not in body.split('<div class="detail-bar">')[0]


def test_the_show_more_rule_does_not_reach_the_panel_menu():
    """`.more` is also the panel's ⋯ menu: the list's link rule is scoped."""
    from oknowledge.web.app import WEB
    css = WEB.joinpath("static", "app.css").read_text(encoding="utf-8")
    assert not re.search(r'(^|[\s,}])\.more\s*[,{]', css, re.M)
    assert re.search(r'^a\.more\s*\{', css, re.M)
