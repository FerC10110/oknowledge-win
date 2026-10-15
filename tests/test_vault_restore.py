"""Putting a deleted note back (spec §6.2). The vault's rule is that nothing
is destroyed and nothing is overwritten: every refusal below leaves both the
file in trash/ and whatever is at the old address exactly as they were."""

import errno
import os

import pytest

from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.vault import (
    IndexesStale, Trashed, delete_note, find_note, index_path, note_path,
    rebuild_indexes, restore_note, trash_dir, update_note, write_note,
)


def make(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    return Config(vault=vault)


def note(id, title="WireGuard", category="Redes", type="article"):
    return Note(id=id, url=f"https://e.com/{id}", title=title, category=category,
                tags=["vpn"], type=type, source="e.com", saved="2026-10-03",
                summary=f"Resumen de {title}.", points=[])


def trashed(cfg, id="a1", **kw):
    path = write_note(cfg, note(id, **kw), "es")
    rebuild_indexes(cfg, "es")
    return path, delete_note(cfg, id, "es")


def test_delete_says_where_the_note_was_and_where_it_went(tmp_path):
    cfg = make(tmp_path)
    path, moved = trashed(cfg)
    assert moved == Trashed(source=path, target=trash_dir(cfg) / path.name)


def test_restore_puts_the_same_file_back_and_rebuilds(tmp_path):
    cfg = make(tmp_path)
    path, moved = trashed(cfg)
    before = moved.target.read_bytes()
    assert not index_path(cfg, "Redes").exists()

    assert restore_note(cfg, "a1", moved.source, moved.target, "es") is True

    assert path.read_bytes() == before
    assert not moved.target.exists()
    assert "WireGuard" in index_path(cfg, "Redes").read_text(encoding="utf-8")


def test_restore_works_on_the_other_shelves(tmp_path):
    cfg = make(tmp_path)
    card = note("c1", title="Alien", category="Películas", type="movie")
    path = write_note(cfg, card, "es", path=note_path(cfg, card, shelf=cfg.ocio))
    moved = delete_note(cfg, "c1", "es", shelf=cfg.ocio)
    assert restore_note(cfg, "c1", moved.source, moved.target, "es", shelf=cfg.ocio)
    assert path.exists() and find_note(cfg, "c1", cfg.ocio) is not None


def test_a_note_edited_in_the_trash_comes_back_with_the_edit(tmp_path):
    cfg = make(tmp_path)
    path, moved = trashed(cfg)
    edited = moved.target.read_text(encoding="utf-8") + "\nUna línea mía.\n"
    moved.target.write_text(edited, encoding="utf-8")
    assert restore_note(cfg, "a1", moved.source, moved.target, "es")
    assert path.read_text(encoding="utf-8") == edited


@pytest.mark.parametrize("damage", ["id", "marker", "gone"])
def test_a_trash_file_that_is_no_longer_that_note_stays(tmp_path, damage):
    cfg = make(tmp_path)
    path, moved = trashed(cfg)
    text = moved.target.read_text(encoding="utf-8")
    if damage == "id":
        moved.target.write_text(text.replace("id: a1", "id: zz"), encoding="utf-8")
    elif damage == "marker":
        moved.target.write_text(text.replace("oknowledge: 1", "oknowledge: 0"), encoding="utf-8")
    else:
        os.replace(moved.target, path)              # dragged back by hand in Obsidian
    after = sorted(p.name for p in cfg.root.rglob("*.md"))

    assert restore_note(cfg, "a1", moved.source, moved.target, "es") is False
    assert sorted(p.name for p in cfg.root.rglob("*.md")) == after


def test_a_file_at_the_old_address_is_never_overwritten(tmp_path):
    cfg = make(tmp_path)
    path, moved = trashed(cfg)
    path.write_text("mine, written after the delete\n", encoding="utf-8")

    assert restore_note(cfg, "a1", moved.source, moved.target, "es") is False
    assert path.read_text(encoding="utf-8") == "mine, written after the delete\n"
    assert moved.target.exists()


def test_a_link_pasted_again_meanwhile_is_not_doubled(tmp_path):
    cfg = make(tmp_path)
    _, moved = trashed(cfg)
    write_note(cfg, note("a1", title="WireGuard otra vez"), "es")   # another name, same id

    assert restore_note(cfg, "a1", moved.source, moved.target, "es") is False
    assert moved.target.exists()


@pytest.mark.parametrize("where", ["source", "target"])
def test_paths_outside_the_shelf_or_the_trash_are_refused(tmp_path, where):
    cfg = make(tmp_path)
    path, moved = trashed(cfg)
    source, target = moved.source, moved.target
    if where == "source":
        source = cfg.ocio.dir / path.name                 # another shelf
    else:
        stray = cfg.root / "elsewhere" / path.name        # not in trash/
        stray.parent.mkdir()
        stray.write_bytes(moved.target.read_bytes())
        target = stray
    assert restore_note(cfg, "a1", source, target, "es") is False
    assert restore_note(cfg, "a1", cfg.root / ".." / ".." / "x.md", moved.target, "es") is False
    assert moved.target.exists() and not path.exists()


def test_a_name_that_appears_during_the_move_wins(tmp_path, monkeypatch):
    cfg = make(tmp_path)
    path, moved = trashed(cfg)

    def raced(src, dst):
        open(dst, "w", encoding="utf-8").write("theirs\n")
        raise FileExistsError(errno.EEXIST, "exists", str(dst))
    monkeypatch.setattr(os, "link", raced)

    assert restore_note(cfg, "a1", moved.source, moved.target, "es") is False
    assert path.read_text(encoding="utf-8") == "theirs\n"
    assert moved.target.exists()


def test_without_hard_links_it_still_moves_without_overwriting(tmp_path, monkeypatch):
    cfg = make(tmp_path)
    path, moved = trashed(cfg)
    before = moved.target.read_bytes()

    def unsupported(src, dst):
        raise OSError(errno.EPERM, "Operation not permitted")
    monkeypatch.setattr(os, "link", unsupported)

    assert restore_note(cfg, "a1", moved.source, moved.target, "es") is True
    assert path.read_bytes() == before and not moved.target.exists()


def count_rebuilds(monkeypatch):
    calls = []
    monkeypatch.setattr("oknowledge.vault.rebuild_indexes",
                        lambda cfg, language, shelf=None: calls.append(shelf))
    return calls


def test_rebuild_false_rebuilds_nothing(tmp_path, monkeypatch):
    cfg = make(tmp_path)
    write_note(cfg, note("a1"), "es")
    write_note(cfg, note("b2", title="SSH"), "es")
    calls = count_rebuilds(monkeypatch)

    update_note(cfg, "a1", "es", category="Seguridad", rebuild=False)
    moved = delete_note(cfg, "b2", "es", rebuild=False)
    assert restore_note(cfg, "b2", moved.source, moved.target, "es", rebuild=False) is True
    assert moved.source.exists()

    assert calls == []
    assert find_note(cfg, "a1")[1].category == "Seguridad"


def test_a_restore_whose_rebuild_fails_says_the_note_is_back(tmp_path, monkeypatch):
    cfg = make(tmp_path)
    path, moved = trashed(cfg)

    def boom(cfg, language, shelf=None):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr("oknowledge.vault.rebuild_indexes", boom)

    with pytest.raises(IndexesStale) as raised:
        restore_note(cfg, "a1", moved.source, moved.target, "es")
    assert raised.value.done is True and path.exists()


def test_a_trash_file_that_vanishes_before_the_link_leaves_nothing(tmp_path, monkeypatch):
    cfg = make(tmp_path)
    path, moved = trashed(cfg)

    def vanished(src, dst):
        raise FileNotFoundError(errno.ENOENT, "gone", str(src))
    monkeypatch.setattr(os, "link", vanished)

    assert restore_note(cfg, "a1", moved.source, moved.target, "es") is False
    assert not path.exists()
    assert not list(path.parent.glob("*.md"))          # no placeholder either
