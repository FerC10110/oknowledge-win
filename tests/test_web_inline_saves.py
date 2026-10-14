"""Saving in place (spec §1): every write the redesigned screens make answers
JSON to a script and the redirect of today to a form."""

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.model import Note
from oknowledge.vault import find_note, note_path, rebuild_indexes, write_note
from oknowledge.web.app import create_app

JSON = {"Accept": "application/json"}
LINK = "aaaaaaaaaaaa"
CARD = "cccccccccccc"


@pytest.fixture
def cfg(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    config = Config(vault=vault)
    write_note(config, Note(id=LINK, url="https://wireguard.com", title="WireGuard",
                            category="Redes", tags=["vpn"], type="article",
                            source="wireguard.com", saved="2026-10-10",
                            summary="Una vpn."), "es")
    card = Note(id=CARD, url="https://imdb.com/title/tt0088247", title="The Terminator",
                category="Películas", tags=["accion"], type="movie", source="imdb.com",
                saved="2026-10-11", summary="Algo pasa.", score=3)
    write_note(config, card, "es", path=note_path(config, card, shelf=config.ocio))
    for shelf in (config.links, config.ocio):
        rebuild_indexes(config, "es", shelf=shelf)
    return config


@pytest.fixture
def idea(cfg):
    note = new_idea("Una vpn para la familia.", "VPN propia", "2026-10-12",
                    "2026-10-12T00:00:00.000001+00:00")
    write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ideas))
    rebuild_indexes(cfg, "es", shelf=cfg.ideas)
    return note


@pytest.fixture
def client(cfg):
    return TestClient(create_app(cfg))


def card_now(cfg):
    return find_note(cfg, CARD, shelf=cfg.ocio)[1]


def idea_now(cfg, idea):
    return find_note(cfg, idea.id, shelf=cfg.ideas)[1]


WRITES = [
    (f"/item/{CARD}/mine/state", {"state": "done"}),
    (f"/item/{CARD}/mine/score", {"score": "4"}),
    (f"/item/{CARD}/mine/note", {"my_note": "La vi."}),
    (f"/item/{CARD}/tags", {"tags": "accion", "add": "culto"}),
    (f"/item/{LINK}/category", {"category": "Seguridad"}),
    (f"/item/{LINK}/collections", {"add": "Casa"}),
    (f"/item/{LINK}/mark", {"mark": "⭐"}),
]


@pytest.mark.parametrize("path,data", WRITES)
def test_a_script_gets_json(client, path, data):
    answer = client.post(path, data=data, headers=JSON, follow_redirects=False)
    assert answer.status_code == 200
    assert answer.headers["content-type"] == "application/json"
    assert answer.json()["ok"] is True


@pytest.mark.parametrize("path,data", WRITES)
def test_a_form_still_gets_a_redirect(client, path, data):
    assert client.post(path, data=data, follow_redirects=False).status_code == 303


def test_the_json_says_what_the_page_would_have(client):
    assert client.post(f"/item/{CARD}/mine/state", data={"state": "done"},
                       headers=JSON).json() == {"ok": True, "notice": "Saved."}


def test_the_change_lands_either_way(client, cfg):
    client.post(f"/item/{CARD}/mine/state", data={"state": "doing"}, headers=JSON)
    assert card_now(cfg).state == "doing"


def test_a_refused_write_is_an_error_with_its_reason(client):
    answer = client.post(f"/item/{LINK}/category", data={"category": "a/b"}, headers=JSON)
    assert answer.status_code == 400
    assert answer.json()["ok"] is False
    assert "cannot be used as a category" in answer.json()["error"]


def test_a_note_that_is_not_there_is_a_json_404(client):
    answer = client.post("/item/zzzzzzzzzzzz/mine/state", data={"state": "done"},
                         headers=JSON)
    assert answer.status_code == 404
    assert answer.json() == {"ok": False, "error": "That is not there any more."}


def test_a_page_that_is_not_there_is_still_the_page(client):
    assert "<html" in client.get("/item/zzzzzzzzzzzz").text


def test_a_vault_that_cannot_be_written_is_a_500(client, monkeypatch):
    def broken(*args, **kwargs):
        raise OSError("read-only")
    monkeypatch.setattr("oknowledge.web.app.update_note", broken)
    answer = client.post(f"/item/{CARD}/mine/state", data={"state": "done"}, headers=JSON)
    assert answer.status_code == 500
    assert answer.json()["ok"] is False


def test_the_current_star_again_clears_the_score(client, cfg):
    client.post(f"/item/{CARD}/mine/score", data={"score": "0"}, headers=JSON)
    assert card_now(cfg).score == 0


@pytest.mark.parametrize("bad", ["9", "-1", "cinco", "", "4.5"])
def test_a_score_that_is_not_zero_to_five_writes_nothing(client, cfg, bad):
    client.post(f"/item/{CARD}/mine/score", data={"score": bad})
    assert card_now(cfg).score == 3


def test_adding_and_dropping_a_link_answer_json(client, cfg, idea):
    stem = find_note(cfg, LINK)[0].stem
    added = client.post(f"/item/{LINK}/ideas", data={"idea": idea.id, "back": "idea"},
                        headers=JSON)
    assert added.json()["ok"] is True
    assert idea_now(cfg, idea).related == [stem]
    dropped = client.post(f"/item/{idea.id}/related/drop", data={"stem": stem}, headers=JSON)
    assert dropped.json()["ok"] is True
    assert idea_now(cfg, idea).related == []


def test_a_full_idea_is_a_409_with_the_reason(client, cfg, idea):
    note = idea_now(cfg, idea)
    note.related = [f"2026-01-{n:02d}-x" for n in range(1, 17)]
    write_note(cfg, note, "es", path=find_note(cfg, idea.id, shelf=cfg.ideas)[0])
    answer = client.post(f"/item/{LINK}/ideas", data={"idea": idea.id, "back": "idea"},
                         headers=JSON)
    assert answer.status_code == 409
    assert "16 links" in answer.json()["error"]


# --- the idea's title -------------------------------------------------------

def test_the_title_has_a_route_of_its_own(client, cfg, idea):
    answer = client.post(f"/item/{idea.id}/title", data={"title": "  VPN\nfamiliar "},
                         headers=JSON)
    assert answer.json()["ok"] is True
    after = idea_now(cfg, idea)
    assert (after.title, after.my_note) == ("VPN familiar", "Una vpn para la familia.")


def test_the_title_moves_the_file_like_the_old_form_did(client, cfg, idea):
    client.post(f"/item/{idea.id}/title", data={"title": "Otra cosa"})
    assert find_note(cfg, idea.id, shelf=cfg.ideas)[0].stem == "2026-10-12-otra-cosa"


@pytest.mark.parametrize("empty", ["", "   ", "\n"])
def test_an_empty_title_is_not_saved(client, cfg, idea, empty):
    answer = client.post(f"/item/{idea.id}/title", data={"title": empty}, headers=JSON)
    assert answer.status_code == 400
    assert answer.json()["ok"] is False
    assert idea_now(cfg, idea).title == "VPN propia"


def test_without_a_script_an_empty_title_comes_back_with_the_reason(client, idea):
    answer = client.post(f"/item/{idea.id}/title", data={"title": ""},
                         follow_redirects=False)
    assert answer.status_code == 303
    assert "notice=title-empty" in answer.headers["location"]


def test_only_an_idea_has_this_title_box(client):
    assert client.post(f"/item/{CARD}/title", data={"title": "x"}).status_code == 404


def test_the_text_alone_keeps_the_title(client, cfg, idea):
    client.post(f"/item/{idea.id}/mine/note", data={"my_note": "Texto nuevo."},
                headers=JSON)
    after = idea_now(cfg, idea)
    assert (after.title, after.my_note) == ("VPN propia", "Texto nuevo.")
