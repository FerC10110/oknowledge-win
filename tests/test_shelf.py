"""Two folders of notes in one vault, told apart by a shelf.

`links/` is the one that always existed, with its category indexes at the root
of the managed folder, where Obsidian shows them beside the folder. `ocio/`
keeps its own indexes inside itself, so a rebuild of one shelf can never
delete the other's.

A shelf of None means links, everywhere: every call that existed before this
behaves exactly as it did.
"""

import pytest

from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.vault import (
    all_notes,
    note_path,
    rebuild_indexes,
    write_index,
    write_note,
)
from oknowledge.web.index import Library


@pytest.fixture
def card_note():
    return Note(
        id="aaaaaaaaaaaa", url="https://imdb.com/title/tt0088247",
        title="The Terminator", category="Películas", tags=["ciencia-ficcion"],
        type="movie", source="imdb.com", saved="2026-10-11",
        summary="Un cyborg viaja al pasado.",
    )


@pytest.fixture
def link_note():
    return Note(
        id="bbbbbbbbbbbb", url="https://example.com/page",
        title="Una página", category="Redes", tags=["python"],
        type="article", source="example.com", saved="2026-10-10",
        summary="Algo sobre redes.",
    )


def test_the_links_shelf_is_where_it_always_was(tmp_path):
    cfg = Config(vault=tmp_path)
    assert cfg.links.dir == cfg.links_dir == tmp_path / "oknowledge" / "links"
    # Los índices de links viven en la raíz: es donde están las 1184 de hoy.
    assert cfg.links.index_dir == cfg.root


def test_the_ocio_shelf_keeps_its_indexes_inside_itself(tmp_path):
    cfg = Config(vault=tmp_path)
    assert cfg.ocio.dir == tmp_path / "oknowledge" / "ocio"
    assert cfg.ocio.index_dir == cfg.ocio.dir


def test_a_note_on_one_shelf_is_not_on_the_other(tmp_path, card_note):
    cfg = Config(vault=tmp_path)
    write_note(cfg, card_note, "es", path=note_path(cfg, card_note, shelf=cfg.ocio))
    assert all_notes(cfg) == []                                   # links
    assert [n.id for n in all_notes(cfg, shelf=cfg.ocio)] == [card_note.id]


def test_the_index_of_a_card_lands_inside_ocio(tmp_path, card_note):
    cfg = Config(vault=tmp_path)
    path = write_note(cfg, card_note, "es",
                      path=note_path(cfg, card_note, shelf=cfg.ocio))
    written = write_index(cfg, "Películas", [(path, card_note)], "es",
                          shelf=cfg.ocio)
    assert written == cfg.root / "ocio" / "Películas.md"


def test_rebuilding_one_shelf_leaves_the_other_alone(tmp_path, card_note, link_note):
    """Lo que esta tarea pone en riesgo: un reindex del ocio que borra los
    índices de categoría de los links, que es lo que hace rebuild_indexes con
    las categorías que se quedaron sin notas."""
    cfg = Config(vault=tmp_path)
    write_note(cfg, link_note, "es")
    rebuild_indexes(cfg, "es")
    redes = cfg.root / "Redes.md"
    assert redes.exists()

    write_note(cfg, card_note, "es", path=note_path(cfg, card_note, shelf=cfg.ocio))
    rebuild_indexes(cfg, "es", shelf=cfg.ocio)

    assert redes.exists()                      # sigue ahí
    assert (cfg.root / "ocio" / "Películas.md").exists()


def test_the_library_reads_the_shelf_it_was_given(tmp_path, card_note):
    cfg = Config(vault=tmp_path)
    write_note(cfg, card_note, "es", path=note_path(cfg, card_note, shelf=cfg.ocio))
    assert Library(cfg).notes == []
    assert [n.id for n in Library(cfg, shelf=cfg.ocio).notes] == [card_note.id]
