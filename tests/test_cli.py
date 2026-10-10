"""The command line. Every test points XDG_STATE_HOME at tmp_path, so nothing
here can touch the real queue, and the config is always passed explicitly."""

import errno
import json
import os
import subprocess
import sys

import pytest

from marks import posix_only
from oknowledge import cli
from oknowledge.cli import main
from oknowledge.config import Config
from oknowledge.extract import Unreadable
from oknowledge.model import Extracted, Note
from oknowledge.pipeline import Result
from oknowledge.queue import Queue, state_dir
from oknowledge.vault import RebuildResult, all_notes, write_note

# Captured at import time, before conftest's autouse fixture swaps them out:
# one test below has to start a real process.
REAL_RUN, REAL_POPEN = subprocess.run, subprocess.Popen

ANSWER = json.dumps({
    "title": "WireGuard",
    "summary": "Compara protocolos.",
    "points": ["Corre en el kernel"],
    "category": "Redes",
    "tags": ["vpn"],
})
PAGE = Extracted(title="WireGuard | Ars", text="Runs in the kernel.", type="article",
                 source="arstechnica.com")


@pytest.fixture(autouse=True)
def state(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    config = Config(vault=vault, chain=("fake",), engines={"fake": {"replies": [ANSWER]}})
    monkeypatch.setattr("oknowledge.cli.load_config", lambda path=None: config)
    return config


def fake_add(monkeypatch, result, seen=None):
    def add(config, url, **kw):
        if seen is not None:
            seen.update(kw)
        return result(url) if callable(result) else result
    monkeypatch.setattr("oknowledge.cli.add", add)


def no_pictures(monkeypatch):
    """No cover and no site icon: both reach the network, which conftest
    refuses, and no test here is about either picture."""
    monkeypatch.setattr("oknowledge.pipeline.download_cover", lambda cfg, url, link_id: None)
    monkeypatch.setattr("oknowledge.pipeline.download_icon", lambda cfg, source: None)


def ok(cfg, **kw):
    return lambda url: Result(id="a1", url=url, path=cfg.links_dir / "n.md",
                              status="ok", engine="opencode", **kw)


def test_the_state_directory_is_under_tmp_path(tmp_path):
    assert state_dir().is_relative_to(tmp_path)
    assert Queue().dir.is_relative_to(tmp_path)


def test_add_prints_where_the_note_landed(cfg, monkeypatch, capsys):
    fake_add(monkeypatch, ok(cfg))
    assert main(["add", "https://e.com/x"]) == 0
    assert "n.md" in capsys.readouterr().out


def test_add_end_to_end_through_the_real_pipeline(cfg, monkeypatch, capsys):
    no_pictures(monkeypatch)
    monkeypatch.setattr("oknowledge.pipeline.extract", lambda url: PAGE)
    assert main(["add", "https://arstechnica.com/vpn", "--summary"]) == 0
    assert "saved:" in capsys.readouterr().out
    assert len(list(cfg.links_dir.glob("*.md"))) == 1
    assert [e.status for e in Queue().entries()] == ["ok"]


def test_add_json_is_one_object_for_the_plugin(cfg, monkeypatch, capsys):
    fake_add(monkeypatch, ok(cfg, warnings=["an index is stale"]))
    main(["add", "https://e.com/x", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"id": "a1", "url": "https://e.com/x", "status": "ok",
                       "engine": "opencode", "path": str(cfg.links_dir / "n.md"),
                       "error": None, "skipped": False, "warnings": ["an index is stale"]}


def test_add_prints_each_warning_on_its_own_line(cfg, monkeypatch, capsys):
    fake_add(monkeypatch, ok(cfg, warnings=["index stale", "queue not recorded"]))
    assert main(["add", "https://e.com/x"]) == 0
    err = capsys.readouterr().err.splitlines()
    assert "warning: index stale" in err
    assert "warning: queue not recorded" in err


def test_the_content_flags_reach_the_pipeline(cfg, monkeypatch):
    seen = {}
    fake_add(monkeypatch, ok(cfg), seen)
    main(["add", "https://e.com/x", "--summary", "--engine", "ollama"])
    assert seen["content"] == "summary"
    assert seen["engine"] == "ollama"


def test_a_partial_result_exits_nonzero_so_a_script_notices(cfg, monkeypatch, capsys):
    fake_add(monkeypatch, Result(id="a1", url="u", path=cfg.links_dir / "n.md",
                                 status="partial", error="403"))
    assert main(["add", "https://e.com/x"]) == 1
    assert "403" in capsys.readouterr().err


def test_a_locked_link_says_someone_else_is_on_it(cfg, monkeypatch, capsys):
    fake_add(monkeypatch, Result(id="a1", url="u", path=None, status="pending",
                                 error="link a1 is locked"))
    assert main(["add", "https://e.com/x"]) == 1
    err = capsys.readouterr().err
    assert "another process" in err and "try again" in err
    assert "None" not in err


def test_status_json_lists_the_queue(cfg, capsys):
    q = Queue()
    q.enqueue("a1", "https://e.com/x", "full")
    q.set_status("a1", "partial", error="403", title="X")
    assert main(["status", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["status"] == "partial"
    assert payload[0]["title"] == "X"
    assert payload[0]["error"] == "403"
    assert "content" not in payload[0]


def test_status_keys_off_status_not_off_error(cfg, capsys):
    q = Queue()
    q.enqueue("a1", "https://e.com/ok", "full")
    q.set_status("a1", "ok", error="re-analysis failed", title="Fine")
    q.enqueue("b2", "https://e.com/bad", "full")
    q.set_status("b2", "failed", error="timeout", title="Broken")
    assert main(["status"]) == 0
    out = capsys.readouterr().out
    assert "Broken" in out and "timeout" in out
    assert "Fine" not in out
    assert "full" not in out


def test_reindex_reports_written_blocked_and_skipped(cfg, monkeypatch, capsys):
    result = RebuildResult(written=[cfg.root / "a.md", cfg.root / "b.md"],
                           skipped=[cfg.links_dir / "broken.md"],
                           blocked=[cfg.root / "Redes.md"])
    monkeypatch.setattr("oknowledge.cli.rebuild_indexes", lambda config, language: result)
    assert main(["reindex"]) == 0
    out = capsys.readouterr()
    assert "2 indexes rewritten" in out.out
    assert "Redes.md" in out.err and "not ours" in out.err
    assert "broken.md" in out.err and "could not be read" in out.err


def test_reindex_runs_for_real(cfg, monkeypatch, capsys):
    no_pictures(monkeypatch)
    monkeypatch.setattr("oknowledge.pipeline.extract", lambda url: PAGE)
    main(["add", "https://arstechnica.com/vpn"])
    indexes = list(cfg.root.glob("*.md"))
    assert len(indexes) == 1
    indexes[0].unlink()
    capsys.readouterr()
    assert main(["reindex"]) == 0
    assert capsys.readouterr().out == "1 index rewritten\n"
    assert len(list(cfg.root.glob("*.md"))) == 1


def test_reindex_leaves_no_index_behind_when_a_category_empties(cfg, monkeypatch, capsys):
    no_pictures(monkeypatch)
    """The shape to worry about: the last note of a category moves away by hand,
    so the category no longer exists and its index must not survive the sweep.
    rebuild_indexes is tested for this directly; this is the command."""
    monkeypatch.setattr("oknowledge.pipeline.extract", lambda url: PAGE)
    main(["add", "https://arstechnica.com/vpn"])
    assert [p.name for p in cfg.root.glob("*.md")] == ["Redes.md"]
    note = next(cfg.links_dir.glob("*.md"))
    note.write_text(note.read_text(encoding="utf-8").replace("category: Redes",
                                                             "category: Seguridad"),
                    encoding="utf-8")
    capsys.readouterr()

    assert main(["reindex"]) == 0

    assert [p.name for p in cfg.root.glob("*.md")] == ["Seguridad.md"]


def test_reindex_leaves_no_index_behind_when_the_last_note_is_deleted(cfg, monkeypatch,
                                                                     capsys):
    no_pictures(monkeypatch)
    monkeypatch.setattr("oknowledge.pipeline.extract", lambda url: PAGE)
    main(["add", "https://arstechnica.com/vpn"])
    next(cfg.links_dir.glob("*.md")).unlink()
    capsys.readouterr()

    assert main(["reindex"]) == 0

    assert list(cfg.root.glob("*.md")) == []


def test_retry_shows_why_a_link_failed(cfg, monkeypatch, capsys):
    monkeypatch.setattr("oknowledge.cli.retry", lambda config, limit=None: [
        Result(id="a1", url="https://e.com/a", path=None, status="ok"),
        Result(id="b2", url="https://e.com/b", path=None, status="failed", error="timeout"),
    ])
    assert main(["retry"]) == 1
    out = capsys.readouterr().out
    assert "1/2 finished" in out
    assert "https://e.com/b" in out and "timeout" in out


def test_retry_json_is_one_array(cfg, monkeypatch, capsys):
    monkeypatch.setattr("oknowledge.cli.retry", lambda config, limit=None: [
        Result(id="a1", url="u", path=None, status="ok"),
        Result(id="b2", url="v", path=None, status="failed", error="x"),
    ])
    main(["retry", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert [p["id"] for p in payload] == ["a1", "b2"]


def test_a_disk_error_is_a_message_not_a_traceback(cfg, monkeypatch, capsys):
    def boom(config, language):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr("oknowledge.cli.rebuild_indexes", boom)
    assert main(["reindex"]) == 3
    assert "oknowledge: [Errno 28] No space left on device" in capsys.readouterr().err


def test_a_missing_config_teaches_what_to_create(tmp_path, capsys):
    path = tmp_path / "nope" / "config.toml"
    assert main(["--config", str(path), "status"]) == 2
    err = capsys.readouterr().err
    assert str(path) in err
    assert "vault" in err and "Obsidian" in err


def test_a_broken_config_keeps_its_own_message(tmp_path, capsys):
    path = tmp_path / "config.toml"
    path.write_text('vault = "/definitely/not/here"\n')
    assert main(["--config", str(path), "status"]) == 2
    assert "vault is not a directory" in capsys.readouterr().err


def test_no_subcommand_prints_help(capsys):
    assert main([]) == 2
    assert "usage" in capsys.readouterr().err.lower()


def test_counts_are_singular_when_there_is_one(cfg, monkeypatch, capsys):
    no_pictures(monkeypatch)
    monkeypatch.setattr("oknowledge.pipeline.extract", lambda url: PAGE)
    main(["add", "https://arstechnica.com/vpn"])
    capsys.readouterr()
    main(["status"])
    assert capsys.readouterr().out.startswith("1 note\n")
    main(["reindex"])
    out = capsys.readouterr().out
    assert "1 index rewritten" in out


@posix_only
def test_an_unreadable_config_is_a_message_not_a_traceback(tmp_path, capsys):
    path = tmp_path / "config.toml"
    path.write_text('vault = "/x"\n')
    path.chmod(0)
    try:
        assert main(["--config", str(path), "status"]) == 2
    finally:
        path.chmod(0o600)
    assert "cannot read the config file" in capsys.readouterr().err


def test_a_directory_where_the_config_should_be_is_a_message(tmp_path, capsys):
    path = tmp_path / "config.toml"
    path.mkdir()
    assert main(["--config", str(path), "status"]) == 2
    assert "cannot read the config file" in capsys.readouterr().err


def test_re_adding_a_partial_link_reprocesses_it(cfg, monkeypatch, capsys):
    no_pictures(monkeypatch)
    url = "https://arstechnica.com/vpn"
    monkeypatch.setattr("oknowledge.pipeline.extract",
                        lambda u: (_ for _ in ()).throw(Unreadable("down")))
    assert main(["add", url]) == 1
    capsys.readouterr()
    monkeypatch.setattr("oknowledge.pipeline.extract", lambda u: PAGE)
    assert main(["add", url]) == 0
    out = capsys.readouterr().out
    assert out.startswith("saved:") and "already" not in out
    assert [e.status for e in Queue().entries()] == ["ok"]


def test_re_adding_an_ok_link_says_already_saved(cfg, monkeypatch, capsys):
    no_pictures(monkeypatch)
    monkeypatch.setattr("oknowledge.pipeline.extract", lambda u: PAGE)
    main(["add", "https://arstechnica.com/vpn"])
    capsys.readouterr()
    assert main(["add", "https://arstechnica.com/vpn"]) == 0
    assert capsys.readouterr().out.startswith("already saved:")


def test_locked_with_json_is_still_one_object_and_exit_1(cfg, monkeypatch, capsys):
    fake_add(monkeypatch, Result(id="a1", url="u", path=None, status="pending", error="locked"))
    assert main(["add", "https://e.com/x", "--json"]) == 1
    captured = capsys.readouterr()
    assert json.loads(captured.out)["status"] == "pending"


@pytest.mark.parametrize("text", [
    'vault = [',
    'vault = 5\n',
    'vault = "{vault}"\nai = 3\n',
    'vault = "{vault}"\n[web]\nport = "x"\n',
    'vault = "{vault}"\nfolder = 3\n',
    'vault = "{vault}"\n[ai]\nchain = 5\n',
])
def test_a_malformed_config_is_a_message_with_exit_2(tmp_path, capsys, text):
    path = tmp_path / "config.toml"
    path.write_text(text.format(vault=tmp_path))
    assert main(["--config", str(path), "status"]) == 2
    captured = capsys.readouterr()
    assert captured.err.startswith("oknowledge: ") and "Traceback" not in captured.err
    assert captured.out == ""


def test_a_config_that_is_not_utf8_is_a_message(tmp_path, capsys):
    path = tmp_path / "config.toml"
    path.write_bytes(b'vault = "\xff\xfe"\n')
    assert main(["--config", str(path), "status"]) == 2
    assert "UTF-8" in capsys.readouterr().err


def test_a_protected_note_exits_3_and_says_if_the_link_was_queued(cfg, monkeypatch, capsys):
    from oknowledge.vault import ProtectedNote

    def boom(config, url, **kw):
        raise ProtectedNote("links is outside the vault")
    monkeypatch.setattr("oknowledge.cli.add", boom)
    assert main(["add", "https://e.com/x"]) == 3
    err = capsys.readouterr().err
    assert "refused to write" in err and "the link was not queued" in err


def test_an_unexpected_error_exits_3_and_reports_the_queue(cfg, monkeypatch, capsys):
    from oknowledge.urls import link_id, normalize
    Queue().enqueue(link_id(normalize("https://e.com/x")), "https://e.com/x", "full")

    def boom(config, url, **kw):
        raise RuntimeError("surprise")
    monkeypatch.setattr("oknowledge.cli.add", boom)
    assert main(["add", "https://e.com/x"]) == 3
    captured = capsys.readouterr()
    assert "unexpected error: RuntimeError: surprise" in captured.err
    assert "the link is in the queue" in captured.err
    assert captured.out == ""


@pytest.mark.parametrize("url", ["", "   "])
def test_an_empty_url_is_rejected_before_the_pipeline(cfg, monkeypatch, capsys, url):
    fake_add(monkeypatch, lambda u: pytest.fail("the pipeline must not run"))
    assert main(["add", url]) == 2
    assert "empty" in capsys.readouterr().err
    assert list(cfg.links_dir.glob("*.md")) == []


def test_an_unknown_engine_is_refused_by_argparse(cfg, capsys):
    with pytest.raises(SystemExit) as exit_:
        main(["add", "https://e.com/x", "--engine", "gpt9"])
    assert exit_.value.code == 2
    assert "invalid choice" in capsys.readouterr().err
    assert list(cfg.links_dir.glob("*.md")) == []


def test_a_failed_reanalysis_says_the_note_was_left_alone(cfg, monkeypatch, capsys):
    fake_add(monkeypatch, Result(id="a1", url="u", path=cfg.links_dir / "n.md",
                                 status="failed", error="all engines down"))
    assert main(["add", "https://e.com/x", "--reprocess"]) == 1
    err = capsys.readouterr().err
    assert "left as it is" in err and "all engines down" in err
    assert "incomplete" not in err


def test_control_characters_do_not_break_the_status_table(cfg, capsys):
    q = Queue()
    q.enqueue("a1", "https://e.com/x", "full")
    q.set_status("a1", "failed", error="bad\nthing", title="Two\nlines\x1b[31m")
    main(["status"])
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 2 and "\x1b" not in lines[1]


def test_status_reports_unreadable_queue_files(cfg, capsys):
    q = Queue()
    q.enqueue("a1", "https://e.com/x", "full")
    (q.dir / "b2.json").write_text("{not json")
    assert main(["status", "--json"]) == 0
    captured = capsys.readouterr()
    assert len(json.loads(captured.out)) == 1
    assert "1 queue file" in captured.err and "could not be read" in captured.err


def test_stdout_stays_empty_when_the_answer_goes_to_stderr(cfg, monkeypatch, capsys):
    for result in (
        Result(id="a", url="u", path=None, status="partial", error="403"),
        Result(id="a", url="u", path=None, status="pending", error="locked"),
        Result(id="a", url="u", path=cfg.links_dir / "n.md", status="failed", error="x"),
    ):
        fake_add(monkeypatch, result)
        assert main(["add", "https://e.com/x"]) == 1
        assert capsys.readouterr().out == ""


def test_retry_survives_an_unreadable_queue_listing(cfg, monkeypatch, capsys):
    no_pictures(monkeypatch)
    from oknowledge.pipeline import retry
    q = Queue()
    q.enqueue("a1", "https://e.com/x", "full")
    q.set_status("a1", "failed", error="old")

    def boom():
        raise PermissionError("locks/x.lock")
    monkeypatch.setattr(q, "orphaned", boom)
    monkeypatch.setattr("oknowledge.pipeline.extract", lambda u: PAGE)
    results = retry(cfg, queue=q)
    assert [r.status for r in results] == ["failed", "ok"]
    assert "could not list the queue" in results[0].error


@posix_only
def test_an_unprobeable_lock_costs_one_link_not_the_whole_list(cfg, monkeypatch):
    no_pictures(monkeypatch)
    from oknowledge.pipeline import retry
    from oknowledge.urls import link_id, normalize
    q = Queue()
    urls = {name: f"https://e.com/{name}" for name in ("a", "b", "c")}
    ids = {name: link_id(normalize(url)) for name, url in urls.items()}
    for name, url in urls.items():
        q.enqueue(ids[name], url, "full")                   # abandoned: pending, unlocked
    bad = q._lock_path(ids["b"])
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text("")
    bad.chmod(0)                                            # os.open(O_RDONLY) now fails
    try:
        assert sorted(e.id for e in q.orphaned()) == sorted([ids["a"], ids["c"]])
        monkeypatch.setattr("oknowledge.pipeline.extract", lambda u: PAGE)
        results = retry(cfg, queue=q)
    finally:
        bad.chmod(0o600)
    assert sorted(r.id for r in results) == sorted([ids["a"], ids["c"]])
    assert q.get(ids["b"]).status == "pending"


def test_re_adding_a_note_with_a_hand_typed_status_leaves_it_alone(cfg, monkeypatch, capsys):
    no_pictures(monkeypatch)
    url = "https://arstechnica.com/vpn"
    monkeypatch.setattr("oknowledge.pipeline.extract", lambda u: PAGE)
    main(["add", url])
    note = next(cfg.links_dir.glob("*.md"))
    text = note.read_text(encoding="utf-8").replace("status: ok", "status: done")
    assert "status: done" in text
    note.write_text(text + "\nMy own thoughts.\n", encoding="utf-8")
    before = note.read_text(encoding="utf-8")
    capsys.readouterr()
    assert main(["add", url]) == 0
    assert capsys.readouterr().out.startswith("already saved:")
    assert note.read_text(encoding="utf-8") == before


def test_a_vault_with_an_unknown_home_is_a_message(tmp_path, capsys):
    path = tmp_path / "config.toml"
    path.write_text('vault = "~nosuchuser_zz/x"\n')
    assert main(["--config", str(path), "status"]) == 2
    err = capsys.readouterr().err
    assert "home directory does not exist" in err and "Traceback" not in err


@pytest.mark.parametrize("folder", ["../escape", "/abs", "a/b", "", "..", "."])
def test_a_folder_that_leaves_the_vault_is_refused(tmp_path, capsys, folder):
    (tmp_path / "v").mkdir()
    path = tmp_path / "config.toml"
    path.write_text(f'vault = "{tmp_path / "v"}"\nfolder = "{folder}"\n')
    assert main(["--config", str(path), "status"]) == 2
    assert "folder must be" in capsys.readouterr().err
    assert not (tmp_path / "escape").exists()


# --- The icon backfill, for the notes saved before icons existed -------------


def saved_note(cfg, source):
    """A note in the vault, written straight in: `add` is not what is under
    test here, and running it would mean stubbing half the pipeline."""
    write_note(cfg, Note(id="a1", url=f"https://{source}/x", title="Guardado",
                         category="Redes", tags=["vpn"], type="article",
                         source=source, saved="2026-10-03", summary="Resumen.",
                         points=[]), "es")


def icon_reply(monkeypatch, content, content_type):
    class Fetched:
        pass
    Fetched.content = content
    Fetched.content_type = content_type
    monkeypatch.setattr("oknowledge.pipeline.fetch", lambda url, **kw: Fetched())


def test_icons_backfills_the_sites_already_in_the_library(cfg, monkeypatch, capsys):
    """The command the user runs once, for the notes saved before icons existed."""
    saved_note(cfg, "arstechnica.com")
    icon_reply(monkeypatch, b"\x89PNG icon bytes", "image/png")

    assert main(["icons"]) == 0

    assert capsys.readouterr().out == "1 site, 1 with an icon\n"
    assert (cfg.attachments_dir / "icons" / "arstechnica.com.png").is_file()


def test_icons_says_when_a_site_has_no_favicon(cfg, monkeypatch, capsys):
    """A site with none answers /favicon.ico with its 404 page, which is HTML."""
    saved_note(cfg, "arstechnica.com")
    icon_reply(monkeypatch, b"<html>404</html>", "text/html")

    assert main(["icons"]) == 0

    assert capsys.readouterr().out == "1 site, 0 with an icon\n"


def test_icons_over_an_empty_library_is_not_an_error(cfg, capsys):
    assert main(["icons"]) == 0
    assert capsys.readouterr().out == "0 sites, 0 with an icon\n"


# --- importing a WhatsApp export ---------------------------------------------

EXPORT = """\
18/7/2019, 11:36 - Fer: https://scratux.org/#download
23/7/2019, 11:39 - Fer: sudo chkrootkit
21/7/2019, 13:50 - Fer: mirá youtu.be/abc
24/7/2019, 10:00 - Fer: el config.json que te mandé
"""


def test_import_saves_the_links_with_their_dates(cfg, tmp_path, capsys):
    export = tmp_path / "chat.txt"
    export.write_text(EXPORT, encoding="utf-8")

    assert main(["import", str(export)]) == 0

    out = capsys.readouterr().out
    assert "2 links in 4 messages" in out
    assert "2 saved, 0 already there" in out
    assert "1 of them was written without a scheme" in out
    assert "1 message looks like it had a link" in out
    saved = sorted(n.saved for n in all_notes(cfg))
    assert saved == ["2019-07-18", "2019-07-21"]


def test_import_says_how_the_dates_were_read(cfg, tmp_path, capsys):
    export = tmp_path / "chat.txt"
    export.write_text(EXPORT, encoding="utf-8")

    main(["import", str(export)])

    out = capsys.readouterr().out
    assert "dates read as day/month" in out
    assert "(assumed)" not in out


def test_import_marks_an_assumed_date_order(cfg, tmp_path, capsys):
    export = tmp_path / "chat.txt"
    export.write_text("7/8/2019, 11:36 - Fer: https://e.com/x\n", encoding="utf-8")

    main(["import", str(export)])

    assert "(assumed)" in capsys.readouterr().out


def test_a_dry_run_writes_nothing_and_lists_the_three_groups(cfg, tmp_path, capsys):
    export = tmp_path / "chat.txt"
    export.write_text(EXPORT, encoding="utf-8")

    assert main(["import", str(export), "--dry-run"]) == 0

    out = capsys.readouterr().out
    assert list(cfg.links_dir.glob("*.md")) == []
    assert "https://scratux.org/#download" in out
    assert "youtu.be/abc" in out                 # the original, not the https:// form
    assert "config.json" in out                  # the suspicious one
    assert "nothing was written" in out


def test_import_json_is_one_object(cfg, tmp_path, capsys):
    export = tmp_path / "chat.txt"
    export.write_text(EXPORT, encoding="utf-8")

    main(["import", str(export), "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["found"] == 2
    assert payload["saved"] == 2
    assert payload["messages"] == 4
    assert payload["day_first"] is True


def test_import_says_the_span_of_the_dates_it_read(cfg, tmp_path, capsys):
    """A phone with a wrong clock dates a note 2099, which then sorts first in
    the index and first in every retry. The dry run's list is in message
    order, so one outlier hides in 1215 lines unless the span says so."""
    export = tmp_path / "chat.txt"
    export.write_text(EXPORT, encoding="utf-8")

    main(["import", str(export)])

    assert ("2 links in 4 messages, 2019-07-18 to 2019-07-21 "
            "(dates read as day/month)") in capsys.readouterr().out


def test_a_dry_run_says_the_span_too(cfg, tmp_path, capsys):
    export = tmp_path / "chat.txt"
    export.write_text(EXPORT, encoding="utf-8")

    main(["import", str(export), "--dry-run"])

    assert "2019-07-18 to 2019-07-21" in capsys.readouterr().out


@pytest.mark.parametrize("extra", [[], ["--dry-run"]])
def test_both_json_documents_carry_the_span(cfg, tmp_path, capsys, extra):
    export = tmp_path / "chat.txt"
    export.write_text(EXPORT, encoding="utf-8")

    main(["import", str(export), "--json", *extra])

    payload = json.loads(capsys.readouterr().out)
    assert payload["earliest"] == "2019-07-18"
    assert payload["latest"] == "2019-07-21"


def test_an_export_with_no_links_has_no_span_to_report(cfg, tmp_path, capsys):
    export = tmp_path / "chat.txt"
    export.write_text("18/7/2019, 11:36 - Fer: sudo chkrootkit\n", encoding="utf-8")

    assert main(["import", str(export)]) == 0

    assert "0 links in 1 message (dates read as day/month)" in capsys.readouterr().out


def test_a_file_that_is_not_there_is_a_config_error(cfg, tmp_path, capsys):
    assert main(["import", str(tmp_path / "nope.txt")]) == 2
    err = capsys.readouterr().err
    assert "nope.txt" in err
    assert "No such file or directory" in err
    assert "[Errno" not in err                   # the path is not printed twice


def test_a_file_that_is_not_an_export_names_the_format(cfg, tmp_path, capsys):
    export = tmp_path / "chat.txt"
    export.write_text("esto no es un export\n", encoding="utf-8")

    assert main(["import", str(export)]) == 2

    assert "D/M/YYYY" in capsys.readouterr().err


def test_a_file_whose_dates_contradict_each_other_is_refused(cfg, tmp_path, capsys):
    export = tmp_path / "chat.txt"
    export.write_text("18/7/2019, 11:36 - Fer: https://e.com/x\n"
                      "7/18/2019, 11:36 - Fer: https://e.com/y\n", encoding="utf-8")

    assert main(["import", str(export)]) == 2

    error = capsys.readouterr().err
    assert "18/7/2019" in error and "7/18/2019" in error
    assert list(cfg.links_dir.glob("*.md")) == []


def test_a_byte_that_is_not_utf8_does_not_abort_the_import(cfg, tmp_path, capsys):
    """Six years of chat can hold one. Losing 1215 links over it is not acceptable."""
    export = tmp_path / "chat.txt"
    export.write_bytes(
        "18/7/2019, 11:36 - Fer: https://e.com/x\n".encode()
        + b"19/7/2019, 11:36 - Fer: \xff\xfe roto\n"
        + "20/7/2019, 11:36 - Fer: https://e.com/y\n".encode())

    assert main(["import", str(export)]) == 0

    assert len(all_notes(cfg)) == 2


def test_an_import_that_saved_nothing_because_it_failed_exits_one(cfg, tmp_path,
                                                                  capsys, monkeypatch):
    export = tmp_path / "chat.txt"
    export.write_text(EXPORT, encoding="utf-8")

    def boom(config, note, language, path=None):
        raise OSError("no space left on device")

    monkeypatch.setattr("oknowledge.pipeline.write_note", boom)

    assert main(["import", str(export)]) == 1

    assert "no space left" in capsys.readouterr().err


def test_an_import_that_lost_some_links_exits_one_and_says_so_on_stdout(
        cfg, tmp_path, capsys, monkeypatch):
    export = tmp_path / "chat.txt"
    export.write_text(EXPORT, encoding="utf-8")
    real = write_note

    def flaky(config, note, language, path=None):
        if "youtu.be" in note.url:
            raise OSError("no space left on device")
        return real(config, note, language, path)

    monkeypatch.setattr("oknowledge.pipeline.write_note", flaky)

    assert main(["import", str(export)]) == 1

    captured = capsys.readouterr()
    assert len(all_notes(cfg)) == 1
    assert "1 link was not saved" in captured.out
    assert "no space left" in captured.err


def test_a_failed_vault_scan_is_reported_without_an_empty_field(
        cfg, tmp_path, capsys, monkeypatch):
    """The one failure that belongs to the batch and to no url. It printed as
    `not saved: : the vault could not be read ...`, with the empty field where
    a link should be."""
    export = tmp_path / "chat.txt"
    export.write_text(EXPORT, encoding="utf-8")

    def unreadable(config):
        raise OSError("input/output error")

    monkeypatch.setattr("oknowledge.pipeline.all_notes", unreadable)

    assert main(["import", str(export)]) == 1

    err = capsys.readouterr().err
    assert "not saved: : " not in err
    assert "not saved: the vault could not be read" in err
    assert "none of 2 links" in err


def test_links_that_fail_for_the_same_reason_are_reported_once(
        cfg, tmp_path, capsys, monkeypatch):
    """A whole batch failing the same way is one thing to say, not 1215.

    The spec's "ninguna nota se pudo escribir -> lo dice" means said once: a
    wall of near-identical lines buries every other line the run printed.
    """
    export = tmp_path / "chat.txt"
    export.write_text("18/7/2019, 11:36 - Fer: https://e.com/a\n"
                      "19/7/2019, 11:36 - Fer: https://e.com/b\n"
                      "20/7/2019, 11:36 - Fer: https://e.com/c\n", encoding="utf-8")

    def boom(config, note, language, path=None):
        # A real write failure names the file, so its text differs per link.
        raise OSError(errno.ENOSPC, "no space left on device",
                      str(tmp_path / f"{note.id}.md"))

    monkeypatch.setattr("oknowledge.pipeline.write_note", boom)

    assert main(["import", str(export)]) == 1

    err = capsys.readouterr().err
    assert err.count("no space left on device") == 1
    assert "3 links" in err
    # The urls are still all there: they are what the user looks at.
    for letter in "abc":
        assert f"https://e.com/{letter}" in err


def test_a_dry_run_with_json_is_one_document_without_senders(cfg, tmp_path, capsys):
    export = tmp_path / "chat.txt"
    export.write_text(EXPORT, encoding="utf-8")

    assert main(["import", str(export), "--dry-run", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert list(cfg.links_dir.glob("*.md")) == []
    assert payload["written"] is False
    assert payload["messages"] == 4
    assert payload["suspicious"] == ["el config.json que te mandé"]
    assert payload["links"][0] == {"sent": "2019-07-18",
                                   "raw": "https://scratux.org/#download",
                                   "url": "https://scratux.org/#download",
                                   "bare": False}
    assert [one["bare"] for one in payload["links"]] == [False, True]
    assert "Fer" not in json.dumps(payload)


def test_an_index_that_could_not_be_rebuilt_is_reported(cfg, tmp_path, capsys,
                                                        monkeypatch):
    """One rebuild covers the whole batch, so its failure hides every note."""
    export = tmp_path / "chat.txt"
    export.write_text(EXPORT, encoding="utf-8")

    def boom(config, language):
        raise OSError("no space left on device")

    monkeypatch.setattr("oknowledge.pipeline.rebuild_indexes", boom)

    assert main(["import", str(export)]) == 0

    assert "warning:" in capsys.readouterr().err


def test_retry_limit_is_passed_through(cfg, monkeypatch, capsys):
    seen = {}

    def fake(config, queue=None, limit=None):
        seen["limit"] = limit
        return []

    monkeypatch.setattr("oknowledge.cli.retry", fake)

    assert main(["retry", "--limit", "50"]) == 0

    assert seen["limit"] == 50


@pytest.mark.parametrize("status,code", [("ok", 0), ("partial", 1)])
def test_a_limited_retry_reports_on_the_links_it_worked_on(cfg, monkeypatch,
                                                           capsys, status, code):
    """What the README's --limit paragraph says: the code describes the links
    the run was asked to do, not the backlog behind them. Exiting 1 for links
    it was never asked to do would exit 1 every day until the last batch, and
    then the code would carry no information at all."""
    monkeypatch.setattr("oknowledge.cli.retry", lambda config, limit=None: [
        Result(id="a1", url="https://e.com/a", path=None, status=status)])

    assert main(["retry", "--limit", "1"]) == code


def test_retry_refuses_a_negative_limit(cfg, capsys):
    assert main(["retry", "--limit", "-1"]) == 2
    assert "limit" in capsys.readouterr().err


def test_mentions_shows_why_a_video_failed(cfg, monkeypatch, capsys):
    monkeypatch.setattr("oknowledge.cli.backfill_mentions", lambda config, limit=None: [
        Result(id="a1", url="https://youtu.be/a", path=None, status="ok"),
        Result(id="b2", url="https://youtu.be/b", path=None, status="failed",
               error="every engine failed"),
    ])
    assert main(["mentions"]) == 1
    out = capsys.readouterr().out
    assert "1/2 videos now have their mentions" in out
    assert "https://youtu.be/b" in out and "every engine failed" in out


def test_mentions_reports_a_skipped_video_without_counting_it_done(
        cfg, monkeypatch, capsys):
    monkeypatch.setattr("oknowledge.cli.backfill_mentions", lambda config, limit=None: [
        Result(id="a1", url="https://youtu.be/a", path=None, status="ok", skipped=True,
               warnings=["it already had its mentions"])])

    assert main(["mentions"]) == 0
    out = capsys.readouterr().out
    assert "0/1 videos now have their mentions" in out
    assert "skipped" in out and "already had its mentions" in out


def test_mentions_json_is_one_array(cfg, monkeypatch, capsys):
    monkeypatch.setattr("oknowledge.cli.backfill_mentions", lambda config, limit=None: [
        Result(id="a1", url="u", path=None, status="ok"),
        Result(id="b2", url="v", path=None, status="failed", error="x"),
    ])
    main(["mentions", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert [p["id"] for p in payload] == ["a1", "b2"]


def test_mentions_with_nothing_to_do_exits_zero(cfg, monkeypatch, capsys):
    monkeypatch.setattr("oknowledge.cli.backfill_mentions", lambda config, limit=None: [])
    assert main(["mentions"]) == 0


def test_mentions_limit_is_passed_through(cfg, monkeypatch, capsys):
    seen = {}

    def fake(config, limit=None):
        seen["limit"] = limit
        return []

    monkeypatch.setattr("oknowledge.cli.backfill_mentions", fake)

    assert main(["mentions", "--limit", "50"]) == 0
    assert seen["limit"] == 50


@pytest.mark.parametrize("status,code", [("ok", 0), ("failed", 1)])
def test_a_limited_mentions_run_reports_on_the_videos_it_worked_on(
        cfg, monkeypatch, capsys, status, code):
    """As for retry: the code describes the videos the run was asked to do, not
    the backlog behind them."""
    monkeypatch.setattr("oknowledge.cli.backfill_mentions", lambda config, limit=None: [
        Result(id="a1", url="https://youtu.be/a", path=None, status=status)])

    assert main(["mentions", "--limit", "1"]) == code


def test_mentions_refuses_a_negative_limit(cfg, capsys):
    assert main(["mentions", "--limit", "-1"]) == 2
    assert "limit" in capsys.readouterr().err


def test_a_reader_that_closes_the_pipe_early_is_not_an_error(tmp_path, monkeypatch):
    """`oknowledge import ... | head` closes stdout while we are still writing.

    Python flushes sys.stdout once more as the interpreter exits, and that
    second failure prints "Exception ignored" past every handler in this file
    and exits 120. Only the report is lost: every command finishes its work
    before it prints its first line.

    This is the one test that starts a real process. Nothing else reproduces
    a flush that happens after main() has already returned.
    """
    monkeypatch.setattr(subprocess, "Popen", REAL_POPEN)   # conftest bans it by default
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    config = tmp_path / "config.toml"
    config.write_text(f'vault = "{vault}"\n', encoding="utf-8")
    export = tmp_path / "chat.txt"
    export.write_text("18/7/2019, 11:36 - Fer: https://e.com/x\n", encoding="utf-8")

    read_end, write_end = os.pipe()
    os.close(read_end)          # nobody will ever read: EPIPE on the first write
    try:
        done = REAL_RUN(
            [sys.executable, "-c",
             "import sys; from oknowledge.cli import main; sys.exit(main())",
             "--config", str(config), "import", str(export), "--dry-run"],
            stdout=write_end, stderr=subprocess.PIPE, text=True,
            env={**os.environ, "XDG_STATE_HOME": str(tmp_path / "state")})
    finally:
        os.close(write_end)

    assert "BrokenPipeError" not in done.stderr
    assert "Exception ignored" not in done.stderr
    assert done.returncode == 0


# --- the message somebody with no config file gets ----------------------------

def test_the_example_vault_is_a_path_this_system_could_have(monkeypatch, tmp_path, capsys):
    """The config does not exist yet, so this message is the whole manual at
    that moment. A Windows user handed a /path/to/your/vault has to translate
    it first, and the translation is where the backslash mistake comes from."""
    missing = tmp_path / "nowhere" / "config.toml"

    monkeypatch.setattr(cli.places, "WINDOWS", True)
    assert main(["--config", str(missing), "status"]) == 2
    said = capsys.readouterr().err
    assert 'vault = "C:/Users' in said
    assert "\\" not in said

    monkeypatch.setattr(cli.places, "WINDOWS", False)
    assert main(["--config", str(missing), "status"]) == 2
    assert 'vault = "/path/to' in capsys.readouterr().err
