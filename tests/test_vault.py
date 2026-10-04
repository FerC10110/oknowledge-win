import pytest

from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.vault import (
    ProtectedNote, note_path, read_front, read_note, slug, write_note,
)


def make_config(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    return Config(vault=vault)


def make_note(**over):
    values = dict(
        id="9f2a1c4b8e07",
        url="https://arstechnica.com/vpn",
        title="WireGuard vs OpenVPN",
        category="Redes",
        tags=["vpn", "wireguard"],
        type="article",
        source="arstechnica.com",
        saved="2026-10-03",
        summary="Compara ambos protocolos.\nY explica cuál conviene.",
        points=["Corre en el kernel", "Menos código que auditar"],
    )
    values.update(over)
    return Note(**values)


def test_a_note_survives_the_round_trip(tmp_path):
    cfg = make_config(tmp_path)
    note = make_note(body="El texto entero del artículo.", author="Dan Goodin")
    path = write_note(cfg, note, "es")

    assert path.name == "2026-10-03-wireguard-vs-openvpn.md"
    back = read_note(path)
    assert back == note


def test_the_frontmatter_carries_the_marker(tmp_path):
    cfg = make_config(tmp_path)
    path = write_note(cfg, make_note(), "es")
    front = read_front(path)
    assert front["oknowledge"] == 1
    assert front["id"] == "9f2a1c4b8e07"
    assert front["category"] == "Redes"


def test_summary_mode_leaves_no_original_content(tmp_path):
    cfg = make_config(tmp_path)
    path = write_note(cfg, make_note(content="summary", body=None), "es")
    text = path.read_text(encoding="utf-8")
    assert "Contenido original" not in text
    assert read_note(path).body is None


def test_a_title_with_no_latin_letters_still_makes_a_filename(tmp_path):
    # An all-emoji or all-kanji title leaves no slug: it falls back to the id,
    # which is always valid and always unique.
    cfg = make_config(tmp_path)
    path = write_note(cfg, make_note(title="🔥🔥🔥"), "es")
    assert path.name == "2026-10-03-9f2a1c4b8e07.md"
    assert read_note(path).title == "🔥🔥🔥"


def test_slug_falls_back_only_when_there_is_nothing_to_use():
    assert slug("Qué pasó en Córdoba", "x") == "que-paso-en-cordoba"
    assert slug("   ", "fallback") == "fallback"
    assert slug("***", "fallback") == "fallback"


def test_a_note_of_yours_in_our_folder_is_never_touched(tmp_path):
    # One of the user's own notes, no marker, sitting right where ours would go.
    cfg = make_config(tmp_path)
    mine = cfg.links_dir / "2026-10-03-wireguard-vs-openvpn.md"
    mine.write_text("# Mis apuntes\n\nNo me toques.\n", encoding="utf-8")
    before = mine.read_text(encoding="utf-8")

    path = write_note(cfg, make_note(), "es")

    assert path.name == "2026-10-03-wireguard-vs-openvpn-2.md"
    assert mine.read_text(encoding="utf-8") == before


def test_a_file_without_the_marker_reads_as_none(tmp_path):
    cfg = make_config(tmp_path)
    other = cfg.links_dir / "ajena.md"
    other.write_text("---\ntitle: mía\n---\n\nhola\n", encoding="utf-8")
    assert read_front(other) is None
    assert read_note(other) is None


def test_rewriting_the_same_link_reuses_its_file(tmp_path):
    cfg = make_config(tmp_path)
    first = write_note(cfg, make_note(), "es")
    second = write_note(cfg, make_note(summary="Otro resumen."), "es")
    assert first == second
    assert read_note(second).summary == "Otro resumen."
    assert len(list(cfg.links_dir.glob("*.md"))) == 1


def test_a_foreign_file_on_the_final_path_is_refused(tmp_path):
    # Defense in depth: note_path already steps around foreign files, so
    # getting here means something changed underneath us.
    cfg = make_config(tmp_path)
    note = make_note()
    target = note_path(cfg, note)
    target.write_text("no soy tuya\n", encoding="utf-8")
    with pytest.raises(ProtectedNote):
        write_note(cfg, note, "es", path=target)


def test_a_path_outside_the_vault_is_refused(tmp_path):
    cfg = make_config(tmp_path)
    outside = tmp_path / "elsewhere.md"
    with pytest.raises(ProtectedNote, match="outside the managed folder"):
        write_note(cfg, make_note(), "es", path=outside)
    assert not outside.exists()


def test_a_path_climbing_out_with_dotdot_is_refused(tmp_path):
    cfg = make_config(tmp_path)
    sneaky = cfg.links_dir / ".." / ".." / "escape.md"
    with pytest.raises(ProtectedNote):
        write_note(cfg, make_note(), "es", path=sneaky)
    assert not (cfg.vault / "escape.md").exists()


def test_a_symlink_pointing_outside_is_refused(tmp_path):
    cfg = make_config(tmp_path)
    outside = tmp_path / "outside.md"
    link = cfg.links_dir / "link.md"
    link.symlink_to(outside)
    with pytest.raises(ProtectedNote):
        write_note(cfg, make_note(), "es", path=link)
    assert not outside.exists()


def test_a_symlinked_directory_pointing_outside_is_refused(tmp_path):
    cfg = make_config(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (cfg.links_dir / "sub").symlink_to(elsewhere, target_is_directory=True)
    with pytest.raises(ProtectedNote):
        write_note(cfg, make_note(), "es", path=cfg.links_dir / "sub" / "n.md")
    assert list(elsewhere.iterdir()) == []


def test_a_write_leaves_no_temp_files(tmp_path):
    cfg = make_config(tmp_path)
    path = write_note(cfg, make_note(), "es")
    write_note(cfg, make_note(summary="Otro."), "es")
    assert list(cfg.links_dir.iterdir()) == [path]


def test_a_failed_write_cleans_up_and_keeps_the_old_note(tmp_path, monkeypatch):
    cfg = make_config(tmp_path)
    path = write_note(cfg, make_note(), "es")
    before = path.read_bytes()

    def boom(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr("oknowledge.vault.os.replace", boom)
    with pytest.raises(OSError):
        write_note(cfg, make_note(summary="Nuevo."), "es")
    monkeypatch.undo()
    assert path.read_bytes() == before
    assert list(cfg.links_dir.iterdir()) == [path]


def test_a_marked_file_missing_a_key_reads_as_none(tmp_path):
    cfg = make_config(tmp_path)
    f = cfg.links_dir / "edited.md"
    f.write_text("---\ntitle: x\noknowledge: 1\n---\n\nhola\n", encoding="utf-8")
    before = f.read_bytes()
    assert read_note(f) is None
    assert f.read_bytes() == before


def test_a_marked_file_with_a_wrong_type_reads_as_none(tmp_path):
    cfg = make_config(tmp_path)
    good = write_note(cfg, make_note(), "es")
    f = cfg.links_dir / "bad.md"
    f.write_text(good.read_text(encoding="utf-8").replace("tags:", "tags: oops\nold:"), encoding="utf-8")
    before = f.read_bytes()
    assert read_note(f) is None
    assert f.read_bytes() == before


def test_a_marked_file_with_broken_yaml_reads_as_none(tmp_path):
    cfg = make_config(tmp_path)
    f = cfg.links_dir / "broken.md"
    f.write_text("---\noknowledge: 1\nurl: [unclosed\n---\n\nhola\n", encoding="utf-8")
    before = f.read_bytes()
    assert read_note(f) is None
    assert f.read_bytes() == before


def test_note_path_steps_around_an_unparseable_marked_file(tmp_path):
    cfg = make_config(tmp_path)
    f = cfg.links_dir / "2026-10-03-wireguard-vs-openvpn.md"
    f.write_text("---\noknowledge: 1\n---\n\nhola\n", encoding="utf-8")
    before = f.read_bytes()
    path = write_note(cfg, make_note(), "es")
    assert path.name == "2026-10-03-wireguard-vs-openvpn-2.md"
    assert f.read_bytes() == before
