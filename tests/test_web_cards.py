"""The library card: where a link came from, and the popup that reads it.

The card has three click targets and they go to two different places. The
body and the cover open the note in a dialog on the page; the title and the
site strip leave for the original site. Both must work with JavaScript off,
which is why the popup's trigger is an ordinary link to the item page.
"""

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.vault import rebuild_indexes, write_note
from oknowledge.web.app import create_app


def note(id, source="github.com", url=None, **kw):
    fields = dict(
        id=id, url=url if url is not None else f"https://{source}/x",
        title="Slime shell", category="Escritorio", tags=["qml"], type="article",
        source=source, saved="2026-10-03", summary="Un shell para Hyprland.",
        points=["Corre en Quickshell"],
    )
    fields.update(kw)
    return Note(**fields)


def build(tmp_path, *notes):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    for one in notes:
        write_note(cfg, one, "es")
    rebuild_indexes(cfg, "es")
    return cfg, TestClient(create_app(cfg))


@pytest.fixture
def client(tmp_path):
    return build(tmp_path, note("a1"))[1]


# --- the favicon on the card -------------------------------------------------


def test_a_card_asks_for_its_site_icon(client):
    assert 'src="/icon/github.com"' in client.get("/").text


def test_a_card_shows_the_site_it_came_from(client):
    assert "github.com" in client.get("/").text


def test_a_note_with_no_source_asks_for_no_icon(tmp_path):
    """`source` is frontmatter: a user can empty it, and /icon/ is not a page."""
    _, client = build(tmp_path, note("a1", source=""))

    body = client.get("/").text

    assert "/icon/" not in body


# --- where each part of the card goes ----------------------------------------


def test_the_card_body_links_the_note_so_it_works_without_javascript(client):
    assert 'href="/item/a1"' in client.get("/").text


def test_the_card_carries_the_popup_hook(client):
    """Without this attribute the script has nothing to find and the card
    just navigates -- correct, but not what was asked for."""
    assert 'data-popup="/embed/a1"' in client.get("/").text


def test_the_title_links_the_original_site_in_a_new_tab(client):
    body = client.get("/").text

    assert 'href="https://github.com/x"' in body
    assert 'target="_blank"' in body
    assert "noreferrer" in body


@pytest.mark.parametrize("url", [
    "javascript:alert(1)", "data:text/html,<script>alert(1)</script>",
    "JavaScript:alert(1)", "vbscript:msgbox(1)", "file:///etc/passwd",
])
def test_a_url_that_is_not_a_web_address_is_never_linked(tmp_path, url):
    """The same guard the item page has had: `url` is hand-editable frontmatter.

    It is still printed, as escaped text -- the point is that it never
    becomes an href and never becomes markup.
    """
    _, client = build(tmp_path, note("a1", url=url))

    body = client.get("/").text

    assert f'href="{url}"' not in body
    assert "<script>" not in body
    assert "<script" not in body.replace('<script src="/static/popup.js" defer>', "")


def test_a_hand_edited_url_is_still_shown_even_when_it_is_not_a_link(tmp_path):
    """Refusing to link it must not mean hiding it: a link is never lost."""
    _, client = build(tmp_path, note("a1", url="ftp://old.example.com/x"))

    assert "ftp://old.example.com/x" in client.get("/").text


# --- the fragment the dialog loads -------------------------------------------


def test_the_fragment_is_the_note_without_the_page_around_it(client):
    answer = client.get("/embed/a1")

    assert answer.status_code == 200
    assert "Un shell para Hyprland." in answer.text
    assert "Corre en Quickshell" in answer.text
    assert "<!doctype html>" not in answer.text.lower()
    assert "<header" not in answer.text


def test_the_fragment_offers_the_whole_note(client):
    """The dialog reads; everything that writes stays on the item page."""
    assert 'href="/item/a1"' in client.get("/embed/a1").text


def test_the_fragment_has_nothing_that_writes(client):
    """No form in the dialog, so none of the write routes is reachable from it."""
    body = client.get("/embed/a1").text

    assert "<form" not in body
    assert "method=\"post\"" not in body.lower()


def test_a_fragment_for_a_link_that_is_not_there_is_a_404(client):
    assert client.get("/embed/nope").status_code == 404


def test_the_fragment_of_a_hand_edited_url_does_not_link_it(tmp_path):
    _, client = build(tmp_path, note("a1", url="javascript:alert(1)"))

    assert "alert(1)" not in client.get("/embed/a1").text


# --- the script that turns the link into a dialog ----------------------------


def test_the_library_loads_the_popup_script(client):
    assert "/static/popup.js" in client.get("/").text


def test_the_popup_script_is_served(client):
    answer = client.get("/static/popup.js")

    assert answer.status_code == 200
    assert "dialog" in answer.text


# --- the one view that takes the whole screen --------------------------------


def test_the_library_goes_full_width(client):
    assert 'class="wide"' in client.get("/").text


@pytest.mark.parametrize("path", ["/item/a1", "/settings", "/categories",
                                  "/search?q=shell"])
def test_everything_that_is_read_rather_than_scanned_keeps_its_measure(client, path):
    """A line of text 2000 pixels wide is unreadable; a grid of cards is not."""
    assert 'class="wide"' not in client.get(path).text
