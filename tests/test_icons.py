"""Favicons, which are per domain rather than per note.

A favicon belongs to a site, not to a link: twenty GitHub notes share one
icon. Keeping them keyed by domain is what lets this feature exist without
writing into notes the status invariant says belong to the user -- there is no
new frontmatter key, so a backfill touches no note at all.

Most of this file is about what must NOT happen, because a domain reaches the
filesystem as a file name: it comes out of frontmatter the user can edit.
"""

import os

import pytest

from oknowledge.config import Config
from oknowledge.net import Fetched
from oknowledge.pipeline import download_icon

PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 40


@pytest.fixture
def cfg(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    return Config(vault=vault)


def served(content=PNG, content_type="image/png"):
    """A fetch() stand-in. No test here touches the network."""
    def fake(url, **kwargs):
        fake.asked.append(url)
        return Fetched(status=200, content_type=content_type, content=content,
                       final_url=url)
    fake.asked = []
    return fake


def test_a_favicon_is_saved_once_per_domain(cfg, monkeypatch):
    fetch = served()
    monkeypatch.setattr("oknowledge.pipeline.fetch", fetch)

    download_icon(cfg, "github.com")

    saved = cfg.attachments_dir / "icons" / "github.com.png"
    assert saved.read_bytes() == PNG
    assert fetch.asked == ["https://github.com/favicon.ico"]


def test_a_domain_already_saved_is_not_fetched_again(cfg, monkeypatch):
    fetch = served()
    monkeypatch.setattr("oknowledge.pipeline.fetch", fetch)

    download_icon(cfg, "github.com")
    download_icon(cfg, "github.com")

    assert len(fetch.asked) == 1


@pytest.mark.parametrize("domain", [
    "../escape", "../../etc/passwd", "/abs", "a/b", "", "   ", ".",
    "..", "x" * 300, "bad\x00name", "-leading.com", "trailing-.com",
])
def test_a_domain_we_would_not_write_back_unchanged_is_refused(
        cfg, monkeypatch, domain):
    """The domain becomes a file name, so it is validated like a link id."""
    fetch = served()
    monkeypatch.setattr("oknowledge.pipeline.fetch", fetch)

    download_icon(cfg, domain)

    assert fetch.asked == []
    icons = cfg.attachments_dir / "icons"
    assert not icons.exists() or list(icons.iterdir()) == []


def test_a_domain_is_lowercased_rather_than_refused(cfg, monkeypatch):
    """Domains are case-insensitive, and one site must not get two files.

    Refusing the uppercase form would make the icon silently never appear,
    which is the kind of quiet nothing this project tries not to ship.
    """
    fetch = served()
    monkeypatch.setattr("oknowledge.pipeline.fetch", fetch)

    download_icon(cfg, "GitHub.COM")

    assert (cfg.attachments_dir / "icons" / "github.com.png").is_file()
    assert fetch.asked == ["https://github.com/favicon.ico"]


def test_nothing_is_written_outside_the_managed_folder(cfg, monkeypatch, tmp_path):
    """attachments/ symlinked elsewhere is an ordinary Obsidian habit."""
    outside = tmp_path / "outside"
    outside.mkdir()
    cfg.attachments_dir.parent.mkdir(parents=True, exist_ok=True)
    cfg.attachments_dir.symlink_to(outside)
    monkeypatch.setattr("oknowledge.pipeline.fetch", served())

    download_icon(cfg, "github.com")

    assert list(outside.iterdir()) == []


def test_a_symlinked_icon_is_left_alone(cfg, monkeypatch, tmp_path):
    """A link the user put there is theirs, and stays a link.

    This asserts the outcome, not one guard: the existence check already
    returns early on any `icons/<domain>.*`, so the explicit symlink refusal
    behind it is defence in depth rather than the thing under test here.
    """
    mine = tmp_path / "mine.png"
    mine.write_bytes(b"the user's own file")
    icons = cfg.attachments_dir / "icons"
    icons.mkdir(parents=True)
    link = icons / "github.com.png"
    link.symlink_to(mine)
    monkeypatch.setattr("oknowledge.pipeline.fetch", served())

    download_icon(cfg, "github.com")

    assert mine.read_bytes() == b"the user's own file"
    assert link.is_symlink()


def test_a_reply_that_is_not_an_image_writes_nothing(cfg, monkeypatch):
    """A site with no favicon answers with its 404 page, which is HTML."""
    monkeypatch.setattr("oknowledge.pipeline.fetch",
                        served(b"<html>not found</html>", "text/html"))

    download_icon(cfg, "github.com")

    assert not (cfg.attachments_dir / "icons").exists()


def test_a_fetch_that_explodes_is_swallowed(cfg, monkeypatch):
    """An icon is decoration: it must never cost the user a note."""
    def boom(url, **kwargs):
        raise OSError("no route to host")
    monkeypatch.setattr("oknowledge.pipeline.fetch", boom)

    download_icon(cfg, "github.com")      # must not raise

    assert not (cfg.attachments_dir / "icons").exists()


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores the mode bits")
def test_an_unwritable_attachments_folder_is_swallowed(cfg, monkeypatch):
    monkeypatch.setattr("oknowledge.pipeline.fetch", served())
    cfg.attachments_dir.mkdir(parents=True)
    os.chmod(cfg.attachments_dir, 0o500)
    try:
        download_icon(cfg, "github.com")  # must not raise
    finally:
        os.chmod(cfg.attachments_dir, 0o700)


def test_no_half_written_icon_is_left_behind(cfg, monkeypatch):
    """os.replace, so a stale icon is never served half overwritten."""
    monkeypatch.setattr("oknowledge.pipeline.fetch", served())
    monkeypatch.setattr("oknowledge.pipeline.os.replace",
                        lambda *a: (_ for _ in ()).throw(OSError("full")))

    download_icon(cfg, "github.com")

    icons = cfg.attachments_dir / "icons"
    assert list(icons.iterdir()) == []
