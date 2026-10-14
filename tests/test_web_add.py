"""Pasting a link into the page.

On Omarchy this is the bar panel: a box, Enter, and two ways to save. There is
no bar here, so the box lives in the header of every page. The route answers
at once and does the work afterwards, for the same reason reprocess does: the
engine chain is minutes per link and no browser waits that long.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.urls import link_id, search_url
from oknowledge.vault import rebuild_indexes, write_note
from oknowledge.web import app as module
from oknowledge.web.app import create_app


@pytest.fixture(autouse=True)
def state_tree(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr("oknowledge.web.app.CONFIG_PATH",
                        tmp_path / "config" / "config.toml")


@pytest.fixture
def taken(monkeypatch):
    """What the background task was handed. The real one is minutes of model
    calls; what the route owes it is the url and the mode, and nothing else."""
    calls = []
    monkeypatch.setattr(module, "fetch",
                        lambda cfg, url, content, **rest: calls.append((url, content)))
    return calls


def vault_at(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    return Config(vault=vault)


@pytest.fixture
def client(tmp_path):
    cfg = vault_at(tmp_path)
    rebuild_indexes(cfg, "es")
    return TestClient(create_app(cfg))


def test_a_pasted_link_is_taken_and_the_page_comes_back_at_once(client, taken):
    body = client.post("/add", data={"url": "https://e.com/x", "content": "full"}).text

    assert taken == [("https://e.com/x", "full")]
    assert "Reading that link" in body
    assert "Nothing saved yet" in body          # the library, not a dead end


def test_the_two_buttons_are_the_two_ways_to_save(client, taken):
    """`default_content` is a preference and this is a decision about this
    link, which is why there are two buttons and not one. A post with neither
    -- which the page cannot produce -- leaves the preference deciding."""
    client.post("/add", data={"url": "https://e.com/a", "content": "summary"})
    client.post("/add", data={"url": "https://e.com/b", "content": ""})
    client.post("/add", data={"url": "https://e.com/c", "content": "whatever"})

    assert taken == [("https://e.com/a", "summary"),
                     ("https://e.com/b", None), ("https://e.com/c", None)]


def test_a_bare_domain_is_a_link(client, taken):
    """What somebody types rather than pastes. The CLI has always taken it."""
    client.post("/add", data={"url": " example.com/x ", "content": "full"})

    assert taken == [("https://example.com/x", "full")]


@pytest.mark.parametrize("raw", [
    "", "   ", "not a link", "javascript:alert(1)", "data:text/html,x",
    "ftp://e.com/a", "https://e.com/" + "a" * 3000,
])
def test_what_is_not_a_link_is_said_and_nothing_is_taken(client, taken, raw):
    """normalize() is a convenience and not a check: it turns "not a link" into
    "https://not a link/" as cheerfully as it turns example.com into a URL."""
    body = client.post("/add", data={"url": raw, "content": "full"}).text

    assert taken == []
    assert "not a link" in body.lower()


def test_a_search_page_is_not_a_page_to_save(client, taken):
    """The address a mention links to when a video only said a name out loud.
    Saving it would save a page of search results."""
    body = client.post("/add", data={"url": search_url("opencode"),
                                     "content": "full"}).text

    assert taken == []
    assert "search" in body.lower()


def test_a_link_already_in_the_library_is_said_and_not_read_again(tmp_path, taken):
    cfg = vault_at(tmp_path)
    write_note(cfg, Note(id=link_id("https://e.com/x"),
                         url="https://e.com/x", title="Uno", category="Redes",
                         tags=["x"], type="article", source="e.com",
                         saved="2026-10-10", summary="Resumen.", points=["un punto"]), "es")
    rebuild_indexes(cfg, "es")
    client = TestClient(create_app(cfg))

    body = client.post("/add", data={"url": "https://e.com/x", "content": "full"}).text

    assert taken == []
    assert "already have" in body
    assert "Uno" in body                        # and there it is


def test_the_box_has_its_own_line_on_a_phone():
    """The header already wraps at 40rem; the box is the widest thing in it,
    so it has to be told where to go rather than squeezed beside the search."""
    import oknowledge.web

    css = (Path(oknowledge.web.__file__).parent / "static" / "style.css").read_text()
    # Every block for that width, not the first one: there is more than one,
    # and a test that reads only the first would pass on a rule in the wrong
    # place -- or fail on one in the right place.
    blocks = [part.split("}\n}")[0]
              for part in css.split("@media (max-width: 40rem)")[1:]]

    assert blocks
    assert any(".paste-form input" in block for block in blocks)


# --- the half that runs after the answer --------------------------------------

def test_what_the_background_half_asks_the_pipeline_for(tmp_path, monkeypatch):
    """reprocess stays off. "You already have that link" is a promise about
    what a paste cannot do, and it has to hold for the link the index did not
    know about yet -- a note something else saved one second ago."""
    calls = []
    monkeypatch.setattr(module, "add_link",
                        lambda cfg, url, **rest: calls.append((url, rest)))

    module.fetch(vault_at(tmp_path), "https://e.com/x", "full", trace=None)

    assert calls == [("https://e.com/x", {"content": "full", "trace": None})]


def test_a_failure_in_the_background_half_never_reaches_the_server(
        tmp_path, monkeypatch, caplog):
    """It runs after the response has been sent: there is nobody left to raise
    to. What there is instead is a line in the log naming the link."""
    def boom(*args, **rest):
        raise RuntimeError("the vault went away")

    monkeypatch.setattr(module, "add_link", boom)

    module.fetch(vault_at(tmp_path), "https://e.com/x", None)

    assert "https://e.com/x" in caplog.text


def test_a_note_saved_after_the_page_opened_still_counts_as_already_had(tmp_path, taken):
    """The library is read once and refreshed per request. Without the refresh
    a link saved by a batch running behind this page would be read all over
    again: the pipeline would refuse to overwrite the note, and the person
    would have been told something was happening when nothing was."""
    cfg = vault_at(tmp_path)
    rebuild_indexes(cfg, "es")
    client = TestClient(create_app(cfg))

    write_note(cfg, Note(id=link_id("https://e.com/x"), url="https://e.com/x",
                         title="Uno", category="Redes", tags=["x"], type="article",
                         source="e.com", saved="2026-10-10", summary="Resumen.",
                         points=["un punto"]), "es")
    body = client.post("/add", data={"url": "https://e.com/x", "content": "full"}).text

    assert taken == []
    assert "already have" in body
