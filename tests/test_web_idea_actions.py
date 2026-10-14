"""The four buttons on an idea's page, and what they show."""

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.model import Note
from oknowledge.vault import find_note, note_path, rebuild_indexes, write_note
from oknowledge.web.app import create_app
from oknowledge.web.markup import inline
from oknowledge.web.working import Working

LINK = "bbbbbbbbbbbb"


@pytest.fixture(autouse=True)
def state_tree(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr("oknowledge.web.app.CONFIG_PATH",
                        tmp_path / "config" / "config.toml")


def make(tmp_path, chain=("opencode",)):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True, exist_ok=True)
    cfg = Config(vault=vault, chain=chain)
    rebuild_indexes(cfg, "es")
    return cfg


@pytest.fixture
def cfg(tmp_path):
    return make(tmp_path)


@pytest.fixture
def ran(monkeypatch):
    calls = []
    outcome = {"problem": None}

    def run(cfg, idea, action, category="", trace=None, scope="vinculados"):
        calls.append((idea, action, category))
        outcome["scope"] = scope
        return outcome["problem"]

    monkeypatch.setattr("oknowledge.web.app.run_idea_action", run)
    return calls, outcome


def put(cfg, **fields):
    note = new_idea("x", "VPN propia", "2026-10-12", "2026-10-12T00:00:00.000001+00:00")
    for key, value in fields.items():
        setattr(note, key, value)
    write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ideas))
    return note


def a_link(cfg):
    path = write_note(cfg, Note(id=LINK, url="https://wireguard.com", title="WireGuard",
                                category="Redes", tags=[], type="article",
                                source="wireguard.com", saved="2026-10-10",
                                summary="Una vpn."), "es")
    rebuild_indexes(cfg, "es")
    return path


# --- the route ------------------------------------------------------------------

def test_a_button_queues_its_action_and_says_it_is_thinking(cfg, ran):
    note = put(cfg)
    reply = TestClient(create_app(cfg)).post(f"/item/{note.id}/actions/improve",
                                             follow_redirects=False)
    assert reply.status_code == 303
    assert reply.headers["location"] == f"/ideas/{note.id}?pestana=mejoras&notice=thinking"
    assert ran[0] == [(note.id, "improve", "")]


def test_the_category_does_nothing_any_more(cfg, ran):
    a_link(cfg)
    note = put(cfg)
    TestClient(create_app(cfg)).post(f"/item/{note.id}/actions/links",
                                     data={"category": "Redes"})
    assert ran[0] == [(note.id, "links", "")]


def test_an_unknown_action_is_404(cfg, ran):
    note = put(cfg)
    assert TestClient(create_app(cfg)).post(
        f"/item/{note.id}/actions/delete").status_code == 404
    assert ran[0] == []


def test_a_missing_idea_goes_back_to_the_ideas(cfg, ran):
    reply = TestClient(create_app(cfg)).post("/item/nope/actions/improve",
                                             follow_redirects=False)
    assert reply.headers["location"] == "/ideas?notice=no-such-idea"
    assert ran[0] == []


def test_exists_without_a_searcher_is_refused_up_front(tmp_path, ran):
    cfg = make(tmp_path, chain=("ollama",))
    note = put(cfg)
    reply = TestClient(create_app(cfg)).post(f"/item/{note.id}/actions/exists",
                                             follow_redirects=False)
    assert reply.headers["location"] == f"/ideas/{note.id}?pestana=existe&notice=cannot-search"
    assert ran[0] == []


def test_a_second_click_while_it_runs_queues_nothing(cfg, ran):
    note = put(cfg)
    app = create_app(cfg)
    app.state.working.start(note.id, "improve")
    TestClient(app).post(f"/item/{note.id}/actions/improve")
    assert ran[0] == []


# --- the registry ---------------------------------------------------------------

def test_working_runs_one_of_each_and_remembers_the_last_failure():
    working = Working()
    assert working.start("i", "improve") is True
    assert working.start("i", "improve") is False
    assert working.start("i", "expand") is True
    assert working.of("i") == ({"improve", "expand"}, {})
    working.finish("i", "improve", "boom")
    assert working.of("i") == ({"expand"}, {"improve": "boom"})
    assert working.start("i", "improve") is True
    working.finish("i", "improve", None)
    assert working.of("i")[1] == {}
    assert working.of("other") == (set(), {})


# --- the page -------------------------------------------------------------------

def page(cfg, note, app=None):
    return TestClient(app or create_app(cfg)).get(f"/ideas/{note.id}").text


def test_the_last_failure_is_shown_and_cleared_by_a_success(cfg, ran):
    note = put(cfg)
    app = create_app(cfg)
    client = TestClient(app)
    ran[1]["problem"] = "opencode: 429"
    client.post(f"/item/{note.id}/actions/improve")
    assert "Last time it failed: opencode: 429" in client.get(f"/ideas/{note.id}").text
    ran[1]["problem"] = None
    client.post(f"/item/{note.id}/actions/improve")
    assert "Last time it failed" not in client.get(f"/ideas/{note.id}").text


def test_exists_is_disabled_with_its_reason_when_nobody_searches(tmp_path):
    cfg = make(tmp_path, chain=("ollama",))
    note = put(cfg)
    assert "No engine in your chain searches the web" in page(cfg, note)


def test_a_section_cannot_inject_markup_or_script_links(cfg):
    note = put(cfg, actions={"exists": "<script>x</script> [mal](javascript:alert(1)) "
                                       "[bien](https://ok.com)"})
    text = page(cfg, note)
    assert "<script>x</script>" not in text
    assert 'href="javascript:' not in text
    assert '<a href="https://ok.com" target="_blank" rel="noreferrer">bien</a>' in text


def test_add_from_the_idea_goes_back_to_the_idea(cfg):
    path = a_link(cfg)
    note = put(cfg)
    reply = TestClient(create_app(cfg)).post(
        f"/item/{LINK}/ideas", data={"idea": note.id, "back": "idea"},
        follow_redirects=False)
    assert reply.headers["location"].startswith(f"/ideas/{note.id}")
    assert find_note(cfg, note.id, shelf=cfg.ideas)[1].related == [path.stem]


def test_add_from_the_link_still_goes_back_to_the_link(cfg):
    a_link(cfg)
    note = put(cfg)
    reply = TestClient(create_app(cfg)).post(
        f"/item/{LINK}/ideas", data={"idea": note.id}, follow_redirects=False)
    assert reply.headers["location"].startswith(f"/item/{LINK}")


# --- the markup -----------------------------------------------------------------

def test_inline_escapes_first_and_links_only_the_web():
    assert str(inline("<b>[x](https://e.com/?a=1&b=2)</b>")) == (
        '&lt;b&gt;<a href="https://e.com/?a=1&amp;b=2" target="_blank" '
        'rel="noreferrer">x</a>&lt;/b&gt;')
    assert "<a" not in str(inline("[x](data:text/html,hi)"))
    assert str(inline("**a** and *b*")) == "<strong>a</strong> and <em>b</em>"


def test_a_category_that_is_not_in_the_library_is_ignored(cfg, ran):
    a_link(cfg)
    note = put(cfg)
    TestClient(create_app(cfg)).post(f"/item/{note.id}/actions/links",
                                     data={"category": "Redes\n\n## Mi nota\n\nx"})
    assert ran[0] == [(note.id, "links", "")]


@pytest.mark.parametrize("sent,used", [({}, "vinculados"), ({"alcance": "todos"}, "todos"),
                                        ({"alcance": "nada"}, "nada"),
                                        ({"alcance": "x"}, "vinculados")])
def test_the_scope_goes_to_the_action(cfg, ran, sent, used):
    note = put(cfg)
    TestClient(create_app(cfg)).post(f"/item/{note.id}/actions/improve", data=sent)
    assert ran[1]["scope"] == used


def test_the_old_link_boxes_do_nothing(cfg, ran):
    note = put(cfg)
    TestClient(create_app(cfg)).post(f"/item/{note.id}/actions/expand",
                                     data={"with_links": "1", "use": ["a"]})
    assert ran[1]["scope"] == "vinculados"


def test_a_script_is_told_in_json(cfg, ran):
    note = put(cfg)
    answer = TestClient(create_app(cfg)).post(f"/item/{note.id}/actions/improve",
                                              headers={"Accept": "application/json"})
    assert answer.json()["ok"] is True


def test_exists_without_a_searcher_is_a_409_for_a_script(tmp_path, ran):
    cfg = make(tmp_path, chain=("ollama",))
    note = put(cfg)
    answer = TestClient(create_app(cfg)).post(f"/item/{note.id}/actions/exists",
                                              headers={"Accept": "application/json"})
    assert answer.status_code == 409


# --- what is running (spec 2.2) --------------------------------------------------

def test_the_state_with_nothing_running(cfg):
    note = put(cfg)
    answer = TestClient(create_app(cfg)).get(f"/item/{note.id}/actions/state")
    assert answer.json() == {"running": [], "failed": [], "title": "VPN propia"}


def test_the_state_while_an_action_runs_and_after_one_failed(cfg):
    note = put(cfg)
    app = create_app(cfg)
    app.state.working.start(note.id, "improve")
    app.state.working.start(note.id, "expand")
    app.state.working.finish(note.id, "expand", "the model did not answer")
    assert TestClient(app).get(f"/item/{note.id}/actions/state").json() == {
        "running": ["improve"], "failed": ["expand"], "title": "VPN propia"}


def test_the_state_of_an_idea_that_is_gone_is_a_404(cfg):
    answer = TestClient(create_app(cfg)).get("/item/nope/actions/state")
    assert answer.status_code == 404
    assert answer.json()["ok"] is False and answer.json()["running"] == []


def test_naming_an_idea_is_watched_like_an_action(cfg, monkeypatch):
    seen = []
    monkeypatch.setattr("oknowledge.web.app.complete_idea",
                        lambda cfg, idea, trace=None: seen.append(idea) or True)
    app = create_app(cfg)
    client = TestClient(app)
    client.post("/ideas/guardar", data={"text": "Una idea."})
    assert len(seen) == 1
    assert app.state.working.of(seen[0]) == (set(), {})       # finished, and well


def test_a_naming_that_fails_is_remembered(cfg, monkeypatch):
    monkeypatch.setattr("oknowledge.web.app.complete_idea",
                        lambda cfg, idea, trace=None: False)
    note = put(cfg)
    app = create_app(cfg)
    TestClient(app).post(f"/item/{note.id}/describe")
    assert set(app.state.working.of(note.id)[1]) == {"complete"}
