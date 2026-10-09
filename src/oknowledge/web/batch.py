"""One batch of re-analysis, and how far along it is.

The Procesar button in Settings starts a run of pipeline.retry() behind the
response, because a batch of fifty links is an hour of model calls and no
browser waits that long. What the user gets back is a page that can say how
far the run has got, which is what this module holds.

It holds it in memory, not in a file. A run only exists while the process
that started it does: if the server dies the run died with it, so there is
nothing to resume, and a file would only leave a stale number to explain. The
links themselves are never at risk either way -- the queue is the record of
what is still owed, and it is on disk.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from typing import NamedTuple

from ..config import Config
from ..pipeline import Result, retry
from ..trace import Step, sweep_traces

log = logging.getLogger("oknowledge.web")


# The most steps a run keeps. A batch of 1164 links is some six thousand of
# them, and the page sends every one it holds on every refresh.
LINES = 200


class State(NamedTuple):
    """A run's numbers, read all at once so they cannot disagree."""

    running: bool
    total: int
    done: int
    failed: int
    error: str | None
    lines: tuple[Step, ...] = ()
    """What the run has been doing, newest first.""" 


class Batch:
    """The current run, or the last one that ended.

    Written from the background task that runs the batch and read from the
    request that draws the bar -- two threads, hence the lock. It is not only
    the counters: `start` has to decide and record in one step, or two clicks
    arriving together both start a run.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._running = False
        self._total = 0
        self._done = 0
        self._failed = 0
        self._error: str | None = None
        self._lines: deque[Step] = deque(maxlen=LINES)

    def start(self, total: int) -> bool:
        """Claim the run. False means one is already in flight -- do not start.

        Two runs over one queue would reach for the same links, and each would
        find the other's work already done: wasted model calls at best.
        """
        with self._lock:
            if self._running:
                return False
            self._running = True
            self._total = total
            self._done = 0
            self._failed = 0
            self._error = None
            # A new run starts with an empty list: the last run's steps under
            # this run's bar would read as this run's work.
            self._lines.clear()
            return True

    def step(self, result: Result) -> None:
        """One more link finished, well or badly.

        Both count: a bar that only counts the ones that came back stops short
        of its total on the first dead link and sits there.
        """
        with self._lock:
            if not self._running:
                return
            self._done += 1
            if result.status == "failed":
                self._failed += 1

    def note(self, step: Step) -> None:
        """One more thing this process is doing, for the page to draw.

        Newest first and capped at `LINES`, which the deque does in one move:
        a step arriving pushes the oldest one off the end.

        Taken whether or not a batch is running, unlike the counters beside
        it: a link re-analysed from its own card is a model call like any
        other, and the page that shows model calls has to show it. A new
        batch still clears the list, so the bar and the lines under it always
        describe the same run.
        """
        with self._lock:
            self._lines.appendleft(step)

    def finish(self, error: str | None = None) -> None:
        """The run is over. The numbers stay, to be read on the next page."""
        with self._lock:
            self._running = False
            self._error = error

    def snapshot(self) -> State:
        with self._lock:
            return State(running=self._running, total=self._total,
                         done=self._done, failed=self._failed,
                         error=self._error, lines=tuple(self._lines))


def run(cfg: Config, held: Batch, limit: int) -> None:
    """Run one batch, and never raise into the server.

    retry() already absorbs a single link's failure, so anything that reaches
    here is the whole run coming down -- an unreadable queue, a full disk. It
    still has to end the run: a record left running leaves the button dead
    until the server is restarted, with nothing on the page to say why.
    """
    problem = None
    if cfg.trace_to:
        # Before the run writes its first file, so the ten kept folders are
        # the ten most recent runs and this one is one of them.
        sweep_traces()
    try:
        retry(cfg, limit=limit, on_step=held.step, trace=held.note)
    except Exception as error:
        problem = f"{type(error).__name__}: {error}"
        log.exception("the batch of %s links failed", limit)
    finally:
        held.finish(problem)
