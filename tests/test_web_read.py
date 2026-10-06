import os
import re
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge import web
from oknowledge.i18n import STRINGS
from oknowledge.model import Mention, Note
from oknowledge.urls import search_url
from oknowledge.vault import rebuild_indexes, write_note
from oknowledge.web.app import create_app


def note(id, title, category, tags, summary, body=None, saved="2026-10-03",
         type="article", mentions=None):
    return Note(
        id=id, url=f"https://e.com/{id}", title=title, category=category, tags=list(tags),
        type=type, source="e.com", saved=saved, summary=summary,
        points=["un punto"], body=body, mentions=mentions,
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


def test_the_interface_follows_the_shared_language_file(tmp_path, isolated_ui_language):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    isolated_ui_language.write_text('{"language": "es"}', encoding="utf-8")
    body = TestClient(create_app(Config(vault=vault))).get("/").text
    assert "Buscá en tu biblioteca" in body


def test_the_interface_is_english_without_the_shared_file(client):
    body = client.get("/").text
    assert "Search your library" in body
    assert "Buscá" not in body


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


def test_the_unreadable_count_is_plural_and_translated(tmp_path, isolated_ui_language):
    cfg = make_cfg(tmp_path)
    for i in range(2):
        break_note(write_note(cfg, note(f"x{i}", f"T{i}", "Redes", ["x"], "S."), "es"))
    isolated_ui_language.write_text('{"language": "es"}', encoding="utf-8")
    body = TestClient(create_app(cfg)).get("/").text
    assert "2 notas no se pudieron leer y no se muestran" in body


def test_no_warning_when_every_note_reads(client):
    assert "could not be read" not in client.get("/").text


# --- ruling 3: a disk error is a readable page --------------------------------------


def test_an_unreadable_vault_renders_a_page_with_the_path(tmp_path, monkeypatch):
    from oknowledge.web import index

    cfg = make_cfg(tmp_path)
    client = TestClient(create_app(cfg))

    def boom(cfg):
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

    def boom(cfg):
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
