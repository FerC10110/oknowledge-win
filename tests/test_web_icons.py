"""Serving a site's favicon, and the letter that stands in when there is none.

The route always answers with an image. That is the whole design: the card
template asks for /icon/<domain> and never has to stat a file or know whether
the download ever happened, which keeps a page of 100 cards free of 100
filesystem lookups and free of 100 broken-image icons.
"""

import pytest
from fastapi.testclient import TestClient

from marks import posix_only
from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.vault import rebuild_indexes, write_note
from oknowledge.web.app import ICON_TYPES, create_app

PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 40


def note(id, source):
    return Note(id=id, url=f"https://{source}/x", title=f"From {source}",
                category="Redes", tags=["x"], type="article", source=source,
                saved="2026-10-03", summary="Resumen.", points=[])


@pytest.fixture
def setup(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    write_note(cfg, note("a1", "github.com"), "es")
    rebuild_indexes(cfg, "es")
    return cfg, TestClient(create_app(cfg))


def put_icon(cfg, name, content=PNG):
    icons = cfg.attachments_dir / "icons"
    icons.mkdir(parents=True, exist_ok=True)
    (icons / name).write_bytes(content)


def test_a_downloaded_favicon_is_served(setup):
    cfg, client = setup
    put_icon(cfg, "github.com.png")

    answer = client.get("/icon/github.com")

    assert answer.status_code == 200
    assert answer.content == PNG
    assert answer.headers["content-type"] == "image/png"
    assert answer.headers["x-content-type-options"] == "nosniff"


def test_an_ico_file_is_served_too(setup):
    """Most sites still answer /favicon.ico with a real .ico."""
    cfg, client = setup
    put_icon(cfg, "github.com.ico", b"\x00\x00\x01\x00rest")

    answer = client.get("/icon/github.com")

    assert answer.status_code == 200
    assert "icon" in answer.headers["content-type"]


def test_a_domain_with_no_icon_gets_a_letter(setup):
    _, client = setup

    answer = client.get("/icon/github.com")

    assert answer.status_code == 200
    assert answer.headers["content-type"].startswith("image/svg+xml")
    assert ">g<" in answer.text


def test_the_letter_is_stable_for_a_domain(setup):
    _, client = setup

    first = client.get("/icon/github.com").text
    second = client.get("/icon/github.com").text

    assert first == second


def test_two_domains_get_different_colours(setup):
    _, client = setup

    one = client.get("/icon/github.com").text
    other = client.get("/icon/wikipedia.org").text

    assert one != other


@pytest.mark.parametrize("domain", [
    "../../etc/passwd", "..", ".", "a/b", "%2e%2e%2fsecret", "x" * 300,
])
def test_a_domain_that_is_not_one_never_serves_a_file(setup, domain):
    """A name that is not a domain never gets a file off the disk.

    What it *does* get varies by shape and that is fine: httpx collapses
    `/icon/..` to `/` before it is ever sent, so the URL layer answers some of
    these and the handler never sees them. The invariant worth pinning is the
    one that holds either way -- no stored image comes back, and nothing 500s.
    """
    _, client = setup

    answer = client.get(f"/icon/{domain}", follow_redirects=False)

    assert answer.status_code < 500
    served_from_disk = answer.headers.get("content-type", "") in ICON_TYPES.values()
    assert not served_from_disk


@posix_only
def test_an_icon_outside_the_folder_is_not_served(setup, tmp_path):
    """The icon name comes off a note's `source`, which the user can edit."""
    cfg, client = setup
    secret = tmp_path / "secret.png"
    secret.write_bytes(b"not yours")
    icons = cfg.attachments_dir / "icons"
    icons.mkdir(parents=True)
    (icons / "github.com.png").symlink_to(secret)

    answer = client.get("/icon/github.com")

    assert answer.content != b"not yours"
    assert answer.headers["content-type"].startswith("image/svg+xml")


def test_an_icon_of_a_type_we_do_not_serve_falls_back_to_the_letter(setup):
    cfg, client = setup
    put_icon(cfg, "github.com.svg", b"<svg onload='alert(1)'></svg>")

    answer = client.get("/icon/github.com")

    assert b"alert(1)" not in answer.content


def test_icons_are_cacheable(setup):
    """A full-width grid asks for one icon per card: they must not re-fetch."""
    cfg, client = setup
    put_icon(cfg, "github.com.png")

    answer = client.get("/icon/github.com")

    assert "max-age" in answer.headers.get("cache-control", "")


def test_a_cross_site_get_of_an_icon_is_still_served(setup):
    cfg, client = setup
    put_icon(cfg, "github.com.png")

    answer = client.get("/icon/github.com",
                        headers={"Sec-Fetch-Site": "cross-site"})

    assert answer.status_code == 200
