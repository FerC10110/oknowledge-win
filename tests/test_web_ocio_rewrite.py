"""A card the model could not rewrite says so, and the shelf can rewrite
every card still in the catalog's English at once.

The rewrite runs after the response, so a failure used to vanish: the card
just stayed "not rewritten" with no word of why. Like the idea actions, the
last failure is kept in memory and shown until a rewrite succeeds.
"""

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.trace import Step
from oknowledge.vault import note_path, rebuild_indexes, write_note
from oknowledge.web.app import create_app

T2 = "aaaaaaaaaaa1"
VINLAND = "aaaaaaaaaaa2"
DONE = "aaaaaaaaaaa3"


@pytest.fixture(autouse=True)
def state_tree(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr("oknowledge.web.app.CONFIG_PATH",
                        tmp_path / "config" / "config.toml")


def card(id, title, engine=""):
    return Note(id=id, url=f"https://imdb.com/title/{id}", title=title,
                category="Películas", tags=[], type="movie", source="imdb.com",
                saved="2026-10-11", summary="A cyborg from the future.", engine=engine)


@pytest.fixture
def cfg(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    config = Config(vault=vault)
    for note in (card(T2, "Terminator 2"), card(VINLAND, "Vinland Saga"),
                 card(DONE, "Dune", engine="opencode")):
        write_note(config, note, "es", path=note_path(config, note, shelf=config.ocio))
    rebuild_indexes(config, "es")
    return config


@pytest.fixture
def model(monkeypatch):
    """The rewrite, faked: `answers[id]` is None for success or the reason it failed."""
    answers, asked = {}, []

    def describe(cfg, link_id, trace=None, **rest):
        asked.append(link_id)
        why = answers.get(link_id)
        if why is None:
            return True
        trace(Step(link=link_id, name="describe", state="fail", seconds=0.0, detail=why))
        return False
    monkeypatch.setattr("oknowledge.web.app.describe", describe)
    return answers, asked


@pytest.fixture
def client(cfg):
    return TestClient(create_app(cfg))


def test_a_failed_rewrite_shows_its_reason_on_the_card_page(client, model):
    model[0][T2] = "every engine failed: opencode: 429"
    client.post(f"/item/{T2}/describe")
    page = client.get(f"/item/{T2}").text
    assert "Last time it failed: every engine failed: opencode: 429" in page


def test_a_rewrite_that_works_clears_the_failure(client, model):
    model[0][T2] = "boom"
    client.post(f"/item/{T2}/describe")
    model[0][T2] = None
    client.post(f"/item/{T2}/describe")
    assert "Last time it failed" not in client.get(f"/item/{T2}").text
    assert "could not be rewritten" not in client.get("/ocio").text


def test_a_running_rewrite_says_so_and_is_not_asked_twice(cfg, model):
    app = create_app(cfg)
    app.state.rewriting.start(T2, "describe")
    client = TestClient(app)
    client.post(f"/item/{T2}/describe")
    assert model[1] == []
    assert "rewriting…" in client.get(f"/item/{T2}").text
    assert f'data-working="{T2}"' in client.get("/ocio").text


# --- every card at once -----------------------------------------------------------


def test_rewriting_all_asks_for_each_unrewritten_card_once(client, model):
    answer = client.post("/ocio/reescribir", follow_redirects=False)
    assert answer.status_code == 303
    assert answer.headers["location"].startswith("/ocio")
    assert sorted(model[1]) == [T2, VINLAND]


def test_rewriting_all_skips_a_card_already_running(cfg, model):
    app = create_app(cfg)
    app.state.rewriting.start(T2, "describe")
    TestClient(app).post("/ocio/reescribir")
    assert model[1] == [VINLAND]


def test_one_failure_does_not_stop_the_rest(client, model):
    model[0][T2] = "boom"
    client.post("/ocio/reescribir")
    assert sorted(model[1]) == [T2, VINLAND]
    assert "Last time it failed: boom" in client.get(f"/item/{T2}").text


