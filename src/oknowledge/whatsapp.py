"""Parse a WhatsApp chat export.

Pure: text in, lists out. Does not know about the vault, queue, or network,
so it can be tested with a plain string without any setup.

Two layers. This one converts the file into messages; the next one decides
which part of a message is a link. They are separate because they fail for
different reasons: the line format is a WhatsApp matter, and what counts
as a link is a matter of how the user writes.
"""

import datetime as dt
import re
from dataclasses import dataclass

# What WhatsApp puts into an export that you don't see when you open it:
# directional marks and spaces that are not regular spaces. Without removing
# them, the regex below matches zero lines from the real file.
# What WhatsApp puts into an export that you don't see when you open it:
# directional marks and spaces that are not regular spaces. Without removing
# them, the regex below matches zero lines from the real file.
INVISIBLE = str.maketrans({
    "\u200e": "", "\u200f": "", "\u202a": "", "\u202b": "", "\u202c": "",
    "\ufeff": "", "\u00a0": " ", "\u202f": " ", "\u2009": " ",
})

LINE = re.compile(
    r"^(\d{1,2})/(\d{1,2})/(\d{2,4}),\s+(\d{1,2}):(\d{2})(?::(\d{2}))?\s+-\s+(.*)$"
)

WANTED = "D/M/YYYY, HH:MM - Remitente: mensaje"


class BadExport(Exception):
    """The file is not a readable WhatsApp export."""


@dataclass
class Message:
    sent: str        # YYYY-MM-DD
    sender: str      # "" for a system message
    text: str


def _clean(text: str) -> list[str]:
    return text.translate(INVISIBLE).replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _order(stamps: list[tuple[int, int]], raw: list[str]) -> tuple[bool, bool]:
    """(day-first, was_assumed). Evidence before convention."""
    day_first = [i for i, (a, _) in enumerate(stamps) if a > 12]
    month_first = [i for i, (_, b) in enumerate(stamps) if b > 12]
    if day_first and month_first:
        raise BadExport(
            f"the dates contradict each other: {raw[day_first[0]]!r} reads as "
            f"day/month and {raw[month_first[0]]!r} reads as month/day"
        )
    if day_first:
        return True, False
    if month_first:
        return False, False
    return True, True        # no evidence: assume day-first and report it


def messages(text: str) -> tuple[list[Message], bool, bool]:
    """(messages, day-first, was_assumed).

    A line without the format is a continuation of the previous message,
    so a multiline message is not split. A line with the format but an
    impossible date is skipped: a bad line does not bring down the file,
    which is the "never lose a link" rule applied to the parser.
    """
    lines = _clean(text)
    starts = [n for n, line in enumerate(lines) if LINE.match(line) is not None]
    if not starts:
        first = next((line for line in lines if line.strip()), "")
        raise BadExport(
            f"no line looks like a WhatsApp export; expected {WANTED!r}, "
            f"and the file starts with {first!r}"
        )

    stamps: list[tuple[int, int]] = []
    bodies: list[tuple[re.Match, str]] = []
    for n, start in enumerate(starts):
        found = LINE.match(lines[start])
        assert found is not None          # starts only contains lines that match
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        tail = lines[start + 1:end]
        while tail and not tail[-1].strip():
            tail.pop()                    # trailing newline at end of file
        stamps.append((int(found.group(1)), int(found.group(2))))
        bodies.append((found, "\n".join([found.group(7), *tail])))

    day_first, assumed = _order(stamps, [lines[n] for n in starts])

    out: list[Message] = []
    for (found, body), (first, second) in zip(bodies, stamps):
        day, month = (first, second) if day_first else (second, first)
        year = int(found.group(3))
        year += 2000 if year < 100 else 0
        try:
            sent = dt.date(year, month, day).isoformat()
        except ValueError:
            continue                      # 31/2: a bad line, not a bad file
        sender, _, rest = body.partition(": ")
        if not rest and ": " not in body:
            sender, rest = "", body       # a system message has no sender
        out.append(Message(sent=sent, sender=sender, text=rest))
    return out, day_first, assumed
