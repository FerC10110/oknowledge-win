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
INVISIBLE = str.maketrans({
    "\u200e": "", "\u200f": "", "\u202a": "", "\u202b": "", "\u202c": "",
    "\ufeff": "", "\u00a0": " ", "\u202f": " ", "\u2009": " ",
})

LINE = re.compile(
    r"^(\d{1,2})/(\d{1,2})/(\d{2,4}),\s+(\d{1,2}):(\d{2})(?::(\d{2}))?\s+-\s+(.*)$"
)

WANTED = "D/M/YYYY, HH:MM - Sender: message"

# WhatsApp's own profile names stop at 25 characters, and a number with no
# saved contact arrives as "+54 9 11 5555-5555". Past that, with a space in
# it, what sits before the colon is text and not a name.
SENDER_MAX = 25

# How many of the contradicting lines the error quotes, per side.
NAMED = 3


class BadExport(Exception):
    """The file is not a readable WhatsApp export."""


@dataclass
class Message:
    sent: str        # YYYY-MM-DD
    sender: str      # "" for a system message
    text: str


def _is_sender(name: str) -> bool:
    """Could what sits before the first ": " be the name the export put there?

    It matters because that part is dropped from the message. On a line whose
    own text holds the first ": " -- `Fer cambió el asunto a "Links: <url>"`
    -- the drop takes the user's words with it, and a link inside the dropped
    part vanishes with no trace: it is not scanned for links, and it is not
    offered as suspicious either, which the never-lose-a-link rule does not
    allow. A name cannot be long and have a space in it, so that shape is read
    as a line with no sender at all and the whole text is kept as the message.
    """
    if "/" in name:
        return False                      # a link, not a name: keep it in the text
    return len(name) <= SENDER_MAX or not any(ch.isspace() for ch in name)


def _clean(text: str) -> list[str]:
    return text.translate(INVISIBLE).replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _side(order: str, where: list[int], raw: list[str]) -> str:
    """One side of the contradiction: how many lines read that way, and which.

    Every line is counted and the first few are quoted. A file can hold
    thousands on one side, and a wall of them would bury the handful on the
    other -- which are the lines the user has to go and edit.
    """
    shown = ", ".join(repr(raw[n]) for n in where[:NAMED])
    more = f" and {len(where) - NAMED} more" if len(where) > NAMED else ""
    reads = "line reads" if len(where) == 1 else "lines read"
    return f"{len(where)} {reads} as {order}: {shown}{more}"


def _order(stamps: list[tuple[int, int]], raw: list[str]) -> tuple[bool, bool]:
    """(day-first, was_assumed). Evidence before convention.

    A line whose two fields are both over 12 is evidence of nothing: neither
    reading of it is a date, so messages() skips it as a bad line. Counting it
    on both sides is what used to name one line as contradicting itself.
    """
    day_first = [n for n, (a, b) in enumerate(stamps) if a > 12 and b <= 12]
    month_first = [n for n, (a, b) in enumerate(stamps) if b > 12 and a <= 12]
    if day_first and month_first:
        # Every contradicting line, not the first pair: one stray pasted
        # fragment vetoes all 1215 links, --dry-run is no escape because this
        # runs first, and a pair at a time costs one import, one edit and one
        # re-run per line.
        one = _side("day/month", day_first, raw)
        other = _side("month/day", month_first, raw)
        raise BadExport(
            "the dates contradict each other, so the file cannot be read "
            f"either way. {one}. {other}. Edit the lines that disagree and "
            "import the file again"
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
        sender, mark, rest = body.partition(": ")
        if not mark or not _is_sender(sender):
            sender, rest = "", body       # a system message has no sender
        out.append(Message(sent=sent, sender=sender, text=rest))
    return out, day_first, assumed


# The TLDs this file can find. Curated, not exhaustive: a full list lets in
# thousands of three-letter suffixes that turn any word with a dot into a
# link. Tune it by looking at the --dry-run output.
TLDS = frozenset("""
com org net io dev app me tv co info biz xyz online site tech blog news edu
gov mil ar es mx cl uy pe br us uk de fr it nl pt ru jp cn in au ca ch se no
fi dk pl cz gr tr il za kr be at ie nz eu gg to ly am st fm cc tk link page
cloud space live work wiki art design studio club shop store garden fun
""".split())

# Real TLDs that are also file extensions this user types. With no path the
# extension wins; with a path the domain wins. `zip` and `mov` are here
# because Google sold them as TLDs and the collision is worse than the others.
EXTENSIONS = frozenset("sh py md ts js rs go pl so rb cs ai zip mov".split())

FULL = re.compile(r"https?://(?:(?![,;]https?://)[^\s<>\"])+", re.IGNORECASE)
# Not preceded by @ (an email), nor by another domain character (so a host is
# not cut in half), nor by a percent sign, nor followed by one of those (an
# email's dotted local part, or a TLD that is only the start of a longer
# label). The path is optional.
#
# The percent sign is there for the percent-encoded urls the real export
# carries: `https%3A%2F%2Fudemycoupons.me` would otherwise be captured as
# `2Fudemycoupons.me`, a domain that does not exist -- a link the user did
# send, saved pointing somewhere else. Decoding the escapes instead would be
# worse: the same file has a magnet link whose tracker list is three more of
# these, where the right answer is to capture nothing, and real urls that
# carry percent-encoding on purpose. Captured wrong is silent; not captured
# is reported, because MAYBE still matches the message.
BARE = re.compile(
    r"(?<![\w@.%-])((?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+([a-z]{2,24}))(?![\w@-])"
    # A port, and only digits count as one: the lookahead above allows the
    # colon, so without this `foo.com:80/x` was captured as `foo.com` and the
    # real target was recorded nowhere. Digits only, so a colon ending a
    # sentence and the `file:line` of a traceback gain nothing.
    r"(:\d{1,5})?"
    r"(/[^\s<>\"]*)?",
    re.IGNORECASE,
)
# A dot between letters: a message like that may have had a link that did
# not match.
MAYBE = re.compile(r"[a-z0-9]\.[a-z]{2,}", re.IGNORECASE)

TRAILING = ".,;:!?'\"”’»)]}>"


def _trim(url: str) -> str:
    """Strip punctuation stuck to the end without breaking a link that uses it.

    A `)` goes only if it does not close a `(` of the link itself: Wikipedia
    writes `/wiki/Python_(lenguaje)` and that parenthesis is part of the URL.
    """
    while url and url[-1] in TRAILING:
        if url[-1] == ")" and url.count("(") > url.count(")") - 1:
            break
        url = url[:-1]
    return url


def _has_host(url: str) -> bool:
    """Is there anything left after the scheme?

    `https://.` loses its dot to _trim() and leaves `https://`, which is
    truthy: it was captured, and normalize() made it `https:///` -- a note
    pointing at nothing. A scheme followed straight by `/`, `?` or `#` has no
    host either: `https://?x`, `https://#`.
    """
    rest = url.partition("://")[2]
    return bool(rest) and rest[0] not in "/?#"


def _spans(text: str) -> list[tuple[int, int, str, bool]]:
    """Every link as (start, end, url with a scheme, came bare), in order.

    The span covers the link exactly as written. parse() needs that to cut
    the links out of the comment: cutting by string corrupts a message
    holding two links where one is a prefix of the other.
    """
    out: list[tuple[int, int, str, bool]] = []
    taken: list[tuple[int, int]] = []

    for found in FULL.finditer(text):
        url = _trim(found.group(0))
        if _has_host(url):
            out.append((found.start(), found.start() + len(url), url, False))
            taken.append((found.start(), found.start() + len(url)))

    for found in BARE.finditer(text):
        start = found.start()
        if any(a <= start < b for a, b in taken):
            continue                      # already part of a full URL
        tld = found.group(2).lower()
        if tld not in TLDS and tld not in EXTENSIONS:
            continue
        port, path = found.group(3) or "", found.group(4) or ""
        if tld in EXTENSIONS and not path:
            continue                      # script.py wins as an extension, and
                                          # so does the script.py:42 of a trace
        url = _trim(found.group(1) + port + path)
        if url:
            out.append((start, start + len(url), f"https://{url}", True))

    out.sort(key=lambda row: row[0])
    return out


def find_links(text: str) -> list[tuple[str, bool]]:
    """[(url with a scheme, came without one)], in the order they appear."""
    return [(url, bare) for _, _, url, bare in _spans(text)]


@dataclass
class Imported:
    url: str          # with scheme, ready for normalize()
    sent: str         # YYYY-MM-DD
    comment: str      # the message without the links, or ""
    sender: str
    raw: str          # the link as it was written
    bare: bool


@dataclass
class Scan:
    links: list[Imported]
    suspicious: list[str]
    messages: int
    day_first: bool
    assumed: bool


def parse(text: str) -> Scan:
    """A whole export to dated links. Raises BadExport if it can't be read."""
    found, day_first, assumed = messages(text)
    links: list[Imported] = []
    suspicious: list[str] = []
    for message in found:
        spans = _spans(message.text)
        if not spans:
            if MAYBE.search(message.text):
                suspicious.append(message.text)
            continue
        kept, last = [], 0
        for start, end, _, _ in spans:
            kept.append(message.text[last:start])
            last = end
        kept.append(message.text[last:])
        comment = " ".join("".join(kept).split())
        for start, end, url, bare in spans:
            links.append(Imported(url=url, sent=message.sent, comment=comment,
                                  sender=message.sender,
                                  raw=message.text[start:end], bare=bare))
    return Scan(links=links, suspicious=suspicious, messages=len(found),
                day_first=day_first, assumed=assumed)
