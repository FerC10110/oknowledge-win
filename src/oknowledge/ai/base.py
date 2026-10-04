"""What the system asks a model, and how it distrusts the answer.

An engine knows exactly one thing: take a prompt, return text. Everything
else -- building the request, finding the JSON in the noise, validating and
normalizing it -- lives here, identical for all three engines.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from importlib.resources import files
from typing import Protocol

DEFAULT_LIMIT = 24_000
UNCATEGORIZED = "Sin clasificar"
LANGUAGE_NAMES = {"es": "español", "en": "inglés"}
STRICTER = (
    "\n\nTu respuesta anterior no era JSON válido. Respondé ONLY con el objeto "
    "JSON pedido: sin explicación, sin comentarios, sin ```."
)
REQUIRED = ("title", "summary", "points", "category", "tags")


class EngineError(Exception):
    """The engine could not answer: missing, crashed, out of quota."""


class AnalysisError(Exception):
    """The engine answered, but the answer is no use."""


class Engine(Protocol):
    name: str

    def complete(self, prompt: str) -> str: ...


@dataclass
class Analysis:
    title: str
    summary: str
    points: list[str]
    category: str
    tags: list[str]


def _deaccent(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def normalize_tags(tags) -> list[str]:
    out: list[str] = []
    for tag in tags or []:
        clean = re.sub(r"[^a-z0-9]+", "-", _deaccent(str(tag)).lower()).strip("-")
        if clean and clean not in out:
            out.append(clean)
    return out[:8]


def canonical_category(category: str, known) -> str:
    wanted = _deaccent(str(category or "")).strip().lower()
    if not wanted:
        return UNCATEGORIZED
    for existing in known or []:
        if _deaccent(existing).strip().lower() == wanted:
            return existing
    return str(category).strip()


def render_prompt(text: str, meta: dict, known, language: str, limit: int = DEFAULT_LIMIT) -> str:
    template = files("oknowledge").joinpath("prompts/analyze.txt").read_text(encoding="utf-8")
    listed = "\n".join(f"- {c}" for c in (known or [])) or "- (todavía no hay ninguna)"
    values = {
        "LANGUAGE": LANGUAGE_NAMES.get(language, language),
        "CATEGORIES": listed,
        "URL": meta.get("url") or "",
        "TITLE": meta.get("title") or "",
        "TEXT": text[:limit],
    }
    # One pass, so a placeholder-looking string inside the page text or title
    # is never substituted a second time.
    return re.sub(r"\{\{([A-Z]+)\}\}", lambda m: values.get(m.group(1), m.group(0)), template)


def extract_json(raw: str) -> dict:
    """The JSON object that is the answer, however it comes wrapped.

    Small models add a preamble, a ```json fence, or chatter afterwards, and
    that chatter can itself contain braces. So instead of slicing between the
    first "{" and the last "}", try to decode an object starting at each "{"
    in turn; the decoder knows where the object really ends, braces inside
    strings included.

    The reply can hold several objects, most often because the model echoed
    the schema example from the prompt before answering. An echo always comes
    before the real answer, so the last object carrying every required key
    wins. If none does, the first decodable object is returned and validation
    reports what is missing.
    """
    decoder = json.JSONDecoder()
    found: list[dict] = []
    position = raw.find("{")
    while position != -1:
        try:
            value, end = decoder.raw_decode(raw, position)
        except json.JSONDecodeError:
            position = raw.find("{", position + 1)
            continue
        if isinstance(value, dict):
            found.append(value)
        # Skip past the object so its nested objects are not candidates.
        position = raw.find("{", end)
    if not found:
        raise AnalysisError("the answer had no JSON object in it")
    complete = [d for d in found if all(k in d for k in REQUIRED)]
    return complete[-1] if complete else found[0]


def _text(data: dict, key: str) -> str:
    value = data[key]
    if not isinstance(value, str):
        raise AnalysisError(f"the answer has a non-text {key}")
    return value.strip()


def _items(data: dict, key: str) -> list:
    value = data[key]
    if not isinstance(value, list):
        raise AnalysisError(f"the answer has a non-list {key}")
    return value


def _to_analysis(data: dict, known, meta: dict | None = None) -> Analysis:
    missing = [k for k in REQUIRED if k not in data]
    if missing:
        raise AnalysisError(f"the answer is missing: {', '.join(missing)}")
    summary = _text(data, "summary")
    if not summary:
        raise AnalysisError("the answer has an empty summary")
    title = _text(data, "title") or ((meta or {}).get("title") or "").strip()
    points = [str(p).strip() for p in _items(data, "points") if str(p).strip()]
    return Analysis(
        title=title,
        summary=summary,
        points=points[:6],
        category=canonical_category(_text(data, "category"), known),
        tags=normalize_tags(_items(data, "tags")),
    )


def analyze(engine: Engine, text: str, meta: dict, known, language: str) -> Analysis:
    prompt = render_prompt(text, meta, known, language)
    for attempt in (prompt, prompt + STRICTER):
        try:
            return _to_analysis(extract_json(engine.complete(attempt)), known, meta)
        except AnalysisError as error:
            last = error
    raise AnalysisError(f"the engine never produced a usable answer: {last}")
