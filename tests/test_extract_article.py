from pathlib import Path

import httpx
import pytest

from oknowledge import net
from oknowledge.extract import Unreadable, detect_type
from oknowledge.extract.article import from_html, from_url

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "article.html"


@pytest.fixture
def html():
    return FIXTURE.read_text(encoding="utf-8")


def test_a_byte_order_mark_does_not_survive_into_the_text():
    body = "Hola".encode("utf-8-sig")
    assert net.Fetched(200, "text/html; charset=utf-8-sig", body, "https://e.com/a").text == "Hola"


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
    ("https://www.youtube.com/shorts/abc", "youtube"),
    ("https://m.youtube.com/watch?v=abc", "youtube"),
    ("https://music.youtube.com/watch?v=abc", "youtube"),
    ("https://www.youtube-nocookie.com/embed/abc", "youtube"),
    ("HTTPS://WWW.YOUTUBE.COM/watch?v=abc", "youtube"),
    ("youtube.com/watch?v=x", "youtube"),
    ("https://github.com/user", "github"),
    ("https://example.com/Paper.PDF?download=1", "pdf"),
    ("https://mobile.twitter.com/user/status/1", "social"),
    ("https://vm.tiktok.com/abc", "social"),
    ("https://old.reddit.com/r/linux", "social"),
    ("https://notyoutube.com/watch", "article"),
    ("https://box.com/x", "article"),
])
def test_the_type_is_guessed_from_the_url(url, expected):
    assert detect_type(url) == expected


# --- the download layer, served by an in-process transport (no sockets) ---

@pytest.fixture
def serve(monkeypatch):
    """Route net.fetch through an httpx MockTransport instead of the network."""
    clients = []
    requests = []

    def install(handler):
        real_client = httpx.Client

        def recording(request):
            requests.append(request)
            return handler(request)

        def client(**kwargs):
            made = real_client(transport=httpx.MockTransport(recording), **kwargs)
            clients.append(made)
            return made

        monkeypatch.setattr(net.httpx, "Client", client)
        return requests

    yield install
    for made in clients:
        made.close()


def fixture_page(name):
    return (FIXTURES / name).read_bytes()


def html_response(content, **headers):
    return httpx.Response(200, content=content,
                          headers={"content-type": "text/html", **headers})


def test_fetch_returns_the_body_and_follows_redirects(serve, html):
    def handler(request):
        if request.url.path == "/old":
            return httpx.Response(301, headers={"location": "https://e.com/new"})
        return html_response(html.encode(), **{"content-type": "text/html; charset=utf-8"})

    serve(handler)
    fetched = net.fetch("https://e.com/old")
    assert fetched.status == 200
    assert fetched.final_url == "https://e.com/new"
    assert "runs inside the kernel" in fetched.text


def test_the_request_carries_our_headers_and_timeout(serve):
    requests = serve(lambda request: html_response(b"ok"))
    net.fetch("https://e.com/x", timeout=7.0)
    sent = requests[0]
    assert sent.headers["user-agent"] == net.USER_AGENT
    assert sent.headers["accept-language"] == net.ACCEPT_LANGUAGE
    assert sent.extensions["timeout"]["read"] == 7.0
    assert sent.extensions["timeout"]["connect"] == 7.0


@pytest.mark.parametrize("status", [403, 404, 500])
def test_an_error_status_is_a_network_error_naming_the_status(serve, status):
    serve(lambda request: httpx.Response(status))
    with pytest.raises(net.NetworkError, match=str(status)):
        net.fetch("https://e.com/x")


def test_an_error_status_carries_the_status_and_headers_for_the_caller(serve):
    serve(lambda request: httpx.Response(403, headers={"X-RateLimit-Remaining": "0"}))
    with pytest.raises(net.NetworkError) as raised:
        net.fetch("https://e.com/x")
    assert raised.value.status == 403
    assert raised.value.headers["x-ratelimit-remaining"] == "0"


@pytest.mark.parametrize("error,word", [
    (httpx.ConnectTimeout, "ConnectTimeout"),
    (httpx.ReadTimeout, "ReadTimeout"),
    (httpx.ConnectError, "ConnectError"),
])
def test_a_connection_failure_names_what_happened_even_with_an_empty_message(
        serve, error, word):
    def handler(request):
        raise error("", request=request)

    serve(handler)
    with pytest.raises(net.NetworkError) as raised:
        net.fetch("https://e.com/x")
    assert str(raised.value).endswith(word)


def test_a_non_http_scheme_is_refused_with_a_clear_message():
    with pytest.raises(net.NetworkError, match="only http and https"):
        net.fetch("file:///etc/passwd")
    with pytest.raises(net.NetworkError, match="only http and https"):
        net.fetch("ftp://e.com/x")


def test_a_redirect_loop_gives_up(serve):
    serve(lambda request: httpx.Response(302, headers={"location": "https://e.com/again"}))
    with pytest.raises(net.NetworkError, match="TooManyRedirects"):
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


def test_the_default_cap_applies_when_no_limit_is_given(serve, monkeypatch):
    monkeypatch.setattr(net, "MAX_BYTES", 1024)
    serve(lambda request: httpx.Response(200, content=b"x" * 4096))
    with pytest.raises(net.NetworkError, match="over 1024"):
        net.fetch("https://e.com/big")


def test_a_declared_huge_length_is_refused_before_reading(serve):
    serve(lambda request: httpx.Response(
        200, content=b"x", headers={"content-length": str(500 * 1024 * 1024)}))
    with pytest.raises(net.NetworkError, match="over"):
        net.fetch("https://e.com/big", max_bytes=1024)


def test_a_download_that_outlasts_the_deadline_is_abandoned(serve, monkeypatch):
    ticks = iter(range(0, 10_000, 40))     # each clock read jumps 40 s
    monkeypatch.setattr(net.time, "monotonic", lambda: next(ticks))
    serve(lambda request: httpx.Response(200, content=iter([b"a", b"b", b"c"])))
    with pytest.raises(net.NetworkError, match="too slow"):
        net.fetch("https://e.com/slow", timeout=30.0)


def test_the_charset_from_the_header_is_honoured(serve):
    page = "<html><body><p>caf\u00e9 ni\u00f1o</p></body></html>"
    serve(lambda request: httpx.Response(
        200, content=page.encode("latin-1"),
        headers={"content-type": "text/html; charset=iso-8859-1"}))
    assert "caf\u00e9 ni\u00f1o" in net.fetch("https://e.com/x").text


def test_the_charset_from_a_meta_tag_wins_when_the_header_is_silent(serve):
    page = '<html><head><meta charset="windows-1252"></head><body>caf\u00e9</body></html>'
    serve(lambda request: html_response(page.encode("cp1252")))
    assert "caf\u00e9" in net.fetch("https://e.com/x").text


def test_an_unknown_charset_falls_back_to_utf8(serve):
    serve(lambda request: html_response(
        "caf\u00e9".encode(), **{"content-type": "text/html; charset=klingon"}))
    assert net.fetch("https://e.com/x").text == "caf\u00e9"


@pytest.mark.parametrize("name", ["base64", "zlib", "hex", "rot13"])
def test_a_binary_codec_as_charset_does_not_raise(serve, name):
    serve(lambda request: html_response(
        "caf\u00e9".encode(), **{"content-type": f"text/html; charset={name}"}))
    assert net.fetch("https://e.com/x").text == "caf\u00e9"


def test_a_binary_codec_in_a_meta_tag_does_not_raise(serve):
    serve(lambda request: html_response(b'<meta charset="zlib"><p>hola</p>'))
    assert "hola" in net.fetch("https://e.com/x").text


def test_utf8_wins_when_the_header_claims_latin1_but_the_bytes_are_utf8(serve, html):
    page = html.replace("hardware", "hardware \u2014 caf\u00e9 ni\u00f1o").encode("utf-8")
    serve(lambda request: html_response(
        page, **{"content-type": "text/html; charset=iso-8859-1"}))
    out = from_url("https://arstechnica.com/vpn")
    assert "caf\u00e9 ni\u00f1o" in out.text
    assert "\u00c3" not in out.text


def test_from_url_reads_a_served_page(serve, html):
    serve(lambda request: html_response(html.encode()))
    assert from_url("https://arstechnica.com/vpn").title == "WireGuard vs OpenVPN"


def test_from_url_uses_the_page_it_landed_on_not_the_shortener(serve, html):
    def handler(request):
        if request.url.host == "bit.ly":
            return httpx.Response(301, headers={"location": "https://arstechnica.com/vpn"})
        return html_response(html.encode())

    serve(handler)
    assert from_url("https://bit.ly/abc").source == "arstechnica.com"


def test_from_url_never_leaves_replacement_characters_for_a_bad_charset(serve, html):
    meta = '<meta charset="windows-1252">'
    page = html.replace("<head>", "<head>" + meta).replace(
        "hardware", "hardware caf\u00e9 ni\u00f1o").encode("cp1252")
    serve(lambda request: html_response(
        page, **{"content-type": "text/html; charset=klingon"}))
    out = from_url("https://arstechnica.com/vpn")
    assert "caf\u00e9 ni\u00f1o" in out.text
    assert "\ufffd" not in out.text


def test_from_url_refuses_a_non_html_response_with_a_clear_reason(serve):
    serve(lambda request: httpx.Response(
        200, content=b"%PDF-1.7 ...", headers={"content-type": "application/pdf"}))
    with pytest.raises(Unreadable, match="application/pdf"):
        from_url("https://e.com/download")


@pytest.mark.parametrize("name", ["spa_shell.html", "cookie_wall.html", "just_below.html"])
def test_pages_without_enough_prose_are_unreadable_with_a_reason(name):
    html = (FIXTURES / name).read_text(encoding="utf-8")
    with pytest.raises(Unreadable, match="JavaScript or a login"):
        from_html(html, "https://e.com/x")


def test_a_page_just_above_the_threshold_is_read():
    html = (FIXTURES / "just_above.html").read_text(encoding="utf-8")
    assert "scheduler wakes" in from_html(html, "https://e.com/x").text


def test_a_parser_crash_becomes_unreadable(monkeypatch):
    def boom(*args, **kwargs):
        raise RecursionError("deep dom")

    monkeypatch.setattr("oknowledge.extract.article.trafilatura.extract", boom)
    with pytest.raises(Unreadable, match="RecursionError"):
        from_html("<p>x</p>", "https://e.com/x")
