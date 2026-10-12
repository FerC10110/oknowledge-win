"""When a link's file is renamed, the ideas that named it follow.

An idea names its links by file name, because that is what a wikilink is.
The pipeline renames a link's file when the model finally gives it a real
title, and an idea left pointing at the old name would show a dead row.
"""

import contextlib

import pytest

from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.queue import Locked
from oknowledge.vault import find_note, note_path, repoint_related, write_note


@pytest.fixture
def cfg(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    return Config(vault=vault)


def put(cfg, instant, related):
    note = new_idea("x", f"Idea {instant[-1]}", "2026-10-12", instant)
    note.related = related
    write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ideas))
    return note


def related_of(cfg, note):
    return find_note(cfg, note.id, shelf=cfg.ideas)[1].related


def test_the_ideas_that_named_the_old_file_name_the_new_one(cfg):
    one = put(cfg, "2026-10-12T00:00:00.000001", ["old", "other"])
    two = put(cfg, "2026-10-12T00:00:00.000002", ["other"])
    result = repoint_related(cfg, "old", "new", "es")
    assert related_of(cfg, one) == ["new", "other"]
    assert related_of(cfg, two) == ["other"]
    assert (result.moved, result.failed) == (1, [])


def test_an_idea_that_already_had_both_keeps_one(cfg):
    one = put(cfg, "2026-10-12T00:00:00.000001", ["old", "new"])
    repoint_related(cfg, "old", "new", "es")
    assert related_of(cfg, one) == ["new"]
    # Reading dedupes too; the file itself must not say it twice.
    path = find_note(cfg, one.id, shelf=cfg.ideas)[0]
    assert path.read_text(encoding="utf-8").count("[[new]]") == 1


def test_an_idea_that_cannot_be_locked_is_reported_and_the_rest_move(cfg):
    one = put(cfg, "2026-10-12T00:00:00.000001", ["old"])
    two = put(cfg, "2026-10-12T00:00:00.000002", ["old"])

    @contextlib.contextmanager
    def lock(idea):
        if idea == one.id:
            raise Locked(idea)
        yield

    result = repoint_related(cfg, "old", "new", "es", lock=lock)
    assert related_of(cfg, one) == ["old"]
    assert related_of(cfg, two) == ["new"]
    assert result.moved == 1 and len(result.failed) == 1


def test_links_are_never_touched(cfg):
    link = new_idea("x", "WireGuard", "2026-10-12", "2026-10-12T00:00:00.000009")
    link.type, link.url, link.related = "article", "https://wireguard.com", ["old"]
    path = write_note(cfg, link, "es")
    before = path.read_text(encoding="utf-8")
    repoint_related(cfg, "old", "new", "es")
    assert path.read_text(encoding="utf-8") == before
