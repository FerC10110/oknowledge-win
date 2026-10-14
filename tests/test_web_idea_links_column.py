"""The idea's column: its links as cards, a box to use each, and the search."""

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.model import Note
from oknowledge.vault import note_path, rebuild_indexes, write_note
from oknowledge.web.app import create_app


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


def a_link(cfg, n, title, summary="Una vpn."):
    return write_note(cfg, Note(id=f"l{n:011d}", url=f"https://e.com/{n}", title=title,
                                category="Redes", tags=["vpn"], type="article",
                                source="e.com", saved="2026-10-10", summary=summary),
                      "es").stem


def an_idea(cfg, related=()):
    note = new_idea("x", "VPN propia", "2026-10-12", "2026-10-12T00:00:00.000001+00:00")
    note.related = list(related)
    write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ideas))
    return note


def page_of(cfg, idea, **params):
    return TestClient(create_app(cfg)).get(f"/item/{idea.id}", params=params).text


def test_the_linked_links_are_cards_in_the_aside(cfg):
    stem = a_link(cfg, 1, "WireGuard")
    text = page_of(cfg, an_idea(cfg, related=[stem]))
    aside = text[text.index('<aside class="idea-links"'):text.index("</aside>")]
    assert 'class="card"' in aside and "WireGuard" in aside
    assert f'name="use" value="{stem}" form="act-think" checked' in aside
    assert '/related/drop' in aside
    assert aside.index("WireGuard") < aside.index('id="field-find"')


def test_the_general_box_only_with_links(cfg):
    stem = a_link(cfg, 1, "WireGuard")
    assert 'name="with_links"' in page_of(cfg, an_idea(cfg, related=[stem]))
    assert 'name="with_links"' not in page_of(cfg, an_idea(cfg))


def test_improve_and_expand_share_one_form(cfg):
    text = page_of(cfg, an_idea(cfg))
    assert '<form id="act-think"' in text
    for action in ("improve", "expand"):
        assert f'formaction="/item/' in text and f'/actions/{action}"' in text
    assert 'id="act-improve"' not in text and 'id="act-expand"' not in text


def test_a_gone_link_is_a_dimmed_card_you_can_remove(cfg):
    text = page_of(cfg, an_idea(cfg, related=["2026-01-01-borrado"]))
    assert 'class="card gone"' in text and "2026-01-01-borrado" in text
    assert 'name="with_links"' not in text


def test_no_links_yet(cfg):
    text = page_of(cfg, an_idea(cfg))
    assert "None yet" in text and 'id="field-find"' in text


def test_the_page_is_wide_and_loads_its_scripts(cfg):
    text = page_of(cfg, an_idea(cfg))
    assert '<body class="wide' in text
    assert "/static/popup.js" in text and "/static/idea-links.js" in text


def test_the_count_of_links(cfg):
    stem = a_link(cfg, 1, "WireGuard")
    assert "1/16" in page_of(cfg, an_idea(cfg, related=[stem]))
