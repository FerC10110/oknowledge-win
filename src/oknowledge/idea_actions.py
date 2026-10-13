"""The four things that can be asked about an idea.

Each one renders its prompt, takes the model's JSON and writes one markdown
section for the idea's note. The model never writes markdown into the note
itself: whatever it says passes through a parser here, which keeps what is
usable and drops the rest -- a URL that is not a web page, an id that was
not offered, a placeholder copied from the prompt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path

from . import ai
from .ai.base import LANGUAGE_NAMES, AnalysisError, _is_placeholder, extract_json
from .config import Config
from .model import Note
from .vault import ACTIONS, all_entries

MAX_MATCHES = 8
MAX_IMPROVEMENTS = 8
MAX_EXPANSIONS = 10
MAX_SUGGESTIONS = 10
MAX_CANDIDATES = 60
SUMMARY_CHARS = 200

VERDICTS = {
    "es": {"exists": "Ya existe.", "similar": "Hay parecidas.",
           "new": "No encontré nada igual."},
    "en": {"exists": "It already exists.", "similar": "There are similar ones.",
           "new": "I found nothing like it."},
}
WORDS = {
    "es": {"searched": "Buscado el {day} con {who}.", "yours": "Lo tuyo:",
           "among": "Entre", "all": "tu biblioteca",
           "none": "Ninguno de estos links le sirve a la idea.",
           "empty": "No hay links en {scope} que no estén ya relacionados."},
    "en": {"searched": "Searched on {day} with {who}.", "yours": "Yours:",
           "among": "Among", "all": "your library",
           "none": "None of these links helps this idea.",
           "empty": "There are no links in {scope} that are not already linked."},
}

_WEB_URL = re.compile(r"https?://[^\s()<>\[\]]+")
_WORD = re.compile(r"\w{4,}")


def _words(language: str) -> dict[str, str]:
    return WORDS.get(language, WORDS["en"])


def _line(value) -> str:
    """One line of model text, or "" for anything that is not usable text."""
    if not isinstance(value, str) or _is_placeholder(value):
        return ""
    return " ".join(value.split())


def _escape(name: str) -> str:
    return name.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def render_action_prompt(action: str, note: Note, language: str,
                         candidates: str = "") -> str:
    """The prompt for one action on one idea."""
    template = files("oknowledge").joinpath(
        f"prompts/idea-{action}.txt").read_text(encoding="utf-8")
    values = {
        "LANGUAGE": LANGUAGE_NAMES.get(language, language),
        "TITLE": note.title,
        "TEXT": note.my_note.strip(),
        "TAGS": ", ".join(note.tags),
        "SUMMARY": note.summary.strip(),
        "CANDIDATES": candidates,
    }
    # One pass, like render_idea_prompt: a text that looks like a
    # placeholder is never substituted a second time.
    return re.sub(r"\{\{([A-Z]+)\}\}",
                  lambda m: values.get(m.group(1), m.group(0)), template)


# --- already out there ----------------------------------------------------------

@dataclass
class Found:
    verdict: str
    matches: list[tuple[str, str, str]] = field(default_factory=list)
    difference: str = ""


def exists_found(data: dict) -> Found:
    """What of a search answer is kept, or AnalysisError if none of it is."""
    if "verdict" not in data and "matches" not in data:
        raise AnalysisError("the answer is missing: verdict")
    verdict = data.get("verdict")
    if verdict not in VERDICTS["en"]:
        verdict = "similar"
    rows = []
    listed = data.get("matches")
    for item in listed if isinstance(listed, list) else []:
        if not isinstance(item, dict):
            continue
        name, url = _line(item.get("name")), item.get("url")
        if not name or not isinstance(url, str) or not _WEB_URL.fullmatch(url.strip()):
            continue
        rows.append((name, url.strip(), _line(item.get("note"))))
        if len(rows) == MAX_MATCHES:
            break
    return Found(verdict=verdict, matches=rows, difference=_line(data.get("difference")))


def exists_section(found: Found, language: str, day: str, who: str) -> str:
    words = _words(language)
    head = (f"**{VERDICTS.get(language, VERDICTS['en'])[found.verdict]}** "
            + words["searched"].format(day=day, who=who))
    lines = [head]
    if found.matches:
        lines.append("")
        lines += [f"- [{_escape(name)}]({url})" + (f" — {note}" if note else "")
                  for name, url, note in found.matches]
    if found.difference:
        lines += ["", f"**{words['yours']}** {found.difference}"]
    return "\n".join(lines)


# --- improve and expand ---------------------------------------------------------

def _listed(data: dict) -> list:
    items = data.get("items")
    if not isinstance(items, list):
        raise AnalysisError("the answer has no list of items")
    return items


def improve_section(data: dict) -> str:
    rows = []
    for item in _listed(data):
        if not isinstance(item, dict):
            continue
        weak, fix = _line(item.get("weak")), _line(item.get("fix"))
        if fix:
            rows.append(f"- **{weak}** — {fix}" if weak else f"- {fix}")
    if not rows:
        raise AnalysisError("the answer had no improvement in it")
    return "\n".join(rows[:MAX_IMPROVEMENTS])


def expand_section(data: dict) -> str:
    rows = [f"- {text}" for text in map(_line, _listed(data)) if text]
    if not rows:
        raise AnalysisError("the answer had nothing to add")
    return "\n".join(rows[:MAX_EXPANSIONS])


# --- links that may help --------------------------------------------------------

def _bag(text: str) -> set[str]:
    return {word.lower() for word in _WORD.findall(text)}


def candidates(note: Note, entries: list[tuple[Path, Note]],
               category: str) -> list[tuple[Path, Note]]:
    """The links offered to the model: in the category (any, if none), not
    already linked to the idea, most words in common with it first, newest
    first among equals."""
    mine = _bag(" ".join([note.title, note.my_note, " ".join(note.tags)]))
    pool = [(path, link) for path, link in reversed(entries)
            if (not category or link.category == category)
            and path.stem not in note.related]

    def shared(pair):
        link = pair[1]
        return len(mine & _bag(" ".join([link.title, link.summary, " ".join(link.tags)])))

    return sorted(pool, key=shared, reverse=True)[:MAX_CANDIDATES]


def candidate_lines(pool: list[tuple[Path, Note]]) -> str:
    return "\n".join(
        " | ".join([link.id, " ".join(link.title.split()), link.category,
                    " ".join(link.summary.split())[:SUMMARY_CHARS]])
        for _, link in pool)


def links_section(data: dict, allowed: dict[str, str], scope: str,
                  language: str) -> str:
    """The suggestions, by file name, of the ids that were offered."""
    listed = data.get("links")
    if not isinstance(listed, list):
        raise AnalysisError("the answer has no list of links")
    words = _words(language)
    rows, seen = [], set()
    for item in listed:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            continue
        stem = allowed.get(item["id"].strip())
        if stem is None or stem in seen:
            continue
        seen.add(stem)
        why = _line(item.get("why"))
        rows.append(f"- [[{stem}]]" + (f" — {why}" if why else ""))
        if len(rows) == MAX_SUGGESTIONS:
            break
    body = "\n".join(rows) if rows else words["none"]
    return f"*{words['among']}: {scope}.*\n\n{body}"


def no_candidates(scope: str, language: str) -> str:
    words = _words(language)
    return f"*{words['among']}: {scope}.*\n\n" + words["empty"].format(scope=scope)


# --- one action, start to end ----------------------------------------------------

def compose(cfg: Config, note: Note, action: str, category: str,
            day: str) -> tuple[str, str, str]:
    """The section `action` writes for this idea: (markdown, engine, model).

    Raises ai.AllEnginesFailed when no engine gave a usable answer. Engine
    and model are empty when nobody had to be asked.
    """
    if action not in ACTIONS:
        raise ValueError(f"no such action: {action!r}")
    language = cfg.language
    if action == "links":
        scope = category or _words(language)["all"]
        pool = candidates(note, all_entries(cfg, cfg.links), category)
        if not pool:
            return no_candidates(scope, language), "", ""
        allowed = {link.id: path.stem for path, link in pool}
        prompt = render_action_prompt("links", note, language, candidate_lines(pool))
        return ai.ask_with_chain(cfg, prompt, lambda reply: links_section(
            extract_json(reply), allowed, scope, language))
    prompt = render_action_prompt(action, note, language)
    if action == "exists":
        found, engine, model = ai.search_with_chain(
            cfg, prompt, lambda reply: exists_found(extract_json(reply)))
        return exists_section(found, language, day, model or engine), engine, model
    parse = improve_section if action == "improve" else expand_section
    return ai.ask_with_chain(cfg, prompt, lambda reply: parse(extract_json(reply)))
