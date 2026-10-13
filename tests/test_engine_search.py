"""Searching the web is a capability, not a mode of complete().

An engine that can search says so with `searches`. One that searches proves
it: a "nothing like this exists" from a model that never looked is worse
than no answer.
"""

import json
import subprocess

import pytest

from oknowledge.ai.base import NO_SEARCH, EngineError
from oknowledge.ai.fake import FakeEngine
from oknowledge.ai.ollama import OllamaEngine
from oknowledge.ai.opencode import OpenCodeEngine, parse_events


def event(**part):
    return json.dumps({"type": part.get("type", "text"), "part": part})


SEARCHED = event(type="tool", tool="websearch", state={"status": "completed"})
FETCHED = event(type="tool", tool="webfetch", state={"status": "completed"})
ANSWER = event(type="text", text='{"verdict": "new"}')


@pytest.fixture
def ran(monkeypatch):
    seen = {"stdout": "", "code": 0, "stderr": ""}

    def run(argv, **kwargs):
        seen["argv"] = argv
        return subprocess.CompletedProcess(argv, seen["code"], stdout=seen["stdout"],
                                           stderr=seen["stderr"])

    monkeypatch.setattr("oknowledge.ai.opencode.sandboxed", lambda argv, cwd: ["bwrap", *argv])
    monkeypatch.setattr("subprocess.run", run)
    return seen


def test_opencode_searches_and_ollama_does_not():
    assert OpenCodeEngine(model="m").searches is True
    assert OllamaEngine(model="q", url="http://x", ensure=lambda: None).searches is False


def test_opencode_search_asks_for_json_events_inside_the_sandbox(ran):
    ran["stdout"] = "\n".join([SEARCHED, ANSWER])
    assert OpenCodeEngine(model="opencode/x-free").search("busca") == '{"verdict": "new"}'
    assert ran["argv"][0] == "bwrap"
    assert ran["argv"][1:] == ["opencode", "run", "--pure", "--format", "json",
                               "-m", "opencode/x-free", "busca"]


def test_complete_does_not_ask_for_events(ran):
    ran["stdout"] = "plain"
    OpenCodeEngine(model="m").complete("hola")
    assert "--format" not in ran["argv"]


def test_the_answer_is_every_text_part_in_order():
    stdout = "\n".join([event(type="text", text="uno "), SEARCHED,
                        event(type="text", text="dos"), "not json", "[1]"])
    assert parse_events(stdout) == "uno dos"


def test_search_without_a_search_tool_is_an_error():
    with pytest.raises(EngineError) as raised:
        parse_events(ANSWER)
    assert str(raised.value) == NO_SEARCH


def test_a_fetch_counts_as_searching():
    assert parse_events("\n".join([FETCHED, ANSWER])) == '{"verdict": "new"}'


def test_a_search_that_failed_does_not_count():
    failed = event(type="tool", tool="websearch", state={"status": "error"})
    with pytest.raises(EngineError, match=NO_SEARCH):
        parse_events("\n".join([failed, ANSWER]))


def test_an_error_event_is_the_error_even_with_exit_one(ran):
    ran["code"] = 1
    ran["stdout"] = json.dumps({"type": "error", "error": {
        "name": "APIError", "data": {"message": "Upstream request failed: Endpoint is unavailable."}}})
    with pytest.raises(EngineError, match="opencode failed: Upstream request failed"):
        OpenCodeEngine(model="m").search("busca")


def test_a_failure_with_no_events_reports_stderr(ran):
    ran["code"] = 1
    ran["stderr"] = "boom"
    with pytest.raises(EngineError, match="opencode failed: boom"):
        OpenCodeEngine(model="m").search("busca")


def test_searching_with_no_text_is_an_empty_answer():
    with pytest.raises(EngineError, match="empty answer"):
        parse_events(SEARCHED)


def test_the_fake_engine_searches_with_its_replies():
    fake = FakeEngine(["uno", "dos"])
    assert fake.searches is True
    assert fake.search("p1") == "uno"
    assert fake.complete("p2") == "dos"
    assert fake.prompts == ["p1", "p2"]
