"""What a model is asked about an idea, and what is kept of its answer."""

import json

import pytest

from oknowledge.ai import AllEnginesFailed, complete_idea_with_chain
from oknowledge.ai.base import (
    LANGUAGE_NAMES, AnalysisError, EngineError, IdeaAnswer, complete_idea,
    normalize_tags, render_idea_prompt,
)
from oknowledge.config import Config
from oknowledge.ideas import new_idea

INSTANT = "2026-10-12T21:04:05.123456+00:00"
GOOD = {"title": "Gimnasio con IA", "tags": ["gimnasio", "ia"],
        "summary": "Una app que arma la rutina.",
        "points": ["Para quien entrena solo."]}


class Says:
    model = "m-1"

    def __init__(self, reply):
        self.reply = reply
        self.prompt = ""

    def complete(self, prompt):
        self.prompt = prompt
        return self.reply


def an_idea(text="Una app que me arme la rutina.", title=""):
    return new_idea(text, title, "2026-10-12", INSTANT)


def answer_to(reply):
    return complete_idea(Says(json.dumps(reply)), an_idea(), "es")


def test_the_prompt_carries_the_text_the_title_and_the_language():
    prompt = render_idea_prompt(an_idea(title="Mi gym"), "es")
    assert "Una app que me arme la rutina." in prompt
    assert "Mi gym" in prompt
    assert LANGUAGE_NAMES["es"] in prompt
    assert "{{" not in prompt


def test_a_text_that_looks_like_a_placeholder_is_not_filled_in_twice():
    prompt = render_idea_prompt(an_idea(text="literal {{TITLE}} here", title="T"), "es")
    assert "literal {{TITLE}} here" in prompt


def test_a_good_answer_is_kept():
    assert answer_to(GOOD) == IdeaAnswer(
        title="Gimnasio con IA", tags=["gimnasio", "ia"],
        summary="Una app que arma la rutina.", points=["Para quien entrena solo."])


def test_a_title_comes_back_as_one_short_line():
    title = answer_to(dict(GOOD, title="Gimnasio\ncon   IA " + "x" * 300)).title
    assert "\n" not in title and "  " not in title
    assert len(title) == 120


def test_tags_are_cleaned_like_every_other_tag():
    raw = ["Inteligencia Artificial", "SALUD", "salud"]
    assert answer_to(dict(GOOD, tags=raw)).tags == normalize_tags(raw)


def test_points_stop_at_six():
    assert len(answer_to(dict(GOOD, points=[f"punto {n}" for n in range(10)])).points) == 6


@pytest.mark.parametrize("broken", [
    dict(GOOD, title=""), dict(GOOD, summary="  "),
    {k: v for k, v in GOOD.items() if k != "title"},
    {k: v for k, v in GOOD.items() if k != "summary"},
])
def test_an_answer_with_no_name_or_no_summary_is_no_use(broken):
    with pytest.raises(AnalysisError):
        answer_to(broken)


def test_an_answer_that_is_not_json_is_no_use():
    with pytest.raises(AnalysisError):
        complete_idea(Says("no tengo idea"), an_idea(), "es")


def test_tags_and_points_may_be_left_out():
    answer = answer_to({"title": "T", "summary": "S."})
    assert (answer.tags, answer.points) == ([], [])


@pytest.fixture
def cfg(tmp_path):
    return Config(vault=tmp_path / "vault", chain=("first", "second"))


def test_the_chain_moves_on_until_one_answers(cfg, monkeypatch):
    class Down:
        model = "x"

        def complete(self, prompt):
            raise EngineError("down")

    engines = {"first": Down(), "second": Says(json.dumps(GOOD))}
    monkeypatch.setattr("oknowledge.ai.build_engine", lambda name, cfg: engines[name])
    answer, engine, model = complete_idea_with_chain(cfg, an_idea())
    assert (answer.title, engine, model) == ("Gimnasio con IA", "second", "m-1")


def test_a_chain_where_nobody_answers_says_so(cfg, monkeypatch):
    monkeypatch.setattr("oknowledge.ai.build_engine", lambda name, cfg: Says("nada"))
    with pytest.raises(AllEnginesFailed) as caught:
        complete_idea_with_chain(cfg, an_idea())
    assert caught.value.answered is True


def test_an_empty_chain_is_refused(tmp_path):
    with pytest.raises(AllEnginesFailed):
        complete_idea_with_chain(Config(vault=tmp_path, chain=()), an_idea())
