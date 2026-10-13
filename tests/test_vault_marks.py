"""A mark lives in the frontmatter, and every rewrite carries it."""

import pytest

from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.vault import (find_note, read_note, rebuild_indexes, rename_category,
                              update_note, write_note)


@pytest.fixture
def cfg(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    return Config(vault=vault)


def a_note(**extra):
    return Note(id="a1a1a1a1a1a1", url="https://e.com/a", title="WireGuard",
                category="Redes", tags=["vpn"], type="article", source="e.com",
                saved="2026-10-03", summary="Una vpn.", points=[], **extra)


def test_a_mark_is_written_and_read_back(cfg):
    path = write_note(cfg, a_note(mark="⭐"), "es")
    assert "mark: ⭐" in path.read_text(encoding="utf-8")
    assert read_note(path).mark == "⭐"


def test_no_mark_no_line(cfg):
    path = write_note(cfg, a_note(), "es")
    assert "mark:" not in path.read_text(encoding="utf-8")
    assert read_note(path).mark == ""


@pytest.mark.parametrize("typed", ["hola", "3", "[⭐, 🔥]", "'1️⃣'"])
def test_a_hand_typed_mark_that_is_not_one_reads_as_none(cfg, typed):
    path = write_note(cfg, a_note(), "es")
    text = path.read_text(encoding="utf-8").replace("id: ", f"mark: {typed}\nid: ", 1)
    path.write_text(text, encoding="utf-8")
    back = read_note(path)
    assert back is not None and back.mark == ""


def test_update_note_sets_and_clears_the_mark(cfg):
    write_note(cfg, a_note(), "es")
    update_note(cfg, "a1a1a1a1a1a1", "es", mark="🔥")
    assert find_note(cfg, "a1a1a1a1a1a1")[1].mark == "🔥"
    update_note(cfg, "a1a1a1a1a1a1", "es", mark="")
    assert find_note(cfg, "a1a1a1a1a1a1")[1].mark == ""


def test_update_note_refuses_what_is_not_a_mark(cfg):
    write_note(cfg, a_note(mark="⭐"), "es")
    update_note(cfg, "a1a1a1a1a1a1", "es", mark="ok")
    assert find_note(cfg, "a1a1a1a1a1a1")[1].mark == "⭐"


def test_other_edits_keep_the_mark(cfg):
    write_note(cfg, a_note(mark="⭐"), "es")
    rebuild_indexes(cfg, "es")
    update_note(cfg, "a1a1a1a1a1a1", "es", category="Seguridad", tags=["x"])
    assert find_note(cfg, "a1a1a1a1a1a1")[1].mark == "⭐"


def test_renaming_the_category_keeps_the_mark(cfg):
    write_note(cfg, a_note(mark="⭐"), "es")
    rebuild_indexes(cfg, "es")
    rename_category(cfg, "Redes", "Networking", "es")
    found = find_note(cfg, "a1a1a1a1a1a1")[1]
    assert (found.category, found.mark) == ("Networking", "⭐")
