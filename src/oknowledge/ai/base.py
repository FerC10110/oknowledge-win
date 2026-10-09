"""What the system asks a model, and how it distrusts the answer.

An engine knows exactly one thing: take a prompt, return text. Everything
else -- building the request, finding the JSON in the noise, validating and
normalizing it -- lives here, identical for all three engines.
"""

from __future__ import annotations

import dataclasses
import json
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib.resources import files
from typing import Protocol
from urllib.parse import urlsplit

from ..model import Mention
from ..urls import is_search_url, search_url

DEFAULT_LIMIT = 24_000
MAX_KNOWN_CATEGORIES = 60
MAX_CATEGORY_LENGTH = 80
MAX_TAG_LENGTH = 40
MAX_TAGS = 8
MAX_POINTS = 6
MAX_MENTIONS = 30
MAX_MENTION_NAME = 80
LANGUAGE_NAMES = {"es": "español", "en": "inglés"}
# Same mechanism as the index boilerplate in vault.py: by content language,
# English for anything that is not Spanish.
UNCATEGORIZED = {"es": "Sin clasificar", "en": "Unclassified"}
TRUNCATION_MARKER = "[... el contenido sigue, pero se cortó acá ...]"
RETRY_SUFFIX = {
    "es": (
        "\n\nTu respuesta anterior no sirvió ({reason}). Respondé sólo con el "
        "objeto JSON pedido: sin explicación, sin comentarios, sin ```."
    ),
    "en": (
        "\n\nYour previous answer was unusable ({reason}). Answer only with the "
        "requested JSON object: no explanation, no comments, no ```."
    ),
}
REQUIRED = ("title", "summary", "points", "category", "tags")
# Tags whose symbols would otherwise be folded away and merge "c++" with "c".
SYMBOL_TAGS = (
    (re.compile(r"(?<!\w)c\+\+"), "cpp"),
    (re.compile(r"(?<!\w)c#"), "csharp"),
    (re.compile(r"(?<!\w)f#"), "fsharp"),
    (re.compile(r"(?<![\w.])\.net(?!\w)"), "dotnet"),
)


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
    mentions: list[Mention] = field(default_factory=list)


def _NOTHING(prompt: str, reply: str, parsed: str) -> None:
    """The recorder of a caller who wants no trace."""


def _as_text(analysis: Analysis) -> str:
    """The parsed analysis, for a person reading a trace beside the raw reply.

    JSON because that is what the reply is, so the two read side by side and
    the difference between them is the question being asked.
    """
    try:
        return json.dumps(dataclasses.asdict(analysis), ensure_ascii=False, indent=2)
    except (TypeError, ValueError):
        return repr(analysis)


def retry_suffix(language: str, reason: str) -> str:
    """The stricter request appended on the second attempt, naming what failed."""
    return RETRY_SUFFIX.get(language, RETRY_SUFFIX["en"]).format(reason=reason)


def _fold(text: str) -> str:
    """Case-fold and drop accents from Latin letters, leaving other scripts intact.

    Marks are only stripped where the base is ASCII: stripping them blindly
    would turn Japanese が into か and mangle Hangul.
    """
    out = []
    for char in unicodedata.normalize("NFC", text):
        decomposed = unicodedata.normalize("NFKD", char)
        if decomposed.isascii():
            out.append(decomposed)
        elif decomposed[0].isascii():
            out.append("".join(c for c in decomposed if not unicodedata.combining(c)))
        else:
            out.append(char)
    return "".join(out).casefold()


def _is_placeholder(text: str) -> bool:
    """A value still wrapped in <...>: the model echoed the schema example."""
    text = text.strip()
    return len(text) >= 2 and text.startswith("<") and text.endswith(">")


def normalize_tags(tags) -> list[str]:
    out: list[str] = []
    for tag in tags or []:
        if not isinstance(tag, str) or _is_placeholder(tag):
            continue
        clean = _fold(tag)
        for pattern, replacement in SYMBOL_TAGS:
            clean = pattern.sub(replacement, clean)
        clean = re.sub(r"[\W_]+", "-", clean).strip("-")[:MAX_TAG_LENGTH].strip("-")
        if clean and clean not in out:
            out.append(clean)
    return out[:MAX_TAGS]


MAX_COLLECTIONS = 16
"""A note in sixteen projects at once is not being classified any more, and a
frontmatter that grows without end is a note that one day cannot be read."""


UNSAFE_IN_A_NAME = '\\/:*?"<>|'
"""The characters an index file name cannot hold.

vault._index_name() replaces them and vault.clean_category() refuses a name
that still has any, so a category the model invents has to be free of them
too -- otherwise the product generates categories the product then refuses to
let the user edit. One list, read from both sides.
"""


def _clean_category(category: str) -> str:
    """Whatever the model wrote, as a name both the vault and the web accept.

    Control characters and the characters a file name cannot hold become
    spaces, whitespace collapses, and dots and spaces go from both ends: ".."
    and "../x" must not survive as a category, and a trailing dot ("Misc.")
    would be stored happily and then refused on the round-trip.
    """
    spaced = "".join(
        " " if char in UNSAFE_IN_A_NAME or unicodedata.category(char).startswith("C")
        else char
        for char in category
    )
    # The cut can expose a new trailing dot or space, so the last strip is
    # after it, not before.
    return " ".join(spaced.split()).strip(". ")[:MAX_CATEGORY_LENGTH].strip(". ")


def normalize_collections(names, known=()) -> list[str]:
    """The user's collections, cleaned but still in their own words.

    Unlike a tag, nobody but the user ever reads one of these, and nobody but
    the user ever writes one: "Casa nueva" stays "Casa nueva" instead of
    becoming `casa-nueva`. It is cleaned the way a category is -- the
    characters a file name cannot hold become spaces, whitespace collapses --
    so a collection can earn its own index file later without migrating
    anything.

    `known` is every collection the library already has. A name that folds to
    one of them comes back spelled the way it is already spelled: someone who
    types "casa" meant the "Casa" they made last week, and two chips for one
    thing is the disorder this feature exists to undo.
    """
    canonical = {_fold(_clean_category(str(name))): str(name) for name in known or []}
    out: dict[str, str] = {}
    for name in names or []:
        if not isinstance(name, str):
            continue
        clean = _clean_category(name)
        if not clean:
            continue
        folded = _fold(clean)
        out.setdefault(folded, canonical.get(folded, clean))
    return list(out.values())[:MAX_COLLECTIONS]


def _first_segment(category: str) -> str:
    """Asked for one category, a model sometimes lists several: keep the first."""
    for part in re.split(r"[,;]", category):
        if part.strip():
            return part.strip()
    return ""


def canonical_category(category: str, known, language: str = "es") -> str:
    clean = _clean_category(str(category or ""))
    if not clean:
        return UNCATEGORIZED.get(language, UNCATEGORIZED["en"])
    first = _first_segment(clean)
    # The whole string is tried first, so a known category that really does
    # contain a comma still matches itself before the list rule applies.
    for candidate in (clean, first):
        if not candidate:
            continue
        wanted = _fold(candidate)
        for existing in known or []:
            if _fold(_clean_category(existing)) == wanted:
                return existing
    return first or clean


def _conditionals(template: str, flags: dict[str, bool]) -> str:
    """Resolve {{IF_NAME}}...{{ELSE}}...{{END}} regions against named flags.

    This runs before the values pass, and that order is the point: a region
    written inside the page text is never resolved, because by the time the
    page text is substituted this pass is over. The ELSE half is optional --
    a region with nothing to say when the flag is false just disappears.
    """
    return re.sub(
        r"\{\{IF_(\w+)\}\}\n(.*?)(?:\{\{ELSE\}\}\n(.*?))?\{\{END\}\}\n",
        lambda m: m.group(2) if flags.get(m.group(1)) else (m.group(3) or ""),
        template,
        flags=re.S,
    )


def _mention_scope(mode: str) -> str:
    # The mode becomes a file name, so its shape is checked here; which modes
    # exist is config's business.
    if not mode.isascii() or not mode.isalpha():
        raise ValueError(f"mention scope must be a plain word, got {mode!r}")
    # Flat file names on purpose: package-data is the single-level glob
    # "prompts/*.txt", so a subdirectory would work editable and not in a wheel.
    return files("oknowledge").joinpath(f"prompts/mentions-{mode}.txt").read_text(
        encoding="utf-8").strip()


def sent_text(text: str, limit: int = DEFAULT_LIMIT) -> str:
    """The slice of the content that travels in the prompt.

    One function, called by the prompt builder and by the guard, so the two
    can never disagree about what the model was actually shown.
    """
    return text[:limit]


def _trim_prose(url: str) -> str:
    """Drop the punctuation a sentence puts after a URL: , ; : ! ? and one .

    Done before the guard's substring test, not after: the guard then judges
    the string we would actually keep, and a URL whose comma was only prose
    cannot pass on the strength of the comma being in `sent`. The trimmed
    string is a prefix of the original, so a URL that was in the video still
    is. `)` is left alone: Wikipedia URLs really end with one.
    """
    url = url.rstrip(",;:!?")
    if url.endswith("."):
        url = url[:-1]
    return url


def to_mentions(data: dict, sent: str) -> list[Mention]:
    """The mentions in an answer, with every URL checked against the video.

    A URL survives only if it appears literally in `sent` -- the text the model
    was given. Anything else becomes a search for the name: a domain it
    remembered, a near miss, the schema's own example. The user's decision was
    that nothing is invented, and this comparison is what keeps it; the
    prompt's wording only asks.

    Only http and https URLs with a host are considered, and the match is a
    plain substring test against `sent`: a prefix of a URL the video said is
    accepted, which is fine, since it is still a string the video said.

    A row that is a bare string is a name: small models answer this way more
    often than with objects, and dropping those would empty the list on
    exactly the local engines. Rows that are neither are dropped one by one --
    a bad row never costs the good ones.
    """
    rows = data.get("mentions")
    if not isinstance(rows, list):
        return []
    best: dict[str, Mention] = {}
    for row in rows:
        if isinstance(row, str):
            row = {"name": row}
        if not isinstance(row, dict):
            continue
        name = row.get("name")
        if not isinstance(name, str):
            continue
        # Whitespace first, like normalize_tags: a newline in a name would
        # render a two-line bullet that reads back with the URL lost.
        name = " ".join(name.split())[:MAX_MENTION_NAME].strip()
        if not name or _is_placeholder(name):
            continue
        raw = row.get("url")
        raw = _trim_prose(raw.strip()) if isinstance(raw, str) else ""
        real = (raw.startswith(("http://", "https://")) and bool(urlsplit(raw).netloc)
                and raw in sent)
        candidate = Mention(name=name, url=raw if real else search_url(name))
        key = _fold(name)
        current = best.get(key)
        if current is None:
            # Past the cap a new name is skipped, but the scan goes on: a later
            # row may still carry the real URL of a name already kept.
            if len(best) < MAX_MENTIONS:
                best[key] = candidate
        elif real and is_search_url(current.url):
            best[key] = candidate
    return list(best.values())


def render_prompt(text: str, meta: dict, known, language: str, limit: int = DEFAULT_LIMIT,
                  mentions: str | None = None) -> str:
    template = files("oknowledge").joinpath("prompts/analyze.txt").read_text(encoding="utf-8")
    categories = [c for c in (known or [])][:MAX_KNOWN_CATEGORIES]
    # The template's own conditional goes first, so nothing from the page can
    # reach it; then one pass for the values, so a placeholder-looking string
    # in the page text or title is never substituted a second time.
    template = _conditionals(template, {"KNOWN": bool(categories),
                                        "MENTIONS": bool(mentions)})
    body = sent_text(text, limit)
    if len(text) > limit:
        body += "\n" + TRUNCATION_MARKER
    values = {
        "LANGUAGE": LANGUAGE_NAMES.get(language, language),
        "SCOPE": _mention_scope(mentions) if mentions else "",
        "CATEGORIES": "\n".join(f"- {c}" for c in categories),
        "URL": meta.get("url") or "",
        "TITLE": meta.get("title") or "",
        "TEXT": body,
    }
    return re.sub(r"\{\{([A-Z]+)\}\}", lambda m: values.get(m.group(1), m.group(0)), template)


def render_mentions_prompt(text: str, meta: dict, language: str, mode: str,
                           limit: int = DEFAULT_LIMIT) -> str:
    """The mentions-only prompt, cut at the same limit as the full one.

    Both sides use sent_text(), so the text the guard compares URLs against is
    exactly the text the model was sent.
    """
    template = files("oknowledge").joinpath("prompts/mentions.txt").read_text(encoding="utf-8")
    # Same order as render_prompt: conditionals first, then one values pass, so
    # nothing from the transcript is ever resolved.
    template = _conditionals(template, {})
    body = sent_text(text, limit)
    if len(text) > limit:
        body += "\n" + TRUNCATION_MARKER
    values = {
        "LANGUAGE": LANGUAGE_NAMES.get(language, language),
        "SCOPE": _mention_scope(mode),
        "URL": meta.get("url") or "",
        "TITLE": meta.get("title") or "",
        "TEXT": body,
    }
    return re.sub(r"\{\{([A-Z]+)\}\}", lambda m: values.get(m.group(1), m.group(0)), template)


def mentions_only(engine: Engine, text: str, meta: dict, language: str,
                  mode: str, limit: int = DEFAULT_LIMIT) -> list[Mention]:
    """Ask for the mentions and nothing else.

    Shares to_mentions() with the full analysis, so there is one definition of
    "nothing is invented" and not two.
    """
    sent = sent_text(text, limit)
    prompt = render_mentions_prompt(text, meta, language, mode, limit)
    return to_mentions(extract_json(engine.complete(prompt)), sent)


def extract_json(raw: str) -> dict:
    """The JSON object that is the answer, however it comes wrapped.

    Small models add a preamble, a ```json fence, or chatter afterwards, and
    that chatter can itself contain braces. So instead of slicing between the
    first "{" and the last "}", try to decode an object starting at each "{"
    in turn; the decoder knows where the object really ends, braces inside
    strings included. Decoding is not strict: models put literal newlines
    inside string values.

    The reply can hold several objects, most often because the model echoed
    the schema example from the prompt before answering. An echo always comes
    before the real answer, so the last object carrying every required key
    wins. If none does, the first decodable object is returned and validation
    reports what is missing. An object that merely wraps the answer
    ({"ficha": {...}}) also offers its inner object as a candidate.
    """
    decoder = json.JSONDecoder(strict=False)
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
            while len(value) == 1 and isinstance(inner := next(iter(value.values())), dict):
                found.append(inner)
                value = inner
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
    if _is_placeholder(value):
        raise AnalysisError(f"the answer left the {key} as the example placeholder")
    return value.strip()


def _items(data: dict, key: str) -> list:
    value = data[key]
    if not isinstance(value, list):
        raise AnalysisError(f"the answer has a non-list {key}")
    return value


def _to_analysis(data: dict, known, meta: dict, language: str, sent: str | None = None) -> Analysis:
    missing = [k for k in REQUIRED if k not in data]
    if missing:
        raise AnalysisError(f"the answer is missing: {', '.join(missing)}")
    summary = _text(data, "summary")
    if not summary:
        raise AnalysisError("the answer has an empty summary")
    title = _text(data, "title") or (meta.get("title") or "").strip() or meta.get("url") or ""
    points = [
        p.strip() for p in _items(data, "points")
        if isinstance(p, str) and p.strip() and not _is_placeholder(p)
    ]
    return Analysis(
        title=title,
        summary=summary,
        points=points[:MAX_POINTS],
        category=canonical_category(_text(data, "category"), known, language),
        tags=normalize_tags(_items(data, "tags")),
        # sent is None when the prompt never asked for mentions
        mentions=[] if sent is None else to_mentions(data, sent),
    )


def analyze(engine: Engine, text: str, meta: dict, known, language: str,
            mentions: str | None = None,
            record: Callable[[str, str, str], None] | None = None) -> Analysis:
    """Ask the engine about the page and give back what it said, parsed.

    `record(prompt, reply, parsed)` is called once per attempt, for a caller
    keeping a trace of what went out and what came back: it is the only place
    that holds all three at once. It is called on the failure paths too --
    those are the ones worth reading -- and never on the happy path of a
    caller who did not ask for it.
    """
    tell = record or _NOTHING
    sent = sent_text(text) if mentions else None
    prompt = render_prompt(text, meta, known, language, mentions=mentions)
    request = prompt
    for attempt in range(2):
        try:
            reply = engine.complete(request)
        except Exception as error:
            # No reply to record, which is itself the thing to record: a
            # timeout and a refusal look alike from the note's side.
            tell(request, "", f"{type(error).__name__}: {error}")
            raise
        try:
            done = _to_analysis(extract_json(reply), known, meta, language, sent)
        except AnalysisError as error:
            tell(request, reply, f"unusable: {error}")
            last = error
            request = prompt + retry_suffix(language, str(error))
            continue
        tell(request, reply, _as_text(done))
        return done
    raise AnalysisError(f"the engine never produced a usable answer: {last}") from last
