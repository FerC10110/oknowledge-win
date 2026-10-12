"""The ideas section: write one, find it again.

Saving writes the idea at once, with your text, and leaves the model's part
to a task behind the page. These tests record that the task was queued and
never run a model.
"""

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.model import Note
from oknowledge.vault import all_notes, note_path, rebuild_indexes, write_note
from oknowledge.web.app import create_app


@pytest.fixture(autouse=True)
def state_tree(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr("oknowledge.web.app.CONFIG_PATH",
                        tmp_path / "config" / "config.toml")


@pytest.fixture
def queued(monkeypatch):
    calls = []
    monkeypatch.setattr("oknowledge.web.app.complete_idea",
                        lambda cfg, idea, trace=None: calls.append(idea))
    return calls


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


def put(cfg, n, text=None, title=None, **fields):
    note = new_idea(text or f"Idea número {n}.",
                    f"Idea {n}" if title is None else title,
                    "2026-10-12", f"2026-10-12T00:00:00.00000{n}+00:00")
    for key, value in fields.items():
        setattr(note, key, value)
    write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ideas))
    return note


def test_the_bar_has_a_way_in(client):
    assert 'href="/ideas"' in client.get("/").text


def test_the_form_is_open_only_while_there_is_nothing(cfg, client):
    page = client.get("/ideas").text
    assert 'action="/ideas/guardar"' in page
    assert '<details class="new-idea" open>' in page
    put(cfg, 1)
    page = client.get("/ideas").text
    assert '<details class="new-idea">' in page


def test_saving_writes_the_idea_and_queues_the_model(cfg, client, queued):
    answer = client.post("/ideas/guardar",
                         data={"text": "  Una app para el gym.  ", "title": ""},
                         follow_redirects=False)
    [idea] = all_notes(cfg, cfg.ideas)
    assert (idea.my_note, idea.title, idea.type) == ("Una app para el gym.", "", "idea")
    assert answer.status_code == 303
    assert answer.headers["location"] == f"/item/{idea.id}?notice=completing"
    assert queued == [idea.id]


def test_a_title_you_type_is_kept(cfg, client, queued):
    client.post("/ideas/guardar", data={"text": "x", "title": "Mi gym"})
    assert all_notes(cfg, cfg.ideas)[0].title == "Mi gym"


def test_no_text_no_idea(cfg, client, queued):
    answer = client.post("/ideas/guardar", data={"text": "   ", "title": "Algo"},
                         follow_redirects=False)
    assert answer.headers["location"] == "/ideas?notice=idea-empty"
    assert all_notes(cfg, cfg.ideas) == []
    assert queued == []


def test_two_saves_are_two_ideas(cfg, client, queued):
    client.post("/ideas/guardar", data={"text": "La misma."})
    client.post("/ideas/guardar", data={"text": "La misma."})
    assert len(all_notes(cfg, cfg.ideas)) == 2


def test_a_stale_index_still_saves_and_says_so(cfg, client, queued, monkeypatch):
    def broken(*args, **kwargs):
        raise OSError("read-only")

    monkeypatch.setattr("oknowledge.web.app.rebuild_indexes", broken)
    answer = client.post("/ideas/guardar", data={"text": "x"}, follow_redirects=False)
    assert answer.headers["location"].endswith("?notice=indexes-stale")
    assert len(all_notes(cfg, cfg.ideas)) == 1
    assert len(queued) == 1


def test_a_failed_write_saves_nothing_and_queues_nothing(cfg, client, queued, monkeypatch):
    def broken(*args, **kwargs):
        raise OSError("read-only")

    monkeypatch.setattr("oknowledge.web.app.write_note", broken)
    answer = client.post("/ideas/guardar", data={"text": "x"}, follow_redirects=False)
    assert answer.headers["location"] == "/ideas?notice=write-failed"
    assert queued == []


def test_the_section_shows_ideas_and_not_links(cfg, client):
    put(cfg, 1, title="Gimnasio con IA")
    write_note(cfg, Note(id="bbbbbbbbbbbb", url="https://wireguard.com",
                         title="WireGuard", category="Redes", tags=[],
                         type="article", source="wireguard.com",
                         saved="2026-10-10", summary="Una vpn."), "es")
    page = client.get("/ideas").text
    assert "Gimnasio con IA" in page
    assert "WireGuard" not in page


def test_dropped_ideas_are_out_of_sight_until_asked_for(cfg, client):
    put(cfg, 1, title="Viva")
    put(cfg, 2, title="Descartada", state="dropped")
    assert "Descartada" not in client.get("/ideas").text
    shown = client.get("/ideas?estado=dropped").text
    assert "Descartada" in shown and "Viva" not in shown


def test_an_unknown_state_shows_the_usual_view(cfg, client):
    put(cfg, 1, title="Viva")
    put(cfg, 2, title="Descartada", state="dropped")
    page = client.get("/ideas?estado=archived").text
    assert "Viva" in page and "Descartada" not in page


def test_a_state_typed_by_hand_does_not_break_the_section(cfg, client):
    put(cfg, 1, title="Rara", state="someday")
    page = client.get("/ideas")
    assert page.status_code == 200
    assert "someday" in page.text


def test_ideas_filter_by_tag(cfg, client):
    put(cfg, 1, title="Con tag", tags=["gimnasio"])
    put(cfg, 2, title="Sin tag")
    page = client.get("/ideas?tag=gimnasio").text
    assert "Con tag" in page and "Sin tag" not in page


def test_an_untitled_idea_is_never_an_empty_link(cfg, client):
    note = put(cfg, 1, title="")
    assert f'<a href="/item/{note.id}">Untitled idea</a>' in client.get("/ideas").text


def test_an_idea_not_yet_completed_says_so(cfg, client):
    put(cfg, 1)
    put(cfg, 2, title="Hecha", engine="fake", summary="Ya completada.")
    assert client.get("/ideas").text.count("not completed") == 1


def test_stars_never_run_past_five(cfg, client):
    put(cfg, 1, score=99)
    assert "★★★★★★" not in client.get("/ideas").text
