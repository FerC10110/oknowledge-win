"""An idea's action sections live in its note, between the points and
your text, as markdown you can edit in Obsidian."""

import pytest

from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.model import Note
from oknowledge.vault import (
    ACTION_HEADINGS, ACTIONS, all_entries, find_note, note_path, read_note,
    render, write_note,
)

INSTANT = "2026-10-12T21:04:05.123456+00:00"


@pytest.fixture
def cfg(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    return Config(vault=vault)


def idea(**fields):
    note = new_idea("Una app de rutinas.", "Gym", "2026-10-12", INSTANT)
    note.points = ["Para quien entrena solo."]
    for key, value in fields.items():
        setattr(note, key, value)
    return note


def roundtrip(cfg, note, language="es"):
    path = write_note(cfg, note, language, path=note_path(cfg, note, shelf=cfg.ideas))
    return read_note(path), path


def test_the_four_actions_and_their_headings():
    assert ACTIONS == ("exists", "improve", "expand", "links")
    assert ACTION_HEADINGS["es"] == {"exists": "Ya existe", "improve": "Mejoras",
                                     "expand": "Ampliación",
                                     "links": "Links que pueden servir"}
    assert ACTION_HEADINGS["en"] == {"exists": "Already out there",
                                     "improve": "Improvements", "expand": "Expansion",
                                     "links": "Links that may help"}


@pytest.mark.parametrize("language", ["es", "en"])
def test_every_section_comes_back(cfg, language):
    sections = {"exists": "**Hay parecidas.**\n\n- [X](https://x.com) — igual",
                "improve": "- **Lento** — cachear", "expand": "- Modo offline",
                "links": "*Entre: Redes.*\n\n- [[2026-10-02-vpn]] — sirve"}
    after, _ = roundtrip(cfg, idea(actions=dict(sections)), language)
    assert after.actions == sections
    assert after.my_note == "Una app de rutinas."
    assert after.points == ["Para quien entrena solo."]


def test_sections_sit_after_the_points_and_before_your_text(cfg):
    _, path = roundtrip(cfg, idea(actions={"improve": "- a", "exists": "b"}))
    text = path.read_text(encoding="utf-8")
    order = [text.index(h) for h in ("## Puntos clave", "## Ya existe", "## Mejoras", "## Mi nota")]
    assert order == sorted(order)


def test_an_idea_without_actions_writes_no_heading(cfg):
    assert render(idea(), "es") == render(idea(actions={"improve": "  "}), "es")
    assert "## Mejoras" not in render(idea(), "es")


def test_a_heading_inside_your_text_stays_yours(cfg):
    mine = "Primero esto.\n\n## Mejoras\n\n- mía"
    after, _ = roundtrip(cfg, idea(my_note=mine))
    assert after.my_note == mine
    assert after.actions == {}


def test_a_card_keeps_a_typed_heading_in_its_summary(cfg):
    card = Note(id="aaaaaaaaaaaa", url="https://imdb.com/title/tt1", title="T",
                category="Películas", tags=[], type="movie", source="imdb.com",
                saved="2026-10-11", summary="Un cyborg.\n\n## Mejoras\n\n- nada")
    path = write_note(cfg, card, "es", path=note_path(cfg, card, shelf=cfg.ocio))
    after = read_note(path)
    assert "## Mejoras" in after.summary
    assert after.actions == {}


def test_a_hand_edited_section_survives_another_action(cfg):
    note, path = roundtrip(cfg, idea(actions={"improve": "- a mano"}))
    note.actions["expand"] = "- nueva"
    write_note(cfg, note, "es", path=path)
    assert read_note(path).actions == {"improve": "- a mano", "expand": "- nueva"}


def test_all_entries_pairs_each_note_with_its_file(cfg):
    note, path = roundtrip(cfg, idea())
    assert all_entries(cfg, cfg.ideas) == [(path, find_note(cfg, note.id, shelf=cfg.ideas)[1])]


def test_a_heading_of_yours_after_a_section_is_not_swallowed_by_it(cfg):
    note, path = roundtrip(cfg, idea(my_note="", actions={"improve": "- a"}))
    text = path.read_text(encoding="utf-8")
    path.write_text(text.rstrip() + "\n\n## Notas mías\n\nalgo que escribí\n", encoding="utf-8")
    after = read_note(path)
    assert after.actions == {"improve": "- a"}
    assert after.my_note == "## Notas mías\n\nalgo que escribí"
    write_note(cfg, after, "es", path=path)
    assert read_note(path).my_note == after.my_note


def test_your_heading_and_your_note_are_both_kept(cfg):
    note, path = roundtrip(cfg, idea(actions={"improve": "- a"}))
    text = path.read_text(encoding="utf-8").replace(
        "## Mi nota", "## Notas mías\n\nantes\n\n## Mi nota")
    path.write_text(text, encoding="utf-8")
    after = read_note(path)
    assert after.actions == {"improve": "- a"}
    assert after.my_note == "## Notas mías\n\nantes\n\nUna app de rutinas."
