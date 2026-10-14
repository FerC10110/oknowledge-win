"""An idea's own screen (spec §2): header, the AI bar, the text beside the
results. The column of links is tests/test_web_idea_screen_links.py."""

import re

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.model import Note
from oknowledge.vault import note_path, rebuild_indexes, write_note
from oknowledge.web.app import create_app

IMPROVE = ("*Con 1 link: WireGuard.*\n\n"
           "- **Acceso desde la tele** — usar un router con WireGuard.\n"
           "- **Quién la mantiene** — automatizar las actualizaciones.")


def make(tmp_path, chain=("opencode",)):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True, exist_ok=True)
    cfg = Config(vault=vault, chain=chain)
    rebuild_indexes(cfg, "es")
    return cfg


@pytest.fixture
def cfg(tmp_path):
    return make(tmp_path)


def put(cfg, **fields):
    note = new_idea("Una vpn para la familia, que ande en la tele.", "VPN familiar",
                    "2026-10-13", "2026-10-13T00:00:00.000001+00:00")
    note.summary, note.points = "Una VPN propia para la casa.", ["Para quién es.", "Qué resuelve."]
    note.tags, note.score, note.state = ["vpn", "casa"], 3, "doing"
    note.actions = {"improve": IMPROVE}
    for key, value in fields.items():
        setattr(note, key, value)
    write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ideas))
    return note


def screen(cfg, note, query="", app=None):
    return TestClient(app or create_app(cfg)).get(f"/ideas/{note.id}{query}").text


def part(body, start, end):
    head = body.index(start)
    return body[head:body.index(end, head)]


def bar(body):
    return part(body, 'id="idea-ai"', 'class="idea-body"')


def test_a_missing_idea_is_the_apps_404(cfg):
    answer = TestClient(create_app(cfg)).get("/ideas/000000000000")
    assert answer.status_code == 404
    assert "Not found" in answer.text


def test_three_columns_and_no_page_scroll(cfg):
    body = screen(cfg, put(cfg))
    assert '<div class="app idea-screen">' in body
    assert 'id="idea"' in body and 'class="links-column"' in body


# --- the header ---------------------------------------------------------------

def test_back_to_the_ideas_and_when_it_was_written(cfg):
    body = screen(cfg, put(cfg))
    assert '<a class="back" href="/ideas">← Ideas</a>' in body
    assert "created 13 Oct" in body


def test_back_keeps_the_filter_it_came_from(cfg):
    body = screen(cfg, put(cfg), "?back=/ideas?estado%3Ddoing")
    assert '<a class="back" href="/ideas?estado=doing">' in body


@pytest.mark.parametrize("back", ["//evil.com", "https://evil.com", "/settings", "/ideasx"])
def test_back_never_leaves_the_ideas(cfg, back):
    assert '<a class="back" href="/ideas">' in screen(cfg, put(cfg), "?back=" + back)


def test_the_title_is_a_box_that_saves_itself(cfg):
    note = put(cfg)
    box = re.search(r'<input[^>]*id="idea-title"[^>]*>', screen(cfg, note)).group(0)
    assert 'value="VPN familiar"' in box
    assert f'data-autosave="/item/{note.id}/title"' in box and "data-skip-empty" in box


def test_while_the_model_names_it_the_box_shows_the_start_of_the_text(cfg):
    note = put(cfg, title="")
    app = create_app(cfg)
    app.state.working.start(note.id, "complete")
    box = re.search(r'<input[^>]*id="idea-title"[^>]*>', screen(cfg, note, app=app)).group(0)
    assert 'value=""' in box and "waiting" in box
    assert 'placeholder="Una vpn para la familia, que ande en la tele."' in box


def test_the_state_is_a_segmented_control(cfg):
    note = put(cfg)
    seg = part(screen(cfg, note), f'action="/item/{note.id}/mine/state"', "</form>")
    assert re.findall(r'value="(\w+)"', seg) == ["pending", "doing", "done", "dropped"]
    assert re.search(r'value="doing" class="on"', seg)
    for word in ("seed", "under way", "done", "dropped"):
        assert f">{word}<" in seg


def test_the_current_star_takes_the_stars_off(cfg):
    note = put(cfg)
    stars = part(screen(cfg, note), f'action="/item/{note.id}/mine/score"', "</form>")
    assert re.findall(r'name="score" value="(\d)"', stars) == ["1", "2", "0", "4", "5"]


def test_the_more_menu_regenerates_and_deletes(cfg):
    note = put(cfg)
    body = screen(cfg, note)
    assert f'action="/item/{note.id}/describe"' in body
    assert "Regenerate everything with the AI" in body
    assert f'action="/item/{note.id}/delete"' in body and "Delete idea" in body


def test_the_tags_are_chips_and_a_box(cfg):
    tags = part(screen(cfg, put(cfg)), 'id="idea-tags"', "</div>")
    assert "#vpn" in tags and "#casa" in tags
    assert 'name="add"' in tags and 'placeholder="+ tag"' in tags


def test_no_save_buttons_but_for_a_browser_without_javascript(cfg):
    body = screen(cfg, put(cfg))
    assert "💾" not in body and "Edit tags" not in body
    saves = re.findall(r"<button[^>]*>Save</button>", body)
    assert saves and all("data-nojs" in button for button in saves)


# --- the AI bar ------------------------------------------------------------------

def test_the_ai_bar_has_three_actions_and_the_scope(cfg):
    note = put(cfg)
    ai = bar(screen(cfg, note))
    for action in ("exists", "improve", "expand"):
        assert f'action="/item/{note.id}/actions/{action}"' in ai
    assert ai.count('name="alcance" value="vinculados"') == 3
    for text in ("ASK THE AI", "using", "Linked links (0)", "The whole library", "Only my text"):
        assert text in ai
    assert "links that may help" not in ai.lower()


def test_the_scope_comes_from_the_url(cfg):
    ai = bar(screen(cfg, put(cfg), "?alcance=todos"))
    assert ai.count('name="alcance" value="todos"') == 3
    assert re.search(r'data-scope="todos" class="on"', ai)


def test_an_unknown_scope_is_the_linked_links(cfg):
    assert bar(screen(cfg, put(cfg), "?alcance=x")).count('name="alcance" value="vinculados"') == 3


def test_the_scope_counts_the_linked_links_still_there(cfg):
    stem = write_note(cfg, Note(id="aaaaaaaaaaaa", url="https://wireguard.com",
                                title="WireGuard", category="Redes", tags=[], type="article",
                                source="wireguard.com", saved="2026-10-10",
                                summary="Una vpn."), "es").stem
    rebuild_indexes(cfg, "es")
    assert "Linked links (1)" in screen(cfg, put(cfg, related=[stem, "2026-01-01-borrado"]))


def test_without_a_searcher_already_out_there_is_off_with_the_reason(tmp_path):
    cfg = make(tmp_path, chain=("ollama",))
    ai = bar(screen(cfg, put(cfg)))
    button = re.search(r'actions/exists".*?(<button[^>]*>)', ai, re.S).group(1)
    assert "disabled" in button
    assert 'title="No engine in your chain searches the web' in button


def test_a_running_action_is_off_and_said(cfg):
    note = put(cfg)
    app = create_app(cfg)
    app.state.working.start(note.id, "improve")
    ai = bar(screen(cfg, note, app=app))
    assert 'data-running="improve"' in ai
    assert "disabled" in re.search(r'actions/improve".*?(<button[^>]*>)', ai, re.S).group(1)
    assert "Improvements…" in ai


# --- the body -------------------------------------------------------------------------

def test_your_idea_fills_the_left_and_saves_itself(cfg):
    note = put(cfg)
    body = screen(cfg, note)
    area = re.search(r'<textarea[^>]*id="idea-text"[^>]*>(.*?)</textarea>', body, re.S)
    assert area.group(1) == "Una vpn para la familia, que ande en la tele."
    assert f'data-autosave="/item/{note.id}/mine/note"' in area.group(0)
    assert 'placeholder="Write it however it comes out: the AI puts it in order."' in area.group(0)
    assert "YOUR IDEA" in body and "saves itself" in body


def test_four_tabs_summary_first(cfg):
    body = screen(cfg, put(cfg))
    assert re.findall(r'data-tab="(\w+)"', body) == ["resumen", "existe", "mejoras", "ampliacion"]
    assert re.search(r'data-tab="resumen" class="on"', body)
    assert re.search(r'data-pane="resumen">', body)
    assert 'data-pane="mejoras" hidden>' in body


def test_the_tab_comes_from_the_url(cfg):
    body = screen(cfg, put(cfg), "?pestana=mejoras")
    assert re.search(r'data-pane="mejoras">', body)
    assert 'data-pane="resumen" hidden>' in body


def test_an_unknown_tab_is_the_summary(cfg):
    assert re.search(r'data-pane="resumen">', screen(cfg, put(cfg), "?pestana=zzz"))


def test_the_summary_is_a_paragraph_and_numbered_points(cfg):
    pane = part(screen(cfg, put(cfg)), 'data-pane="resumen"', 'data-pane="existe"')
    assert "Una VPN propia para la casa." in pane
    assert re.search(r'>01</span>\s*<span[^>]*>Para quién es\.', pane)
    assert ">02</span>" in pane


def test_improvements_are_cards_of_title_and_detail_under_the_links_line(cfg):
    pane = part(screen(cfg, put(cfg)), 'data-pane="mejoras"', 'data-pane="ampliacion"')
    assert pane.index("Con 1 link: WireGuard.") < pane.index("Acceso desde la tele")
    assert re.search(r'<div class="result-card">\s*<p class="title">Acceso desde la tele</p>\s*'
                     r'<p class="detail">usar un router con WireGuard\.</p>', pane)
    assert pane.count('class="result-card"') == 2


def test_already_out_there_draws_each_finding_as_a_card(cfg):
    found = ("**Hay parecidas.** Buscado el 2026-10-13 con fake.\n\n"
             "- [Tailscale](https://tailscale.com) — VPN sobre WireGuard.\n\n"
             "**Lo tuyo:** es para la familia.")
    pane = part(screen(cfg, put(cfg, actions={"exists": found})), 'data-pane="existe"',
                'data-pane="mejoras"')
    assert "Hay parecidas." in pane and "es para la familia." in pane
    assert '<a href="https://tailscale.com" target="_blank" rel="noreferrer">Tailscale</a>' in pane


def test_an_empty_tab_offers_to_ask(cfg):
    note = put(cfg)
    pane = part(screen(cfg, note), 'data-pane="ampliacion"', "</section>")
    assert "You have not asked yet." in pane
    assert f'action="/item/{note.id}/actions/expand"' in pane
    assert 'class="btn primary"' in pane


def test_a_summary_not_written_yet_offers_to_regenerate(cfg):
    note = put(cfg, summary="", points=[])
    pane = part(screen(cfg, note), 'data-pane="resumen"', 'data-pane="existe"')
    assert "You have not asked yet." in pane
    assert f'action="/item/{note.id}/describe"' in pane


def test_the_last_failure_is_said_in_its_tab(cfg):
    note = put(cfg)
    app = create_app(cfg)
    app.state.working.start(note.id, "expand")
    app.state.working.finish(note.id, "expand", "the model did not answer")
    pane = part(screen(cfg, note, app=app), 'data-pane="ampliacion"', "</section>")
    assert "Last time it failed: the model did not answer" in pane


# --- back to the screen without JavaScript ---------------------------------------------

def test_an_action_comes_back_to_its_tab(cfg, monkeypatch):
    monkeypatch.setattr("oknowledge.web.app.run_idea_action", lambda *a, **k: None)
    note = put(cfg)
    answer = TestClient(create_app(cfg)).post(f"/item/{note.id}/actions/improve",
                                              data={"alcance": "todos"}, follow_redirects=False)
    assert answer.headers["location"] == (
        f"/ideas/{note.id}?pestana=mejoras&alcance=todos&notice=thinking")


def test_regenerating_comes_back_to_the_screen(cfg, monkeypatch):
    monkeypatch.setattr("oknowledge.web.app.complete_idea", lambda cfg, idea, trace=None: True)
    note = put(cfg)
    answer = TestClient(create_app(cfg)).post(f"/item/{note.id}/describe",
                                              follow_redirects=False)
    assert answer.headers["location"] == f"/ideas/{note.id}?notice=completing"


def test_the_notice_is_a_toast(cfg):
    assert 'class="notice toast"' in screen(cfg, put(cfg), "?notice=thinking")
