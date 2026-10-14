"""The little markdown an idea's sections are written in, drawn as HTML.

The text is escaped before anything else, so nothing in it -- a model's
answer, or a hand edit in Obsidian -- becomes markup by accident. Then
three things are drawn: [name](http(s) URL) as a link, **bold**, *italic*.
A link to anything that is not a web page stays text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from markupsafe import Markup, escape

_LINK = re.compile(r"\[((?:[^\]\\\n]|\\.)+)\]\((https?://[^\s()<>]+)\)")
_STRONG = re.compile(r"\*\*(.+?)\*\*")
_EM = re.compile(r"(?<![*\w])\*(?![\s*])([^*\n]+?)\*(?![*\w])")
_ITEM = re.compile(r"[-*+]\s+(.*)")


def _unescape(name: str) -> str:
    return re.sub(r"\\(.)", r"\1", name)


def inline(text: str) -> Markup:
    safe = str(escape(text))
    safe = _LINK.sub(
        lambda m: (f'<a href="{m.group(2)}" target="_blank" rel="noreferrer">'
                   f'{_unescape(m.group(1))}</a>'), safe)
    safe = _STRONG.sub(r"<strong>\1</strong>", safe)
    safe = _EM.sub(r"<em>\1</em>", safe)
    return Markup(safe)


_USED = re.compile(r"\*(?:Con|With) \d+ links?: .+\*")
_CARD = re.compile(r"(.+?)\s+[—–]\s+(.*)")
_BOLD = re.compile(r"\*\*(.+)\*\*")


@dataclass
class Section:
    """One action's section, the way the idea's screen draws it."""

    used: Markup | None = None
    lead: list[Markup] = field(default_factory=list)
    cards: list[tuple[Markup, Markup]] = field(default_factory=list)
    tail: list[Markup] = field(default_factory=list)


def section_cards(text: str) -> Section:
    """Every bullet a card -- its title, and the detail after its dash -- the
    "Con N links" line on its own, and the lines before and after the cards
    as paragraphs (spec §2). Escaped first, like everything here."""
    part = Section()
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        item = _ITEM.fullmatch(line)
        if item is None:
            if part.used is None and not part.lead and not part.cards and _USED.fullmatch(line):
                part.used = inline(line.strip("*"))
            elif part.cards:
                part.tail.append(inline(line))
            else:
                part.lead.append(inline(line))
            continue
        pair = _CARD.fullmatch(item.group(1))
        title, detail = (pair.group(1), pair.group(2)) if pair else (item.group(1), "")
        bold = _BOLD.fullmatch(title)
        part.cards.append((inline(bold.group(1) if bold else title), inline(detail)))
    return part
