"""Writing a batch of imported links.

What this function has to achieve is cheap: the expensive steps -- scanning
the vault and rebuilding the indexes -- are paid once for the batch, not once
per link. What it must NOT lose are the guarantees: it only writes inside
oknowledge/, it deduplicates, and it leaves a queue entry so retry can finish
each one.
"""

import pytest

from oknowledge.config import Config
from oknowledge.pipeline import import_links
from oknowledge.queue import Queue
from oknowledge.urls import link_id
from oknowledge.vault import read_note
from oknowledge.whatsapp import Imported


def item(url, sent="2019-07-18", comment="", sender="Fer", bare=False):
    return Imported(url=url, sent=sent, comment=comment, sender=sender,
                    raw=url, bare=bare)


@pytest.fixture
def cfg(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    return Config(vault=vault)


@pytest.fixture
def q(tmp_path):
    return Queue(tmp_path / "state")


def test_three_links_become_three_partial_notes_with_their_dates(cfg, q):
    result = import_links(cfg, [
        item("https://a.com/x", sent="2019-07-18"),
        item("https://b.com/y", sent="2021-03-02"),
        item("https://c.com/z", sent="2025-11-30"),
    ], queue=q)

    assert (result.found, result.saved, result.already) == (3, 3, 0)
    notes = sorted((read_note(p) for p in cfg.links_dir.glob("*.md")),
                   key=lambda n: n.saved)
    assert [n.saved for n in notes] == ["2019-07-18", "2021-03-02", "2025-11-30"]
    assert {n.status for n in notes} == {"partial"}
    assert {n.category for n in notes} == {"Sin clasificar"}


def test_the_comment_becomes_the_summary_and_stays_in_the_body(cfg, q):
    """The summary is rewritten by the analysis; the body is not."""
    import_links(cfg, [item("https://a.com/x", comment="mirá esto para el gym")],
                 queue=q)

    note = read_note(next(cfg.links_dir.glob("*.md")))
    assert note.summary == "mirá esto para el gym"
    assert note.body == "mirá esto para el gym"


def test_a_message_with_no_comment_gets_the_usual_partial_summary(cfg, q):
    import_links(cfg, [item("https://a.com/x", comment="")], queue=q)

    note = read_note(next(cfg.links_dir.glob("*.md")))
    assert "retry" in note.summary
    assert note.body is None


def test_every_link_leaves_a_queue_entry_so_retry_can_finish_it(cfg, q):
    import_links(cfg, [item("https://a.com/x")], queue=q)

    entry = q.get(link_id("https://a.com/x"))
    assert entry is not None
    assert entry.status == "partial"


def test_a_link_already_in_the_vault_is_counted_and_not_rewritten(cfg, q):
    """By mtime, not by content: a write that yields the same bytes is a write."""
    import_links(cfg, [item("https://a.com/x")], queue=q)
    path = next(cfg.links_dir.glob("*.md"))
    before = path.stat().st_mtime_ns

    result = import_links(cfg, [item("https://a.com/x", sent="2025-01-01")], queue=q)

    assert (result.saved, result.already) == (0, 1)
    assert path.stat().st_mtime_ns == before


def test_the_same_link_twice_in_the_chat_keeps_the_oldest_date(cfg, q):
    """That is when it was first saved."""
    result = import_links(cfg, [
        item("https://a.com/x", sent="2021-05-05"),
        item("https://a.com/x", sent="2019-07-18"),
    ], queue=q)

    assert (result.found, result.saved, result.duplicated) == (2, 1, 1)
    assert read_note(next(cfg.links_dir.glob("*.md"))).saved == "2019-07-18"


def test_a_queue_entry_written_during_the_run_blocks_a_second_note(cfg, q, monkeypatch):
    """Closes the window between the initial scan and the write.

    Another add() lands after the scan has already come back empty: the entry
    appears while the import is running, so it is at or after its start.
    """
    real = __import__("oknowledge.pipeline", fromlist=["x"]).all_notes

    def scan_then_a_concurrent_add(config):
        notes = real(config)
        q.enqueue(link_id("https://a.com/x"), "https://a.com/x", "full")
        q.set_status(link_id("https://a.com/x"), "ok")
        return notes

    monkeypatch.setattr("oknowledge.pipeline.all_notes", scan_then_a_concurrent_add)

    result = import_links(cfg, [item("https://a.com/x")], queue=q)

    assert (result.saved, result.already) == (0, 1)
    assert list(cfg.links_dir.glob("*.md")) == []


def test_an_old_queue_entry_with_no_note_does_not_block_the_link(cfg, q, monkeypatch):
    """A note deleted by hand has to be able to come back: the vault is the truth."""
    q.enqueue(link_id("https://a.com/x"), "https://a.com/x", "full")
    q.set_status(link_id("https://a.com/x"), "ok")
    entry = q.get(link_id("https://a.com/x"))
    entry.updated = "2019-01-01T00:00:00.000+00:00"
    q._write(entry)

    result = import_links(cfg, [item("https://a.com/x")], queue=q)

    assert (result.saved, result.already) == (1, 0)


def test_the_indexes_are_rebuilt_once_for_the_whole_batch(cfg, q, monkeypatch):
    """The reason this function exists: 1215 times is 19 minutes."""
    calls = []
    real = __import__("oknowledge.pipeline", fromlist=["x"]).rebuild_indexes

    def counted(config, language):
        calls.append(language)
        return real(config, language)

    monkeypatch.setattr("oknowledge.pipeline.rebuild_indexes", counted)

    import_links(cfg, [item(f"https://a{n}.com/x") for n in range(10)], queue=q)

    assert len(calls) == 1


def test_one_note_that_cannot_be_written_does_not_stop_the_others(cfg, q, monkeypatch):
    real = __import__("oknowledge.pipeline", fromlist=["x"]).write_note
    seen = []

    def boom(config, note, language, path=None):
        seen.append(note.id)
        if len(seen) == 2:
            raise OSError("no space left on device")
        return real(config, note, language, path=path)

    monkeypatch.setattr("oknowledge.pipeline.write_note", boom)

    result = import_links(cfg, [item(f"https://a{n}.com/x") for n in range(3)],
                          queue=q)

    assert result.saved == 2
    assert len(result.failed) == 1
    assert "no space left" in result.failed[0][1]


def test_nothing_is_written_outside_the_managed_folder(cfg, q, tmp_path):
    """links/ pointed elsewhere is an Obsidian habit, not an attack."""
    outside = tmp_path / "outside"
    outside.mkdir()
    cfg.links_dir.rmdir()
    cfg.links_dir.symlink_to(outside)

    result = import_links(cfg, [item("https://a.com/x")], queue=q)

    assert list(outside.iterdir()) == []
    assert result.saved == 0
    assert len(result.failed) == 1


def test_an_empty_batch_is_not_an_error(cfg, q):
    result = import_links(cfg, [], queue=q)

    assert (result.found, result.saved, result.already) == (0, 0, 0)


def test_a_url_that_normalizes_to_the_same_link_is_one_note(cfg, q):
    """normalize() strips utm: the same link sent twice is one."""
    result = import_links(cfg, [
        item("https://a.com/x?utm_source=wa"),
        item("https://a.com/x"),
    ], queue=q)

    assert result.saved == 1
