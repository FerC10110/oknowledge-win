"""The prompt and the reply on disk: the only thing that helps when the
analysis does not fail but comes out wrong, and the only thing in this
feature that can fill a disk."""

import re
import shutil

import pytest

from oknowledge.trace import CAP, sweep_traces, trace_run, write_trace


def test_the_file_says_the_url_the_engine_and_the_model(tmp_path):
    path = write_trace(tmp_path, "abc123", url="https://example.com/a",
                       engine="opencode", model="ling-3.1-flash-free",
                       prompt="p", reply="r", parsed="{}", run="run-1")
    assert path == tmp_path / "trace" / "run-1" / "abc123.md"
    text = path.read_text(encoding="utf-8")
    assert "https://example.com/a" in text
    assert "opencode" in text and "ling-3.1-flash-free" in text
    assert "p" in text and "r" in text


def test_a_huge_prompt_keeps_its_head_and_its_tail(tmp_path):
    path = write_trace(tmp_path, "abc123", prompt="A" * 400_000 + "TAIL",
                       reply="ok", run="r")
    text = path.read_text(encoding="utf-8")
    assert len(text.encode()) <= CAP
    assert "A" * 100 in text
    assert "TAIL" in text
    assert "cut from the middle" in text


def test_the_cut_says_how_much_it_took(tmp_path):
    """Everything that was there is either in the file or in the count: a
    vague "truncated" leaves you guessing whether the model saw the part
    that mattered."""
    path = write_trace(tmp_path, "a", prompt="A" * 400_000, reply="", run="r")
    text = path.read_text(encoding="utf-8")
    said = int(re.search(r"\((\d+) characters cut", text).group(1))
    assert said + text.count("A") == 400_000


def test_a_huge_reply_cannot_push_the_file_over_the_cap(tmp_path):
    """The prompt is the one the design expects to be big, but the reply is
    the model's and the model is not ours to trust."""
    path = write_trace(tmp_path, "a", prompt="p", reply="R" * 900_000,
                       parsed="X" * 900_000, run="r")
    assert len(path.read_text(encoding="utf-8").encode()) <= CAP


def test_a_small_prompt_is_not_cut_at_all(tmp_path):
    path = write_trace(tmp_path, "a", prompt="hola", reply="chau", run="r")
    text = path.read_text(encoding="utf-8")
    assert "cut from the middle" not in text
    assert "hola" in text and "chau" in text


def test_a_prompt_that_is_not_clean_utf8_is_still_written(tmp_path):
    """Six years of pages hold bytes that are not text. The importer replaces
    them rather than refusing the file, and so does this."""
    path = write_trace(tmp_path, "a", prompt="hola \udcff mundo", reply="",
                       run="r")
    assert "hola" in path.read_text(encoding="utf-8")


def test_a_prompt_full_of_backticks_does_not_break_the_block(tmp_path):
    """A page about Markdown has fences in it. A fence that ends early turns
    the rest of the trace into prose."""
    path = write_trace(tmp_path, "a", prompt="```\nnot the end\n```",
                       reply="", run="r")
    text = path.read_text(encoding="utf-8")
    assert "````" in text
    assert "not the end" in text


def test_a_folder_that_cannot_be_created_is_not_an_error(tmp_path):
    (tmp_path / "trace").write_text("I am a file, not a folder", encoding="utf-8")
    assert write_trace(tmp_path, "a", prompt="x", reply="y", run="r") is None


def test_a_link_id_cannot_climb_out_of_the_folder(tmp_path):
    assert write_trace(tmp_path, "../../etc/passwd", prompt="x", reply="",
                       run="r") is None
    assert write_trace(tmp_path, "", prompt="x", reply="", run="r") is None


def test_the_file_is_numbered_but_the_link_is_not(tmp_path):
    """The link's id is what the vault, the queue and the library all call
    this page. Only the file is numbered."""
    path = write_trace(tmp_path, "abc123", prompt="p", reply="r", run="r",
                       attempt=2)
    assert path.name == "abc123-02.md"
    assert "abc123-02" not in path.read_text(encoding="utf-8")
    assert "abc123" in path.read_text(encoding="utf-8")


def test_two_links_of_one_run_land_in_the_same_folder(tmp_path):
    first = write_trace(tmp_path, "aaa", prompt="1", reply="", run="r")
    second = write_trace(tmp_path, "bbb", prompt="2", reply="", run="r")
    assert first.parent == second.parent


def test_a_run_with_no_name_is_named_for_the_clock(tmp_path):
    path = write_trace(tmp_path, "aaa", prompt="1", reply="")
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}", path.parent.name)
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}", trace_run())


def test_the_sweep_keeps_the_last_ten_runs(tmp_path):
    for n in range(14):
        write_trace(tmp_path, "aaa", prompt="x", reply="", run=f"2026-10-{n:02d}")
    sweep_traces(tmp_path)
    left = sorted(p.name for p in (tmp_path / "trace").iterdir())
    assert len(left) == 10
    assert left[0] == "2026-10-04"          # the oldest four are the ones gone
    assert left[-1] == "2026-10-13"


def test_the_sweep_survives_a_folder_it_cannot_remove(tmp_path, monkeypatch):
    for n in range(12):
        write_trace(tmp_path, "aaa", prompt="x", reply="", run=f"2026-10-{n:02d}")
    monkeypatch.setattr(shutil, "rmtree",
                        lambda *a, **k: (_ for _ in ()).throw(PermissionError("no")))
    sweep_traces(tmp_path)                  # does not raise
    assert len(list((tmp_path / "trace").iterdir())) == 12


def test_the_sweep_of_a_folder_that_is_not_there_is_quiet(tmp_path):
    sweep_traces(tmp_path / "nowhere")


@pytest.mark.parametrize("keep", [0, 1])
def test_the_sweep_keeps_what_it_is_asked_to(tmp_path, keep):
    for n in range(3):
        write_trace(tmp_path, "aaa", prompt="x", reply="", run=f"2026-10-{n:02d}")
    sweep_traces(tmp_path, keep=keep)
    assert len(list((tmp_path / "trace").iterdir())) == keep


def test_the_headings_are_translated(tmp_path):
    path = write_trace(tmp_path, "a", prompt="p", reply="r", run="r",
                       language="es")
    assert "Respuesta" in path.read_text(encoding="utf-8")
