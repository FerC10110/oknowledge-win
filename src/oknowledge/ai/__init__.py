"""The engine chain: the order is the priority, and being listed is the switch."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from itertools import count
from time import monotonic
from typing import TypeVar

from ..config import Config
from ..model import Mention
from ..trace import SILENT, Step, Tracer, write_trace
from .base import (
    Analysis, AnalysisError, Engine, EngineError, IdeaAnswer, analyze,
    complete_idea, describe_card, mentions_only,
)


class AllEnginesFailed(Exception):
    """No engine in the chain could analyse the page.

    `answered` says whether any engine actually replied: False means none even
    got that far (the chain is down), True means at least one answered and its
    answer was no use (this page's problem). Set only by mentions_with_chain.
    """

    def __init__(self, *args, answered: bool = False):
        super().__init__(*args)
        self.answered = answered


def build_engine(name: str, cfg: Config) -> Engine:
    options = dict(cfg.engines.get(name, {}))
    if name == "opencode":
        from .opencode import OpenCodeEngine
        return OpenCodeEngine(model=options.get("model", "opencode/ling-3.1-flash-free"))
    if name == "ollama":
        from .ollama import OllamaEngine
        return OllamaEngine(
            model=options.get("model", "qwen2.5:7b"),
            url=options.get("url", "http://localhost:11434"),
        )
    if name == "api":
        from .api import ApiEngine
        return ApiEngine(
            provider=options.get("provider", "anthropic"),
            model=options.get("model", "claude-sonnet-5"),
            key_env=options.get("key_env", ""),
            key=options.get("key", ""),
            base_url=options.get("base_url", ""),
            config=cfg.source,
        )
    if name == "fake":
        from .fake import FakeEngine
        return FakeEngine(options.get("replies", []), options.get("model", ""))
    raise EngineError(f"unknown engine: {name!r}")


def _recorder(cfg: Config, link: str, tally: Iterator[int], engine: str,
              model: str, meta: dict) -> Callable[[str, str, str], None] | None:
    """A `record` for `analyze()` that writes one trace file per attempt.

    One file per attempt and not per link: a link that falls through a chain
    of two, each of which gets a second stricter try, is four prompts and four
    replies, and that is precisely the run somebody is reading a trace to
    understand. A single file would hold the last one and lose the rest.

    Returns None when nobody asked for traces, which is the usual case and
    the one that has to cost nothing.
    """
    if not cfg.trace_to or not link:
        return None
    url = str(meta.get("url", "")) if isinstance(meta, dict) else ""

    def record(prompt: str, reply: str, parsed: str) -> None:
        try:
            write_trace(link=link, attempt=next(tally), url=url, engine=engine,
                        model=model, prompt=prompt, reply=reply, parsed=parsed,
                        run=cfg.trace_to, language=cfg.language)
        except Exception:
            # write_trace promises to return None rather than raise, and the
            # rule that a link is never lost does not rest on a promise: this
            # runs between the reply and the note, which is the worst place in
            # the run to discover that the promise had an edge.
            pass

    return record


def analyze_with_chain(cfg: Config, text: str, meta: dict, known,
                       engine: str | None = None,
                       mentions: str | None = None,
                       trace: Tracer = SILENT,
                       link: str = "") -> tuple[Analysis, str, str]:
    """Try each listed engine in order; return the analysis, who produced it
    and with which model.

    An engine that is not in the chain is never tried. Forcing one by name is an
    explicit request and bypasses the chain.

    The model comes off the engine the chain actually built, not off the
    config: those differ whenever the config names none and the engine falls
    back to its own default, which is the common case.
    """
    names = (engine,) if engine else cfg.chain
    if not names:
        raise AllEnginesFailed("no engine is enabled: [ai] chain is empty")
    failures = []
    tally = count(1)
    for name in names:
        # One step per turn of this loop, which is the whole point of tracing
        # here rather than around the call: a link that fails on the first
        # engine and comes out of the second shows two lines, and that is
        # exactly what nothing says today.
        trace(Step(link=link, name="analyze", state="start", seconds=0.0, engine=name))
        clock = monotonic()
        model = ""
        try:
            # build_engine stays inside the try: an engine named in the chain
            # that does not exist is a failure to record, not one to raise.
            engine_used = build_engine(name, cfg)
            model = str(getattr(engine_used, "model", ""))
            analysis = analyze(engine_used, text, meta, known, cfg.language,
                               mentions=mentions,
                               record=_recorder(cfg, link, tally, name, model, meta))
        except (EngineError, AnalysisError) as error:
            failures.append(f"{name}: {error}")
            trace(Step(link=link, name="analyze", state="fail",
                       seconds=monotonic() - clock, engine=name,
                       detail=" · ".join(p for p in (model, str(error)) if p)))
            continue
        trace(Step(link=link, name="analyze", state="ok",
                   seconds=monotonic() - clock, engine=name, detail=model))
        return analysis, name, model
    raise AllEnginesFailed("every engine failed: " + "; ".join(failures))


def describe_with_chain(cfg: Config, note) -> tuple[str, list[str], str, str]:
    """Ask the chain to write a card's summary in the user's language.

    Returns (summary, points, engine name, model). Mirrors the other two:
    the order is the priority, and every failure is kept for the one error
    raised when none of them answers.
    """
    if not cfg.chain:
        raise AllEnginesFailed("no engine is enabled: [ai] chain is empty")
    failures = []
    answered = False
    for name in cfg.chain:
        try:
            engine = build_engine(name, cfg)
            summary, points = describe_card(engine, note, cfg.language)
        except AnalysisError as error:
            # The engine replied; what it said was no use.
            answered = True
            failures.append(f"{name}: {error}")
            continue
        except EngineError as error:
            failures.append(f"{name}: {error}")
            continue
        return summary, points, name, str(getattr(engine, "model", ""))
    raise AllEnginesFailed("every engine failed: " + "; ".join(failures),
                           answered=answered)


def complete_idea_with_chain(cfg: Config, note) -> tuple[IdeaAnswer, str, str]:
    """Ask the chain to fill in an idea. Returns (answer, engine name,
    model). Mirrors describe_with_chain: the order is the priority, and
    every failure is kept for the one error raised when none answers."""
    if not cfg.chain:
        raise AllEnginesFailed("no engine is enabled: [ai] chain is empty")
    failures = []
    answered = False
    for name in cfg.chain:
        try:
            engine = build_engine(name, cfg)
            answer = complete_idea(engine, note, cfg.language)
        except AnalysisError as error:
            answered = True
            failures.append(f"{name}: {error}")
            continue
        except EngineError as error:
            failures.append(f"{name}: {error}")
            continue
        return answer, name, str(getattr(engine, "model", ""))
    raise AllEnginesFailed("every engine failed: " + "; ".join(failures),
                           answered=answered)


def mentions_with_chain(cfg: Config, text: str,
                        meta: dict) -> tuple[list[Mention], str]:
    """Ask the chain for a video's mentions and nothing else.

    Returns the mentions and the name of the engine that produced them, like
    analyze_with_chain.

    Mirrors analyze_with_chain: the order is the priority, and every failure
    is kept for the one error raised when none of them answers.
    """
    if not cfg.chain:
        raise AllEnginesFailed("no engine is enabled: [ai] chain is empty")
    failures = []
    answered = False
    for name in cfg.chain:
        try:
            return mentions_only(build_engine(name, cfg), text, meta,
                                 cfg.language, cfg.mentions), name
        except AnalysisError as error:
            # The engine replied; what it said was no use.
            answered = True
            failures.append(f"{name}: {error}")
        except EngineError as error:
            failures.append(f"{name}: {error}")
    raise AllEnginesFailed("every engine failed: " + "; ".join(failures),
                           answered=answered)


T = TypeVar("T")


def _through_chain(cfg: Config, prompt: str, parse: Callable[[str], T],
                   web: bool) -> tuple[T, str, str]:
    """Each listed engine in order, until one answers something `parse`
    accepts. With `web`, only the engines that can search are asked, and
    they are asked to search."""
    if not cfg.chain:
        raise AllEnginesFailed("no engine is enabled: [ai] chain is empty")
    failures = []
    answered = False
    asked = False
    for name in cfg.chain:
        try:
            engine = build_engine(name, cfg)
            if web and not getattr(engine, "searches", False):
                continue
            asked = True
            reply = engine.search(prompt) if web else engine.complete(prompt)
            result = parse(reply)
        except AnalysisError as error:
            answered = True
            failures.append(f"{name}: {error}")
            continue
        except EngineError as error:
            failures.append(f"{name}: {error}")
            continue
        return result, name, str(getattr(engine, "model", ""))
    if web and not asked:
        raise AllEnginesFailed("no engine in the chain can search the web")
    raise AllEnginesFailed("every engine failed: " + "; ".join(failures),
                           answered=answered)


def ask_with_chain(cfg: Config, prompt: str,
                   parse: Callable[[str], T]) -> tuple[T, str, str]:
    """Ask the chain to think about `prompt`. Returns (parsed, engine, model)."""
    return _through_chain(cfg, prompt, parse, web=False)


def search_with_chain(cfg: Config, prompt: str,
                      parse: Callable[[str], T]) -> tuple[T, str, str]:
    """Ask the first engines of the chain that can search the web."""
    return _through_chain(cfg, prompt, parse, web=True)


def can_search(cfg: Config) -> bool:
    """Whether search_with_chain has anyone to ask. Calls no model: building
    an engine reads its config and nothing else."""
    for name in cfg.chain:
        try:
            if getattr(build_engine(name, cfg), "searches", False):
                return True
        except EngineError:
            continue
    return False
