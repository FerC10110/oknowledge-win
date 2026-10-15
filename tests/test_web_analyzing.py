"""Links being read show up at the top as "Analysing…" and leave on their own."""

import re

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.queue import Queue
from oknowledge.urls import link_id, normalize
from oknowledge.vault import rebuild_indexes, write_note
from oknowledge.web import app as module
from oknowledge.web.app import create_app

URL = "https://nuevo.com/articulo"


@pytest.fixture
def cfg(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    write_note(cfg, Note(id="old1", url="https://e.com/old", title="Viejo", category="Redes",
                         tags=[], type="article", source="e.com", saved="2026-10-01",
                         summary="s"), "es")
    rebuild_indexes(cfg, "es")
    return cfg


@pytest.fixture
def client(cfg, monkeypatch):
    monkeypatch.setattr(module, "fetch", lambda *a, **k: None)   # nothing is read
    return TestClient(create_app(cfg))


def items(body):
    return re.findall(r'<li class="item[^"]*" id="card-([^"]+)"', body)


def test_a_saved_link_opens_selected_while_it_is_read(client):
    answer = client.post("/add", data={"q": URL, "content": "full"}, follow_redirects=False)
    new = link_id(normalize(URL))
    assert answer.headers["location"] == f"/?sel={new}&notice=reading"
    body = client.get(answer.headers["location"]).text
    assert items(body)[0] == new
    assert re.search(rf'<li class="item pending on" id="card-{new}" data-working="{new}"', body)
    assert "The AI is reading the link…" in body


def test_the_state_says_working_before_the_queue_knows(client):
    client.post("/add", data={"q": URL})
    assert client.get(f"/item/{link_id(normalize(URL))}/state").json()["working"] is True


def test_the_fresh_window_ends(client, monkeypatch):
    client.post("/add", data={"q": URL})
    clock = module.time.monotonic() + module.FRESH_SECONDS + 1
    monkeypatch.setattr(module.time, "monotonic", lambda: clock)
    assert link_id(normalize(URL)) not in items(client.get("/").text)


def test_once_the_queue_knows_it_is_the_queue_that_answers(client):
    client.post("/add", data={"q": URL})
    new = link_id(normalize(URL))
    q = Queue()
    q.enqueue(new, URL, "full")
    q.set_status(new, "ok")
    assert new not in items(client.get("/").text)


def test_a_pending_entry_nobody_holds_is_not_listed(client):
    Queue().enqueue("dead0000", "https://muerto.com", "full")
    assert "dead0000" not in items(client.get("/").text)


def test_a_held_entry_is_listed_and_a_held_note_is_marked_busy(client):
    q = Queue()
    q.enqueue("live0000", "https://vivo.com", "full")
    q.enqueue("old1", "https://e.com/old", "full")
    with q.lock("live0000"), q.lock("old1"):
        body = client.get("/").text
    assert items(body)[:2] == ["live0000", "old1"]
    assert re.search(r'id="card-old1" data-working="old1"', body)


def test_filters_do_not_list_the_pending(client):
    client.post("/add", data={"q": URL})
    assert items(client.get("/?cat=Redes").text) == ["old1"]


def test_the_state_of_a_pending_entry_nobody_holds_is_not_working(client):
    """A link whose analysis died (an OSError after enqueue, a restart) is
    pending with no lock. The open page polls /state; calling it working
    would keep its card "Analizando…" for ever, against the rule the list
    itself follows."""
    Queue().enqueue("dead0000", "https://muerto.com", "full")
    assert client.get("/item/dead0000/state").json() == {"working": False,
                                                         "status": "pending"}


def test_the_state_of_a_pending_entry_someone_holds_is_working(client):
    q = Queue()
    q.enqueue("live0000", "https://vivo.com", "full")
    with q.lock("live0000"):
        assert client.get("/item/live0000/state").json() == {"working": True,
                                                             "status": "pending"}


# --- batch G: the phone's way back, read off the page and not off app.py ----------

def test_a_link_being_analysed_has_its_way_back_to_the_list(client):
    """panel_context's first return (no note yet) carries list_url too: the
    phone's "← Library" goes to the list it came from, without the pick."""
    client.post("/add", data={"q": URL})
    new = link_id(normalize(URL))
    for path in (f"/panel/{new}?vista=lista", f"/?sel={new}&vista=lista"):
        body = client.get(path).text
        assert "The AI is reading the link…" in body, path
        found = re.search(r'<a class="detail-back"[^>]*>', body)
        assert found, path
        href = re.search(r'href="([^"]*)"', found.group(0)).group(1).replace("&amp;", "&")
        assert href.startswith("/?") and "sel=" not in href, href
        assert "vista=lista" in href, href
