"""The chain, asked to think or to search."""

import pytest

from oknowledge.ai import AllEnginesFailed, ask_with_chain, can_search, search_with_chain
from oknowledge.ai.base import AnalysisError, EngineError
from oknowledge.config import Config


class Stub:
    def __init__(self, name, searches, reply="r", error=None):
        self.name, self.searches, self.reply, self.error = name, searches, reply, error
        self.model = f"{name}-1"
        self.calls = []

    def complete(self, prompt):
        self.calls.append(("complete", prompt))
        if self.error:
            raise self.error
        return self.reply

    def search(self, prompt):
        self.calls.append(("search", prompt))
        if self.error:
            raise self.error
        return self.reply


@pytest.fixture
def engines(monkeypatch):
    table = {}

    def build(name, cfg):
        if name not in table:
            raise EngineError(f"unknown engine: {name!r}")
        return table[name]

    monkeypatch.setattr("oknowledge.ai.build_engine", build)
    return table


def chain(tmp_path, *names):
    return Config(vault=tmp_path, chain=names)


def test_search_skips_the_engines_that_cannot_search(tmp_path, engines):
    engines["ollama"] = Stub("ollama", False)
    engines["opencode"] = Stub("opencode", True, reply="hallado")
    assert search_with_chain(chain(tmp_path, "ollama", "opencode"), "p", str.upper) == (
        "HALLADO", "opencode", "opencode-1")
    assert engines["ollama"].calls == []
    assert engines["opencode"].calls == [("search", "p")]


def test_a_chain_with_no_searcher_calls_nobody(tmp_path, engines):
    engines["ollama"] = Stub("ollama", False)
    with pytest.raises(AllEnginesFailed, match="no engine in the chain can search the web"):
        search_with_chain(chain(tmp_path, "ollama"), "p", str)
    assert engines["ollama"].calls == []


def test_ask_uses_complete_on_every_engine(tmp_path, engines):
    engines["ollama"] = Stub("ollama", False, reply="pensado")
    assert ask_with_chain(chain(tmp_path, "ollama"), "p", str)[0] == "pensado"
    assert engines["ollama"].calls == [("complete", "p")]


def test_a_useless_answer_falls_through_to_the_next_engine(tmp_path, engines):
    engines["a"] = Stub("a", True, reply="malo")
    engines["b"] = Stub("b", True, reply="bueno")

    def parse(reply):
        if reply == "malo":
            raise AnalysisError("no JSON")
        return reply

    assert search_with_chain(chain(tmp_path, "a", "b"), "p", parse)[:2] == ("bueno", "b")


def test_every_failure_is_named(tmp_path, engines):
    engines["a"] = Stub("a", True, error=EngineError("429"))
    with pytest.raises(AllEnginesFailed, match="a: 429"):
        search_with_chain(chain(tmp_path, "a"), "p", str)


def test_an_empty_chain_is_its_own_error(tmp_path, engines):
    with pytest.raises(AllEnginesFailed, match="chain is empty"):
        ask_with_chain(chain(tmp_path), "p", str)


def test_can_search_says_the_same_without_calling(tmp_path, engines):
    engines["ollama"] = Stub("ollama", False)
    engines["opencode"] = Stub("opencode", True)
    assert can_search(chain(tmp_path, "ollama")) is False
    assert can_search(chain(tmp_path, "ollama", "opencode")) is True
    assert can_search(chain(tmp_path, "nope")) is False
    assert engines["opencode"].calls == []
