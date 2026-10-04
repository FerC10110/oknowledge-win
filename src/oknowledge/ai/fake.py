"""An engine that returns whatever it is told to. For tests only."""

from __future__ import annotations

import json

from .base import EngineError


class FakeEngine:
    """Replays `replies` in order, recording every prompt in `prompts`.

    Each reply is one of:
      - a str, returned as is;
      - an Exception instance, raised (use EngineError to simulate a failure);
      - a callable taking the prompt and returning either of the above, so a
        test can answer according to the prompt instead of pre-ordering.

    If `replies` is itself a callable it answers every prompt, forever: handy
    for tests that push several pages through, in any order.

    Anything else is a mistake in the test and raises TypeError, so it is
    never mistaken for an engine failure the code under test might swallow.
    """

    name = "fake"

    def __init__(self, replies):
        self._answer = replies if callable(replies) else None
        self.replies = [] if self._answer else list(replies)
        self.prompts: list[str] = []

    @staticmethod
    def answer(**overrides) -> str:
        """A valid JSON reply with sane defaults; keyword arguments replace fields."""
        data = {
            "title": "A title",
            "summary": "A summary of what the page says.",
            "points": ["First point", "Second point"],
            "category": "General",
            "tags": ["one", "two", "three"],
        }
        data.update(overrides)
        return json.dumps(data, ensure_ascii=False)

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if self._answer:
            reply = self._answer
        elif self.replies:
            reply = self.replies.pop(0)
        else:
            raise EngineError("the fake engine ran out of replies")
        if isinstance(reply, type):
            raise TypeError(f"the fake engine got the class {reply.__name__}; pass an instance")
        if callable(reply):
            reply = reply(prompt)
        if isinstance(reply, Exception):
            raise reply
        if not isinstance(reply, str):
            raise TypeError(f"the fake engine needs a str reply, got {type(reply).__name__}: {reply!r}")
        return reply
