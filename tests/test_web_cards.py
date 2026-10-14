"""The library card: where a link came from, and the popup that reads it.

The card has three click targets and they go to two different places. The
body and the cover open the note in a dialog on the page; the title and the
site strip leave for the original site. Both must work with JavaScript off,
which is why the popup's trigger is an ordinary link to the item page.
"""

import re

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


# --- the site on the card ----------------------------------------------------


def test_a_card_shows_the_site_it_came_from(client):
    assert "github.com" in client.get("/").text


def test_a_note_with_no_source_asks_for_no_icon(tmp_path):
    """`source` is frontmatter: a user can empty it, and /icon/ is not a page."""
    _, client = build(tmp_path, note("a1", source=""))

    body = client.get("/").text

    assert "/icon/" not in body


# --- where each part of the card goes ----------------------------------------


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
    # Our own <script src="/static/*.js"> tags come out first, by shape (with
    # or without defer): a new one of those is a file somebody wrote, and
    # anything else at all in here came out of the note.
    import re
    assert "<script" not in re.sub(r'<script src="/static/[a-z]+\.js"( defer)?>', "", body)


# --- the one view that takes the whole screen --------------------------------


@pytest.mark.parametrize("path", ["/settings", "/categories",
                                  "/search?q=shell"])
def test_everything_that_is_read_rather_than_scanned_keeps_its_measure(client, path):
    """A line of text 2000 pixels wide is unreadable; a grid of cards is not."""
    assert 'class="wide"' not in client.get(path).text


# --- and the scrolling itself, which lives in the stylesheet ----------------


def card_css() -> str:
    from pathlib import Path

    import oknowledge.web

    css = (Path(oknowledge.web.__file__).parent / "static" / "style.css").read_text()
    start = css.index(".card .sum {")
    return css[start:css.index("}", start)]


def test_the_summary_box_scrolls_rather_than_clamping():
    block = card_css()

    assert "overflow-y: auto" in block
    assert "line-clamp" not in block


def test_the_scrollbar_is_not_drawn():
    """Minimal on purpose: the wheel works, the bar is not there."""
    css = card_css()
    from pathlib import Path

    import oknowledge.web

    whole = (Path(oknowledge.web.__file__).parent / "static" / "style.css").read_text()

    assert "scrollbar-width: none" in css
    assert ".card .sum::-webkit-scrollbar" in whole


def test_scrolling_a_card_does_not_scroll_the_page_behind_it():
    assert "overscroll-behavior: contain" in card_css()


# --- the cover, where the note is read ---------------------------------------

@pytest.fixture
def with_cover(tmp_path):
    """A note whose cover is really on disk, so the chain can be followed from
    the page that names it to the bytes that come back."""
    cfg, client = build(tmp_path, note("a1", cover="../attachments/a1.png"),
                        note("b2", source="e.com", url="https://e.com/b2"))
    attachments = cfg.attachments_dir
    attachments.mkdir(parents=True, exist_ok=True)
    # The smallest PNG there is: one transparent pixel.
    (attachments / "a1.png").write_bytes(bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000a49444154789c6300010000050001" "0d0a2db4" "0000000049454e44ae426082"))
    return client


def test_a_note_with_no_cover_draws_no_frame(with_cover):
    assert "/cover/" not in with_cover.get("/panel/b2").text


def test_the_picture_the_note_points_at_is_really_served(with_cover):
    answer = with_cover.get("/cover/a1")
    assert answer.status_code == 200
    assert answer.headers["content-type"] == "image/png"


def test_joining_a_collection_is_not_drawn_as_saving(client):
    """Two actions that differ should not look the same: that button does not
    save the box beside it, it files the note somewhere."""
    body = client.get("/panel/a1").text
    more = re.search(r'<details class="menu up more">.*?</details>', body, re.S).group(0)
    join = re.search(r'<form[^>]*action="/item/a1/collections".*?</form>', more, re.S).group(0)

    assert 'name="add"' in join
    assert "<svg" not in join and "💾" not in join


# --- which engine analysed the note ------------------------------------------


def test_a_note_nobody_analysed_draws_no_engine_icon(client):
    """1182 of 1184 notes are in that state. An icon meaning "I don't know",
    repeated a thousand times, is noise and not information."""
    assert "icon-engine" not in client.get("/panel/a1").text


def test_the_card_draws_the_engine_that_analysed_it(tmp_path):
    _, client = build(tmp_path, note("a1", engine="opencode",
                                     model="opencode/ling-3.1-flash-free"))

    assert "icon-engine opencode" in client.get("/panel/a1").text


def test_the_model_is_named_where_the_mouse_finds_it(tmp_path):
    _, client = build(tmp_path, note("a1", engine="ollama", model="qwen2.5:7b"))
    body = client.get("/panel/a1").text

    assert 'title="ollama · qwen2.5:7b"' in body
    assert 'aria-label="ollama · qwen2.5:7b"' in body


def test_an_engine_with_no_model_names_only_itself(tmp_path):
    """The model is empty on a note whose engine never reported one. A dangling
    separator is worse than no separator."""
    _, client = build(tmp_path, note("a1", engine="opencode"))

    assert 'title="opencode"' in client.get("/panel/a1").text


def test_an_engine_nobody_has_an_icon_for_draws_nothing(tmp_path):
    """`engine: pepe` typed by hand must not reach a template as a file name."""
    _, client = build(tmp_path, note("a1", engine="../../etc/passwd", model="m"))
    body = client.get("/panel/a1").text

    assert "icon-engine" not in body
    assert "passwd" not in body


def test_the_engine_icon_follows_the_theme(tmp_path):
    """The lesson of the floppy disk: a fixed colour breaks in the other theme."""
    _, client = build(tmp_path, note("a1", engine="api", model="gpt-5"))
    body = client.get("/panel/a1").text
    drawn = body[body.index("icon-engine"):body.index("</svg>")]

    assert "currentColor" in drawn
    assert "fill=\"#" not in drawn


def test_the_note_page_names_the_engine_too(tmp_path):
    _, client = build(tmp_path, note("a1", engine="opencode", model="m"))

    assert "icon-engine" in client.get("/panel/a1").text
