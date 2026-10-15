"""The column of links beside an idea (spec §2): the linked ones, the ones
that may help, and a search over the whole library."""

import re

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.model import Note
from oknowledge.vault import note_path, rebuild_indexes, write_note
from oknowledge.web.app import create_app


@pytest.fixture
def cfg(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    config = Config(vault=vault)
    rebuild_indexes(config, "es")
    return config


def a_link(cfg, n, title, summary="Una vpn.", tags=("vpn",), category="Redes"):
    stem = write_note(cfg, Note(id=f"l{n:011d}", url=f"https://e{n}.com/x", title=title,
                                category=category, tags=list(tags), type="article",
                                source=f"e{n}.com", saved=f"2026-10-{n:02d}",
                                summary=summary), "es").stem
    rebuild_indexes(cfg, "es")
    return stem


def an_idea(cfg, related=(), text="Una vpn para la familia.", tags=("vpn",)):
    note = new_idea(text, "VPN familiar", "2026-10-12", "2026-10-12T00:00:00.000001+00:00")
    note.related, note.tags = list(related), list(tags)
    write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ideas))
    return note


def column(cfg, idea, query=""):
    body = TestClient(create_app(cfg)).get(f"/ideas/{idea.id}{query}").text
    head = body.index('<aside class="links-column"')
    return body[head:body.index("</aside>", head)]


def test_the_head_counts_the_linked_links(cfg):
    stem = a_link(cfg, 1, "WireGuard")
    aside = column(cfg, an_idea(cfg, related=[stem]))
    assert "Links of this idea" in aside
    assert '<b class="mono" id="idea-links-count">1</b>' in aside


def test_the_search_box_counts_the_library(cfg):
    a_link(cfg, 1, "WireGuard")
    a_link(cfg, 2, "Tailscale")
    box = re.search(r'<input[^>]*id="links-q"[^>]*>', column(cfg, an_idea(cfg))).group(0)
    assert 'placeholder="Search your 2 links to add"' in box
    assert 'data-results="/item/' in box and 'name="q"' in box


def test_a_linked_link_is_a_row_that_opens_in_the_library(cfg):
    stem = a_link(cfg, 1, "WireGuard", category="Redes")
    idea = an_idea(cfg, related=[stem])
    aside = column(cfg, idea)
    linked = aside[aside.index("LINKED"):]
    assert '<a href="/?sel=l00000000001"' in linked and ">WireGuard</a>" in linked
    assert "e1.com" in linked
    assert 'style="background: oklch(' in linked
    drop = re.search(rf'<form[^>]*action="/item/{idea.id}/related/drop"[^>]*>', linked).group(0)
    assert "data-json" in drop and "data-links" in drop
    assert f'name="stem" value="{stem}"' in linked


def test_a_gone_link_is_dimmed_and_can_still_go(cfg):
    idea = an_idea(cfg, related=["2026-01-01-borrada"])
    aside = column(cfg, idea)
    assert 'class="row gone"' in aside and "2026-01-01-borrada" in aside
    assert 'name="stem" value="2026-01-01-borrada"' in aside


def test_no_linked_links_yet(cfg):
    assert "No linked links yet" in column(cfg, an_idea(cfg))


def test_links_in_common_may_help_with_an_add_button(cfg):
    a_link(cfg, 1, "Montar una vpn casera", tags=("vpn",))
    a_link(cfg, 2, "Recetas de pan", summary="Harina.", tags=("cocina",), category="Cocina")
    idea = an_idea(cfg)
    aside = column(cfg, idea)
    serve = aside[aside.index("MAY HELP"):]
    assert "Montar una vpn casera" in serve and "Recetas de pan" not in serve
    add = re.search(r'<form[^>]*action="/item/l00000000001/ideas"[^>]*>', serve).group(0)
    assert "data-json" in add and "data-links" in add
    assert f'name="idea" value="{idea.id}"' in serve and 'name="back" value="idea"' in serve
    assert "+ Add" in serve


def test_a_linked_link_is_not_offered_again(cfg):
    stem = a_link(cfg, 1, "Montar una vpn casera")
    aside = column(cfg, an_idea(cfg, related=[stem]))
    assert aside.count("Montar una vpn casera") == 1


def test_nothing_in_common(cfg):
    a_link(cfg, 1, "Recetas de pan", summary="Harina.", tags=("cocina",))
    assert "Nothing in common yet" in column(cfg, an_idea(cfg))


def test_a_search_replaces_may_help_with_results(cfg):
    a_link(cfg, 1, "Recetas de pan", summary="Harina.", tags=("cocina",))
    aside = column(cfg, an_idea(cfg), "?q=pan")
    assert "RESULTS" in aside and "MAY HELP" not in aside
    assert "Recetas de pan" in aside
    assert 'name="q" value="pan"' in aside


def test_a_search_that_finds_nothing_says_so(cfg):
    a_link(cfg, 1, "VPN")
    assert "Nothing matches" in column(cfg, an_idea(cfg), "?q=zzzz")


def test_adding_and_removing_come_back_to_the_screen(cfg):
    stem = a_link(cfg, 1, "WireGuard")
    idea = an_idea(cfg)
    client = TestClient(create_app(cfg))
    joined = client.post("/item/l00000000001/ideas",
                         data={"idea": idea.id, "back": "idea", "q": "wire"},
                         follow_redirects=False)
    assert joined.headers["location"] == f"/ideas/{idea.id}?q=wire&notice=saved"
    left = client.post(f"/item/{idea.id}/related/drop", data={"stem": stem},
                       follow_redirects=False)
    assert left.headers["location"] == f"/ideas/{idea.id}?notice=saved"


def test_adding_by_script_answers_json(cfg):
    a_link(cfg, 1, "WireGuard")
    idea = an_idea(cfg)
    reply = TestClient(create_app(cfg)).post(
        "/item/l00000000001/ideas", data={"idea": idea.id, "back": "idea"},
        headers={"Accept": "application/json"})
    assert reply.json()["ok"] is True


# --- polish (docs/2026-10-14-rediseno-ocio-ideas-pendientes.md, Ideas) ------------------

def row_of(aside, title):
    head = aside.rindex('<li class="row', 0, aside.index(title))
    return aside[head:aside.index("</li>", head)]


def test_a_row_that_may_help_has_its_category_dot(cfg):
    from oknowledge.web.app import dot
    a_link(cfg, 1, "Montar una vpn casera", tags=("vpn",))
    row = row_of(column(cfg, an_idea(cfg)), "Montar una vpn casera")
    assert f'<span class="dot" style="background: {dot("Redes")}"></span>' in row


def test_a_result_row_has_its_category_dot(cfg):
    from oknowledge.web.app import dot
    a_link(cfg, 1, "Recetas de pan", summary="Harina.", tags=("cocina",), category="Cocina")
    row = row_of(column(cfg, an_idea(cfg), "?q=pan"), "Recetas de pan")
    assert f'<span class="dot" style="background: {dot("Cocina")}"></span>' in row
