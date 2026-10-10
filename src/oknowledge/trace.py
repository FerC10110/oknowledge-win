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

import datetime as dt
import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .i18n import translator
from .places import state_dir


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


CAP = 256 * 1024
"""The most one trace file may weigh. A batch of fifty links writes fifty
files, so the cap is what keeps a debugging session from being a disk
problem."""
REPLY_CAP = 64 * 1024
PARSED_CAP = 8 * 1024
"""The reply is the model's and the model is not ours to trust; the parsed
result is ours and is short. What is left of the cap after those two is the
prompt's, which is the one the page makes big."""
_MARKER_ROOM = 160
"""Bytes held back in a cut body for the line that says it was cut."""

_ID = re.compile(r"[A-Za-z0-9_-]+")


def trace_run(when: dt.datetime | None = None) -> str:
    """The name of the folder one run writes into.

    Seconds and dashes: it sorts as text, which is what `sweep_traces()`
    leans on, and it is a legal folder name everywhere.
    """
    moment = when or dt.datetime.now(dt.timezone.utc)
    return moment.strftime("%Y-%m-%dT%H-%M-%S")


def _clean(text: str) -> str:
    """Text that is certainly encodable, surrogates and all.

    A page's bytes are not always text. The WhatsApp importer replaces what
    it cannot decode rather than refusing the file, and a trace of a page
    that cannot be written is worth less than a trace with a `?` in it.
    """
    return text.encode("utf-8", "replace").decode("utf-8")


def _fenced(body: str) -> str:
    """`body` in a code block whose fence is longer than anything inside it.

    A page about Markdown has fences in it, and a fence that ends early turns
    the rest of the trace into prose.
    """
    longest = max((len(run) for run in re.findall(r"`+", body)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}text\n{body}\n{fence}"


def _middle(text: str, limit: int, t) -> str:
    """`text` within `limit` bytes, cut from the middle if it has to be.

    The head and the tail are what gets looked at -- how the prompt starts
    and how it ends -- so the hole goes between them, and it says how big it
    is: everything that was there is either in the file or in that count.
    """
    raw = text.encode("utf-8")
    if len(raw) <= limit:
        return text
    room = max(0, limit - _MARKER_ROOM)
    head = raw[: room // 2].decode("utf-8", "ignore")
    tail = raw[len(raw) - (room - room // 2):].decode("utf-8", "ignore")
    cut = len(text) - len(head) - len(tail)
    return f"{head}\n\n[... {t('(%1 characters cut from the middle)', cut)} ...]\n\n{tail}"


def write_trace(base: Path | str | None = None, link: str = "", *,
                url: str = "", engine: str = "", model: str = "",
                prompt: str = "", reply: str = "", parsed: str = "",
                run: str = "", attempt: int = 0,
                language: str = "en") -> Path | None:
    """Write one link's prompt and reply, and return the path, or None.

    `attempt` numbers the file when there is more than one for a link, which
    is the interesting case: a link that falls through a chain of two, each
    getting a second stricter try, is four prompts and four replies. It
    numbers the file and not the link -- the link's id is what the vault, the
    queue and the library all call this page, and it has to stay the same
    word everywhere.

    None is every way this can fail: a folder that will not be created, a
    disk that is full, a link id that is not one. A trace is a convenience
    and the run is worth more than it, so nothing here raises.

    Outside the vault on purpose -- these are throwaway, and have no business
    syncing to Obsidian or turning up in a search.
    """
    if not _ID.fullmatch(link or ""):
        return None
    t = translator(language)
    root = Path(base) if base else state_dir()
    folder = root / "trace" / (run or trace_run())
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None

    named = " · ".join(part for part in (engine, model) if part)
    head = "\n".join([
        f"# {_clean(url) or link}",
        "",
        f"- {t('Engine')}: {_clean(named) or '-'}",
        f"- {t('Link')}: {link}",
        f"- {t('Saved')}: {dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')}",
        "",
    ])
    reply_block = _middle(_clean(reply), REPLY_CAP, t)
    parsed_block = _middle(_clean(parsed), PARSED_CAP, t)
    budget = CAP - len(head.encode()) - len(reply_block.encode()) - len(parsed_block.encode()) - 512
    prompt_block = _middle(_clean(prompt), max(0, budget), t)

    text = head + "\n".join([
        f"## {t('Prompt')}", "", _fenced(prompt_block), "",
        f"## {t('Reply')}", "", _fenced(reply_block), "",
        f"## {t('Parsed')}", "", _fenced(parsed_block), "",
    ])
    target = folder / (f"{link}-{attempt:02d}.md" if attempt else f"{link}.md")
    try:
        target.write_text(text, encoding="utf-8")
    except OSError:
        return None
    return target


def sweep_traces(base: Path | str | None = None, keep: int = 10) -> None:
    """Leave the last `keep` runs and drop the rest. Never raises.

    Housekeeping, in the shape the queue's own sweep has: a folder that will
    not be removed is a folder that stays, and the run goes on.
    """
    root = (Path(base) if base else state_dir()) / "trace"
    try:
        runs = sorted(p for p in root.iterdir() if p.is_dir())
    except OSError:
        return
    for stale in runs[: max(0, len(runs) - keep)]:
        try:
            shutil.rmtree(stale)
        except OSError:
            pass
