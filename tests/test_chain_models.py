"""Several models for one engine, tried in order like the engines are.

`model = "a, b"` in an engine's table: if `a` fails, `b` is asked before the
chain moves on to the next engine. A free model that is down for the
afternoon should not take the whole engine down with it.
"""

import pytest

from oknowledge.ai import (
    AllEnginesFailed, analyze_with_chain, attempts, can_search, describe_with_chain,
    models_of, search_with_chain,
)
from oknowledge.ai.base import EngineError
from oknowledge.ai.fake import FakeEngine
from oknowledge.config import Config
from oknowledge.model import Note

GOOD = ('{"title": "T", "category": "Redes", "tags": ["vpn"], "summary": "S", '
        '"points": ["p"], "type": "article"}')
META = {"url": "https://e.com", "title": "x"}


def config(tmp_path, chain=("opencode",), **engines):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True, exist_ok=True)
    return Config(vault=vault, chain=tuple(chain), engines=engines)


@pytest.fixture
def models(monkeypatch):
    """build_engine faked per model: `replies[model]` is what that model says."""
    replies, built = {}, []

    def build(name, cfg):
        model = cfg.engines.get(name, {}).get("model", "default")
        built.append((name, model))
        engine = FakeEngine(list(replies.get(model, [EngineError(f"{model} is down")])), model)
        engine.searches = True
        return engine
    monkeypatch.setattr("oknowledge.ai.build_engine", build)
    return replies, built


def test_the_models_are_read_in_order_without_blanks(tmp_path):
    cfg = config(tmp_path, opencode={"model": " a , b,, c "})
    assert models_of(cfg, "opencode") == ["a", "b", "c"]
    assert models_of(cfg, "ollama") == []


def test_one_model_is_one_attempt_named_after_the_engine(tmp_path):
    cfg = config(tmp_path, opencode={"model": "a"})
    [(name, label, built)] = attempts(cfg, ("opencode",))
    assert (name, label, built.engines["opencode"]["model"]) == ("opencode", "opencode", "a")


def test_no_model_leaves_the_engine_its_default(tmp_path, models):
    cfg = config(tmp_path)
    models[0]["default"] = [GOOD]
    _, used, model = analyze_with_chain(cfg, "t", META, [])
    assert (used, model) == ("opencode", "default")


def test_the_next_model_is_asked_when_one_fails(tmp_path, models):
    replies, built = models
    replies["b"] = [GOOD]
    cfg = config(tmp_path, opencode={"model": "a, b, c"})
    _, used, model = analyze_with_chain(cfg, "t", META, [])
    assert (used, model) == ("opencode", "b")
    assert built == [("opencode", "a"), ("opencode", "b")]


def test_every_model_failing_names_each_one(tmp_path, models):
    cfg = config(tmp_path, opencode={"model": "a, b"})
    with pytest.raises(AllEnginesFailed) as error:
        analyze_with_chain(cfg, "t", META, [])
    assert "opencode [a]: a is down" in str(error.value)
    assert "opencode [b]: b is down" in str(error.value)


def test_the_next_engine_comes_after_every_model(tmp_path, models):
    replies, built = models
    replies["q"] = [GOOD]
    cfg = config(tmp_path, chain=("opencode", "ollama"),
                 opencode={"model": "a, b"}, ollama={"model": "q"})
    _, used, _ = analyze_with_chain(cfg, "t", META, [])
    assert used == "ollama"
    assert built == [("opencode", "a"), ("opencode", "b"), ("ollama", "q")]


def test_each_model_tried_is_a_line_of_its_own(tmp_path, models):
    replies, _ = models
    replies["b"] = [GOOD]
    steps = []
    cfg = config(tmp_path, opencode={"model": "a, b"})
    analyze_with_chain(cfg, "t", META, [], trace=steps.append)
    closes = [(s.state, s.detail) for s in steps if s.state != "start"]
    assert closes[0][0] == "fail" and closes[0][1].startswith("a")
    assert closes[1] == ("ok", "b")


def test_a_search_moves_on_to_the_next_model(tmp_path, models):
    replies, _ = models
    replies["b"] = ["found it"]
    cfg = config(tmp_path, opencode={"model": "a, b"})
    answer, used, model = search_with_chain(cfg, "p", lambda text: text)
    assert (answer, model) == ("found it", "b")


def test_a_card_rewrite_moves_on_to_the_next_model(tmp_path, models):
    replies, _ = models
    replies["b"] = ['{"summary": "Un cyborg.", "points": ["uno"]}']
    cfg = config(tmp_path, opencode={"model": "a, b"})
    note = Note(id="aaaaaaaaaaaa", url="https://imdb.com/title/t", title="T2",
                category="Películas", tags=[], type="movie", source="imdb.com",
                saved="2026-10-13", summary="A cyborg.")
    summary, _, _, model = describe_with_chain(cfg, note)
    assert (summary, model) == ("Un cyborg.", "b")


def test_searching_is_possible_if_any_model_can(tmp_path, models):
    assert can_search(config(tmp_path, opencode={"model": "a, b"}))
