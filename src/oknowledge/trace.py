"""What the pipeline is doing while it takes its time.

The pipeline knows a great deal it never says: which page it is reading,
which engine just refused, how long each of them took. This module is the
shape of that telling -- one flat step, and a wrapper with a single promise.

The promise is the point. A tracer is new code in the critical path of a run
whose rule is that a link never dies for something that is not the link, so
every call goes through `guarded()` and anything it raises stops there. A
caller with nothing to tell gets `SILENT`, and then not tracing costs one
comparison.

There is no `logging` here on purpose: the tracer is a callback the caller
hands in, which is what makes it something a test can watch.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Step:
    """One thing the pipeline started or finished, for one link.

    Frozen because it is handed out and kept: the page holds the last two
    hundred and reads them again on every refresh. Nothing may change under
    it after the fact.
    """

    link: str
    """The link's id, which is how a reader groups the steps of one link."""
    name: str
    """`find` | `extract` | `analyze` | `cover` | `save`."""
    state: str
    """`start` | `ok` | `fail`."""
    seconds: float
    """How long the step took; 0.0 on a `start`. Measured on the monotonic
    clock, so a time adjustment in the middle of a long batch cannot make a
    step last a negative while."""
    engine: str = ""
    """Only on an `analyze` step: which engine this turn of the chain tried."""
    detail: str = ""
    """One line, for a person: a size, a page type, the reason it failed."""


Tracer = Callable[[Step], None]


def SILENT(step: Step) -> None:   # noqa: N802 - a constant that happens to be callable
    """The tracer of a caller who does not want one."""
    return None


def guarded(tracer: Tracer | None) -> Tracer:
    """`tracer`, wrapped so that whatever it raises never reaches the caller.

    With `None` there is nothing to wrap and nothing to pay: `SILENT` is
    returned as it is, which is also how a caller can tell that nobody is
    watching without calling anything.
    """
    if tracer is None:
        return SILENT

    def safe(step: Step) -> None:
        try:
            tracer(step)
        except Exception:
            # Exception and not BaseException: a tracer that raises is a bug
            # worth surviving, but a Ctrl-C is the user talking and must get
            # through, or a batch of a thousand links cannot be stopped.
            pass

    return safe
