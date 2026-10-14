import os
import re
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from marks import posix_only
from oknowledge.config import Config
from oknowledge import web
from oknowledge.i18n import STRINGS
from oknowledge.model import Mention, Note
from oknowledge.urls import search_url
from oknowledge.vault import rebuild_indexes, write_note
from oknowledge.web.app import create_app


def note(id, title, category, tags, summary, body=None, saved="2026-10-03",
         type="article", mentions=None, collections=()):
    return Note(
        id=id, url=f"https://e.com/{id}", title=title, category=category, tags=list(tags),
        type=type, source="e.com", saved=saved, summary=summary,
        points=["un punto"], body=body, mentions=mentions,
        collections=list(collections),
    )


@pytest.fixture
def client(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    write_note(cfg, note("a1", "WireGuard vs OpenVPN", "Redes", ["vpn"],
                         "Compara ambos protocolos.",
                         body="El kernel hace la diferencia."), "es")
    write_note(cfg, note("b2", "Masa madre", "Cocina", ["pan"],
                         "Cómo arrancar una masa madre.", saved="2026-09-20"), "es")
    rebuild_indexes(cfg, "es")
    return TestClient(create_app(cfg))


def test_the_library_shows_every_note_newest_first(client):
    body = client.get("/").text
    assert "WireGuard vs OpenVPN" in body
    assert "Masa madre" in body
    assert body.index("WireGuard") < body.index("Masa madre")


def test_the_library_filters_by_category(client):
    body = client.get("/?category=Cocina").text
    assert "Masa madre" in body
    assert "WireGuard" not in body


def test_the_library_filters_by_tag(client):
    body = client.get("/?tag=vpn").text
    assert "WireGuard" in body
    assert "Masa madre" not in body


def test_search_looks_inside_the_summary(client):
    body = client.get("/search?q=protocolos").text
    assert "WireGuard" in body
    assert "Masa madre" not in body


def test_search_looks_inside_the_saved_content(client):
    body = client.get("/search?q=kernel").text
    assert "WireGuard" in body


def test_search_shows_the_fragment_where_it_matched(client):
    body = client.get("/search?q=kernel").text
    assert "kernel hace la diferencia" in body


def test_search_ignores_case_and_accents(client):
    assert "Masa madre" in client.get("/search?q=COMO").text


def test_search_with_no_hits_says_so(client):
    assert "No results" in client.get("/search?q=zzzz").text


def test_an_item_page_shows_the_summary_the_points_and_the_link(client):
    body = client.get("/item/a1").text
    assert "Compara ambos protocolos." in body
    assert "un punto" in body
    assert "https://e.com/a1" in body


def test_an_unknown_item_is_a_404(client):
    assert client.get("/item/zzzz").status_code == 404


def test_the_interface_follows_the_config(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    body = TestClient(create_app(Config(vault=vault, ui_language="es"))).get("/").text
    assert "Biblioteca" in body and "Ajustes" in body


def test_the_interface_is_english_unless_the_config_says_otherwise(client):
    body = client.get("/").text
    assert "Library" in body and "Settings" in body
    assert "Biblioteca" not in body


# --- ruling 1: refresh() is cheap when nothing changed -------------------------------


@pytest.fixture
def scans(monkeypatch):
    """Counts how many times the vault is really read and parsed."""
    from oknowledge.web import index

    calls = []
    real = index.scan_file

    def counting(path):
        calls.append(path.name)
        return real(path)

    monkeypatch.setattr(index, "scan_file", counting)
    return calls


def make_cfg(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    return Config(vault=vault)


def test_a_second_request_with_nothing_changed_does_not_reread_the_vault(tmp_path, scans):
    cfg = make_cfg(tmp_path)
    write_note(cfg, note("a1", "Uno", "Redes", ["vpn"], "Resumen."), "es")
    client = TestClient(create_app(cfg))
    after_startup = len(scans)
    for url in ("/", "/", "/search?q=uno", "/item/a1", "/?category=Redes"):
        assert client.get(url).status_code == 200
    assert len(scans) == after_startup


def test_a_note_edited_by_hand_is_picked_up(tmp_path, scans):
    cfg = make_cfg(tmp_path)
    path = write_note(cfg, note("a1", "Uno", "Redes", ["vpn"], "Resumen."), "es")
    client = TestClient(create_app(cfg))
    assert "Titulo nuevo" not in client.get("/").text
    path.write_text(path.read_text(encoding="utf-8").replace("Uno", "Titulo nuevo"),
                    encoding="utf-8")
    assert "Titulo nuevo" in client.get("/").text


def test_an_edit_that_keeps_size_and_mtime_is_the_only_blind_spot(tmp_path):
    """Documented limit: same size and same mtime_ns is invisible. Obsidian always
    moves the mtime, so this is accepted; the test pins the contract."""
    cfg = make_cfg(tmp_path)
    path = write_note(cfg, note("a1", "Uno", "Redes", [], "Resumen."), "es")
    client = TestClient(create_app(cfg))
    client.get("/")
    stat = path.stat()
    path.write_text(path.read_text(encoding="utf-8").replace("Uno", "Dos"), encoding="utf-8")
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    assert "Uno" in client.get("/").text


def test_a_new_note_and_a_deleted_note_are_picked_up(tmp_path):
    cfg = make_cfg(tmp_path)
    first = write_note(cfg, note("a1", "Uno", "Redes", [], "Resumen."), "es")
    client = TestClient(create_app(cfg))
    assert "Uno" in client.get("/").text
    write_note(cfg, note("b2", "Dos", "Redes", [], "Otro."), "es")
    assert "Dos" in client.get("/").text
    first.unlink()
    body = client.get("/").text
    assert "Uno" not in body and "Dos" in body


# --- ruling 2: say how many notes could not be read ---------------------------------


def break_note(path):
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("tags:", "tags: [unclosed\nmore:", 1), encoding="utf-8")


def test_a_note_that_cannot_be_read_is_counted_in_the_page(tmp_path):
    cfg = make_cfg(tmp_path)
    write_note(cfg, note("a1", "Uno", "Redes", ["vpn"], "Resumen."), "es")
    broken = write_note(cfg, note("b2", "Dos", "Redes", ["x"], "Otro."), "es")
    break_note(broken)
    body = TestClient(create_app(cfg)).get("/").text
    assert "Uno" in body
    assert "1 note could not be read and is not shown" in body


def test_the_unreadable_count_is_plural_and_translated(tmp_path):
    import dataclasses

    cfg = make_cfg(tmp_path)
    for i in range(2):
        break_note(write_note(cfg, note(f"x{i}", f"T{i}", "Redes", ["x"], "S."), "es"))
    body = TestClient(create_app(dataclasses.replace(cfg, ui_language="es"))).get("/").text
    assert "2 notas no se pudieron leer y no se muestran" in body


def test_no_warning_when_every_note_reads(client):
    assert "could not be read" not in client.get("/").text


# --- ruling 3: a disk error is a readable page --------------------------------------


def test_an_unreadable_vault_renders_a_page_with_the_path(tmp_path, monkeypatch):
    from oknowledge.web import index

    cfg = make_cfg(tmp_path)
    client = TestClient(create_app(cfg))

    def boom(cfg, shelf=None):
        raise PermissionError("denied")

    monkeypatch.setattr(index, "fingerprint", boom)
    # force a change so the scan is attempted
    write_note(cfg, note("a1", "Uno", "Redes", [], "Resumen."), "es")
    for url in ("/", "/search?q=x", "/item/a1", "/cover/a1"):
        response = client.get(url)
        assert response.status_code in (404, 503), url
        assert "Traceback" not in response.text
    page = client.get("/")
    assert page.status_code == 503
    assert "The vault could not be read" in page.text
    assert str(cfg.links_dir) in page.text


@posix_only
def test_an_unreadable_links_folder_is_a_readable_page(tmp_path):
    if os.geteuid() == 0:
        pytest.skip("root ignores permissions")
    cfg = make_cfg(tmp_path)
    write_note(cfg, note("a1", "Uno", "Redes", [], "Resumen."), "es")
    client = TestClient(create_app(cfg))
    cfg.links_dir.chmod(0)
    try:
        response = client.get("/")
    finally:
        cfg.links_dir.chmod(0o755)
    assert response.status_code == 503
    assert "The vault could not be read" in response.text
    assert client.get("/").status_code == 200  # and it recovers


def test_the_app_starts_even_if_the_vault_cannot_be_read_at_startup(tmp_path, monkeypatch):
    from oknowledge.web import index

    def boom(cfg, shelf=None):
        raise OSError("gone")

    monkeypatch.setattr(index, "fingerprint", boom)
    client = TestClient(create_app(make_cfg(tmp_path)))
    assert client.get("/").status_code == 503


# --- ruling 4: the cover route treats the frontmatter as untrusted -------------------


def cover_client(tmp_path, cover, make_files=None):
    cfg = make_cfg(tmp_path)
    cfg.attachments_dir.mkdir(parents=True, exist_ok=True)
    n = note("a1", "Uno", "Redes", [], "Resumen.")
    n.cover = cover
    write_note(cfg, n, "es")
    if make_files:
        make_files(cfg)
    return cfg, TestClient(create_app(cfg))


def test_a_cover_inside_attachments_is_served(tmp_path):
    def files(cfg):
        (cfg.attachments_dir / "a1.png").write_bytes(b"PNGDATA")

    _, client = cover_client(tmp_path, "../attachments/a1.png", files)
    response = client.get("/cover/a1")
    assert response.status_code == 200
    assert response.content == b"PNGDATA"


def test_a_cover_that_climbs_out_is_a_404(tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("SECRET")
    _, client = cover_client(tmp_path, "../../../../etc/passwd")
    response = client.get("/cover/a1")
    assert response.status_code == 404
    assert "root:" not in response.text


def test_an_absolute_cover_is_a_404(tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("SECRET")
    _, client = cover_client(tmp_path, str(secret))
    response = client.get("/cover/a1")
    assert response.status_code == 404
    assert "SECRET" not in response.text


def test_a_cover_that_escapes_and_comes_back_is_a_404(tmp_path):
    def files(cfg):
        (cfg.root / "private.png").write_bytes(b"PRIVATE")

    # resolves to <root>/private.png: inside the vault, outside attachments/
    _, client = cover_client(tmp_path, "../attachments/../private.png", files)
    assert client.get("/cover/a1").status_code == 404


@posix_only
def test_an_attachment_that_is_a_symlink_to_outside_is_a_404(tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("SECRET")

    def files(cfg):
        (cfg.attachments_dir / "a1.png").symlink_to(outside)

    _, client = cover_client(tmp_path, "../attachments/a1.png", files)
    response = client.get("/cover/a1")
    assert response.status_code == 404
    assert "SECRET" not in response.text


def test_odd_cover_values_are_404_not_exceptions(tmp_path):
    for value in ("../attachments", "../attachments/", "", "../attachments/a\x00b.png",
                  "../attachments/missing.png"):
        _, client = cover_client(tmp_path / (str(abs(hash(value)))), value)
        assert client.get("/cover/a1").status_code == 404, repr(value)


def test_a_missing_note_or_a_note_without_cover_is_a_404(client):
    assert client.get("/cover/zzzz").status_code == 404
    assert client.get("/cover/a1").status_code == 404


def test_a_cover_added_a_moment_ago_is_served_without_loading_another_page(tmp_path):
    cfg, client = cover_client(tmp_path, "../attachments/a1.png")
    assert client.get("/cover/a1").status_code == 404
    (cfg.attachments_dir / "a1.png").write_bytes(b"PNG")
    assert client.get("/cover/a1").status_code == 200


def test_a_cover_added_to_the_note_by_hand_is_seen_by_the_cover_route(tmp_path):
    cfg = make_cfg(tmp_path)
    cfg.attachments_dir.mkdir(parents=True)
    path = write_note(cfg, note("a1", "Uno", "Redes", [], "Resumen."), "es")
    client = TestClient(create_app(cfg))
    (cfg.attachments_dir / "a1.png").write_bytes(b"PNG")
    assert client.get("/cover/a1").status_code == 404
    text = path.read_text(encoding="utf-8").replace(
        "status:", "cover: ../attachments/a1.png\nstatus:", 1)
    path.write_text(text, encoding="utf-8")
    assert client.get("/cover/a1").status_code == 200


# --- ruling 5: everything a model or the user wrote is escaped -----------------------

XSS_TITLE = "<script>alert(1)</script> Title"
XSS_SUMMARY = '<img src=x onerror=alert(2)> "quoted" summary'


def xss_client(tmp_path):
    cfg = make_cfg(tmp_path)
    n = note("x1", XSS_TITLE, "<b>Cat</b>", ["<i>tag</i>"], XSS_SUMMARY,
             body="<script>alert(3)</script> body text")
    n.points = ["<script>alert(4)</script>"]
    n.source = "<u>src</u>"
    write_note(cfg, n, "es")
    return TestClient(create_app(cfg))


@pytest.mark.parametrize("url", ["/", "/?category=%3Cb%3ECat%3C/b%3E", "/search?q=body",
                                 "/item/x1"])
def test_note_content_is_escaped_on_every_page(tmp_path, url):
    body = xss_client(tmp_path).get(url).text
    assert "<script>alert" not in body
    assert "<img src=x" not in body
    assert "<b>Cat" not in body and "<i>tag" not in body and "<u>src" not in body
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body or "alert(3)" in body


def test_the_item_page_escapes_title_summary_and_points(tmp_path):
    body = xss_client(tmp_path).get("/item/x1").text
    assert "&lt;script&gt;alert(1)&lt;/script&gt; Title" in body
    assert "&lt;img src=x onerror=alert(2)&gt;" in body
    assert "&lt;script&gt;alert(4)&lt;/script&gt;" in body


def test_the_search_query_is_escaped_where_it_is_reflected(client):
    body = client.get("/search", params={"q": '"><script>alert(9)</script>'}).text
    assert "<script>alert(9)" not in body
    assert "&#34;&gt;&lt;script&gt;alert(9)&lt;/script&gt;" in body


def test_the_search_snippet_is_escaped(tmp_path):
    body = xss_client(tmp_path).get("/search?q=body text").text
    assert "<script>alert(3)" not in body
    assert "&lt;script&gt;alert(3)&lt;/script&gt;" in body


def test_no_template_marks_note_content_safe():
    from pathlib import Path

    import oknowledge.web

    templates = Path(oknowledge.web.__file__).parent / "templates"
    for html in templates.glob("*.html"):
        text = html.read_text(encoding="utf-8")
        assert "|safe" not in text and "| safe" not in text, html.name
        assert "autoescape" not in text, html.name


def test_a_javascript_url_in_the_frontmatter_is_not_a_live_link(tmp_path):
    cfg = make_cfg(tmp_path)
    n = note("j1", "Uno", "Redes", [], "Resumen.")
    n.url = "javascript:alert(1)"
    write_note(cfg, n, "es")
    body = TestClient(create_app(cfg)).get("/item/j1").text
    assert 'href="javascript:' not in body


MENTIONED = [Mention(name="opencode", url="https://opencode.ai"),
             Mention(name="Railway", url=search_url("Railway"))]


@pytest.fixture
def video(tmp_path):
    """A client whose a1 is a video with two mentions: a real one and a search."""
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    write_note(cfg, note("a1", "Mi stack 2026", "Redes", ["dev"],
                         "Qué herramientas usa.", type="youtube",
                         mentions=MENTIONED), "es")
    rebuild_indexes(cfg, "es")
    return TestClient(create_app(cfg))


def test_the_mentions_show_up_on_the_note(video):
    page = video.get("/item/a1").text

    assert 'class="mentions"' in page
    assert "opencode" in page
    assert "https://opencode.ai" in page


def test_a_search_link_is_marked_and_a_real_one_is_not(video):
    """The distinction the user chose has to be readable without thinking."""
    page = video.get("/item/a1").text

    assert page.count('class="mention-search"') == 1


def stylesheet() -> str:
    from pathlib import Path

    import oknowledge.web

    return (Path(oknowledge.web.__file__).parent / "static" / "style.css").read_text()


def rules_only() -> str:
    """The stylesheet without its comments: what the browser acts on."""
    import re

    return re.sub(r"/\*.*?\*/", "", stylesheet(), flags=re.S)


def rule_for(selector: str) -> str:
    css = stylesheet()
    start = css.index(selector)
    return css[css.index("{", start):css.index("}", start)]


@pytest.mark.parametrize("selector", [".mentions a", ".empty a"])
def test_a_link_is_never_left_to_the_browsers_own_colours(selector):
    """An <a> this stylesheet never claims falls through to the UA's blue and
    its visited purple: a hue that moves under the reader, over a background
    chosen here, and painful against the dark one. A mention's link and the
    one on the not-found page were the last two.

    The underline carries the meaning instead. It is the one signal that does
    not depend on seeing a particular colour.
    """
    block = rule_for(selector)

    assert "color:" in block
    assert "underline" in block


def test_nothing_makes_a_visited_link_look_different():
    """Hue as the only difference between two states is exactly the cue a
    colour blind reader cannot use, and it is why these links appeared to
    change colour on their own. A non-colour :visited cue would be fine, but
    it would have to be argued for here rather than arrive by accident.
    """
    assert ":visited" not in rules_only()


def test_a_note_never_asked_shows_no_section(client):
    """The section's own class, not its heading: conftest points the shared
    language file at a path that does not exist, so every test here renders in
    English and `"Menciones" not in page` would pass however the note looks.
    `client`'s a1 is an article nobody asked, which is the case under test."""
    assert 'class="mentions"' not in client.get("/item/a1").text


def test_the_popup_shows_the_mentions_but_offers_no_way_to_delete(video):
    """embed.html is a fragment that writes nothing, and its own header says
    so. Respecting that matters more than saving a click."""
    page = video.get("/embed/a1").text

    assert 'class="mentions"' in page
    assert "opencode" in page
    assert "mentions/delete" not in page
    assert "<form" not in page and "<button" not in page


def test_every_confirmation_in_the_note_page_still_has_its_translation():
    """In i18n the key IS the English text, so changing the reprocess warning
    changes the key. The Spanish entry has to move with it, or a Spanish
    interface shows an English warning about what it is going to overwrite."""
    template = (Path(web.__file__).parent / "templates" / "item.html").read_text(
        encoding="utf-8")

    asked = re.findall(r"data-ask=\"\{\{ t\('(.+?)'\) \}\}\"", template)

    assert asked, "the forms lost their data-ask"
    assert [text for text in asked if text not in STRINGS["es"]] == []
    assert any("mention" in text.lower() for text in asked), (
        "the reprocess warning does not say the mentions are replaced too")


def test_a_javascript_url_in_a_mention_is_text_not_a_live_link(tmp_path):
    """A mention's URL comes out of the note body, which is as hand-editable as
    the frontmatter. Refusing to link it must not mean hiding it."""
    cfg = make_cfg(tmp_path)
    write_note(cfg, note("j1", "Uno", "Redes", [], "Resumen.", type="youtube",
                         mentions=[Mention(name="Sneaky", url="javascript:alert(1)")]),
               "es")
    client = TestClient(create_app(cfg))
    for path in ("/item/j1", "/embed/j1"):
        page = client.get(path).text
        assert "Sneaky" in page, path
        assert 'href="javascript:' not in page, path


@pytest.mark.parametrize("bad", ["www.foo.com", "javascript:alert(1)"])
def test_a_rejected_mention_url_is_still_shown_as_text(tmp_path, bad):
    """Not linking a URL must not hide it, like note.url: the user typed
    `- [Foo](www.foo.com)` in Obsidian and needs to see what to repair."""
    cfg = make_cfg(tmp_path)
    write_note(cfg, note("j1", "Uno", "Redes", [], "Resumen.", type="youtube",
                         mentions=[Mention(name="Foo", url=bad)]), "es")
    client = TestClient(create_app(cfg))
    for path in ("/item/j1", "/embed/j1"):
        page = client.get(path).text
        assert "Foo" in page, path
        assert bad in page.replace("&#39;", "'"), path
        assert f'href="{bad}"' not in page, path


# --- the tag row, which grows without end ------------------------------------

@pytest.fixture
def many_tags(tmp_path):
    """Thirty tags, each on a different number of notes, the way a library of a
    thousand links ends up: the row of them grows longer than the screen."""
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    for n in range(30):
        # Tag n goes on (30 - n) notes, so t00 is the most used and t29 the
        # least: the order is known and nothing ties.
        for copy in range(30 - n):
            write_note(cfg, note(f"n{n}x{copy}", f"Nota {n}-{copy}", "Redes",
                                 [f"t{n:02d}"], "Un resumen."), "es")
    rebuild_indexes(cfg, "es")
    return TestClient(create_app(cfg))


def tag_chips(body):
    """(the tags shown at once, the tags behind the disclosure)."""
    head, _, tail = body.partition('<details class="more-tags"')
    found = lambda part: re.findall(r'class="chip small[^"]*">#([^<]+)</a>', part)
    return found(head), found(tail)


def test_only_the_most_used_tags_are_shown_at_once(many_tags):
    """A row of ninety-five chips pushes the cards themselves off the screen,
    and the answer to "what did I save" should not be below the fold.

    The twelve is written out rather than taken from TAGS_SHOWN: a test that
    builds what it expects out of the number it is checking agrees with any
    number at all, and this one is a judgement about a screen.
    """
    shown, _ = tag_chips(many_tags.get("/").text)

    assert len(shown) == 12
    assert shown == [f"t{n:02d}" for n in range(12)]      # most used first


def test_the_rest_of_the_tags_are_one_click_away_and_not_gone(many_tags):
    """Dropping them would make a tag on four notes unreachable from the page
    whose whole job is finding things."""
    shown, hidden = tag_chips(many_tags.get("/").text)

    assert hidden == [f"t{n:02d}" for n in range(12, 30)]
    assert sorted(shown + hidden) == sorted(f"t{n:02d}" for n in range(30))


def test_the_tag_being_filtered_by_is_shown_however_rare_it_is(many_tags):
    """Otherwise the page gives no sign of what it is filtered by: the one chip
    that would say so is behind the fold."""
    body = many_tags.get("/?tag=t29").text
    shown, hidden = tag_chips(body)

    assert "t29" in shown
    assert "t29" not in hidden        # twice on a page is one of them wrong
    assert 'class="chip small on">#t29</a>' in body


def test_pulling_a_rare_tag_forward_does_not_push_a_common_one_out(many_tags):
    """The row is already the length it was; the filtered tag is one more."""
    shown, _ = tag_chips(many_tags.get("/?tag=t29").text)

    assert shown == [f"t{n:02d}" for n in range(12)] + ["t29"]


def test_a_short_tag_row_gets_no_more_at_all(client):
    """Two tags behind a disclosure is a disclosure that hides nothing."""
    assert '<details class="more-tags"' not in client.get("/").text


def test_a_tag_belongs_to_the_category_it_is_used_in_most(tmp_path):
    """Half the tags are used under two categories. Each chip is one chip, so
    it has to sit in one group, and the one it is mostly about is that group."""
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    for n in range(3):
        write_note(cfg, note(f"r{n}", f"Red {n}", "Redes", ["python"], "x"), "es")
    write_note(cfg, note("c1", "Cocina 1", "Cocina", ["python"], "x"), "es")
    rebuild_indexes(cfg, "es")
    library = web.index.Library(cfg)
    library.refresh()

    assert library.tag_home()["python"] == "Redes"


def test_a_tag_used_evenly_lands_in_the_same_group_every_time(tmp_path):
    """A tie decided by whichever note was read first would move the chip
    around between page loads, for no reason the user could ever see."""
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    write_note(cfg, note("z1", "Zeta", "Zeta", ["python"], "x"), "es")
    write_note(cfg, note("a1", "Alfa", "Alfa", ["python"], "x"), "es")
    rebuild_indexes(cfg, "es")
    library = web.index.Library(cfg)
    library.refresh()

    assert library.tag_home()["python"] == "Alfa"      # by name, not by luck


def grouped_fixture(tmp_path):
    """Three categories, each with its own tags, plus counts that put them in
    a known order when everything is flattened by use."""
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    plan = {"Redes": [("vpn", 5), ("dns", 3), ("ssh", 1)],
            "Cocina": [("pan", 4), ("masa", 2)],
            "Audio": [("mpv", 6), ("flac", 1)]}
    n = 0
    for category, tags in plan.items():
        for tag, count in tags:
            for _ in range(count):
                n += 1
                write_note(cfg, note(f"n{n}", f"Nota {n}", category, [tag], "x"), "es")
    rebuild_indexes(cfg, "es")
    return TestClient(create_app(cfg))


def test_the_visible_row_keeps_tags_of_a_category_next_to_each_other(tmp_path):
    """Pegadas, not titled: a title per group turns a one-line row into eight
    lines, which is the thing that was just fixed."""
    client = grouped_fixture(tmp_path)

    shown, _ = tag_chips(client.get("/").text)

    # mpv(6) leads Audio, vpn(5) leads Redes, pan(4) leads Cocina.
    assert shown == ["mpv", "flac", "vpn", "dns", "ssh", "pan", "masa"]


def test_the_hidden_half_is_grouped_under_the_category_names(tmp_path):
    """There is room in a disclosure for the titles there is no room for in
    the row, and eighty chips without them are a wall again."""
    client = grouped_fixture(tmp_path)
    body = client.get("/").text

    assert '<p class="group">Redes</p>' not in body      # nothing hidden yet
    assert '<details class="more-tags"' not in body


def test_a_long_tag_list_is_grouped_by_name_inside_the_disclosure(many_tags):
    body = many_tags.get("/").text

    assert '<details class="more-tags"' in body
    assert '<p class="group">' in body


def test_the_disclosure_counts_tags_and_not_groups(many_tags):
    """The groups inside it are a way of reading the list, not the list: a
    drawer that says "1 more tags" over eighteen chips is lying about them."""
    body = many_tags.get("/").text

    assert "18 more tags" in body


# --- colecciones -------------------------------------------------------------

@pytest.fixture
def collected(tmp_path):
    """Three notes across two categories, two of them in one project."""
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    write_note(cfg, note("a1", "WireGuard", "Redes", ["vpn"], "Un resumen.",
                         collections=["Casa nueva"]), "es")
    write_note(cfg, note("b2", "Masa madre", "Cocina", ["pan"], "Otro resumen.",
                         collections=["Casa nueva", "Leer después"]), "es")
    write_note(cfg, note("c3", "Hyprland", "Redes", ["vpn"], "Y otro."), "es")
    rebuild_indexes(cfg, "es")
    return TestClient(create_app(cfg))


def library_of(client):
    return client.app.state.library


def test_the_library_counts_how_many_notes_each_collection_has(collected):
    assert library_of(collected).collections() == {"Casa nueva": 2, "Leer después": 1}


def test_a_library_with_no_collections_has_none(client):
    assert library_of(client).collections() == {}


def test_filtering_by_collection_leaves_the_rest_out(collected):
    found = library_of(collected).filter(collection="Casa nueva")
    assert {n.id for n in found} == {"a1", "b2"}


def test_a_collection_and_a_category_are_asked_together(collected):
    found = library_of(collected).filter(category="Redes", collection="Casa nueva")
    assert [n.id for n in found] == ["a1"]


def test_the_page_filters_by_collection(collected):
    body = collected.get("/?collection=Casa nueva").text
    assert "WireGuard" in body and "Masa madre" in body
    assert "Hyprland" not in body


def test_searching_a_collection_name_finds_its_notes_first(collected):
    """The only word in a note the user chose themselves: it outranks a
    summary that happens to say the same thing."""
    hits, total = library_of(collected).search("casa")
    assert total == 2
    assert {h.note.id for h in hits} == {"a1", "b2"}


def test_the_collections_come_back_in_the_same_order_every_time(tmp_path):
    """Alphabetical, like the categories: a bucket that moves every time you
    file something into it is a bucket you have to go looking for."""
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    # Written in an order that is not the alphabet, and read back newest
    # first, so a missing sort would show.
    for n, names in enumerate([["Casa"], ["Mudanza"], ["Zapatos"]]):
        write_note(cfg, note(f"n{n}", f"Nota {n}", "Redes", ["x"], "Un resumen.",
                             collections=names), "es")
    rebuild_indexes(cfg, "es")

    found = TestClient(create_app(cfg)).app.state.library.collections()

    assert list(found) == ["Casa", "Mudanza", "Zapatos"]


def test_a_library_with_no_collections_draws_no_row_for_them(client):
    """An empty row is still a row: the gap under it is paid by everyone who
    never uses this."""
    assert 'class="chips mine"' not in client.get("/").text


def test_the_row_is_there_as_soon_as_there_is_one(collected):
    assert 'class="chips mine"' in collected.get("/").text


# --- la línea de tiempo ------------------------------------------------------

@pytest.fixture
def dated(tmp_path):
    """Notes across three years, one of them with a date nobody can read."""
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    plan = [("a1", "2021-11-05", "Redes", ["Casa"]),
            ("b2", "2021-11-20", "Redes", []),
            ("c3", "2021-03-02", "Cocina", ["Casa"]),
            ("d4", "2019-07-14", "Redes", []),
            ("e5", "2026-10-01", "Cocina", [])]
    for n, (lid, saved, category, collections) in enumerate(plan):
        write_note(cfg, note(lid, f"Nota {lid}", category, ["x"], "Un resumen.",
                             saved=saved, collections=collections), "es")
    broken = note("f6", "Nota rota", "Redes", ["x"], "Un resumen.", saved="2019-07-14")
    path = write_note(cfg, broken, "es")
    path.write_text(path.read_text().replace("saved: '2019-07-14'", "saved: alguna vez"))
    rebuild_indexes(cfg, "es")
    return TestClient(create_app(cfg))


def test_the_library_counts_the_notes_of_each_year(dated):
    assert library_of(dated).years() == {"2026": 1, "2021": 3, "2019": 1, "undated": 1}


def test_the_years_come_newest_first(dated):
    assert list(library_of(dated).years())[:3] == ["2026", "2021", "2019"]


def test_undated_comes_last_whatever_it_sorts_like(dated):
    """It is not a year and it is not 2026: it goes at the foot of the strip,
    where a note whose date was typed over can still be found."""
    assert list(library_of(dated).years())[-1] == "undated"


def test_a_library_where_every_date_reads_has_no_undated_entry(client):
    assert "undated" not in library_of(client).years()


def test_the_library_counts_the_notes_of_each_month(dated):
    assert library_of(dated).months() == {"2026-10": 1, "2021-11": 2,
                                          "2021-03": 1, "2019-07": 1}


def test_filtering_by_a_year_leaves_the_other_years_out(dated):
    assert {n.id for n in library_of(dated).filter(when="2021")} == {"a1", "b2", "c3"}


def test_filtering_by_a_month_is_narrower_than_its_year(dated):
    assert {n.id for n in library_of(dated).filter(when="2021-11")} == {"a1", "b2"}


def test_a_note_whose_date_cannot_be_read_is_still_reachable(dated):
    assert [n.id for n in library_of(dated).filter(when="undated")] == ["f6"]


def test_a_period_this_library_does_not_have_matches_nothing(dated):
    """Not everything: a filter that quietly gives up shows the whole library
    and lets the user believe that was the answer."""
    assert library_of(dated).filter(when="2017") == []
    assert library_of(dated).filter(when="hola") == []
    # Not a month, and a prefix match would hand back October to December.
    assert library_of(dated).filter(when="2021-1") == []


def test_a_period_and_a_collection_are_asked_together(dated):
    found = library_of(dated).filter(collection="Casa", when="2021-11")
    assert [n.id for n in found] == ["a1"]


def strip(body):
    """(what the strip links, what it draws dimmed and unclickable)."""
    nav = re.search(r'<nav class="timeline".*?</nav>', body, re.S)
    if nav is None:
        return None, None
    live = re.findall(r'<a href="([^"]*)"[^>]*>\s*([^<]+?)\s*<b>(\d+)</b>', nav.group(0))
    return live, re.findall(r'<span class="[^"]*off">([^<]+)</span>', nav.group(0))


def test_the_strip_counts_what_the_other_filters_left(dated):
    """With a project chosen it answers "which years does this live in", so
    the numbers are of that project and not of the library."""
    live, _ = strip(dated.get("/?collection=Casa").text)

    assert [(name, n) for _, name, n in live] == [("All", "2"), ("2021", "2")]


def test_a_year_with_nothing_of_what_you_are_looking_at_is_still_drawn(dated):
    """Where a project is not is as much of an answer as where it is, and a
    strip that changes shape every click is one you cannot read."""
    _, off = strip(dated.get("/?collection=Casa").text)

    assert off == ["2026", "2019", "Undated"]


def test_the_whole_library_fills_the_strip(dated):
    live, off = strip(dated.get("/").text)

    assert [(name, n) for _, name, n in live] == [
        ("All", "6"), ("2026", "1"), ("2021", "3"), ("2019", "1"), ("Undated", "1")]
    assert off == []


def test_only_the_year_you_are_in_opens_its_months(dated):
    live, _ = strip(dated.get("/?when=2021").text)

    assert [name for _, name, _ in live] == ["All", "2026", "2021", "Nov", "Mar",
                                             "2019", "Undated"]


def test_no_year_is_open_until_one_is_chosen(dated):
    live, _ = strip(dated.get("/").text)

    assert "Nov" not in [name for _, name, _ in live]


def test_a_month_opens_its_own_year(dated):
    live, _ = strip(dated.get("/?when=2021-11").text)

    assert "Mar" in [name for _, name, _ in live]      # the year is still open
    assert 'class="month on"' in dated.get("/?when=2021-11").text


def test_travelling_in_time_keeps_what_you_were_looking_at(dated):
    """The two axes cross, they do not compete: choosing a year must not undo
    the project you chose first."""
    live, _ = strip(dated.get("/?collection=Casa").text)

    assert all("collection=Casa" in href for href, _, _ in live)


def test_the_chips_keep_the_period(dated):
    body = dated.get("/?when=2021").text
    chips = re.findall(r'<a href="(/\?(?:category|tag|collection)=[^"]*)"', body)

    assert chips and all("when=2021" in href for href in chips)


def test_the_tags_behind_the_disclosure_keep_it_too(many_tags):
    """Eighteen of the thirty are down there, and they are chips like the
    others: clicking one must not cost the year."""
    body = many_tags.get("/?when=2026").text
    hidden = body.partition('<details class="more-tags"')[2]
    chips = re.findall(r'<a href="(/\?tag=[^"]*)"', hidden)

    assert len(chips) == 18
    assert all("when=2026" in href for href in chips)


def test_the_way_out_of_a_period_keeps_what_you_were_looking_at(dated):
    live, _ = strip(dated.get("/?collection=Casa&when=2021").text)
    out = live[0][0]

    assert out == "/?collection=Casa"


def test_the_search_results_have_no_strip_of_time(dated):
    """They are ordered by how well they match, and a strip of time beside a
    list that is not in time order lies about the order it is in."""
    assert strip(dated.get("/search?q=resumen").text) == (None, None)
