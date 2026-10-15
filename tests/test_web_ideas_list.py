"""/ideas (spec §2): the sidebar, a field, and the ideas at full width."""

import re

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.vault import note_path, rebuild_indexes, write_note
from oknowledge.web.app import create_app


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


def put(cfg, n, state="pending", title=None, text=None, related=(), day=None):
    day = day or n
    note = new_idea(text or f"Texto de la idea {n}.", f"Idea {n}" if title is None else title,
                    f"2026-10-{day:02d}", f"2026-10-{day:02d}T00:00:00.{n:06d}+00:00")
    note.state, note.related = state, list(related)
    write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ideas))
    return note


def test_two_columns_and_no_panel(cfg, client):
    put(cfg, 1)
    body = client.get("/ideas").text
    assert '<div class="app idea-shelf">' in body
    assert 'id="list"' in body and 'data-source="/ideas/lista"' in body
    assert 'id="panel"' not in body
    assert '<script src="/static/shell.js" defer></script>' in body


def test_the_field_searches_and_offers_a_new_idea(cfg, client):
    body = client.get("/ideas").text
    form = re.search(r'<form[^>]*id="unified"[^>]*>', body).group(0)
    assert 'action="/ideas"' in form and 'data-mode="ideas"' in form
    assert 'placeholder="Search your ideas"' in body
    button = re.search(r'<button[^>]*id="save-link"[^>]*>(.*?)</button>', body, re.S)
    assert 'formaction="/ideas/guardar"' in button.group(0) and 'New idea<span class="enter-hint" aria-hidden="true">&nbsp;↵</span>' in button.group(1)


def test_with_text_in_the_field_the_new_idea_button_shows(cfg, client):
    assert re.search(r'class="unified saving"', client.get("/ideas?q=vpn").text)


def test_the_head_counts_and_switches_layout(cfg, client):
    put(cfg, 1), put(cfg, 2)
    body = client.get("/ideas").text
    assert re.search(r"Ideas · <b class=\"mono\">2</b>", body)
    assert 'data-view="lista"' in body and 'data-view="tarjetas"' in body


def test_a_card_is_title_text_state_and_links(cfg, client):
    note = put(cfg, 1, state="doing", related=["a", "b"])
    body = client.get("/ideas").text
    card = re.search(rf'<li class="item idea" id="idea-{note.id}">.*?</li>', body, re.S).group(0)
    assert f'href="/ideas/{note.id}"' in card
    assert ">Idea 1<" in card and "Texto de la idea 1." in card
    assert "under way · 2 links" in card
    assert 'style="background: #a9b4de"' in card


def test_one_link_is_said_in_the_singular(cfg, client):
    put(cfg, 1, related=["a"])
    assert "seed · 1 link<" in client.get("/ideas").text


def test_the_card_opens_the_screen_with_the_way_back(cfg, client):
    note = put(cfg, 1, state="doing")
    assert f'href="/ideas/{note.id}?back=%2Fideas%3Festado%3Ddoing"' in client.get("/ideas?estado=doing").text


def test_an_untitled_idea_is_never_an_empty_link(cfg, client):
    put(cfg, 1, title="")
    assert ">Untitled idea<" in client.get("/ideas").text


def test_the_list_layout_is_rows(cfg, client):
    put(cfg, 1)
    assert 'class="items rows"' in client.get("/ideas?vista=lista").text


def test_the_sidebar_has_the_state_group(cfg, client):
    put(cfg, 1), put(cfg, 2, "dropped")
    body = client.get("/ideas").text
    side = body[body.index('<aside class="sidebar"'):body.index("</aside>")]
    assert "STATE" in side
    assert re.search(r'href="/ideas"[^>]*class="filter on"[^>]*>.*?All.*?<b class="count mono">1</b>',
                     side, re.S)
    assert 'href="/ideas?estado=dropped"' in side


def test_dropped_ideas_are_out_of_all_and_in_their_state(cfg, client):
    put(cfg, 1, "dropped", title="Descartada")
    assert ">Descartada<" not in client.get("/ideas").text
    assert ">Descartada<" in client.get("/ideas?estado=dropped").text


def test_an_unknown_state_is_all(cfg, client):
    put(cfg, 1)
    assert ">Idea 1<" in client.get("/ideas?estado=archived").text


def test_a_state_typed_by_hand_does_not_break_it(cfg, client):
    put(cfg, 1, state="whatever")
    assert client.get("/ideas").status_code == 200


def test_the_column_alone_for_the_live_search(cfg, client):
    put(cfg, 1, title="VPN casera"), put(cfg, 2, title="Pan")
    column = client.get("/ideas/lista?q=vpn").text
    assert "<html" not in column and ">VPN casera<" in column and ">Pan<" not in column


def test_more_comes_in_chunks(cfg, client):
    for n in range(1, 63):
        put(cfg, n, day=n % 28 + 1)
    body = client.get("/ideas").text
    assert body.count('class="item idea"') == 60
    assert 'data-more="/ideas/lista?desde=60"' in body
    rest = client.get("/ideas/lista?desde=60").text
    assert rest.count('class="item idea"') == 2


def test_nothing_yet_says_where_to_start(client):
    assert "No ideas yet" in client.get("/ideas").text


def test_a_search_that_finds_nothing_says_so(cfg, client):
    put(cfg, 1)
    assert "No idea matches “zzz”" in client.get("/ideas?q=zzz").text


def test_new_idea_takes_the_field_and_opens_the_screen(cfg, client, monkeypatch):
    monkeypatch.setattr("oknowledge.web.app.complete_idea", lambda cfg, idea, trace=None: True)
    answer = client.post("/ideas/guardar", data={"q": "una vpn para la familia"},
                         follow_redirects=False)
    assert re.fullmatch(r"/ideas/[0-9a-f]{12}\?notice=completing", answer.headers["location"])


def test_the_screen_route_is_not_shadowed(cfg, client):
    assert client.get("/ideas/lista").status_code == 200


def test_the_state_group_names_the_parameter_it_changes(client):
    body = client.get("/ideas").text
    assert '<nav class="group" data-apart data-param="estado"' in body
