"""Multi-selection (spec §5): a checkbox outside the link on each item that
can be ticked, and one bar per section with that section's actions."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.model import Note
from oknowledge.vault import note_path, rebuild_indexes, write_note
from oknowledge.web.app import create_app

WEB = Path(__file__).resolve().parent.parent / "src" / "oknowledge" / "web"
SELECT = WEB / "static" / "select.js"
CARD = "c00000000001"


@pytest.fixture
def client(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    for id, category in (("a1", "Redes"), ("b2", "Cocina")):
        write_note(cfg, Note(id=id, url=f"https://e.com/{id}", title=f"T {id}", category=category,
                             tags=[], type="article", source="e.com", saved="2026-10-03",
                             summary="s"), "es")
    card = Note(id=CARD, url="https://www.imdb.com/title/tt1", title="Dune", category="Películas",
                tags=[], type="movie", source="imdb.com", saved="2026-10-02", summary="s",
                engine="")
    write_note(cfg, card, "es", path=note_path(cfg, card, shelf=cfg.ocio))
    idea = new_idea("Una idea.", "VPN", "2026-10-13", "2026-10-13T00:00:00.000001+00:00")
    write_note(cfg, idea, "es", path=note_path(cfg, idea, shelf=cfg.ideas))
    for shelf in (cfg.links, cfg.ocio, cfg.ideas):
        rebuild_indexes(cfg, "es", shelf=shelf)
    client = TestClient(create_app(cfg))
    client.idea = idea.id
    return client


def bar(body):
    return re.search(r'<form id="bulk".*?</form>', body, re.S).group(0)


def between(text, start, end):
    head = text.index(start)
    return text[head:text.index(end, head)]


# --- checkboxes ----------------------------------------------------------------------

@pytest.mark.parametrize("path, id, title", [("/", "a1", "T a1"), ("/?vista=lista", "a1", "T a1"),
                                             ("/ocio", CARD, "Dune"), ("/ideas", "idea", "VPN"),
                                             ("/ideas?vista=lista", "idea", "VPN")])
def test_each_item_has_its_checkbox_outside_the_link(client, path, id, title):
    id = client.idea if id == "idea" else id
    body = client.get(path).text
    item = re.search(rf'<li class="item[^"]*" id="(?:card|idea)-{id}".*?</li>', body, re.S).group(0)
    check = (f'<label class="check js-only"><input type="checkbox" name="ids" value="{id}" '
             f'form="bulk" aria-label="Select {title}"></label>')
    assert check in item
    assert item.index(check) < item.index('<a class="hit"')


def test_an_item_being_analysed_has_no_checkbox():
    text = (WEB / "templates" / "shelf-items.html").read_text(encoding="utf-8")
    assert 'class="check' not in between(text, "{% macro pending", "{%- endmacro %}")


def test_settings_and_the_idea_screen_have_no_bar(client):
    for path in ("/settings", f"/ideas/{client.idea}", "/retry"):
        assert 'id="bulk"' not in client.get(path).text, path


# --- the bar -------------------------------------------------------------------------------

def test_the_library_bar_moves_to_a_category_stars_and_deletes(client):
    found = bar(client.get("/").text)
    assert 'class="bulk js-only"' in found and " hidden" in found
    assert 'data-one="1 selected" data-many="%1 selected"' in found
    assert 'formaction="/bulk/category" name="category" value="Redes"' in found
    assert 'formaction="/bulk/category" name="category" value="Cocina"' in found
    assert 'name="new_category"' in found
    assert 'formaction="/bulk/mark" name="mark" value="⭐"' in found
    assert 'formaction="/bulk/delete"' in found and "data-clear" in found
    # The hidden first button: Enter in "New category" moves.
    assert found.index('class="default-submit"') < found.index('name="new_category"')


def test_the_ocio_bar_changes_the_kind_and_has_no_star(client):
    found = bar(client.get("/ocio").text)
    for kind in ("movie", "series", "anime", "book"):
        assert f'formaction="/bulk/kind" name="kind" value="{kind}"' in found
    assert "/bulk/mark" not in found and "/bulk/category" not in found
    assert 'formaction="/bulk/delete"' in found


def test_the_ideas_bar_changes_the_state_and_has_no_star(client):
    found = bar(client.get("/ideas").text)
    for state in ("pending", "doing", "done", "dropped"):
        assert f'formaction="/bulk/state" name="state" value="{state}"' in found
    assert "/bulk/mark" not in found and "/bulk/kind" not in found
    assert 'formaction="/bulk/delete"' in found


@pytest.mark.parametrize("path", ["/", "/ocio", "/ideas"])
def test_select_js_comes_after_shell_js(client, path):
    body = client.get(path).text
    assert (body.index('<script src="/static/shell.js" defer></script>')
            < body.index('<script src="/static/select.js" defer></script>'))


# --- select.js -------------------------------------------------------------------------------

def test_select_follows_the_list():
    text = SELECT.read_text(encoding="utf-8")
    listening = between(text, '"oknowledge:list"', "});")
    assert '"filter"' in listening


def test_select_registers_its_keys():
    text = SELECT.read_text(encoding="utf-8")
    for key in ("keys.x", "keys.Backspace", "keys.Delete", "keys.Escape"):
        assert key in text, key


def test_select_sends_the_ticked_ids_and_offers_undo():
    text = SELECT.read_text(encoding="utf-8")
    sending = between(text, "function submit", "function pickAfter")
    assert 'data.delete("ids")' in sending and 'data.append("ids"' in sending
    assert "ok.offerUndo(body.notice, body.undo" in sending and "ok.list.reload(" in sending


# --- fix round 1 -------------------------------------------------------------------------

@pytest.mark.parametrize("name, macro", [("shelf-items.html", "{% macro item"),
                                         ("posters.html", "{% macro poster")])
def test_a_note_being_reanalysed_has_no_checkbox(name, macro):
    text = between((WEB / "templates" / name).read_text(encoding="utf-8"), macro, "{%- endmacro %}")
    guarded = re.search(r"\{%- if note\.id not in busy %\}\s*<label class=\"check js-only\">.*?</label>"
                        r"\s*\{%- endif %\}", text, re.S)
    assert guarded, name


def test_a_bulk_change_reloads_the_pick_when_it_was_ticked():
    text = SELECT.read_text(encoding="utf-8")
    sending = between(text, "function submit", "function pickAfter")
    assert "var mine = picked.indexOf(cur) >= 0;" in sending
    # Once the list is back: the same pick redrawn, or the next one if it left.
    assert "ok.list.pick(listed(cur) ? cur : after)" in sending


def test_the_list_leaves_room_for_the_bar_while_picking():
    css = (WEB / "static" / "app.css").read_text(encoding="utf-8")
    assert re.search(r"#list\.picking \.list-body \{ padding-bottom: \d+px; \}", css)
