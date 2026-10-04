"""The command line. Every test points XDG_STATE_HOME at tmp_path, so nothing
here can touch the real queue, and the config is always passed explicitly."""

import json

import pytest

from oknowledge.cli import main
from oknowledge.config import Config
from oknowledge.model import Extracted
from oknowledge.pipeline import Result
from oknowledge.queue import Queue, state_dir
from oknowledge.vault import RebuildResult

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
    assert "2 indexes" in out.out
    assert "Redes.md" in out.err and "not ours" in out.err
    assert "broken.md" in out.err and "could not be read" in out.err


def test_reindex_runs_for_real(cfg, capsys):
    assert main(["reindex"]) == 0
    assert "0 indexes" in capsys.readouterr().out


def test_retry_shows_why_a_link_failed(cfg, monkeypatch, capsys):
    monkeypatch.setattr("oknowledge.cli.retry", lambda config: [
        Result(id="a1", url="https://e.com/a", path=None, status="ok"),
        Result(id="b2", url="https://e.com/b", path=None, status="failed", error="timeout"),
    ])
    assert main(["retry"]) == 1
    out = capsys.readouterr().out
    assert "1/2 finished" in out
    assert "https://e.com/b" in out and "timeout" in out


def test_retry_json_is_one_array(cfg, monkeypatch, capsys):
    monkeypatch.setattr("oknowledge.cli.retry", lambda config: [
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
    assert main(["reindex"]) == 1
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
