"""Which actions are running on which idea, and how the last one ended.

In memory, like Batch: a run only exists while this process does, so a
restart leaves nothing to explain and every button free again.
"""

from __future__ import annotations

import threading


class Working:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._running: set[tuple[str, str]] = set()
        self._failed: dict[tuple[str, str], str] = {}

    def start(self, idea: str, action: str) -> bool:
        """Claim the run. False means that action is already running there."""
        with self._lock:
            if (idea, action) in self._running:
                return False
            self._running.add((idea, action))
            return True

    def finish(self, idea: str, action: str, problem: str | None) -> None:
        with self._lock:
            self._running.discard((idea, action))
            if problem:
                self._failed[(idea, action)] = problem
            else:
                self._failed.pop((idea, action), None)

    def of(self, idea: str) -> tuple[set[str], dict[str, str]]:
        """(the actions running on this idea, the last failure of each)."""
        with self._lock:
            return ({action for i, action in self._running if i == idea},
                    {action: why for (i, action), why in self._failed.items() if i == idea})

    def all_of(self, action: str) -> tuple[set[str], dict[str, str]]:
        """(every id running this action, the last failure of each), for a
        page that lists many at once."""
        with self._lock:
            return ({i for i, a in self._running if a == action},
                    {i: why for (i, a), why in self._failed.items() if a == action})
