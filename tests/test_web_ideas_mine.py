"""An idea's own page: your title and text in one form, four states in an
idea's own words, the stars, and the button that asks the model again.
Nothing on it that belongs to a link."""

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.model import Note
from oknowledge.vault import find_note, note_path, rebuild_indexes, write_note
from oknowledge.web.app import create_app

CARD = "aaaaaaaaaaaa"
LINK = "bbbbbbbbbbbb"


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


def put(cfg, n=1, text="Una app.", title="Mi gym", **fields):
    note = new_idea(text, title, "2026-10-12", f"2026-10-12T00:00:00.00000{n}+00:00")
    for key, value in fields.items():
        setattr(note, key, value)
    write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ideas))
    return note


def idea_now(cfg, note):
    return find_note(cfg, note.id, shelf=cfg.ideas)[1]


def page_of(client, note):
    return client.get(f"/ideas/{note.id}").text


def test_four_states_in_an_idea_s_own_words(cfg, client):
    page = page_of(client, put(cfg))
    for word in ("seed", "under way", "done", "dropped"):
        assert f">{word}</button>" in page


def test_an_idea_page_offers_nothing_that_belongs_to_a_link(cfg, client):
    note = put(cfg)
    page = page_of(client, note)
    for action in ("category", "collections", "reprocess"):
        assert f'/item/{note.id}/{action}"' not in page
    for action in ("tags", "delete", "describe", "mine/state", "mine/score", "mine/note"):
        assert f'/item/{note.id}/{action}"' in page


def test_an_idea_can_be_dropped_from_its_page(cfg, client):
    note = put(cfg)
    client.post(f"/item/{note.id}/mine/state", data={"state": "dropped"})
    assert idea_now(cfg, note).state == "dropped"


def test_stars_on_an_idea(cfg, client):
    note = put(cfg)
    client.post(f"/item/{note.id}/mine/score", data={"score": "4"})
    assert idea_now(cfg, note).score == 4


def test_saving_title_and_text_renames_the_file(cfg, client):
    note = put(cfg, title="Mi gym")
    answer = client.post(f"/item/{note.id}/mine/note",
                         data={"title": "Gimnasio con IA", "my_note": "Texto nuevo."},
                         follow_redirects=False)
    assert answer.headers["location"] == f"/item/{note.id}?notice=saved"
    path, after = find_note(cfg, note.id, shelf=cfg.ideas)
    assert (after.title, after.my_note) == ("Gimnasio con IA", "Texto nuevo.")
    assert path.name == "2026-10-12-gimnasio-con-ia.md"


def test_a_card_s_note_still_saves_without_a_title(cfg, client):
    card = Note(id=CARD, url="https://imdb.com/title/tt1", title="The Terminator",
                category="Películas", tags=[], type="movie", source="imdb.com",
                saved="2026-10-11", summary="Un cyborg.")
    write_note(cfg, card, "es", path=note_path(cfg, card, shelf=cfg.ocio))
    client.post(f"/item/{CARD}/mine/note", data={"my_note": "La vi."})
    after = find_note(cfg, CARD, shelf=cfg.ocio)[1]
    assert (after.title, after.my_note) == ("The Terminator", "La vi.")


def test_a_link_has_no_state_of_its_own(cfg, client):
    write_note(cfg, Note(id=LINK, url="https://wireguard.com", title="WireGuard",
                         category="Redes", tags=[], type="article",
                         source="wireguard.com", saved="2026-10-10",
                         summary="Una vpn."), "es")
    rebuild_indexes(cfg, "es")
    assert client.post(f"/item/{LINK}/mine/state", data={"state": "done"}).status_code == 404


def test_asking_again_queues_the_model(cfg, client, queued):
    note = put(cfg)
    answer = client.post(f"/item/{note.id}/describe", follow_redirects=False)
    assert answer.headers["location"] == f"/ideas/{note.id}?notice=completing"
    assert queued == [note.id]


def test_asking_again_is_offered_after_the_model_was_over_it(cfg, client):
    note = put(cfg, engine="fake", summary="Hecha.")
    assert f'/item/{note.id}/describe"' in page_of(client, note)


def test_tags_are_edited_on_an_idea(cfg, client):
    note = put(cfg)
    client.post(f"/item/{note.id}/tags", data={"tags": "gimnasio, ia"})
    assert idea_now(cfg, note).tags == ["gimnasio", "ia"]


def test_a_deleted_idea_goes_back_to_the_ideas(cfg, client):
    note = put(cfg)
    answer = client.post(f"/item/{note.id}/delete", follow_redirects=False)
    assert answer.headers["location"].startswith("/ideas?notice=trashed&undo=")
    assert find_note(cfg, note.id, shelf=cfg.ideas) is None


def test_a_page_opened_before_the_model_named_it_keeps_the_name(cfg, client):
    # The page was drawn while the idea had no name; the model gave it one;
    # you add a line and save without reloading. The empty box you never
    # touched must not erase the name.
    note = put(cfg, title="")
    path, there = find_note(cfg, note.id, shelf=cfg.ideas)
    there.title = "Gimnasio con IA"
    write_note(cfg, there, "es", path=path)
    client.post(f"/item/{note.id}/mine/note",
                data={"title": "", "title_was": "", "my_note": "Más texto."})
    after = idea_now(cfg, note)
    assert (after.title, after.my_note) == ("Gimnasio con IA", "Más texto.")


def test_a_title_you_changed_is_saved_even_over_the_model_s(cfg, client):
    note = put(cfg, title="Del modelo")
    client.post(f"/item/{note.id}/mine/note",
                data={"title": "Mío", "title_was": "Del modelo", "my_note": "x"})
    assert idea_now(cfg, note).title == "Mío"


def test_a_stale_page_does_not_put_back_an_old_title(cfg, client):
    # Two tabs: you rename the idea in one, then save a text change from the
    # other, drawn before the rename. The box you did not touch there still
    # says the old name, and saving must not put it back.
    note = put(cfg, title="Mi gym")
    client.post(f"/item/{note.id}/mine/note",
                data={"title": "Gimnasio con IA", "title_was": "Mi gym", "my_note": "x"})
    client.post(f"/item/{note.id}/mine/note",
                data={"title": "Mi gym", "title_was": "Mi gym", "my_note": "Más texto."})
    after = idea_now(cfg, note)
    assert (after.title, after.my_note) == ("Gimnasio con IA", "Más texto.")


# --- review I-1: the title and the text each keep their own revision -------------------------

def test_the_title_and_the_text_are_ordered_apart(cfg, client):
    note = put(cfg)
    json = {"Accept": "application/json"}
    client.post(f"/item/{note.id}/mine/note", data={"my_note": "Texto nuevo", "rev": "50"},
                headers=json)
    title = client.post(f"/item/{note.id}/title", data={"title": "Nombre nuevo", "rev": "10"},
                        headers=json)
    assert "stale" not in title.json()
    stale = client.post(f"/item/{note.id}/title", data={"title": "Viejo", "rev": "5"},
                        headers=json)
    assert stale.json()["stale"] is True
    now = idea_now(cfg, note)
    assert (now.title, now.my_note) == ("Nombre nuevo", "Texto nuevo")


def test_an_idea_title_from_another_page_is_written_whatever_its_revision(cfg, client):
    """Final review I-1: revs of the title are ordered within one page only."""
    note = put(cfg)
    json = {"Accept": "application/json"}
    client.post(f"/item/{note.id}/title", data={"title": "Del teléfono", "rev": "9000", "page": "p1"},
                headers=json)
    desk = client.post(f"/item/{note.id}/title",
                       data={"title": "Del escritorio", "rev": "10", "page": "p2"}, headers=json)
    assert "stale" not in desk.json() and idea_now(cfg, note).title == "Del escritorio"
