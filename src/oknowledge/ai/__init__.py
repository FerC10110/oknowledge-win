"""The engine chain: the order is the priority, and being listed is the switch."""

from __future__ import annotations

from ..config import Config
from ..model import Mention
from .base import Analysis, AnalysisError, Engine, EngineError, analyze, mentions_only


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
        )
    if name == "fake":
        from .fake import FakeEngine
        return FakeEngine(options.get("replies", []))
    raise EngineError(f"unknown engine: {name!r}")


def analyze_with_chain(cfg: Config, text: str, meta: dict, known,
                       engine: str | None = None,
                       mentions: str | None = None) -> tuple[Analysis, str]:
    """Try each listed engine in order; return the analysis and who produced it.

    An engine that is not in the chain is never tried. Forcing one by name is an
    explicit request and bypasses the chain.
    """
    names = (engine,) if engine else cfg.chain
    if not names:
        raise AllEnginesFailed("no engine is enabled: [ai] chain is empty")
    failures = []
    for name in names:
        try:
            return analyze(build_engine(name, cfg), text, meta, known,
                           cfg.language, mentions=mentions), name
        except (EngineError, AnalysisError) as error:
            failures.append(f"{name}: {error}")
    raise AllEnginesFailed("every engine failed: " + "; ".join(failures))


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
