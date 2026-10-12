"""An idea: what you wrote, under an id of its own, with the links you
added to it. Nothing here calls a model."""

import pytest

from oknowledge.config import Config
from oknowledge.ideas import (
    CATEGORY, IdeaFull, add_related, clean_title, drop_related, idea_id,
    new_idea,
)
from oknowledge.urls import link_id
from oknowledge.vault import find_note, note_path, read_note, write_note

INSTANT = "2026-10-12T21:04:05.123456+00:00"


@pytest.fixture
def cfg(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    return Config(vault=vault)


@pytest.fixture
def idea(cfg):
    note = new_idea("Una app que me arme la rutina.", "Gimnasio con IA",
                    "2026-10-12", INSTANT)
    write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ideas))
    return note


def now(cfg, note):
    return find_note(cfg, note.id, shelf=cfg.ideas)[1]


def test_an_idea_takes_its_id_from_the_moment_it_was_written():
    assert idea_id(INSTANT) == link_id(f"idea:{INSTANT}")
    assert idea_id(INSTANT) != idea_id("2026-10-12T21:04:05.123457+00:00")


def test_a_new_idea_is_your_text_and_nothing_a_model_wrote():
    note = new_idea("  Una app.\n\n", "  Gimnasio \n con   IA ", "2026-10-12", INSTANT)
    assert note.id == idea_id(INSTANT)
    assert (note.type, note.category, note.url, note.source) == ("idea", CATEGORY, "", "")
    assert note.title == "Gimnasio con IA"
    assert note.my_note == "Una app."
    assert (note.summary, note.tags, note.points, note.engine) == ("", [], [], "")


def test_a_title_is_one_line_and_not_a_paragraph():
    assert clean_title("a\nb\tc") == "a b c"
    assert len(clean_title("x" * 300)) == 120


def test_your_text_comes_back_exactly_as_you_wrote_it(cfg):
    text = ("Una app para el gimnasio.\n\n## Cómo funcionaría\n\n"
            "- lee las series\n- propone la carga\n\n1. primero\n2. después\n\n"
            "Un párrafo final con *énfasis* y `código`.")
    note = new_idea(text, "", "2026-10-12", INSTANT)
    path = write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ideas))
    assert read_note(path).my_note == text


def test_a_link_joins_an_idea_once(cfg, idea):
    add_related(cfg, idea.id, "2026-10-02-rutina", "es")
    add_related(cfg, idea.id, "2026-10-02-rutina", "es")
    assert now(cfg, idea).related == ["2026-10-02-rutina"]


def test_joining_reads_the_idea_as_it_is_on_disk_now(cfg, idea):
    add_related(cfg, idea.id, "a", "es")
    path, on_disk = find_note(cfg, idea.id, shelf=cfg.ideas)
    on_disk.related.append("b")
    on_disk.state = "doing"
    write_note(cfg, on_disk, "es", path=path)
    add_related(cfg, idea.id, "c", "es")
    assert now(cfg, idea).related == ["a", "b", "c"]
    assert now(cfg, idea).state == "doing"


def test_joining_touches_nothing_else(cfg, idea):
    add_related(cfg, idea.id, "a", "es")
    after = now(cfg, idea)
    assert (after.title, after.my_note) == (idea.title, idea.my_note)


def test_a_full_idea_says_so_instead_of_dropping_the_link(cfg, idea):
    for n in range(16):
        add_related(cfg, idea.id, f"n{n}", "es")
    with pytest.raises(IdeaFull):
        add_related(cfg, idea.id, "one-more", "es")
    assert "one-more" not in now(cfg, idea).related
    add_related(cfg, idea.id, "n3", "es")              # already in: no error


def test_an_idea_that_is_not_there_is_none(cfg):
    assert add_related(cfg, "000000000000", "a", "es") is None
    assert drop_related(cfg, "000000000000", "a", "es") is None


def test_a_link_leaves_an_idea(cfg, idea):
    add_related(cfg, idea.id, "a", "es")
    add_related(cfg, idea.id, "b", "es")
    drop_related(cfg, idea.id, "a", "es")
    drop_related(cfg, idea.id, "never-there", "es")
    assert now(cfg, idea).related == ["b"]


def test_a_new_idea_is_a_seed():
    # The seed chip is how you find what you have not started; an idea with
    # no state at all would be in no chip but "All".
    assert new_idea("x", "", "2026-10-12", INSTANT).state == "pending"


@pytest.mark.parametrize("heading", [
    "## Menciones", "## Mentions", "## Mi nota", "## My note",
    "## Contenido original", "## Original content",
])
def test_your_text_survives_the_app_s_own_headings_inside_it(cfg, heading):
    # Your text is the idea's whole body after its heading: a line that
    # happens to look like one of the app's sections is still yours.
    text = f"Una app.\n\n{heading}\n\n- algo\n\nY sigue."
    note = new_idea(text, "T", "2026-10-12", INSTANT)
    path = write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ideas))
    assert read_note(path).my_note == text
