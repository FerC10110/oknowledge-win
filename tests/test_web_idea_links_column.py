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
    aside = text[text.index('<aside class="idea-links'):text.index("</aside>")]
    assert 'class="card"' in aside and "WireGuard" in aside
    assert f'name="use" value="{stem}" form="act-think" checked' in aside
    assert '/related/drop' in aside


def aside_of(text):
    return text[text.index('<aside class="idea-links'):text.index("</aside>")]


def test_the_aside_is_a_panel_with_two_tabs_search_first(cfg):
    stem = a_link(cfg, 1, "WireGuard")
    aside = aside_of(page_of(cfg, an_idea(cfg, related=[stem])))
    assert 'class="idea-links panel"' in aside
    assert '<input type="radio" name="idea-tab" id="tab-find" class="tab-switch" checked>' in aside
    assert '<input type="radio" name="idea-tab" id="tab-linked" class="tab-switch">' in aside
    assert '<label for="tab-find">Search</label>' in aside
    assert '<label for="tab-linked">Linked (1/16)</label>' in aside


def test_the_search_pane_holds_the_box_and_the_results(cfg):
    a_link(cfg, 1, "WireGuard")
    aside = aside_of(page_of(cfg, an_idea(cfg), q="wire"))
    pane = aside[aside.index('class="tab-pane pane-find"'):aside.index('class="tab-pane pane-linked"')]
    assert pane.index('id="field-find"') < pane.index('id="idea-found"')
    assert 'action="/item/l00000000001/ideas"' in pane


def test_the_linked_pane_holds_the_cards(cfg):
    stem = a_link(cfg, 1, "WireGuard")
    aside = aside_of(page_of(cfg, an_idea(cfg, related=[stem])))
    pane = aside[aside.index('class="tab-pane pane-linked"'):]
    assert "WireGuard" in pane and f'name="use" value="{stem}"' in pane


def test_the_tabs_switch_without_javascript():
    for selector in ("#tab-linked:checked ~ .pane-linked", "#tab-linked:checked ~ .pane-find"):
        assert css_rule(selector), selector


def test_the_panel_stays_in_view_and_scrolls_inside():
    panel = " ".join(css_rule(".item.has-aside > .mine.idea > .idea-links"))
    assert "position: sticky" in panel and "height: calc(100vh - 2rem)" in panel
    assert any("overflow-y: auto" in rule for rule in css_rule(".idea-links .tab-pane"))


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


def test_the_script_is_served(cfg):
    reply = TestClient(create_app(cfg)).get("/static/idea-links.js")
    assert reply.status_code == 200 and "dataset.results" in reply.text


def css_rule(selector):
    import re
    from oknowledge.web.app import WEB
    css = WEB.joinpath("static", "style.css").read_text(encoding="utf-8")
    return [m.group(1) for m in re.finditer(re.escape(selector) + r"\s*\{([^}]*)\}", css)]


def test_the_idea_keeps_the_spacing_of_its_section():
    """display: contents drops .mine's gap and top margin; the grid gives them back."""
    assert any("margin-top: 0.8rem" in rule
               for rule in css_rule(".item.has-aside > .mine.idea > * + *"))
    assert any("margin-top: 1.25rem" in rule for rule in css_rule(".item.has-aside > .mine.idea > form.field"))


def test_below_two_columns_the_idea_keeps_the_reading_width():
    """body.wide lifts main's limit at every width; one column must not run edge to edge."""
    assert any("max-width: var(--measure)" in rule for rule in css_rule("body.wide .item.has-aside"))
