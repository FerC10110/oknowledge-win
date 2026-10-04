from pathlib import Path

import httpx
import pytest

from oknowledge import net
from oknowledge.extract import Unreadable, detect_type
from oknowledge.extract.article import from_html, from_url

FIXTURE = Path(__file__).parent / "fixtures" / "article.html"


@pytest.fixture
def html():
    return FIXTURE.read_text(encoding="utf-8")


def test_the_article_text_comes_out_and_the_chrome_does_not(html):
    out = from_html(html, "https://arstechnica.com/vpn")
    assert "runs inside the kernel" in out.text
    assert "hostile middleboxes" in out.text
    assert "Subscribe now" not in out.text
    assert "only 2.99 a month" not in out.text
    assert "Cookie preferences" not in out.text


def test_the_metadata_comes_out(html):
    out = from_html(html, "https://arstechnica.com/vpn")
    assert out.title == "WireGuard vs OpenVPN"
    assert out.author == "Dan Goodin"
    assert out.published == "2026-09-28"
    assert out.cover_url == "https://cdn.example.com/wg.jpg"
    assert out.source == "arstechnica.com"
    assert out.type == "article"


def test_a_page_with_no_text_is_unreadable():
    with pytest.raises(Unreadable):
        from_html("<html><body><nav>menu</nav></body></html>", "https://e.com/x")


@pytest.mark.parametrize("url,expected", [
    ("https://arstechnica.com/vpn", "article"),
    ("https://www.youtube.com/watch?v=abc", "youtube"),
    ("https://youtu.be/abc", "youtube"),
    ("https://github.com/sst/opencode", "github"),
    ("https://github.com/sst/opencode/issues/4", "github"),
    ("https://example.com/paper.pdf", "pdf"),
    ("https://example.com/paper.PDF?x=1", "pdf"),
    ("https://www.reddit.com/r/linux/comments/x/y/", "social"),
    ("https://x.com/user/status/1", "social"),
    ("https://twitter.com/user/status/1", "social"),
    ("https://www.instagram.com/p/abc/", "social"),
    ("https://www.tiktok.com/@u/video/1", "social"),
])
def test_the_type_is_guessed_from_the_url(url, expected):
    assert detect_type(url) == expected


# --- the download layer, served by an in-process transport (no sockets) ---

@pytest.fixture
def serve(monkeypatch):
    """Route net.fetch through an httpx MockTransport instead of the network."""

    def install(handler):
        real_client = httpx.Client

        def stream(method, url, **kwargs):
            client = real_client(transport=httpx.MockTransport(handler))
            return client.stream(method, url, **kwargs)

        monkeypatch.setattr(net.httpx, "stream", stream)

    return install


def test_fetch_returns_the_body_and_follows_redirects(serve, html):
    def handler(request):
        if request.url.path == "/old":
            return httpx.Response(301, headers={"location": "https://e.com/new"})
        return httpx.Response(200, content=html.encode(),
                              headers={"content-type": "text/html; charset=utf-8"})

    serve(handler)
    fetched = net.fetch("https://e.com/old")
    assert fetched.status == 200
    assert fetched.final_url == "https://e.com/new"
    assert "runs inside the kernel" in fetched.text


@pytest.mark.parametrize("status", [403, 404, 500])
def test_an_error_status_is_a_network_error_naming_the_status(serve, status):
    serve(lambda request: httpx.Response(status))
    with pytest.raises(net.NetworkError, match=str(status)):
        net.fetch("https://e.com/x")


def test_a_connection_failure_is_a_network_error(serve):
    def handler(request):
        raise httpx.ConnectTimeout("timed out", request=request)

    serve(handler)
    with pytest.raises(net.NetworkError, match="could not fetch"):
        net.fetch("https://e.com/x")


def test_a_huge_response_is_cut_off_instead_of_downloaded(serve):
    pulled = []

    def body():
        for _ in range(1000):
            pulled.append(1)
            yield b"x" * 1024

    serve(lambda request: httpx.Response(200, content=body()))
    with pytest.raises(net.NetworkError, match="over"):
        net.fetch("https://e.com/big", max_bytes=10 * 1024)
    assert len(pulled) < 100


def test_a_declared_huge_length_is_refused_before_reading(serve):
    serve(lambda request: httpx.Response(
        200, content=b"x", headers={"content-length": str(500 * 1024 * 1024)}))
    with pytest.raises(net.NetworkError, match="over"):
        net.fetch("https://e.com/big", max_bytes=1024)


def test_the_charset_from_the_header_is_honoured(serve):
    page = "<html><body><p>café niño</p></body></html>"
    serve(lambda request: httpx.Response(
        200, content=page.encode("latin-1"),
        headers={"content-type": "text/html; charset=iso-8859-1"}))
    assert "café niño" in net.fetch("https://e.com/x").text


def test_the_charset_from_a_meta_tag_wins_when_the_header_is_silent(serve):
    page = '<html><head><meta charset="windows-1252"></head><body>café</body></html>'
    serve(lambda request: httpx.Response(
        200, content=page.encode("cp1252"), headers={"content-type": "text/html"}))
    assert "café" in net.fetch("https://e.com/x").text


def test_an_unknown_charset_falls_back_to_utf8(serve):
    serve(lambda request: httpx.Response(
        200, content="café".encode(),
        headers={"content-type": "text/html; charset=klingon"}))
    assert net.fetch("https://e.com/x").text == "café"


def test_from_url_reads_a_served_page(serve, html):
    serve(lambda request: httpx.Response(
        200, content=html.encode(), headers={"content-type": "text/html"}))
    assert from_url("https://arstechnica.com/vpn").title == "WireGuard vs OpenVPN"


def test_from_url_refuses_a_non_html_response_with_a_clear_reason(serve):
    serve(lambda request: httpx.Response(
        200, content=b"%PDF-1.7 ...", headers={"content-type": "application/pdf"}))
    with pytest.raises(Unreadable, match="application/pdf"):
        from_url("https://e.com/download")
