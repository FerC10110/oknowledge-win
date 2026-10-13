"""The little markdown an idea's sections are written in, drawn as HTML.

The text is escaped before anything else, so nothing in it -- a model's
answer, or a hand edit in Obsidian -- becomes markup by accident. Then
three things are drawn: [name](http(s) URL) as a link, **bold**, *italic*.
A link to anything that is not a web page stays text.
"""

from __future__ import annotations

import re

from markupsafe import Markup, escape

from ..vault import normalize_related

_LINK = re.compile(r"\[((?:[^\]\\\n]|\\.)+)\]\((https?://[^\s()<>]+)\)")
_STRONG = re.compile(r"\*\*(.+?)\*\*")
_EM = re.compile(r"(?<![*\w])\*(?![\s*])([^*\n]+?)\*(?![*\w])")
_ITEM = re.compile(r"[-*+]\s+(.*)")
_SUGGESTION = re.compile(r"\s*[-*+]\s+\[\[([^\]\n]+)\]\]\s*(?:[—–-]\s*)?(.*)")


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


def blocks(text: str) -> list[tuple[str, object]]:
    """("p", line) and ("ul", [items]), consecutive bullets in one list."""
    drawn: list[tuple[str, object]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        item = _ITEM.fullmatch(line)
        if item and drawn and drawn[-1][0] == "ul":
            drawn[-1][1].append(inline(item.group(1)))
        elif item:
            drawn.append(("ul", [inline(item.group(1))]))
        else:
            drawn.append(("p", inline(line)))
    return drawn


def split_suggestions(text: str) -> tuple[str, list[tuple[str, str]]]:
    """(the section without its suggestion rows, the rows as (stem, why))."""
    rest, rows = [], []
    for line in text.splitlines():
        match = _SUGGESTION.fullmatch(line)
        stem = normalize_related([f"[[{match.group(1)}]]"]) if match else []
        if stem:
            rows.append((stem[0], match.group(2).strip()))
        else:
            rest.append(line)
    return "\n".join(rest).strip(), rows
