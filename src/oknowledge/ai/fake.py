"""An engine that returns whatever it is told to. For tests only."""

from __future__ import annotations

from .base import EngineError


class FakeEngine:
    """Replays `replies` in order; an Exception in the list is raised instead.

    Every prompt it receives is recorded in `prompts`.
    """

    name = "fake"

    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if not self.replies:
            raise EngineError("the fake engine ran out of replies")
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply
