import base64
import json
import subprocess
from pathlib import Path

import pytest

from oknowledge import net
from oknowledge.extract import Unreadable, article, extract, github, pdf, social, youtube

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def make_pdf(tmp_path, encrypt=None, author=None, title=None):
    from reportlab.pdfgen import canvas

    path = tmp_path / "paper.pdf"
    page = canvas.Canvas(str(path), encrypt=encrypt)
    if author:
        page.setAuthor(author)
    if title:
        page.setTitle(title)
    page.drawString(72, 720, "Resultados del experimento")
    page.drawString(72, 700, "La latencia bajo a la mitad")
    page.save()
    return path.read_bytes()


@pytest.fixture(autouse=True)
def no_network_and_no_ytdlp(monkeypatch):
    """Whatever a test forgets to fake fails loudly instead of reaching out.
    (tests/conftest.py also blocks httpx and subprocess for every module.)"""

    def refuse(*args, **kwargs):
        raise AssertionError("a test reached the network or ran yt-dlp")

    for module in (youtube, github, pdf, social, article):
        monkeypatch.setattr(module, "fetch", refuse)


def served(responses):
    """A fake fetch: maps a URL to a Fetched, or to a NetworkError to raise."""
    calls = []

    def fake(url, **kwargs):
        calls.append(url)
        answer = responses[url]
        if isinstance(answer, Exception):
            raise answer
        return answer

    fake.calls = calls
    return fake


def reply(body, content_type="application/json", url="https://x"):
    content = body if isinstance(body, bytes) else body.encode("utf-8")
    return net.Fetched(status=200, content_type=content_type, content=content, final_url=url)


# --- YouTube -----------------------------------------------------------------

def test_a_youtube_video_becomes_title_channel_description_and_transcript():
    out = youtube.from_ytdlp(
        load("ytdlp.json"),
        "https://youtube.com/watch?v=abc",
        captions=(FIXTURES / "captions.vtt").read_text(encoding="utf-8"),
    )
    assert out.title == "Cómo funciona WireGuard"
    assert out.author == "Redes en 10"
    assert out.published == "2026-09-15"
    assert out.type == "youtube"
    assert out.cover_url == "https://i.ytimg.com/vi/abc/hq.jpg"
    assert "Explicación corta" in out.text
    assert "cómo funciona WireGuard" in out.text
    assert "más rápido que OpenVPN" in out.text


def test_the_transcript_loses_timestamps_tags_and_repeats():
    vtt = (FIXTURES / "captions.vtt").read_text(encoding="utf-8")
    text = youtube.vtt_to_text(vtt)
    assert "-->" not in text
    assert "WEBVTT" not in text
    assert "<c>" not in text
    assert text.startswith("Hola, hoy vemos")


def test_a_video_without_transcript_still_gives_a_note():
    out = youtube.from_ytdlp(load("ytdlp.json"), "https://youtube.com/watch?v=abc", captions=None)
    assert "Explicación corta" in out.text
    assert out.title == "Cómo funciona WireGuard"


def test_a_video_with_neither_transcript_nor_description_is_unreadable():
    data = dict(load("ytdlp.json"), description="")
    with pytest.raises(Unreadable):
        youtube.from_ytdlp(data, "https://youtube.com/watch?v=abc", captions=None)


def fake_ytdlp(monkeypatch, stdout="", stderr="", returncode=0, raises=None):
    seen = {}

    def run(cmd, **kwargs):
        seen["cmd"], seen["kwargs"] = cmd, kwargs
        if raises:
            raise raises
        return subprocess.CompletedProcess(cmd, returncode, stdout, stderr)

    monkeypatch.setattr(youtube.subprocess, "run", run)
    return seen


def test_from_url_runs_ytdlp_for_one_video_and_reads_the_vtt_track(monkeypatch):
    seen = fake_ytdlp(monkeypatch, stdout=(FIXTURES / "ytdlp.json").read_text(encoding="utf-8"))
    vtt = (FIXTURES / "captions.vtt").read_text(encoding="utf-8")
    monkeypatch.setattr(
        youtube, "fetch", served({"https://example.com/captions.vtt": reply(vtt, "text/vtt")}))

    out = youtube.from_url("https://youtube.com/watch?v=abc")

    assert "más rápido que OpenVPN" in out.text
    assert seen["cmd"][0] == "yt-dlp"
    assert "--no-playlist" in seen["cmd"]
    assert seen["cmd"][-2:] == ["--", "https://youtube.com/watch?v=abc"]
    assert seen["kwargs"]["timeout"] > 0


def test_from_url_keeps_the_note_when_the_captions_cannot_be_fetched(monkeypatch):
    fake_ytdlp(monkeypatch, stdout=(FIXTURES / "ytdlp.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(
        youtube, "fetch",
        served({"https://example.com/captions.vtt": net.NetworkError("429")}))
    out = youtube.from_url("https://youtube.com/watch?v=abc")
    assert "Explicación corta" in out.text


@pytest.mark.parametrize("failure", [
    dict(raises=FileNotFoundError("yt-dlp")),
    dict(raises=subprocess.TimeoutExpired("yt-dlp", 120)),
    dict(returncode=1, stderr="ERROR: Video unavailable. This video is private"),
    dict(stdout="not json at all"),
    dict(stdout="[1, 2]"),
])
def test_every_ytdlp_failure_is_unreadable_with_a_reason(monkeypatch, failure):
    fake_ytdlp(monkeypatch, **failure)
    with pytest.raises(Unreadable) as raised:
        youtube.from_url("https://youtube.com/watch?v=abc")
    assert "youtube.com/watch?v=abc" in str(raised.value)


def test_a_private_video_message_says_what_ytdlp_said(monkeypatch):
    fake_ytdlp(monkeypatch, returncode=1, stderr="ERROR: Video unavailable. This video is private")
    with pytest.raises(Unreadable, match="private"):
        youtube.from_url("https://youtube.com/watch?v=abc")


# --- GitHub ------------------------------------------------------------------

def test_a_github_repo_becomes_description_facts_and_readme():
    out = github.from_api(
        load("github_repo.json"),
        "# opencode\n\nCorre en la terminal y no necesita API key.\n",
        "https://github.com/sst/opencode",
    )
    assert out.title == "sst/opencode"
    assert out.type == "github"
    assert out.author == "sst"
    assert "AI coding agent" in out.text
    assert "TypeScript" in out.text
    assert "31245" in out.text or "31,245" in out.text
    assert "no necesita API key" in out.text


def test_a_repo_without_readme_uses_what_it_has():
    out = github.from_api(load("github_repo.json"), "", "https://github.com/sst/opencode")
    assert "AI coding agent" in out.text


API = "https://api.github.com/repos/sst/opencode"


def readme_payload(text):
    return json.dumps({"content": base64.b64encode(text.encode()).decode() + "\n"})


def test_from_url_reads_the_repo_and_its_readme(monkeypatch):
    fake = served({
        API: reply((FIXTURES / "github_repo.json").read_text(encoding="utf-8")),
        API + "/readme": reply(readme_payload("Corre en la terminal.")),
    })
    monkeypatch.setattr(github, "fetch", fake)
    out = github.from_url("https://github.com/sst/opencode/tree/dev/packages?tab=x")
    assert "Corre en la terminal." in out.text
    assert fake.calls == [API, API + "/readme"]


def test_from_url_accepts_a_dot_git_suffix(monkeypatch):
    fake = served({API: reply((FIXTURES / "github_repo.json").read_text(encoding="utf-8")),
                   API + "/readme": net.NetworkError("404", status=404)})
    monkeypatch.setattr(github, "fetch", fake)
    github.from_url("https://github.com/sst/opencode.git")
    assert fake.calls[0] == API


def test_from_url_survives_a_missing_readme(monkeypatch):
    monkeypatch.setattr(github, "fetch", served({
        API: reply((FIXTURES / "github_repo.json").read_text(encoding="utf-8")),
        API + "/readme": net.NetworkError("404 for readme", status=404),
    }))
    assert "AI coding agent" in github.from_url("https://github.com/sst/opencode").text


def test_from_url_survives_a_garbled_readme(monkeypatch):
    monkeypatch.setattr(github, "fetch", served({
        API: reply((FIXTURES / "github_repo.json").read_text(encoding="utf-8")),
        API + "/readme": reply('{"content": "!!!not base64!!!"}'),
    }))
    assert "AI coding agent" in github.from_url("https://github.com/sst/opencode").text


def test_a_missing_repo_that_is_not_a_page_either_says_missing_or_private(monkeypatch):
    monkeypatch.setattr(github, "fetch", served({API: net.NetworkError("404", status=404)}))
    monkeypatch.setattr(article, "from_url", served({
        "https://github.com/sst/opencode": net.NetworkError("404 for page", status=404)}))
    with pytest.raises(Unreadable, match="not found or private"):
        github.from_url("https://github.com/sst/opencode")


def test_a_404_from_the_api_falls_back_to_the_page(monkeypatch):
    """github.com/solutions/... looks like owner/repo but is a site page."""
    sentinel = object()
    monkeypatch.setattr(github, "fetch", served({
        "https://api.github.com/repos/solutions/ci": net.NetworkError("404", status=404)}))
    monkeypatch.setattr(article, "from_url", lambda u: sentinel)
    assert github.from_url("https://github.com/solutions/ci") is sentinel


def test_a_repo_with_no_description_and_no_readme_is_unreadable(monkeypatch):
    bare = dict(load("github_repo.json"), description=None)
    monkeypatch.setattr(github, "fetch", served({
        API: reply(json.dumps(bare)), API + "/readme": net.NetworkError("404", status=404)}))
    with pytest.raises(Unreadable, match="no description or readme"):
        github.from_url("https://github.com/sst/opencode")


@pytest.mark.parametrize("error", [
    net.NetworkError("500", status=500),
    net.NetworkError("could not fetch: ReadTimeout"),
    net.NetworkError("403", status=403, headers={"x-ratelimit-remaining": "0"}),
])
def test_a_readme_call_that_fails_for_another_reason_than_404_is_not_success(monkeypatch, error):
    monkeypatch.setattr(github, "fetch", served({
        API: reply((FIXTURES / "github_repo.json").read_text(encoding="utf-8")),
        API + "/readme": error}))
    with pytest.raises(Unreadable):
        github.from_url("https://github.com/sst/opencode")


def test_the_facts_are_in_english():
    out = github.from_api(dict(load("github_repo.json"), language=None), "", "https://github.com/sst/opencode")
    assert "Primary language: unknown." in out.text and "Stars: 31245." in out.text
    assert "Topics: ai, cli." in out.text


def test_a_rate_limited_api_says_so_and_when_it_resets(monkeypatch):
    limited = net.NetworkError("403", status=403, headers={
        "x-ratelimit-remaining": "0", "x-ratelimit-reset": "1790000000"})
    monkeypatch.setattr(github, "fetch", served({API: limited}))
    with pytest.raises(Unreadable, match="rate limit") as raised:
        github.from_url("https://github.com/sst/opencode")
    assert "2026-09-21 14:13 UTC" in str(raised.value)


def test_a_retry_after_header_is_a_rate_limit_too(monkeypatch):
    limited = net.NetworkError("429", status=429, headers={"retry-after": "60"})
    monkeypatch.setattr(github, "fetch", served({API: limited}))
    with pytest.raises(Unreadable, match="rate limit"):
        github.from_url("https://github.com/sst/opencode")


def test_a_plain_403_is_not_called_a_rate_limit(monkeypatch):
    monkeypatch.setattr(github, "fetch", served({API: net.NetworkError("403", status=403)}))
    with pytest.raises(Unreadable) as raised:
        github.from_url("https://github.com/sst/opencode")
    assert "rate limit" not in str(raised.value)


def test_a_non_json_api_answer_is_unreadable(monkeypatch):
    monkeypatch.setattr(github, "fetch", served({API: reply("<html>")}))
    with pytest.raises(Unreadable):
        github.from_url("https://github.com/sst/opencode")


@pytest.mark.parametrize("url", [
    "https://gist.github.com/someone/abcdef0123",
    "https://docs.github.com/en/actions",
    "https://github.com/someone",
    "https://github.com/",
    "https://github.com/features",
    "https://github.com/features/copilot",
    "https://github.com/orgs/vercel/people",
    "https://github.com/topics/cli",
    "https://github.com/sponsors/someone",
])
def test_a_github_url_that_is_not_a_repository_goes_to_the_article_extractor(monkeypatch, url):
    sentinel = object()
    asked = []
    monkeypatch.setattr(article, "from_url", lambda u: asked.append(u) or sentinel)
    # the autouse guard fails the test if the GitHub API were called
    assert github.from_url(url) is sentinel
    assert asked == [url]


def test_a_non_repository_page_that_is_too_thin_is_unreadable_not_a_crash(monkeypatch):
    def thin(url):
        raise Unreadable("too little text")

    monkeypatch.setattr(article, "from_url", thin)
    with pytest.raises(Unreadable):
        github.from_url("https://github.com/someone")


# --- PDF ---------------------------------------------------------------------

def test_a_pdf_becomes_text(tmp_path):
    out = pdf.from_bytes(make_pdf(tmp_path), "https://e.com/paper.pdf")
    assert "Resultados del experimento" in out.text
    assert "latencia" in out.text
    assert out.type == "pdf"
    assert out.title == "paper.pdf"


def test_a_pdfs_metadata_comes_out_as_plain_text_the_note_header_can_hold(tmp_path):
    # pypdf hands back its own str subclass, which yaml refuses to write: the
    # first real PDF with an author crashed `add` with exit 3.
    import yaml

    out = pdf.from_bytes(make_pdf(tmp_path, author="Ada Lovelace", title="On engines"),
                         "https://e.com/paper.pdf")
    assert (out.author, out.title) == ("Ada Lovelace", "On engines")
    assert type(out.author) is str and type(out.title) is str
    yaml.safe_dump({"author": out.author, "title": out.title})


def test_a_pdf_with_no_text_layer_is_unreadable():
    with pytest.raises(Unreadable):
        pdf.from_bytes(b"%PDF-1.4\n%%EOF\n", "https://e.com/scan.pdf")


def test_a_pdf_with_no_text_layer_says_so(tmp_path):
    from reportlab.pdfgen import canvas

    path = tmp_path / "blank.pdf"
    page = canvas.Canvas(str(path))
    page.rect(10, 10, 100, 100)
    page.save()
    with pytest.raises(Unreadable, match="no text layer"):
        pdf.from_bytes(path.read_bytes(), "https://e.com/blank.pdf")


def test_a_password_protected_pdf_says_it_is_encrypted(tmp_path):
    data = make_pdf(tmp_path, encrypt="secret")
    with pytest.raises(Unreadable, match="password"):
        pdf.from_bytes(data, "https://e.com/locked.pdf")


def test_a_pdf_with_an_empty_user_password_is_still_read(tmp_path):
    from reportlab.lib import pdfencrypt

    data = make_pdf(tmp_path, encrypt=pdfencrypt.StandardEncryption("", ownerPassword="owner"))
    assert "Resultados" in pdf.from_bytes(data, "https://e.com/p.pdf").text


@pytest.mark.parametrize("data", [b"", b"this is not a pdf", b"%PDF-1.7\n" + b"\x00" * 200])
def test_a_corrupt_pdf_is_unreadable_not_a_crash(data):
    with pytest.raises(Unreadable):
        pdf.from_bytes(data, "https://e.com/bad.pdf")


def test_pdf_from_url_turns_a_failed_download_into_unreadable(monkeypatch):
    monkeypatch.setattr(pdf, "fetch", served({
        "https://e.com/huge.pdf": net.NetworkError("page over 8388608 bytes: https://e.com/huge.pdf")}))
    with pytest.raises(Unreadable, match="over 8388608"):
        pdf.from_url("https://e.com/huge.pdf")


def test_pdf_from_url_reads_the_pdf_it_landed_on(monkeypatch, tmp_path):
    monkeypatch.setattr(pdf, "fetch", served({
        "https://e.com/short": reply(make_pdf(tmp_path), "application/pdf",
                                     url="https://e.com/files/paper.pdf")}))
    out = pdf.from_url("https://e.com/short")
    assert out.title == "paper.pdf"
    assert out.source == "e.com"


# --- the dispatcher re-routes on what the server answers ---------------------

def test_an_extensionless_url_that_serves_a_pdf_is_read_as_a_pdf(monkeypatch, tmp_path):
    url = "https://arxiv.org/pdf/2301.12345"
    monkeypatch.setattr(article, "fetch", served({
        url: reply(make_pdf(tmp_path), "application/pdf", url=url)}))
    out = extract(url)
    assert out.type == "pdf"
    assert "Resultados del experimento" in out.text


def test_a_pdf_content_type_with_parameters_is_still_a_pdf(monkeypatch, tmp_path):
    url = "https://arxiv.org/pdf/2301.12345"
    monkeypatch.setattr(article, "fetch", served({
        url: reply(make_pdf(tmp_path), "Application/PDF; charset=binary", url=url)}))
    assert extract(url).type == "pdf"


def test_other_non_html_responses_stay_unreadable(monkeypatch):
    url = "https://e.com/data"
    monkeypatch.setattr(article, "fetch", served({url: reply(b"\x89PNG", "image/png", url=url)}))
    with pytest.raises(Unreadable, match="image/png"):
        extract(url)


def test_a_normal_page_does_not_go_through_the_pdf_extractor(monkeypatch):
    url = "https://e.com/post"
    page = (FIXTURES / "article.html").read_bytes()
    monkeypatch.setattr(article, "fetch", served({url: reply(page, "text/html", url=url)}))
    assert extract(url).type == "article"


# --- social ------------------------------------------------------------------

def test_a_reddit_thread_becomes_post_plus_comments():
    out = social.from_reddit(load("reddit.json"), "https://reddit.com/r/linux/comments/x/y/")
    assert out.title == "Why I moved from OpenVPN to WireGuard"
    assert out.type == "social"
    assert "la latencia bajó a la mitad" in out.text
    assert "Raspberry Pi" in out.text


def test_a_network_that_blocks_us_is_unreadable_not_a_crash(monkeypatch):
    def boom(url, **kwargs):
        raise net.NetworkError("403")

    monkeypatch.setattr("oknowledge.extract.social.fetch", boom)
    with pytest.raises(Unreadable):
        social.from_url("https://x.com/user/status/1")


def test_reddit_from_url_asks_for_the_json_of_the_thread_not_of_its_query(monkeypatch):
    fake = served({
        "https://www.reddit.com/r/linux/comments/x/y.json":
            reply((FIXTURES / "reddit.json").read_text(encoding="utf-8"))})
    monkeypatch.setattr(social, "fetch", fake)
    out = social.from_url("https://www.reddit.com/r/linux/comments/x/y/?context=3")
    assert out.title == "Why I moved from OpenVPN to WireGuard"
    assert len(fake.calls) == 1


@pytest.mark.parametrize("body", ["<html>login</html>", '{"message": "Forbidden"}', "[]", "[1]"])
def test_reddit_answers_that_are_not_a_thread_are_unreadable(monkeypatch, body):
    monkeypatch.setattr(social, "fetch", served({
        "https://www.reddit.com/r/linux/comments/x/y.json": reply(body)}))
    with pytest.raises(Unreadable):
        social.from_url("https://www.reddit.com/r/linux/comments/x/y/")


def page(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_a_post_with_preview_tags_gives_title_blurb_image_and_author(monkeypatch):
    url = "https://x.com/someone/status/1"
    monkeypatch.setattr(social, "fetch", served({url: reply(page("social_post.html"), "text/html", url)}))
    out = social.from_url(url)
    assert out.title == 'someone on X: "WireGuard cut my latency in half"'
    assert out.text == "Moved from OpenVPN last week. Ping went from 40ms to 20ms."
    assert out.cover_url == "https://pbs.example.com/media/wg.jpg"
    assert out.author == "@someone"
    assert out.type == "social"
    assert out.source == "x.com"


def test_a_page_with_only_an_og_title_still_gives_a_note_with_an_empty_body(monkeypatch):
    url = "https://www.tiktok.com/@maker/video/1"
    monkeypatch.setattr(social, "fetch", served({url: reply(page("social_title_only.html"), "text/html", url)}))
    out = social.from_url(url)
    assert out.title == "A video by @maker"
    assert out.text == ""
    assert out.cover_url is None and out.author is None


def test_a_plain_title_alone_is_not_a_preview():
    with pytest.raises(Unreadable):
        social.from_preview_tags("<head><title>Instagram</title></head>", "https://instagram.com/p/1")


def test_twitter_cards_and_plain_tags_are_the_fallbacks():
    html = (
        '<title> Plain  title </title><meta name="description" content="plain blurb">'
        '<meta name="twitter:image" content="https://i/x.png">')
    out = social.from_preview_tags(html, "https://threads.net/@a/post/1")
    assert (out.title, out.text, out.cover_url) == ("Plain title", "plain blurb", "https://i/x.png")
    cards = social.from_preview_tags(
        '<meta name="twitter:title" content="T"><meta name="twitter:description" content="D">',
        "https://x.com/a/status/2")
    assert (cards.title, cards.text) == ("T", "D")


def test_a_real_login_wall_with_just_a_site_name_title_is_unreadable(monkeypatch):
    url = "https://www.instagram.com/p/abc/"
    monkeypatch.setattr(social, "fetch", served({url: reply(page("social_login_wall.html"), "text/html", url)}))
    with pytest.raises(Unreadable, match="without logging in"):
        social.from_url(url)


def test_only_the_first_title_in_the_head_counts():
    html = ('<head><title>Real</title><meta name="description" content="d"></head>'
            '<body><svg><title>Close</title></svg><svg><title>Home</title></svg></body>')
    assert social.from_preview_tags(html, "https://x.com/a").title == "Real"


@pytest.mark.parametrize("tail", ['<meta name="description" content="d"></head><body>', "</head><body>" + "x" * 5000])
def test_an_unclosed_title_does_not_swallow_the_page(tail):
    parser = social._Meta()
    parser.feed("<head><title>Broken" + tail)
    parser.close()
    assert parser.title == "Broken"


def test_an_endless_title_is_capped():
    parser = social._Meta()
    parser.feed("<head><title>" + "t" * 5000 + "</title>")
    assert len(parser.title) == social.MAX_TITLE


def test_a_host_that_merely_contains_reddit_is_read_by_its_tags(monkeypatch):
    monkeypatch.setattr(social, "fetch", served({"https://notreddit.com/a": reply("<html></html>")}))
    with pytest.raises(Unreadable, match="without logging in"):
        social.from_url("https://notreddit.com/a")


# --- PDF size ceiling --------------------------------------------------------

def big_pdf(tmp_path, size):
    """A valid PDF padded with trailing comment bytes up to `size`."""
    data = make_pdf(tmp_path)
    return data + b"\n%" + b"x" * (size - len(data) - 2)


def test_a_pdf_between_the_page_cap_and_the_pdf_ceiling_is_accepted(monkeypatch, tmp_path):
    size = 9 * 1024 * 1024
    assert net.MAX_BYTES < size < pdf.PDF_MAX_BYTES
    data = big_pdf(tmp_path, size)
    asked = {}

    def fake(url, max_bytes=None, **kwargs):
        asked["max_bytes"] = max_bytes
        assert len(data) <= max_bytes
        return reply(data, "application/pdf", url)

    monkeypatch.setattr(pdf, "fetch", fake)
    assert "Resultados" in pdf.from_url("https://e.com/thesis.pdf").text
    assert asked["max_bytes"] == pdf.PDF_MAX_BYTES == 32 * 1024 * 1024


def test_a_pdf_over_the_ceiling_is_refused_naming_size_and_limit(monkeypatch):
    too_big = net.NetworkError(
        f"page is {40 * 2**20} bytes, over {32 * 2**20} bytes: https://e.com/b.pdf",
        status=200, headers={"content-type": "application/pdf"}, too_large=True)
    monkeypatch.setattr(pdf, "fetch", served({"https://e.com/b.pdf": too_big}))
    with pytest.raises(Unreadable) as raised:
        pdf.from_url("https://e.com/b.pdf")
    assert str(40 * 2**20) in str(raised.value) and "32 MiB" in str(raised.value)


def test_the_real_fetch_enforces_the_ceiling_on_a_declared_pdf_size(monkeypatch):
    import httpx

    class Client:
        def __init__(self, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def stream(self, method, url):
            response = httpx.Response(
                200, headers={"content-type": "application/pdf",
                              "content-length": str(40 * 2**20)},
                content=b"%PDF", request=httpx.Request(method, url))
            class Ctx:
                def __enter__(s): return response
                def __exit__(s, *a): return False
            return Ctx()

    monkeypatch.setattr(net.httpx, "Client", Client)
    monkeypatch.setattr(pdf, "fetch", net.fetch)
    with pytest.raises(Unreadable, match=r"41943040 bytes.*32 MiB|32 MiB.*41943040"):
        pdf.from_url("https://e.com/b.pdf")


def test_a_big_extensionless_pdf_is_refetched_under_the_pdf_ceiling(monkeypatch, tmp_path):
    url = "https://arxiv.org/pdf/2301.12345"
    data = make_pdf(tmp_path)
    page_cap = net.NetworkError(
        f"page is {9 * 2**20} bytes, over {net.MAX_BYTES} bytes: {url}",
        status=200, headers={"content-type": "application/pdf; qs=1"}, too_large=True)
    monkeypatch.setattr(article, "fetch", served({url: page_cap}))
    inner = served({url: reply(data, "application/pdf", url)})
    asked = []

    def fake(u, **kwargs):
        asked.append(kwargs.get("max_bytes"))
        return inner(u)

    monkeypatch.setattr(pdf, "fetch", fake)
    assert extract(url).type == "pdf"
    assert asked == [pdf.PDF_MAX_BYTES]


def test_an_oversized_web_page_is_still_refused_at_the_page_cap(monkeypatch):
    url = "https://e.com/huge"
    big = net.NetworkError("page over 8388608 bytes", status=200,
                           headers={"content-type": "text/html"}, too_large=True)
    monkeypatch.setattr(article, "fetch", served({url: big}))
    with pytest.raises(Unreadable, match="over"):
        extract(url)


def test_a_removed_reddit_post_is_not_text():
    thread = [
        {"data": {"children": [{"data": {"title": "T", "selftext": "[removed]", "author": "a"}}]}},
        {"data": {"children": [{"data": {"body": "[deleted]"}}]}}]
    out = social.from_reddit(thread, "https://reddit.com/r/x/comments/1/t/")
    assert out.title == "T" and out.text == ""


def test_a_reddit_post_with_neither_title_nor_text_is_unreadable():
    thread = [{"data": {"children": [{"data": {"selftext": "[deleted]"}}]}}]
    with pytest.raises(Unreadable):
        social.from_reddit(thread, "https://reddit.com/r/x/comments/1/t/")


# --- youtube: real yt-dlp output and its odd shapes ---------------------------

def test_real_ytdlp_output_is_read_and_manual_captions_beat_automatic_ones():
    data = load("ytdlp_real.json")
    out = youtube.from_ytdlp(data, "https://www.youtube.com/watch?v=dQw4w9WgXcQ", captions=None)
    assert out.title.startswith("Rick Astley - Never Gonna Give You Up")
    assert out.author == "Rick Astley"
    assert out.published == "2009-10-25"
    assert out.cover_url.startswith("https://i.ytimg.com/")
    assert out.text.startswith("The official video")
    # manual en is json3 only, so the automatic en vtt is the one that can be read
    assert youtube._caption_url(data) == data["automatic_captions"]["en"][0]["url"]


def test_a_manual_vtt_track_wins_over_an_automatic_one_in_the_same_language():
    data = {"subtitles": {"es": [{"ext": "vtt", "url": "manual"}]},
            "automatic_captions": {"es": [{"ext": "vtt", "url": "auto"}]}}
    assert youtube._caption_url(data) == "manual"


@pytest.mark.parametrize("data", [
    {"subtitles": "oops", "automatic_captions": None},
    {"subtitles": {"es": [None, 3, {"ext": "vtt"}]}},
])
def test_caption_shape_surprises_mean_no_captions_not_a_crash(data):
    assert youtube._caption_url(data) is None


@pytest.mark.parametrize("data", [
    {"title": 5, "description": ["x"]},
    {"title": "T", "description": 7, "channel": ["a"], "upload_date": 20260915},
])
def test_field_type_surprises_are_unreadable_or_survived_never_a_crash(data):
    try:
        out = youtube.from_ytdlp(data, "https://youtube.com/watch?v=a", captions=None)
    except Unreadable:
        return
    assert isinstance(out.title, str)


def test_a_spoken_line_starting_with_language_survives_and_entities_are_decoded():
    vtt = ("WEBVTT\nKind: captions\nLanguage: es\n\n"
           "1\n00:00:01.000 --> 00:00:03.000\nLanguage: es una palabra &amp; mas\n\n"
           "NOTE a comment\n\n00:00:03.000 --> 00:00:05.000\n&gt;&gt; Kind: of fun\n")
    text = youtube.vtt_to_text(vtt)
    assert text == "Language: es una palabra & mas >> Kind: of fun"


def test_a_caption_body_that_is_not_vtt_is_discarded(monkeypatch):
    fake_ytdlp(monkeypatch, stdout=(FIXTURES / "ytdlp.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(youtube, "fetch", served({
        "https://example.com/captions.vtt": reply("<html>Before you continue</html>", "text/html")}))
    out = youtube.from_url("https://youtube.com/watch?v=abc")
    assert "Before you continue" not in out.text and "Explicación corta" in out.text


def test_the_ytdlp_command_line_is_pinned(monkeypatch):
    seen = fake_ytdlp(monkeypatch, stdout=(FIXTURES / "ytdlp_real.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(youtube, "fetch", served({
        load("ytdlp_real.json")["automatic_captions"]["en"][0]["url"]:
            reply("WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nhola\n", "text/vtt")}))
    youtube.from_url("https://youtube.com/watch?v=abc")
    for flag in ("--dump-json", "--skip-download", "--no-playlist", "--no-warnings"):
        assert flag in seen["cmd"]
    assert seen["cmd"][seen["cmd"].index("--playlist-items") + 1] == "1"


def test_several_json_documents_from_a_playlist_say_playlist(monkeypatch):
    fake_ytdlp(monkeypatch, stdout='{"a": 1}\n{"a": 2}\n')
    with pytest.raises(Unreadable, match="playlist"):
        youtube.from_url("https://www.youtube.com/playlist?list=PL1")


# --- pdf: AES, bad pages, placeholder titles ----------------------------------

def test_an_aes_encrypted_pdf_with_an_empty_user_password_is_read(tmp_path):
    import io

    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(make_pdf(tmp_path))))
    writer.encrypt(user_password="", owner_password="owner", algorithm="AES-256")
    buffer = io.BytesIO()
    writer.write(buffer)
    assert b"/AESV3" in buffer.getvalue()
    assert "Resultados del experimento" in pdf.from_bytes(buffer.getvalue(), "https://e.com/p.pdf").text


def test_one_bad_page_does_not_lose_the_rest(monkeypatch, tmp_path):
    from pypdf import PageObject

    real = PageObject.extract_text
    calls = []

    def flaky(self, *a, **k):
        calls.append(1)
        if len(calls) == 1:
            raise ValueError("broken page")
        return real(self, *a, **k)

    from reportlab.pdfgen import canvas
    path = tmp_path / "two.pdf"
    c = canvas.Canvas(str(path))
    c.drawString(72, 720, "primera")
    c.showPage()
    c.drawString(72, 720, "segunda pagina")
    c.save()
    monkeypatch.setattr(PageObject, "extract_text", flaky)
    out = pdf.from_bytes(path.read_bytes(), "https://e.com/two.pdf")
    assert "segunda pagina" in out.text and "primera" not in out.text


@pytest.mark.parametrize("title", ["Microsoft Word - informe final.doc", "paper.docx", "Untitled", "  "])
def test_generator_placeholder_titles_fall_back_to_the_file_name(title):
    import io

    from reportlab.pdfgen import canvas
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer)
    c.setTitle(title)
    c.drawString(72, 720, "contenido")
    c.save()
    assert pdf.from_bytes(buffer.getvalue(), "https://e.com/real-name.pdf").title == "real-name.pdf"


def test_a_real_title_is_kept():
    import io

    from reportlab.pdfgen import canvas
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer)
    c.setTitle("Attention Is All You Need")
    c.drawString(72, 720, "contenido")
    c.save()
    assert pdf.from_bytes(buffer.getvalue(), "https://e.com/1706.pdf").title == "Attention Is All You Need"


# --- extract() only ever raises Unreadable -----------------------------------

def test_a_network_failure_from_the_article_path_is_unreadable(monkeypatch):
    url = "https://e.com/gone"
    monkeypatch.setattr(article, "fetch", served({url: net.NetworkError("404 for " + url, status=404)}))
    with pytest.raises(Unreadable, match="404"):
        extract(url)


def test_a_network_failure_from_a_github_page_is_unreadable(monkeypatch):
    url = "https://docs.github.com/en/gone"
    monkeypatch.setattr(article, "fetch", served({url: net.NetworkError("404 for " + url, status=404)}))
    with pytest.raises(Unreadable):
        extract(url)
    with pytest.raises(Unreadable):
        github.from_url(url)


# --- payload shape surprises --------------------------------------------------

@pytest.mark.parametrize("change", [
    {"description": 5},
    {"topics": ["ai", 3]},
    {"topics": "ai"},
    {"owner": "sst"},
    {"language": ["TypeScript"]},
    {"full_name": 7},
])
def test_a_malformed_github_payload_is_unreadable(change):
    with pytest.raises(Unreadable, match="unexpected GitHub payload"):
        github.from_api(dict(load("github_repo.json"), **change), "", "https://github.com/sst/opencode")


@pytest.mark.parametrize("selftext", [5, ["x"]])
def test_a_reddit_payload_with_a_non_text_selftext_is_unreadable(selftext):
    thread = [{"data": {"children": [{"data": {"title": "T", "selftext": selftext}}]}}]
    with pytest.raises(Unreadable, match="TypeError"):
        social.from_reddit(thread, "https://reddit.com/r/x/comments/1/t/")


def test_a_comment_that_is_not_text_is_unreadable():
    thread = [{"data": {"children": [{"data": {"title": "T", "selftext": "s"}}]}},
              {"data": {"children": [{"data": {"body": 9}}]}}]
    with pytest.raises(Unreadable):
        social.from_reddit(thread, "https://reddit.com/r/x/comments/1/t/")


def test_the_dispatcher_turns_an_unforeseen_type_error_into_unreadable_naming_it(monkeypatch):
    def broken(url):
        return {}["missing"]

    monkeypatch.setattr(github, "from_url", broken)
    with pytest.raises(Unreadable, match="KeyError") as raised:
        extract("https://github.com/sst/opencode")
    assert "github.com/sst/opencode" in str(raised.value)


def test_a_none_track_does_not_stop_the_search_in_other_languages():
    data = {"subtitles": {"es": [None, "x"], "en": [{"ext": "vtt", "url": "english"}]}}
    assert youtube._caption_url(data) == "english"
