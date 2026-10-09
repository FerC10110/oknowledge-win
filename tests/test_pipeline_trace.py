"""What the pipeline says while it works.

The first test is the one that justifies the whole wrapper: tracing is new
code in the critical path of a module whose rule is that a link is never
lost.
"""

import json

import pytest

from oknowledge.ai.fake import FakeEngine
from oknowledge.config import Config
from oknowledge.extract import Unreadable
from oknowledge.model import Extracted
from oknowledge.pipeline import add, retry
from oknowledge.queue import Queue
from oknowledge.trace import trace_run

ANSWER = json.dumps({
    "title": "WireGuard vs OpenVPN",
    "summary": "Compara ambos protocolos.",
    "points": ["Corre en el kernel"],
    "category": "Redes",
    "tags": ["vpn"],
})

PAGE = Extracted(
    title="WireGuard vs OpenVPN | Ars",
    text="WireGuard runs inside the kernel...",
    type="article",
    source="arstechnica.com",
    cover_url="https://cdn.example.com/wg.jpg",
)


@pytest.fixture(autouse=True)
def state_under_tmp_path(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))


@pytest.fixture
def cfg(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    return Config(vault=vault, chain=("fake",),
                  engines={"fake": {"replies": [ANSWER, ANSWER], "model": "fake-7b"}})


@pytest.fixture
def q(tmp_path):
    return Queue(tmp_path / "state")


@pytest.fixture
def ready(monkeypatch):
    """A readable page and no pictures: the plain good path."""
    monkeypatch.setattr("oknowledge.pipeline.extract", lambda url: PAGE)
    monkeypatch.setattr("oknowledge.pipeline.download_cover",
                        lambda cfg, url, link: None)
    monkeypatch.setattr("oknowledge.pipeline.download_icon",
                        lambda cfg, source: None)


def angry(step):
    raise RuntimeError("boom")


def opened_and_closed(steps, name):
    return ([s for s in steps if s.name == name and s.state == "start"],
            [s for s in steps if s.name == name and s.state in ("ok", "fail")])


def test_a_tracer_that_explodes_still_saves_the_note(cfg, q, ready):
    quiet = add(cfg, "https://a.test/x", queue=q)
    loud = add(cfg, "https://a.test/y", queue=q, trace=angry)

    assert loud.status == quiet.status == "ok"
    assert loud.path is not None
    assert loud.warnings == quiet.warnings


def test_every_step_closes(cfg, q, ready):
    seen = []
    add(cfg, "https://a.test/x", queue=q, trace=seen.append)

    assert {s.name for s in seen} == {"find", "extract", "analyze", "cover", "save"}
    for name in {s.name for s in seen}:
        opened, closed = opened_and_closed(seen, name)
        assert len(opened) == len(closed) == 1, name


def test_every_step_closes_on_the_failure_path(cfg, q, monkeypatch):
    monkeypatch.setattr("oknowledge.pipeline.extract",
                        lambda url: (_ for _ in ()).throw(Unreadable("no text")))
    monkeypatch.setattr("oknowledge.pipeline.download_icon", lambda cfg, source: None)
    seen = []
    result = add(cfg, "https://a.test/x", queue=q, trace=seen.append)

    assert result.status == "partial"
    for name in {s.name for s in seen}:
        opened, closed = opened_and_closed(seen, name)
        assert len(opened) == len(closed), name
    extract_closed = opened_and_closed(seen, "extract")[1][0]
    assert extract_closed.state == "fail"
    assert "no text" in extract_closed.detail
    # The page never arrived, so nothing was analysed and nothing downloaded.
    assert {s.name for s in seen} == {"find", "extract", "save"}


def test_a_link_that_falls_to_the_second_engine_says_so_twice(cfg, q, ready,
                                                              monkeypatch):
    engines = {
        "first": FakeEngine(["not json at all", "still not json"], "ling-3.1-flash"),
        "second": FakeEngine([ANSWER], "qwen2.5:7b"),
    }
    monkeypatch.setattr("oknowledge.ai.build_engine",
                        lambda name, cfg: engines[name])
    seen = []
    result = add(dataclasses_replace(cfg, chain=("first", "second")),
                 "https://a.test/x", queue=q, trace=seen.append)

    assert result.status == "ok"
    steps = [s for s in seen if s.name == "analyze"]
    assert [(s.state, s.engine) for s in steps] == [
        ("start", "first"), ("fail", "first"),
        ("start", "second"), ("ok", "second"),
    ]
    assert "ling-3.1" in steps[1].detail          # the model, not just the engine
    assert "qwen2.5:7b" in steps[3].detail


def test_a_start_costs_no_time_and_a_close_does(cfg, q, ready):
    seen = []
    add(cfg, "https://a.test/x", queue=q, trace=seen.append)
    assert all(s.seconds == 0.0 for s in seen if s.state == "start")
    assert all(s.seconds >= 0.0 for s in seen)


def test_every_step_names_the_link_it_belongs_to(cfg, q, ready):
    seen = []
    result = add(cfg, "https://a.test/x", queue=q, trace=seen.append)
    assert {s.link for s in seen} == {result.id}


def test_retry_hands_the_tracer_down(cfg, q, ready):
    q.enqueue("a" * 12, "https://a.test/x", "full")
    q.set_status("a" * 12, "partial", "never analysed")
    seen = []
    retry(cfg, queue=q, trace=seen.append)
    assert "extract" in {s.name for s in seen}


def test_nothing_is_written_unless_the_run_asks_for_it(cfg, q, ready, tmp_path):
    add(cfg, "https://a.test/x", queue=q)
    assert not (tmp_path / "state" / "oknowledge" / "trace").exists()


def test_the_prompt_and_the_reply_land_in_a_file(cfg, q, ready, tmp_path):
    result = add(dataclasses_replace(cfg, trace_to="run-1"),
                 "https://a.test/x", queue=q)
    folder = tmp_path / "state" / "oknowledge" / "trace" / "run-1"
    written = sorted(p.name for p in folder.iterdir())
    assert written == [f"{result.id}-01.md"]
    text = (folder / written[0]).read_text(encoding="utf-8")
    assert "WireGuard runs inside the kernel" in text      # the prompt
    assert "Compara ambos protocolos" in text              # the reply
    assert "fake-7b" in text                               # and who said it


def test_each_try_gets_its_own_file(cfg, q, ready, monkeypatch, tmp_path):
    engines = {
        "first": FakeEngine(["not json at all", "still not json"], "ling-3.1-flash"),
        "second": FakeEngine([ANSWER], "qwen2.5:7b"),
    }
    monkeypatch.setattr("oknowledge.ai.build_engine", lambda name, cfg: engines[name])
    result = add(dataclasses_replace(cfg, chain=("first", "second"), trace_to="r"),
                 "https://a.test/x", queue=q)

    folder = tmp_path / "state" / "oknowledge" / "trace" / "r"
    written = sorted(p.name for p in folder.iterdir())
    assert written == [f"{result.id}-0{n}.md" for n in (1, 2, 3)]
    first = (folder / written[0]).read_text(encoding="utf-8")
    assert "not json at all" in first and "ling-3.1-flash" in first
    assert "qwen2.5:7b" in (folder / written[2]).read_text(encoding="utf-8")


def test_a_run_folder_that_cannot_be_written_does_not_cost_the_note(cfg, q, ready,
                                                                    tmp_path):
    (tmp_path / "state" / "oknowledge").mkdir(parents=True)
    (tmp_path / "state" / "oknowledge" / "trace").write_text("a file", encoding="utf-8")
    result = add(dataclasses_replace(cfg, trace_to="r"), "https://a.test/x", queue=q)
    assert result.status == "ok"


def test_a_trace_that_explodes_does_not_cost_the_note(cfg, q, ready, monkeypatch):
    """write_trace promises not to raise. The rule that a link is never lost
    does not rest on a promise, and this runs between the reply and the
    note."""
    monkeypatch.setattr("oknowledge.ai.write_trace",
                        lambda **kw: (_ for _ in ()).throw(RuntimeError("boom")))
    result = add(dataclasses_replace(cfg, trace_to="r"), "https://a.test/x", queue=q)
    assert result.status == "ok"


def test_the_run_folder_is_named_for_the_clock_when_the_config_asks(tmp_path):
    """`[debug] trace = true` means "this process traces", and one process is
    one run folder."""
    from oknowledge import config as config_module

    path = tmp_path / "config.toml"
    path.write_text(f'vault = "{tmp_path}"\n\n[debug]\ntrace = true\n', encoding="utf-8")
    loaded = config_module.load(path)
    assert loaded.trace_to in (trace_run(), "")
    assert loaded.trace_to != ""


def test_the_config_traces_nothing_by_default(tmp_path):
    from oknowledge import config as config_module

    path = tmp_path / "config.toml"
    path.write_text(f'vault = "{tmp_path}"\n', encoding="utf-8")
    assert config_module.load(path).trace_to == ""


def dataclasses_replace(cfg, **changes):
    import dataclasses
    return dataclasses.replace(cfg, **changes)
