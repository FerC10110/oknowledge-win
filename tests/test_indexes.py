
import os

import pytest

from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.vault import (
    all_notes, categories, find_note, index_path, rebuild_indexes, write_index, write_note,
    ProtectedNote,
)


def make_config(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    return Config(vault=vault)


def note(id, title, category, tags=("x",), saved="2026-10-03"):
    return Note(
        id=id, url=f"https://e.com/{id}", title=title, category=category,
        tags=list(tags), type="article", source="e.com", saved=saved,
        summary=f"Resumen de {title}.", points=["uno"],
    )


def test_an_index_lists_its_notes_newest_first(tmp_path):
    cfg = make_config(tmp_path)
    write_note(cfg, note("a1", "Túneles SSH", "Redes", saved="2026-09-28"), "es")
    write_note(cfg, note("b2", "WireGuard", "Redes", saved="2026-10-03"), "es")

    rebuild_indexes(cfg)

    text = index_path(cfg, "Redes").read_text(encoding="utf-8")
    assert "# Redes · 2 links" in text
    assert text.index("WireGuard") < text.index("Túneles SSH")
    assert "[[2026-10-03-wireguard|WireGuard]]" in text
    assert "Generado por oknowledge" in text


def test_each_category_gets_its_own_index(tmp_path):
    cfg = make_config(tmp_path)
    write_note(cfg, note("a1", "WireGuard", "Redes"), "es")
    write_note(cfg, note("b2", "Masa madre", "Cocina"), "es")

    rebuild_indexes(cfg)

    assert index_path(cfg, "Redes").exists()
    assert index_path(cfg, "Cocina").exists()


def test_an_index_left_without_notes_is_deleted(tmp_path):
    cfg = make_config(tmp_path)
    path = write_note(cfg, note("a1", "WireGuard", "Redes"), "es")
    rebuild_indexes(cfg)
    assert index_path(cfg, "Redes").exists()

    path.unlink()
    rebuild_indexes(cfg)
    assert not index_path(cfg, "Redes").exists()


def test_changing_the_category_by_hand_moves_the_note(tmp_path):
    cfg = make_config(tmp_path)
    path = write_note(cfg, note("a1", "WireGuard", "Redes"), "es")
    rebuild_indexes(cfg)

    path.write_text(path.read_text(encoding="utf-8").replace("category: Redes",
                                                             "category: Seguridad"), encoding="utf-8")
    rebuild_indexes(cfg)

    assert not index_path(cfg, "Redes").exists()
    assert "WireGuard" in index_path(cfg, "Seguridad").read_text(encoding="utf-8")


def test_a_file_of_yours_in_the_folder_is_not_an_index_and_is_not_deleted(tmp_path):
    cfg = make_config(tmp_path)
    mine = cfg.root / "Mis lecturas.md"
    mine.write_text("# Mis lecturas\n\nA mano.\n", encoding="utf-8")
    write_note(cfg, note("a1", "WireGuard", "Redes"), "es")

    rebuild_indexes(cfg)

    assert mine.read_text(encoding="utf-8") == "# Mis lecturas\n\nA mano.\n"


def test_a_category_with_a_slash_does_not_escape_the_folder(tmp_path):
    cfg = make_config(tmp_path)
    write_note(cfg, note("a1", "Algo", "IA/LLMs"), "es")
    rebuild_indexes(cfg)
    created = index_path(cfg, "IA/LLMs")
    assert created.parent == cfg.root
    assert created.exists()


def test_find_note_locates_a_link_by_id(tmp_path):
    cfg = make_config(tmp_path)
    write_note(cfg, note("a1", "WireGuard", "Redes"), "es")
    found = find_note(cfg, "a1")
    assert found is not None and found[1].title == "WireGuard"
    assert find_note(cfg, "zz") is None


def test_categories_counts_what_exists(tmp_path):
    cfg = make_config(tmp_path)
    write_note(cfg, note("a1", "WireGuard", "Redes"), "es")
    write_note(cfg, note("b2", "SSH", "Redes"), "es")
    write_note(cfg, note("c3", "Masa madre", "Cocina"), "es")
    assert categories(cfg) == {"Cocina": 1, "Redes": 2}


def test_all_notes_ignores_files_that_are_not_ours(tmp_path):
    cfg = make_config(tmp_path)
    write_note(cfg, note("a1", "WireGuard", "Redes"), "es")
    (cfg.links_dir / "ajena.md").write_text("# mía\n", encoding="utf-8")
    assert [n.id for n in all_notes(cfg)] == ["a1"]


def test_a_note_of_yours_without_marker_in_links_is_untouched_by_a_reindex(tmp_path):
    cfg = make_config(tmp_path)
    write_note(cfg, note("a1", "WireGuard", "Redes"), "es")
    mine = cfg.links_dir / "mia.md"
    mine.write_bytes("# mía\n\nA mano, con ñ.\n".encode("utf-8"))
    before = mine.read_bytes()

    result = rebuild_indexes(cfg)

    assert mine.read_bytes() == before
    assert mine not in result.skipped          # not ours: nothing to report


def test_a_hand_broken_note_of_ours_is_reported_as_skipped(tmp_path):
    cfg = make_config(tmp_path)
    write_note(cfg, note("a1", "WireGuard", "Redes"), "es")
    broken = write_note(cfg, note("b2", "SSH", "Redes"), "es")
    broken_text = broken.read_text(encoding="utf-8").replace("url: https://e.com/b2\n", "")
    broken.write_text(broken_text, encoding="utf-8")

    result = rebuild_indexes(cfg)

    assert result.skipped == [broken]
    assert result.written == [index_path(cfg, "Redes")]
    assert "# Redes · 1 link\n" in index_path(cfg, "Redes").read_text(encoding="utf-8")
    assert broken.read_text(encoding="utf-8") == broken_text


def test_a_note_with_broken_yaml_that_claims_the_marker_is_reported(tmp_path):
    cfg = make_config(tmp_path)
    broken = cfg.links_dir / "rota.md"
    broken.write_text("---\ntitle: [oops\noknowledge: 1\n---\n# x\n", encoding="utf-8")
    assert rebuild_indexes(cfg).skipped == [broken]


def test_a_file_of_yours_named_like_a_category_is_never_overwritten(tmp_path):
    cfg = make_config(tmp_path)
    mine = cfg.root / "Redes.md"
    mine.write_text("# Redes\n\nMis apuntes.\n", encoding="utf-8")
    before = mine.read_bytes()
    write_note(cfg, note("a1", "WireGuard", "Redes"), "es")
    write_note(cfg, note("b2", "Masa madre", "Cocina"), "es")

    result = rebuild_indexes(cfg)            # must not raise

    assert mine.read_bytes() == before
    assert result.blocked == [mine]
    assert result.written == [index_path(cfg, "Cocina")]
    assert "Masa madre" in index_path(cfg, "Cocina").read_text(encoding="utf-8")


def test_write_index_itself_still_refuses_an_unmarked_file(tmp_path):
    cfg = make_config(tmp_path)
    (cfg.root / "Redes.md").write_text("# mine\n", encoding="utf-8")
    with pytest.raises(ProtectedNote):
        write_index(cfg, "Redes", [(cfg.links_dir / "x.md", note("a1", "WireGuard", "Redes"))])


def test_a_clean_rebuild_blocks_nothing(tmp_path):
    cfg = make_config(tmp_path)
    write_note(cfg, note("a1", "WireGuard", "Redes"), "es")
    result = rebuild_indexes(cfg)
    assert result.blocked == [] and result.skipped == []


def test_an_index_symlinked_outside_the_folder_is_not_written(tmp_path):
    cfg = make_config(tmp_path)
    outside = tmp_path / "elsewhere.md"
    outside.write_text("---\noknowledge: 1\nkind: index\n---\nkeep\n", encoding="utf-8")
    index_path(cfg, "Redes").symlink_to(outside)

    with pytest.raises(ProtectedNote):
        write_index(cfg, "Redes", [(cfg.links_dir / "x.md", note("a1", "WireGuard", "Redes"))])

    assert outside.read_text(encoding="utf-8").endswith("keep\n")


def test_two_categories_with_one_slug_write_the_first_and_block_the_other(tmp_path):
    cfg = make_config(tmp_path)
    write_note(cfg, note("a1", "Uno", "IA-LLMs"), "es")
    write_note(cfg, note("b2", "Dos", "IA/LLMs"), "es")

    first = rebuild_indexes(cfg)
    text = index_path(cfg, "IA-LLMs").read_text(encoding="utf-8")
    second = rebuild_indexes(cfg)

    assert index_path(cfg, "IA-LLMs") == index_path(cfg, "IA/LLMs")
    assert first.written == [index_path(cfg, "IA-LLMs")]
    assert first.blocked == [index_path(cfg, "IA/LLMs")]
    assert "Uno" in text and "Dos" not in text
    assert index_path(cfg, "IA-LLMs").read_text(encoding="utf-8") == text
    assert second.blocked == first.blocked


def test_the_index_links_to_the_real_filename_after_a_rename(tmp_path):
    cfg = make_config(tmp_path)
    path = write_note(cfg, note("a1", "WireGuard", "Redes"), "es")
    renamed = path.rename(path.with_name("mi-nombre.md"))

    rebuild_indexes(cfg)

    text = index_path(cfg, "Redes").read_text(encoding="utf-8")
    assert f"[[{renamed.stem}|WireGuard]]" in text


def test_a_hand_edited_title_keeps_the_link_and_shows_the_new_title(tmp_path):
    cfg = make_config(tmp_path)
    path = write_note(cfg, note("a1", "WireGuard", "Redes"), "es")
    path.write_text(path.read_text(encoding="utf-8").replace("title: WireGuard", "title: VPN moderna"),
                    encoding="utf-8")

    rebuild_indexes(cfg)

    text = index_path(cfg, "Redes").read_text(encoding="utf-8")
    assert f"[[{path.stem}|VPN moderna]]" in text


def test_duplicate_ids_each_link_to_their_own_file(tmp_path):
    cfg = make_config(tmp_path)
    p1 = write_note(cfg, note("a1", "WireGuard", "Redes"), "es")
    p2 = cfg.links_dir / "copia.md"
    p2.write_bytes(p1.read_bytes())

    rebuild_indexes(cfg)

    text = index_path(cfg, "Redes").read_text(encoding="utf-8")
    assert f"[[{p1.stem}|" in text and "[[copia|" in text


def test_pipes_and_brackets_in_a_title_do_not_break_the_wikilink(tmp_path):
    cfg = make_config(tmp_path)
    path = write_note(cfg, note("a1", "WireGuard vs OpenVPN | Ars [Technica]", "Redes"), "es")

    rebuild_indexes(cfg)

    text = index_path(cfg, "Redes").read_text(encoding="utf-8")
    assert f"[[{path.stem}|WireGuard vs OpenVPN Ars Technica]]" in text


def test_a_newline_in_a_category_does_not_break_the_heading(tmp_path):
    cfg = make_config(tmp_path)
    write_note(cfg, note("a1", "Algo", "Redes\nOtra"), "es")
    rebuild_indexes(cfg)
    assert "# Redes Otra · 1 link\n" in index_path(cfg, "Redes\nOtra").read_text(encoding="utf-8")


def test_the_heading_is_singular_for_one_link_and_no_empty_backticks(tmp_path):
    cfg = make_config(tmp_path)
    write_note(cfg, note("a1", "Algo", "Redes", tags=()), "es")
    rebuild_indexes(cfg)
    text = index_path(cfg, "Redes").read_text(encoding="utf-8")
    assert "# Redes · 1 link\n" in text
    assert "``" not in text


@pytest.mark.skipif(os.geteuid() == 0, reason="chmod 000 does not bite as root")
def test_a_note_that_cannot_be_read_is_reported_and_keeps_the_other_indexes(tmp_path):
    cfg = make_config(tmp_path)
    locked = write_note(cfg, note("a1", "WireGuard", "Redes"), "es")
    write_note(cfg, note("b2", "Masa madre", "Cocina"), "es")
    locked.chmod(0o000)
    try:
        result = rebuild_indexes(cfg)
    finally:
        locked.chmod(0o644)
    assert result.skipped == [locked]
    assert index_path(cfg, "Cocina").exists()


def test_an_escaping_symlink_reaches_blocked_in_a_rebuild(tmp_path):
    cfg = make_config(tmp_path)
    outside = tmp_path / "elsewhere.md"
    outside.write_text("---\noknowledge: 1\nkind: index\n---\nkeep\n", encoding="utf-8")
    link = index_path(cfg, "Redes")
    link.symlink_to(outside)
    write_note(cfg, note("a1", "WireGuard", "Redes"), "es")
    write_note(cfg, note("b2", "Masa madre", "Cocina"), "es")

    result = rebuild_indexes(cfg)

    assert result.blocked == [link]
    assert index_path(cfg, "Cocina").exists()
    assert outside.read_text(encoding="utf-8").endswith("keep\n")
    assert link.is_symlink()
