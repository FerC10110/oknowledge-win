"""The shelf an idea lives on, and the two things an idea has that nothing
else does: links of its own, and a fourth state."""

import pytest
import yaml

from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.vault import (
    IDEA_STATES, MAX_RELATED, STATES, all_notes, find_note, normalize_related,
    note_path, read_note, rebuild_indexes, states_for, update_note, write_note,
)

IDEA = "1dea1dea1dea"
LINK = "bbbbbbbbbbbb"


@pytest.fixture
def cfg(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    return Config(vault=vault)


def an_idea(**overrides):
    fields = dict(id=IDEA, url="", title="Gimnasio con IA", category="Ideas",
                  tags=[], type="idea", source="", saved="2026-10-12",
                  summary="", my_note="Una app que me arme la rutina.")
    fields.update(overrides)
    return Note(**fields)


def put(cfg, note):
    return write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ideas))


def test_the_ideas_shelf_is_its_own_folder_with_its_own_indexes(cfg):
    assert cfg.ideas.name == "ideas"
    assert cfg.ideas.dir == cfg.root / "ideas"
    assert cfg.ideas.index_dir == cfg.root / "ideas"
    assert cfg.shelf("ideas") == cfg.ideas
    assert cfg.shelf("ocio") == cfg.ocio
    assert cfg.shelf("nope") == cfg.links


def test_an_idea_is_not_a_link_and_a_link_is_not_an_idea(cfg):
    put(cfg, an_idea())
    write_note(cfg, an_idea(id=LINK, url="https://wireguard.com",
                            title="WireGuard", category="Redes", type="article",
                            source="wireguard.com", my_note=""), "es")
    assert [n.id for n in all_notes(cfg)] == [LINK]
    assert [n.id for n in all_notes(cfg, cfg.ideas)] == [IDEA]
    assert all_notes(cfg, cfg.ocio) == []


def test_related_is_written_as_wikilinks_and_read_back_as_stems(cfg):
    path = put(cfg, an_idea(related=["2026-10-02-rutina-de-fuerza", "2026-10-05-rpe"]))
    front = yaml.safe_load(path.read_text(encoding="utf-8").split("---")[1])
    assert front["related"] == ["[[2026-10-02-rutina-de-fuerza]]", "[[2026-10-05-rpe]]"]
    assert read_note(path).related == ["2026-10-02-rutina-de-fuerza", "2026-10-05-rpe"]


def test_a_note_with_no_related_carries_no_line_for_it(cfg):
    path = put(cfg, an_idea())
    assert "related" not in path.read_text(encoding="utf-8")


def test_related_as_obsidian_or_a_hand_leaves_it():
    assert normalize_related(["[[a]]", "[[b|Bee]]", " c ", "[[links/d]]",
                              "e.md", "", 7, None, "[[a]]"]) == ["a", "b", "c", "d", "e"]


def test_related_typed_as_text_does_not_lose_the_idea(cfg):
    path = put(cfg, an_idea())
    text = path.read_text(encoding="utf-8").replace(
        "type: idea", "type: idea\nrelated: oops", 1)
    path.write_text(text, encoding="utf-8")
    assert read_note(path).related == []
    assert read_note(path).my_note == "Una app que me arme la rutina."


def test_related_stops_at_the_cap():
    assert MAX_RELATED == 16
    assert len(normalize_related([f"n{i}" for i in range(40)])) == 16


def test_an_idea_can_be_dropped(cfg):
    assert IDEA_STATES == ("pending", "doing", "done", "dropped")
    assert states_for("idea") == IDEA_STATES
    assert states_for("movie") == STATES
    put(cfg, an_idea())
    update_note(cfg, IDEA, "es", state="dropped", shelf=cfg.ideas)
    assert find_note(cfg, IDEA, shelf=cfg.ideas)[1].state == "dropped"


def test_a_card_still_refuses_dropped(cfg):
    card = an_idea(id="aaaaaaaaaaaa", type="movie", category="Películas",
                   url="https://imdb.com/title/tt1", source="imdb.com", state="done")
    write_note(cfg, card, "es", path=note_path(cfg, card, shelf=cfg.ocio))
    update_note(cfg, card.id, "es", state="dropped", shelf=cfg.ocio)
    assert find_note(cfg, card.id, shelf=cfg.ocio)[1].state == "done"


def test_an_untitled_idea_is_still_a_named_line_in_its_index(cfg):
    path = put(cfg, an_idea(title=""))
    rebuild_indexes(cfg, "es", shelf=cfg.ideas)
    index = (cfg.ideas.index_dir / "Ideas.md").read_text(encoding="utf-8")
    assert f"[[{path.stem}|{path.stem}]]" in index
