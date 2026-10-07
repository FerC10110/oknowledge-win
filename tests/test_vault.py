import pytest

from oknowledge.config import Config
from oknowledge.model import Mention, Note
from oknowledge.urls import search_url
from oknowledge.vault import (
    ProtectedNote, note_path, read_front, read_note, render, slug, write_note,
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
    assert slug("日本語のタイトル", "fallback") == "fallback"


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
    assert target.read_text(encoding="utf-8") == "no soy tuya\n"


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

    monkeypatch.setattr("oknowledge.atomic.os.replace", boom)
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


def test_a_marked_file_with_an_impossible_date_reads_as_none(tmp_path):
    cfg = make_config(tmp_path)
    f = cfg.links_dir / "baddate.md"
    f.write_text(
        "---\noknowledge: 1\nurl: https://e.com/a\npublished: 2026-13-45\n---\n\nhola\n",
        encoding="utf-8",
    )
    before = f.read_bytes()
    assert read_front(f) is None
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


def test_points_empty_with_a_body_round_trips(tmp_path):
    cfg = make_config(tmp_path)
    note = make_note(points=[], body="Texto extraido.\n\n- una viñeta del articulo")
    back = read_note(write_note(cfg, note, "es"))
    assert back == note
    assert back.points == []


def test_a_body_with_an_inner_heading_round_trips(tmp_path):
    cfg = make_config(tmp_path)
    note = make_note(body="Intro\n\n## Deep dive\n\nmas texto")
    back = read_note(write_note(cfg, note, "es"))
    assert back.body == "Intro\n\n## Deep dive\n\nmas texto"
    assert back == note


def test_a_summary_with_a_heading_line_round_trips(tmp_path):
    cfg = make_config(tmp_path)
    note = make_note(summary="Primero.\n\n## Seccion\n\nSegundo.", body="Cuerpo.")
    back = read_note(write_note(cfg, note, "es"))
    assert back == note


def test_body_bullets_are_not_points(tmp_path):
    cfg = make_config(tmp_path)
    note = make_note(points=["real"], body="- a\n- b")
    back = read_note(write_note(cfg, note, "es"))
    assert back.points == ["real"]
    assert back.body == "- a\n- b"


def test_english_headings_round_trip(tmp_path):
    cfg = make_config(tmp_path)
    note = make_note(body="Texto.")
    assert read_note(write_note(cfg, note, "en")) == note


def test_the_vault_root_itself_is_refused(tmp_path):
    cfg = Config(vault=tmp_path / "vault")
    cfg.vault.mkdir()
    with pytest.raises(ProtectedNote):
        write_note(cfg, make_note(), "es", path=cfg.root)
    assert list(cfg.vault.iterdir()) == []


def test_separators_in_saved_or_id_still_write_a_flat_file(tmp_path):
    cfg = make_config(tmp_path)
    note = make_note(saved="../../../pwned", id="a/b/../c", title="🔥")
    path = write_note(cfg, note, "es")
    assert path.parent == cfg.links_dir.resolve()
    assert list(cfg.links_dir.iterdir()) == [path]
    nested = write_note(cfg, make_note(saved="2026/10/03", id="z1"), "es")
    assert nested.parent == cfg.links_dir.resolve()
    assert not (cfg.links_dir / "2026").exists()


def test_new_notes_honor_the_umask(tmp_path):
    import os
    old = os.umask(0o077)
    try:
        path = write_note(make_config(tmp_path), make_note(), "es")
    finally:
        os.umask(old)
    assert path.stat().st_mode & 0o777 == 0o600


# --- the note is at least as durable as the entry that describes it (F3) -----
# queue._write passes fsync_dir=True; write_note did not. A power cut between
# the two could leave a durable `ok` entry for a note whose directory entry
# never reached the disk -- and an `ok` entry is in neither unfinished() nor
# orphaned(), so nothing would ever look at that link again.

def _synced_kinds(monkeypatch):
    import os
    import stat as stat_module

    synced = []
    real = os.fsync

    def watched(fd):
        synced.append(stat_module.S_ISDIR(os.fstat(fd).st_mode))
        return real(fd)

    monkeypatch.setattr(os, "fsync", watched)
    return synced


def test_a_notes_directory_entry_is_synced(tmp_path, monkeypatch):
    cfg = make_config(tmp_path)
    synced = _synced_kinds(monkeypatch)

    write_note(cfg, make_note(), "es")

    assert any(synced), "the note's directory was not synced"


def test_a_note_is_flushed_and_so_is_its_directory(tmp_path, monkeypatch):
    """Both halves: the bytes of the note and the name that points at them."""
    cfg = make_config(tmp_path)
    synced = _synced_kinds(monkeypatch)

    write_note(cfg, make_note(), "es")

    assert True in synced and False in synced      # a directory and a file


def note_with(mentions):
    return Note(id="a1", url="https://youtu.be/x", title="Un video",
                category="Redes", tags=["x"], type="youtube", source="youtu.be",
                saved="2026-10-05", summary="Resumen.", points=["uno"],
                mentions=mentions)


def test_a_note_keeps_its_mentions_through_a_write_and_a_read(tmp_path):
    path = tmp_path / "n.md"
    note = note_with([Mention(name="opencode", url="https://opencode.ai"),
                      Mention(name="Railway", url=search_url("Railway"))])

    path.write_text(render(note, "es"), encoding="utf-8")

    assert read_note(path).mentions == note.mentions


def test_a_note_that_was_never_asked_reads_none(tmp_path):
    path = tmp_path / "n.md"
    path.write_text(render(note_with(None), "es"), encoding="utf-8")

    assert read_note(path).mentions is None


def test_a_note_asked_with_nothing_found_reads_an_empty_list(tmp_path):
    """Not None: this one was asked. That is what stops the backfill from
    spending a model call on it again."""
    path = tmp_path / "n.md"
    path.write_text(render(note_with([]), "es"), encoding="utf-8")

    assert read_note(path).mentions == []


def test_a_bracket_in_a_name_survives(tmp_path):
    path = tmp_path / "n.md"
    note = note_with([Mention(name="Algo [raro]", url="https://e.com")])

    path.write_text(render(note, "es"), encoding="utf-8")

    assert read_note(path).mentions == note.mentions


def test_a_hand_written_bullet_with_no_link_becomes_a_search(tmp_path):
    """This section gets hand-edited. Nothing written in it is thrown away."""
    path = tmp_path / "n.md"
    path.write_text(render(note_with([]), "es").replace(
        "## Menciones\n", "## Menciones\n\n- Caddy\n"), encoding="utf-8")

    assert read_note(path).mentions == [Mention(name="Caddy", url=search_url("Caddy"))]


def test_a_mentions_heading_inside_the_original_content_is_not_a_section(tmp_path):
    """A transcript can say anything, '## Menciones' included."""
    path = tmp_path / "n.md"
    note = note_with(None)
    note.body = "El video dice:\n\n## Menciones\n\n- no soy una seccion\n"
    path.write_text(render(note, "es"), encoding="utf-8")

    read = read_note(path)

    assert read.mentions is None
    assert "## Menciones" in read.body


def test_the_original_content_still_parses_with_mentions_in_between(tmp_path):
    """HEADINGS grew a middle element: the content heading moved from h[1] to
    h[2], and reading the body back is where getting that wrong shows up."""
    path = tmp_path / "n.md"
    note = note_with([Mention(name="opencode", url="https://opencode.ai")])
    note.body = "El texto del video."
    path.write_text(render(note, "es"), encoding="utf-8")

    read = read_note(path)

    assert read.body == "El texto del video."
    assert read.points == ["uno"]
    assert read.mentions == note.mentions


def test_a_url_with_parentheses_survives(tmp_path):
    path = tmp_path / "n.md"
    note = note_with([Mention(name="Foo", url="https://en.wikipedia.org/wiki/Foo_(bar)")])

    path.write_text(render(note, "es"), encoding="utf-8")

    assert read_note(path).mentions == note.mentions


def test_an_empty_bullet_is_not_a_mention(tmp_path):
    path = tmp_path / "n.md"
    path.write_text(render(note_with([]), "es").replace(
        "## Menciones\n", "## Menciones\n\n- \n- Caddy\n"), encoding="utf-8")

    assert read_note(path).mentions == [Mention(name="Caddy", url=search_url("Caddy"))]


def test_a_bullet_that_is_neither_form_is_kept_verbatim_as_the_name(tmp_path):
    path = tmp_path / "n.md"
    path.write_text(render(note_with([]), "es").replace(
        "## Menciones\n", "## Menciones\n\n- [roto](\n"), encoding="utf-8")

    assert read_note(path).mentions == [
        Mention(name="[roto](", url=search_url("[roto]("))]


def test_the_english_headings_round_trip(tmp_path):
    path = tmp_path / "n.md"
    note = note_with([Mention(name="opencode", url="https://opencode.ai")])
    note.body = "The video text."

    text = render(note, "en")
    path.write_text(text, encoding="utf-8")

    assert "## Mentions\n" in text
    read = read_note(path)
    assert read.mentions == note.mentions
    assert read.points == ["uno"]
    assert read.body == "The video text."


HAND_EDITED = """\
## Menciones

- [opencode](https://opencode.ai)
* [Caddy](https://caddyserver.com)
  - [sub](https://sub.example)
1. [Numbered](https://num.example)
Esto lo escribi yo a mano y me importa.
- [Railway](https://duckduckgo.com/?q=Railway)
"""


def _with_section(tmp_path, section):
    path = tmp_path / "n.md"
    text = render(note_with(None), "es").rstrip("\n") + "\n\n" + section
    path.write_text(text, encoding="utf-8")
    return path


def test_a_hand_edited_section_survives_a_round_trip(tmp_path):
    """README: 'Editing by hand is part of the design.' One click on a
    mention's x rewrites this section, and nothing a person typed may go."""
    cfg = make_config(tmp_path)
    path = _with_section(tmp_path, HAND_EDITED)

    first = read_note(path)
    written = write_note(cfg, first, "es")
    second = read_note(written)

    assert [(m.name, m.url) for m in second.mentions] == [
        ("opencode", "https://opencode.ai"),
        ("Caddy", "https://caddyserver.com"),
        ("sub", "https://sub.example"),
        ("Railway", "https://duckduckgo.com/?q=Railway"),
    ]
    text = written.read_text(encoding="utf-8")
    assert "1. [Numbered](https://num.example)" in text
    assert "Esto lo escribi yo a mano y me importa." in text
    # And a second pass changes nothing: the lines are not duplicated.
    again = write_note(cfg, second, "es")
    assert again.read_text(encoding="utf-8") == text


def test_the_three_bullet_markers_all_make_mentions(tmp_path):
    path = _with_section(tmp_path,
                         "## Menciones\n\n- [a](https://a.x)\n* [b](https://b.x)\n"
                         "+ [c](https://c.x)\n   * [d](https://d.x)\n")

    assert [m.name for m in read_note(path).mentions] == ["a", "b", "c", "d"]


def test_a_repeated_mentions_heading_accumulates(tmp_path):
    """Like a repeated key-points heading: the first list is not discarded."""
    path = _with_section(tmp_path,
                         "## Menciones\n\n- [a](https://a.x)\n\n"
                         "## Menciones\n\n- [b](https://b.x)\n")

    assert [m.name for m in read_note(path).mentions] == ["a", "b"]


# --- colecciones: el único campo que es del usuario y no del modelo ----------

def test_the_collections_of_a_note_survive_the_round_trip(tmp_path):
    cfg = make_config(tmp_path)
    note = make_note(collections=["Casa nueva", "Leer después"])
    path = write_note(cfg, note, "es")

    assert read_note(path) == note


def test_collections_are_written_next_to_the_tags(tmp_path):
    """They are the other way of classifying a note, so they read together."""
    cfg = make_config(tmp_path)
    text = write_note(cfg, make_note(collections=["Casa"]), "es").read_text()
    head = text.split("---")[1]

    assert head.index("tags:") < head.index("collections:") < head.index("type:")


def test_a_note_in_no_collection_writes_no_key(tmp_path):
    """An empty list in every one of a thousand notes says nothing and is a
    thousand lines of frontmatter to scroll past."""
    cfg = make_config(tmp_path)
    path = write_note(cfg, make_note(), "es")

    assert "collections" not in path.read_text()
    assert read_front(path).get("collections") is None
    assert read_note(path).collections == []


def test_collections_that_are_not_a_list_make_the_note_unreadable(tmp_path):
    """The same answer `tags` gives: a frontmatter broken by hand is worth
    seeing, not worth guessing at."""
    cfg = make_config(tmp_path)
    path = write_note(cfg, make_note(collections=["Casa"]), "es")
    path.write_text(path.read_text().replace("collections:\n- Casa", "collections: Casa"))

    assert read_note(path) is None
