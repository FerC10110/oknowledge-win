# La interfaz en el celular, y marcas con emoji — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** una marca con emoji por nota (links, fichas, ideas), con filtro en el nav, y la web usable a 390px.

**Architecture:** `marks.py` (sin dependencias) valida y ordena marcas; `Note.mark` viaja por `render`/`read_note` y por toda reescritura; la web suma `POST /item/{id}/mark`, `GET /marked` y un partial `mark-picker.html`. El celular se resuelve con CSS por debajo de 42rem, `<details>` y un `layout.js` de pocas líneas.

**Tech Stack:** Python 3.12, FastAPI + Jinja2, PyYAML, pytest, CSS sin preprocesador, JS sin dependencias.

**Spec:** `docs/2026-10-13-interfaz-celular-y-marcas-design.md`

## Global Constraints

- Rama `feat/mobile-and-marks`. Sin merge ni push sin la palabra del usuario.
- Suite: `~/.local/share/oknowledge/venv/bin/python -m pytest -q` (abreviado abajo como `PY -m pytest`; `PY=~/.local/share/oknowledge/venv/bin/python`). Corré siempre desde `/home/fer/Projects/oknowledge`.
- TDD: cada test se ve fallar antes de implementar.
- Commits en inglés, **sin** líneas `Co-Authored-By`, `Claude-Session` ni "Generated with Claude Code".
- Nunca `datetime.utcnow()`; usar `datetime.datetime.now(datetime.timezone.utc)`.
- Código, rutas, docstrings en inglés. Textos nuevos de interfaz: clave en inglés en la plantilla y traducción en `STRINGS["es"]` de `src/oknowledge/i18n.py` (`test_every_translated_string_is_one_the_code_asks_for` exige que toda clave traducida se use).
- CSS: colores sólo como tokens de `:root` con su versión oscura; nada de estilos en línea.
- "Celular" = `max-width: 42rem`.
- `clean_mark`: 1–8 code points, al menos uno de categoría `So`, ninguno de `L*`, `N*`, `Z*`, `C*` salvo U+200D, U+FE0F, U+FE0E.
- Lista por defecto: `("⭐", "🔥", "❤️", "📌", "✅", "❓", "💡", "⚠️", "🧪", "📚", "🎯", "👀")`.
- Nunca tocar el vault real; las capturas van contra el vault de prueba del Task 14.

## Review Focus

1. Un link con marca que se reprocesa y el análisis falla y queda parcial (pipeline `_partial`): la marca sigue. → test en Task 3.
2. `back` armado a mano (`//evil.com`, `https://evil.com`, `/\evil`) en `POST /item/{id}/mark`: se ignora y se vuelve a la página de la nota. → test en Task 6.
3. Una marca escrita a mano en Obsidian que no pasa `clean_mark` (`mark: hola`, `mark: 3`, una lista): la nota se lee igual, sin marca. → test en Task 2.
4. Guardar Ajustes con una lista de marcas propia en config.toml: la lista sobrevive. → test en Task 4.
5. Una marca que está en la lista pero `back` lleva ya `?notice=...`: no se acumulan avisos en la URL. → test en Task 6.

---

### Task 1: `marks.py` — validar y ordenar

**Files:**
- Create: `src/oknowledge/marks.py`
- Test: `tests/test_marks.py`

**Interfaces:**
- Produces: `DEFAULT_MARKS: tuple[str, ...]`, `MAX_MARK = 8`, `clean_mark(value) -> str | None` ("" = sacar, None = rechazado), `rank_marks(notes, preferred) -> list[tuple[str, int]]` (notes: iterable de objetos con `.mark`).

- [ ] **Step 1: tests que fallan**

```python
"""A mark is one emoji you put on a note. These are the rules for what counts."""

import pytest

from oknowledge.marks import DEFAULT_MARKS, clean_mark, rank_marks


@pytest.mark.parametrize("mark", ["⭐", "🔥", "❤️", "👍🏽", "🇦🇷", "👨‍👩‍👧", "📚"])
def test_an_emoji_is_a_mark(mark):
    assert clean_mark(mark) == mark


def test_spaces_around_it_go():
    assert clean_mark("  ⭐ \n") == "⭐"


@pytest.mark.parametrize("empty", ["", "   ", None])
def test_nothing_means_take_the_mark_off(empty):
    assert clean_mark(empty) == ""


@pytest.mark.parametrize("bad", ["a", "ab", "⭐a", "1️⃣", "3", "⭐ ⭐", "!!", "→",
                                 "⭐" * 9, "\x00⭐", "⭐‮"])
def test_anything_else_is_refused(bad):
    assert clean_mark(bad) is None


def test_a_number_from_a_hand_edit_is_refused():
    assert clean_mark(3) is None


def test_the_default_list_passes_its_own_rule():
    assert all(clean_mark(m) == m for m in DEFAULT_MARKS)
    assert len(DEFAULT_MARKS) == 12


class N:
    def __init__(self, mark):
        self.mark = mark


def test_most_used_first_then_the_list_order_then_first_seen():
    notes = [N("👀"), N("⭐"), N("🔥"), N("⭐"), N(""), N("🦄"), N("🔥"), N("🐙")]
    assert rank_marks(notes, DEFAULT_MARKS) == [
        ("⭐", 2), ("🔥", 2), ("👀", 1), ("🦄", 1), ("🐙", 1)]


def test_no_marks_no_list():
    assert rank_marks([N(""), N("")], DEFAULT_MARKS) == []
```

- [ ] **Step 2:** `PY -m pytest tests/test_marks.py -q` → FAIL: `ModuleNotFoundError: oknowledge.marks`.

- [ ] **Step 3: implementación**

```python
"""Marks: one emoji you put on a note, and nothing a model ever writes.

Its own module and not part of the vault's: the config reads the list of
marks to offer, and the config cannot import the vault (the vault imports
it). Nothing here touches a disk.
"""

from __future__ import annotations

import unicodedata

DEFAULT_MARKS = ("⭐", "🔥", "❤️", "📌", "✅", "❓", "💡", "⚠️", "🧪", "📚", "🎯", "👀")
"""What the picker offers until `[web] marks` says otherwise."""

MAX_MARK = 8
"""Code points, not characters: 👍🏽 is two and a family is five, joined."""

# What glues an emoji together: the joiner of 👨‍👩‍👧 and the selectors that
# turn ❤ into ❤️. They are format characters (Cf), which the rule below
# otherwise refuses along with every other invisible one.
_GLUE = frozenset({"‍", "️", "︎"})


def clean_mark(value) -> str | None:
    """The mark as it will be stored: "" for none, None when refused.

    Refused rather than repaired, like a category name: whoever typed "ok"
    into the box gets told no, not a mark they did not ask for. A symbol
    (So) is what every emoji is; letters, digits, spaces and invisible
    characters are what an emoji never needs.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return ""
    if len(text) > MAX_MARK:
        return None
    if not any(unicodedata.category(ch) == "So" for ch in text):
        return None
    for ch in text:
        if ch in _GLUE:
            continue
        if unicodedata.category(ch)[0] in "LNZC":
            return None
    return text


def rank_marks(notes, preferred) -> list[tuple[str, int]]:
    """(mark, how many notes carry it), most used first.

    A tie goes to the order of the picker's list, and after that to the
    note seen first: a filter that swapped places between two page loads
    for a reason nobody can see would be worse than no order at all.
    """
    counts: dict[str, int] = {}
    for note in notes:
        if note.mark:
            counts[note.mark] = counts.get(note.mark, 0) + 1
    listed = {mark: i for i, mark in enumerate(preferred)}
    seen = {mark: i for i, mark in enumerate(counts)}
    return sorted(counts.items(),
                  key=lambda kv: (-kv[1], listed.get(kv[0], len(listed)), seen[kv[0]]))
```

- [ ] **Step 4:** `PY -m pytest tests/test_marks.py -q` → PASS.
- [ ] **Step 5:** `git add src/oknowledge/marks.py tests/test_marks.py && git commit -m "feat: marks, one emoji per note, and the rule for what counts as one"`

---

### Task 2: `Note.mark` en el archivo, y `update_note(mark=)`

**Files:**
- Modify: `src/oknowledge/model.py` (campo después de `my_note`), `src/oknowledge/vault.py` (`FRONTMATTER_ORDER`, `render`, `read_note`, `update_note`)
- Test: `tests/test_vault_marks.py`

**Interfaces:**
- Consumes: `clean_mark` (Task 1).
- Produces: `Note.mark: str = ""`; `update_note(..., mark: str | None = None)` — `None` no toca; otro valor pasa por `clean_mark`, y si es `None` (rechazado) deja la nota como estaba.

- [ ] **Step 1: tests que fallan**

```python
"""A mark lives in the frontmatter, and every rewrite carries it."""

import pytest

from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.vault import (find_note, read_note, rebuild_indexes, rename_category,
                              update_note, write_note)


@pytest.fixture
def cfg(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    return Config(vault=vault)


def a_note(**extra):
    return Note(id="a1a1a1a1a1a1", url="https://e.com/a", title="WireGuard",
                category="Redes", tags=["vpn"], type="article", source="e.com",
                saved="2026-10-03", summary="Una vpn.", points=[], **extra)


def test_a_mark_is_written_and_read_back(cfg):
    path = write_note(cfg, a_note(mark="⭐"), "es")
    assert "mark: ⭐" in path.read_text(encoding="utf-8")
    assert read_note(path).mark == "⭐"


def test_no_mark_no_line(cfg):
    path = write_note(cfg, a_note(), "es")
    assert "mark:" not in path.read_text(encoding="utf-8")
    assert read_note(path).mark == ""


@pytest.mark.parametrize("typed", ["hola", "3", "[⭐, 🔥]", "'1️⃣'"])
def test_a_hand_typed_mark_that_is_not_one_reads_as_none(cfg, typed):
    path = write_note(cfg, a_note(), "es")
    text = path.read_text(encoding="utf-8").replace("id: ", f"mark: {typed}\nid: ", 1)
    path.write_text(text, encoding="utf-8")
    back = read_note(path)
    assert back is not None and back.mark == ""


def test_update_note_sets_and_clears_the_mark(cfg):
    write_note(cfg, a_note(), "es")
    update_note(cfg, "a1a1a1a1a1a1", "es", mark="🔥")
    assert find_note(cfg, "a1a1a1a1a1a1")[1].mark == "🔥"
    update_note(cfg, "a1a1a1a1a1a1", "es", mark="")
    assert find_note(cfg, "a1a1a1a1a1a1")[1].mark == ""


def test_update_note_refuses_what_is_not_a_mark(cfg):
    write_note(cfg, a_note(mark="⭐"), "es")
    update_note(cfg, "a1a1a1a1a1a1", "es", mark="ok")
    assert find_note(cfg, "a1a1a1a1a1a1")[1].mark == "⭐"


def test_other_edits_keep_the_mark(cfg):
    write_note(cfg, a_note(mark="⭐"), "es")
    rebuild_indexes(cfg, "es")
    update_note(cfg, "a1a1a1a1a1a1", "es", category="Seguridad", tags=["x"])
    assert find_note(cfg, "a1a1a1a1a1a1")[1].mark == "⭐"


def test_renaming_the_category_keeps_the_mark(cfg):
    write_note(cfg, a_note(mark="⭐"), "es")
    rebuild_indexes(cfg, "es")
    rename_category(cfg, "Redes", "Networking", "es")
    found = find_note(cfg, "a1a1a1a1a1a1")[1]
    assert (found.category, found.mark) == ("Networking", "⭐")
```

- [ ] **Step 2:** `PY -m pytest tests/test_vault_marks.py -q` → FAIL: `TypeError: Note.__init__() got an unexpected keyword argument 'mark'`.

- [ ] **Step 3: implementación**

En `model.py`, después de `my_note`:

```python
    mark: str = ""
    """Yours: one emoji, or nothing. Like state and score, no model ever
    writes it, and every rewrite of a note carries it across."""
```

En `vault.py`:
- `from .marks import clean_mark` junto a los otros imports relativos.
- `FRONTMATTER_ORDER`: agregar `"mark"` entre `"state"` y `"content"`.
- En `render()`, después de `"state": note.state or None,`: `"mark": note.mark or None,`
- En `read_note()`, en el `Note(...)`, después de `state=...`: `mark=clean_mark(front.get("mark")) or "",`
- En `update_note()`: parámetro `mark: str | None = None,` después de `my_note`, y después del bloque de `my_note`:

```python
    if mark is not None:
        picked = clean_mark(mark)
        note.mark = note.mark if picked is None else picked
```

- [ ] **Step 4:** `PY -m pytest tests/test_vault_marks.py tests/test_vault.py tests/test_vault_edit.py -q` → PASS.
- [ ] **Step 5:** `git add -A src/oknowledge/model.py src/oknowledge/vault.py tests/test_vault_marks.py && git commit -m "feat: a note carries its mark in the frontmatter"`

---

### Task 3: las reescrituras del pipeline conservan la marca

**Files:**
- Modify: `src/oknowledge/pipeline.py` (`_partial` ~línea 319 y el `Note(...)` del análisis ~línea 558)
- Test: `tests/test_pipeline.py` (al lado de `test_a_reprocess_keeps_the_collections_the_user_made`), `tests/test_pipeline_describe.py`, `tests/test_pipeline_idea.py`

**Interfaces:**
- Consumes: `Note.mark` (Task 2).

- [ ] **Step 1: tests que fallan.** En `tests/test_pipeline.py`, después de `test_a_retry_that_fails_again_keeps_the_collections`:

```python
def test_a_reprocess_keeps_the_mark(cfg, q, monkeypatch):
    extraction(monkeypatch, PAGE)
    no_pictures(monkeypatch)
    first = add(cfg, "https://arstechnica.com/vpn", queue=q)
    note = read_note(first.path)
    note.mark = "⭐"
    write_note(cfg, note, "es", path=first.path)

    again = dataclasses.replace(cfg, engines={"fake": {"replies": [OTHER_ANSWER]}})
    second = add(again, "https://arstechnica.com/vpn", reprocess=True, queue=q)

    done = read_note(second.path)
    assert done.category == "Cocina"                              # really reprocessed
    assert done.mark == "⭐"


def test_a_retry_that_fails_again_keeps_the_mark(cfg, q, monkeypatch):
    extraction(monkeypatch, Unreadable("503"))
    no_pictures(monkeypatch)
    first = add(cfg, "https://arstechnica.com/vpn", queue=q)
    note = read_note(first.path)
    note.mark = "🔥"
    write_note(cfg, note, "es", path=first.path)

    second = retry(cfg, queue=q)[0]

    assert second.status == "partial"
    assert read_note(second.path).mark == "🔥"
```

En `tests/test_pipeline_describe.py`, al final:

```python
def test_the_rewrite_keeps_your_mark(cfg, fake_engine):
    path, note = find_note(cfg, CARD, shelf=cfg.ocio)
    note.mark = "📚"
    write_note(cfg, note, "es", path=path)
    fake_engine.answers('{"summary": "Otra cosa.", "points": []}')
    describe(cfg, CARD)
    assert note_now(cfg).mark == "📚"
```

En `tests/test_pipeline_idea.py`, después de `test_retitling_keeps_the_rest`:

```python
def test_completing_and_retitling_keep_the_mark(cfg, engine):
    note, _ = put(cfg, mark="💡")
    complete_idea(cfg, note.id)
    assert now(cfg, note)[1].mark == "💡"
    retitle_idea(cfg, note.id, "Otro nombre", "Texto.", "es")
    assert now(cfg, note)[1].mark == "💡"
```

- [ ] **Step 2:** `PY -m pytest tests/test_pipeline.py -k mark tests/test_pipeline_describe.py tests/test_pipeline_idea.py -q` → los dos de `test_pipeline.py` FALLAN (`'' == '⭐'`); los de describe e ideas pasan ya (re-leen la nota). Eso está bien: son de regresión, y Task 2 es lo que los hizo pasar. Anotalo en el ledger.

- [ ] **Step 3: implementación.** En `_partial` (el `return Note(...)`), después de `collections=(keep.collections if keep else []),`:

```python
        mark=(keep.mark if keep else ""),
```

En el `note = Note(...)` del análisis, después de `collections=(existing[1].collections if existing else []),`:

```python
        mark=(existing[1].mark if existing else ""),
```

Y en el comentario que sigue ("A card never reaches here ... `score`, `state`, `my_note`, `length` and `rating` are not carried across") no cambia nada: `mark` sí se carga, como `collections`.

- [ ] **Step 4:** `PY -m pytest tests/test_pipeline.py tests/test_pipeline_describe.py tests/test_pipeline_idea.py -q` → PASS.
- [ ] **Step 5:** `git commit -am "fix: a reprocess or a failed retry keeps the mark"` (con los tests agregados: `git add tests/` antes).

---

### Task 4: `Config.marks`, leída y guardada

**Files:**
- Modify: `src/oknowledge/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: `DEFAULT_MARKS`, `clean_mark` (Task 1).
- Produces: `Config.marks: tuple[str, ...] = DEFAULT_MARKS`.

- [ ] **Step 1: tests que fallan** (al final de `tests/test_config.py`):

```python
def test_the_marks_default_to_the_short_list(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    from oknowledge.marks import DEFAULT_MARKS
    assert load(write_config(tmp_path, f'vault = "{vault}"\n')).marks == DEFAULT_MARKS


def test_your_own_marks_are_read_and_the_bad_ones_dropped(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    path = write_config(tmp_path, f'vault = "{vault}"\n[web]\n'
                                  'marks = ["🦄", "hola", "⭐", "🦄", ""]\n')
    assert load(path).marks == ("🦄", "⭐")


@pytest.mark.parametrize("value", ['"⭐"', "3", "[1, 2]"])
def test_marks_that_are_not_a_list_of_text_are_refused_by_name(tmp_path, value):
    vault = tmp_path / "vault"
    vault.mkdir()
    path = write_config(tmp_path, f'vault = "{vault}"\n[web]\nmarks = {value}\n')
    with pytest.raises(ConfigError, match="web.marks"):
        load(path)


def test_saving_keeps_your_marks(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    out = tmp_path / "out.toml"
    save(Config(vault=vault, marks=("🦄", "⭐")), out)
    assert load(out).marks == ("🦄", "⭐")


def test_the_default_marks_are_not_written(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    out = tmp_path / "out.toml"
    save(Config(vault=vault), out)
    assert "marks" not in out.read_text(encoding="utf-8")
```

- [ ] **Step 2:** `PY -m pytest tests/test_config.py -k marks -q` → FAIL (`AttributeError: 'Config' object has no attribute 'marks'`).

- [ ] **Step 3: implementación.** En `config.py`:
- `from .marks import DEFAULT_MARKS, clean_mark`
- En `Config`, después de `idle_timeout`:

```python
    marks: tuple[str, ...] = DEFAULT_MARKS
    """The emojis the picker offers. Any other can be typed into its box;
    these are the ones a tap away."""
```

- Una función junto a `_host`:

```python
def _marks(web: dict) -> tuple[str, ...]:
    """The picker's list, or a ConfigError naming the key. A mark that is
    not one is dropped rather than refused: the list is a convenience, and
    one typo in it should not keep the server from starting."""
    value = web.get("marks", DEFAULT_MARKS)
    if not isinstance(value, (list, tuple)) or not all(isinstance(m, str) for m in value):
        raise ConfigError(f"web.marks must be a list of emojis in quotes, not {value!r}")
    kept: list[str] = []
    for raw in value:
        mark = clean_mark(raw)
        if mark and mark not in kept:
            kept.append(mark)
    return tuple(kept)
```

- En `load()`, en el `Config(...)`, después de `idle_timeout=...`: `marks=_marks(web),`
- En `save()`, el dict `"web"` pasa a:

```python
        "web": {"host": cfg.host, "port": cfg.port,
                "idle_timeout": cfg.idle_timeout,
                # Only a list of your own: the default in everybody's file
                # would be twelve emojis nobody chose.
                **({"marks": list(cfg.marks)} if cfg.marks != DEFAULT_MARKS else {})},
```

- [ ] **Step 4:** `PY -m pytest tests/test_config.py tests/test_web_settings.py -q` → PASS. Si Ajustes arma el `Config` nuevo con `dataclasses.replace(cfg, ...)`, `marks` viaja sola; si lo arma de cero, agregá `marks=current["cfg"].marks` y un test en `tests/test_web_settings.py` que guarde Ajustes con `marks=("🦄",)` y lea `load(...)` de vuelta.
- [ ] **Step 5:** `git add -A src/oknowledge/config.py tests/test_config.py tests/test_web_settings.py && git commit -m "feat: the marks a tap away come from [web] marks"`

---

### Task 5: la web conoce las marcas (contexto común y nav)

**Files:**
- Modify: `src/oknowledge/web/app.py` (`page()`), `src/oknowledge/web/templates/base.html` (nav), `src/oknowledge/web/static/style.css`
- Test: `tests/test_web_marks.py` (nuevo)

**Interfaces:**
- Consumes: `rank_marks`, `Config.marks`, `Note.mark`.
- Produces: en toda plantilla: `marks` (tuple, lista del picker), `used_marks` (list[(mark, n)]), `active_mark` (str | None, por defecto None), `here` (str: path + query de la página actual).

- [ ] **Step 1: tests que fallan.** Crear `tests/test_web_marks.py`:

```python
"""Marks on the web: the picker, the route that writes one, the nav, /marked."""

import re
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.vault import find_note, note_path, rebuild_indexes, write_note
from oknowledge.web.app import create_app

LINK, CARD, IDEA = "aaaaaaaaaaaa", "bbbbbbbbbbbb", "cccccccccccc"


@pytest.fixture(autouse=True)
def state_tree(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr("oknowledge.web.app.CONFIG_PATH",
                        tmp_path / "config" / "config.toml")


@pytest.fixture
def cfg(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    config = Config(vault=vault)
    write_note(config, Note(id=LINK, url="https://wireguard.com", title="WireGuard",
                            category="Redes", tags=[], type="article",
                            source="wireguard.com", saved="2026-10-10",
                            summary="Una vpn."), "es")
    card = Note(id=CARD, url="https://imdb.com/title/tt0088247", title="The Terminator",
                category="Películas", tags=[], type="movie", source="imdb.com",
                saved="2026-10-11", summary="Un cyborg.")
    write_note(config, card, "es", path=note_path(config, card, shelf=config.ocio))
    idea = Note(id=IDEA, url="", title="Gimnasio", category="Ideas", tags=[],
                type="idea", source="", saved="2026-10-12", summary="Una app.")
    write_note(config, idea, "es", path=note_path(config, idea, shelf=config.ideas))
    for shelf in (None, config.ocio, config.ideas):
        rebuild_indexes(config, "es", shelf)
    return config


@pytest.fixture
def client(cfg):
    return TestClient(create_app(cfg))


def mark_of(cfg, link_id):
    for shelf in (None, cfg.ocio, cfg.ideas):
        found = find_note(cfg, link_id, shelf)
        if found:
            return found[1].mark
    raise AssertionError("gone")


def nav(body):
    return re.search(r"<nav[^>]*>.*?</nav>", body, re.S).group(0)


def test_no_marks_nothing_in_the_nav(client):
    assert "/marked" not in nav(client.get("/").text)


def test_the_marks_in_use_are_in_the_nav_most_used_first(client, cfg):
    for link_id, mark in ((LINK, "🔥"), (CARD, "⭐"), (IDEA, "⭐")):
        path, note = next(f for f in (find_note(cfg, link_id, s)
                                      for s in (None, cfg.ocio, cfg.ideas)) if f)
        note.mark = mark
        write_note(cfg, note, "es", path=path)
    links = re.findall(r'href="/marked\?mark=([^"]+)"', nav(client.get("/").text))
    assert links == [quote("⭐"), quote("🔥")]
```

- [ ] **Step 2:** `PY -m pytest tests/test_web_marks.py -q` → el segundo FALLA (lista vacía).

- [ ] **Step 3: implementación.** En `app.py`, `from ..marks import clean_mark, rank_marks` y en `page()`, dentro del `base` y del return normal:

```python
        here = request.url.path + ("?" + request.url.query if request.url.query else "")
        base = {..., "here": here, "marks": current["cfg"].marks,
                "used_marks": [], "active_mark": None}
```

y en la rama normal (no la de `library.error`), antes del `return`:

```python
        # Every shelf, because the filter is in the nav and the nav is on
        # every page. Each refresh is a stat per file, and the library one
        # already ran for this request anyway.
        for other in (shelf, ideas):
            other.refresh()
        used = rank_marks([*library.notes, *shelf.notes, *ideas.notes],
                          current["cfg"].marks)
```

pasando `"used_marks": used` en el `context` (antes de `**context`, para que una ruta pueda pisarlo).

En `base.html`, dentro de `<nav>` después del link de Ajustes:

```html
      {# Yours, most used first: one tap to everything you marked with it. #}
      {% for mark, n in used_marks %}
        <a href="/marked?mark={{ mark|urlencode }}" class="mark{% if active_mark == mark %} on{% endif %}"
           title="{{ n }}" aria-label="{{ t('Marked %1', mark) }}">{{ mark }}</a>
      {% endfor %}
```

En `i18n.py` (`STRINGS["es"]`): `"Marked %1": "Marcadas con %1",`.

En `style.css`, después de `header nav a:hover`:

```css
header nav a.mark { font-size: 1.05rem; margin-left: 0.6rem; }
header nav a.mark.on { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 6px; }
```

- [ ] **Step 4:** `PY -m pytest tests/test_web_marks.py tests/test_web_read.py tests/test_i18n.py -q` → PASS.
- [ ] **Step 5:** `git add -A src/oknowledge/web tests/test_web_marks.py src/oknowledge/i18n.py && git commit -m "feat: the marks in use sit in the nav, right of Settings"`

---

### Task 6: `POST /item/{id}/mark`

**Files:**
- Modify: `src/oknowledge/web/app.py`, `tests/test_web_write.py` (`WRITE_ROUTES`)
- Test: `tests/test_web_marks.py`

**Interfaces:**
- Consumes: `update_note(mark=)`, `held_by`, `edit`, `see_other`, `item_url`.
- Produces: `local_path(back: str) -> str | None` (módulo `app.py`, nivel módulo); ruta `POST /item/{link_id}/mark` con form `mark`, `back`; aviso `bad-mark`.

- [ ] **Step 1: tests que fallan** (en `tests/test_web_marks.py`):

```python
@pytest.mark.parametrize("link_id", [LINK, CARD, IDEA])
def test_a_mark_goes_on_a_link_a_card_and_an_idea(client, cfg, link_id):
    client.post(f"/item/{link_id}/mark", data={"mark": "⭐", "back": "/"})
    assert mark_of(cfg, link_id) == "⭐"


def test_an_empty_mark_takes_it_off(client, cfg):
    client.post(f"/item/{LINK}/mark", data={"mark": "⭐", "back": "/"})
    client.post(f"/item/{LINK}/mark", data={"mark": "", "back": "/"})
    assert mark_of(cfg, LINK) == ""


def test_it_goes_back_to_the_same_card(client):
    answer = client.post(f"/item/{LINK}/mark", data={"mark": "⭐", "back": "/?category=Redes"},
                         follow_redirects=False)
    assert answer.status_code == 303
    assert answer.headers["location"] == f"/?category=Redes#card-{LINK}"


def test_what_is_not_a_mark_writes_nothing_and_says_so(client, cfg):
    files = sorted(cfg.root.rglob("*.md"))
    before = [p.read_text(encoding="utf-8") for p in files]
    answer = client.post(f"/item/{LINK}/mark", data={"mark": "ok", "back": "/"},
                         follow_redirects=False)
    assert answer.headers["location"] == f"/?notice=bad-mark#card-{LINK}"
    assert [p.read_text(encoding="utf-8") for p in files] == before


@pytest.mark.parametrize("back", ["//evil.com/x", "https://evil.com/", "/\\evil.com",
                                  "evil", "", "/\x07"])
def test_a_way_back_that_is_not_ours_goes_to_the_note(client, back):
    answer = client.post(f"/item/{LINK}/mark", data={"mark": "⭐", "back": back},
                         follow_redirects=False)
    assert answer.headers["location"] == f"/item/{LINK}#card-{LINK}"


def test_notices_do_not_pile_up_in_the_way_back(client):
    answer = client.post(f"/item/{LINK}/mark",
                         data={"mark": "ok", "back": "/?notice=bad-mark&page=2"},
                         follow_redirects=False)
    assert answer.headers["location"] == f"/?page=2&notice=bad-mark#card-{LINK}"


def test_a_note_that_is_not_there_is_404(client):
    assert client.post("/item/000000000000/mark", data={"mark": "⭐"}).status_code == 404


def test_the_bad_mark_notice_is_translated(client, isolated_ui_language):
    from oknowledge.i18n import STRINGS
    from oknowledge.web.app import NOTICES
    assert NOTICES["bad-mark"] in STRINGS["es"]
```

Y en `tests/test_web_write.py`, en `WRITE_ROUTES`, al final de la lista:

```python
    # Your mark on a note. A cross-site POST here would rewrite one of
    # your notes.
    ("/item/a1/mark", {"mark": "⭐"}),
```

- [ ] **Step 2:** `PY -m pytest tests/test_web_marks.py tests/test_web_write.py -q` → FALLAN (405 / KeyError `bad-mark`).

- [ ] **Step 3: implementación.** En `app.py`, a nivel módulo (cerca de `item_url`), con `from urllib.parse import parse_qsl, urlsplit` y `import unicodedata` si faltan:

```python
def local_path(back: str) -> str | None:
    """A page of ours to go back to, or None.

    It arrives from a form, so it can arrive as anything: only a path on
    this server is taken, never another host (//x, \\x, a scheme), and a
    notice it already carries is dropped so they do not pile up.
    """
    text = (back or "").strip()
    if not text.startswith("/") or text.startswith("//") or "\\" in text:
        return None
    if any(unicodedata.category(ch)[0] == "C" for ch in text):
        return None
    parts = urlsplit(text)
    if parts.scheme or parts.netloc:
        return None
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if k != "notice"])
    return parts.path + ("?" + query if query else "")
```

En `NOTICES`: `"bad-mark": "That is not an emoji the mark can be.",` y en `STRINGS["es"]`: `"That is not an emoji the mark can be.": "Eso no es un emoji que pueda ser una marca.",`

La ruta, después de `set_my_note`:

```python
    @app.post("/item/{link_id}/mark")
    def set_mark(link_id: str, mark: str = Form(""), back: str = Form("")):
        """Your one emoji on a note, on any shelf. Back to the card it was
        set from, so marking ten cards is ten taps and no scrolling."""
        shelves, which = held_by(link_id)
        if shelves.by_id(link_id) is None:
            raise HTTPException(status_code=404, detail="no such note")
        home = local_path(back) or item_url(link_id)

        def to_card(notice: str):
            answer = see_other(home, notice=notice)
            answer.headers["location"] += "#card-" + quote(link_id, safe="")
            return answer

        if clean_mark(mark) is None:
            return to_card("bad-mark")
        result = edit(link_id, lambda cfg, language: update_note(
            cfg, link_id, language, shelf=cfg.shelf(which.name), mark=mark),
            "", "indexes-stale", shelves=shelves)
        if result.notice == MISSING:
            raise HTTPException(status_code=404, detail="no such note")
        return to_card(result.notice)
```

(Éxito = aviso vacío: una marca se ve en la tarjeta, no hace falta un "Guardado." arriba de la página. `see_other` descarta los valores vacíos.)

- [ ] **Step 4:** `PY -m pytest tests/test_web_marks.py tests/test_web_write.py tests/test_i18n.py -q` → PASS.
- [ ] **Step 5:** `git add -A && git commit -m "feat: POST /item/{id}/mark, back to the card it came from"`

---

### Task 7: `GET /marked`

**Files:**
- Create: `src/oknowledge/web/templates/marked.html`
- Modify: `src/oknowledge/web/app.py`
- Test: `tests/test_web_marks.py`

**Interfaces:**
- Consumes: `page`, `pager`, `page_number`, `PER_PAGE`, `active_mark`.

- [ ] **Step 1: tests que fallan:**

```python
def test_marked_shows_the_three_shelves(client):
    for link_id in (LINK, CARD, IDEA):
        client.post(f"/item/{link_id}/mark", data={"mark": "⭐", "back": "/"})
    body = client.get("/marked", params={"mark": "⭐"}).text
    assert body.index("Gimnasio") < body.index("The Terminator") < body.index("WireGuard")


def test_marked_leaves_out_the_other_marks(client):
    client.post(f"/item/{LINK}/mark", data={"mark": "🔥", "back": "/"})
    client.post(f"/item/{CARD}/mark", data={"mark": "⭐", "back": "/"})
    body = client.get("/marked", params={"mark": "⭐"}).text
    assert "The Terminator" in body and "WireGuard" not in body


def test_the_mark_you_are_on_is_lit_in_the_nav(client):
    client.post(f"/item/{CARD}/mark", data={"mark": "⭐", "back": "/"})
    assert 'class="mark on"' in nav(client.get("/marked", params={"mark": "⭐"}).text)


@pytest.mark.parametrize("mark", ["", "🦄"])
def test_a_mark_nobody_uses_is_an_empty_page(client, mark):
    answer = client.get("/marked", params={"mark": mark})
    assert answer.status_code == 200 and "card-" not in answer.text


def test_marked_pages_like_the_library(client, cfg, monkeypatch):
    monkeypatch.setattr("oknowledge.web.app.PER_PAGE", 1)
    for link_id in (LINK, CARD, IDEA):
        client.post(f"/item/{link_id}/mark", data={"mark": "⭐", "back": "/"})
    body = client.get("/marked", params={"mark": "⭐", "page": "2"}).text
    assert "The Terminator" in body and "WireGuard" not in body
    assert "page=3" in body
```

- [ ] **Step 2:** `PY -m pytest tests/test_web_marks.py -k marked -q` → FAIL (404).

- [ ] **Step 3: implementación.** Ruta, después de `search`:

```python
    @app.get("/marked", response_class=HTMLResponse)
    def marked(request: Request, mark: str = ""):
        """Everything with one mark, whichever shelf it sits on. Newest
        first, the way every listing here is."""
        found = []
        for shelves in (library, shelf, ideas):
            shelves.refresh()
            found += [n for n in shelves.notes if mark and n.mark == mark]
        found.sort(key=lambda n: n.saved, reverse=True)
        pages = -(-len(found) // PER_PAGE)
        number = page_number(request.query_params.get("page", "1"), pages)
        shown = found[(number - 1) * PER_PAGE:number * PER_PAGE]
        return page(request, "marked.html", notes=shown, active_mark=mark or None,
                    **pager("/marked", {"mark": mark}, number, pages))
```

`templates/marked.html`:

```html
{% extends "base.html" %}
{% block title %}{{ active_mark or '' }} - oknowledge{% endblock %}
{% block body_class %}wide{% endblock %}
{% block main %}
  {% if not notes %}<p class="empty">{{ t('Nothing matches that filter') }}</p>{% endif %}
  <ul class="grid">
    {% for note in notes %}
      {# What the three shelves share, and the way to the note: each
         shelf's own buttons live on its own page. #}
      <li class="card" id="card-{{ note.id }}">
        {% include "mark-picker.html" %}
        {% if note.cover %}
          <a class="shot" href="/item/{{ note.id|slug }}" tabindex="-1" aria-hidden="true">
            <img src="/cover/{{ note.id|slug }}" alt="" loading="lazy">
          </a>
        {% endif %}
        <div class="pad">
          <h2 dir="auto"><a href="/item/{{ note.id|slug }}">{{ note.title or t('Untitled idea') }}</a></h2>
          <a class="body" href="/item/{{ note.id|slug }}">
            <p class="meta"><span class="cat">{{ note.category }}</span> · {{ note.saved }}</p>
            <p class="sum" dir="auto">{{ (note.summary or note.my_note)|plain }}</p>
          </a>
        </div>
      </li>
    {% endfor %}
  </ul>
  {% if prev_url or next_url %}
    <nav class="pager">
      {% if prev_url %}<a rel="prev" href="{{ prev_url }}">{{ t('Previous') }}</a>{% endif %}
      <span>{{ t('Page %1 of %2', page, pages) }}</span>
      {% if next_url %}<a rel="next" href="{{ next_url }}">{{ t('Next') }}</a>{% endif %}
    </nav>
  {% endif %}
{% endblock %}
```

`mark-picker.html` lo crea el Task 8; para este task creá el archivo vacío (`touch`) y el Task 8 lo llena.

- [ ] **Step 4:** `PY -m pytest tests/test_web_marks.py -q` → PASS.
- [ ] **Step 5:** `git add -A && git commit -m "feat: /marked, everything with one mark on one page"`

---

### Task 8: el selector de marca en las tarjetas y en la nota

**Files:**
- Modify: `src/oknowledge/web/templates/mark-picker.html`, `library.html`, `ocio.html`, `ideas.html`, `item.html`, `static/style.css`, `i18n.py`
- Test: `tests/test_web_marks.py`

**Interfaces:**
- Consumes: `marks`, `here`, `note`.

- [ ] **Step 1: tests que fallan:**

```python
@pytest.mark.parametrize("path, link_id", [("/", LINK), ("/ocio", CARD), ("/ideas", IDEA),
                                           (f"/item/{LINK}", LINK)])
def test_every_card_and_note_page_has_the_picker(client, path, link_id):
    body = client.get(path).text
    assert f'action="/item/{link_id}/mark"' in body
    assert body.count('value="⭐"') >= 1


@pytest.mark.parametrize("path", ["/", "/ocio", "/ideas"])
def test_each_card_has_an_anchor_to_come_back_to(client, path):
    assert re.search(r'<li class="card[^"]*" id="card-[0-9a-f]{12}"', client.get(path).text)


def test_the_picker_sends_you_back_where_you_were(client):
    body = client.get("/?category=Redes").text
    assert 'name="back" value="/?category=Redes"' in body


def test_tapping_the_mark_you_have_takes_it_off(client):
    client.post(f"/item/{LINK}/mark", data={"mark": "⭐", "back": "/"})
    body = client.get("/").text
    assert re.search(r'name="mark" value=""[^>]*aria-pressed="true"[^>]*>⭐', body)


def test_the_picker_is_not_inside_the_popup_link(client):
    body = client.get("/").text
    for block in re.findall(r'<a class="body".*?</a>', body, re.S):
        assert "/mark" not in block
```

- [ ] **Step 2:** `PY -m pytest tests/test_web_marks.py -k "picker or anchor or tapping" -q` → FAIL.

- [ ] **Step 3: implementación.** `mark-picker.html`:

```html
{# One emoji, yours. A <details> so it costs nothing until it is opened, and
   forms and not a script, so it works with JavaScript off. Tapping the mark
   you already have sends "" and takes it off. #}
<details class="mark">
  <summary title="{{ t('Mark') }}" aria-label="{{ t('Mark') }}">
    {%- if note.mark %}<span class="has">{{ note.mark }}</span>{% else %}<span class="none">＋</span>{% endif -%}
  </summary>
  <div class="mark-menu">
    <form action="/item/{{ note.id|slug }}/mark" method="post" class="mark-list">
      <input type="hidden" name="back" value="{{ here }}">
      {% for m in marks %}
        {% if m == note.mark %}
          <button type="submit" name="mark" value="" class="on" aria-pressed="true"
                  title="{{ t('Remove') }}">{{ m }}</button>
        {% else %}
          <button type="submit" name="mark" value="{{ m }}">{{ m }}</button>
        {% endif %}
      {% endfor %}
    </form>
    <form action="/item/{{ note.id|slug }}/mark" method="post" class="mark-other">
      <input type="hidden" name="back" value="{{ here }}">
      <input name="mark" maxlength="16" autocomplete="off" required
             aria-label="{{ t('Another emoji') }}" placeholder="{{ t('Another emoji') }}">
      <button type="submit">{{ t('OK') }}</button>
      {% if note.mark %}
        <button type="submit" name="mark" value="" formnovalidate>{{ t('Remove') }}</button>
      {% endif %}
    </form>
  </div>
</details>
```

(El "Quitar" del segundo form manda dos `mark`: el del campo vacío y el del botón, `""`. FastAPI toma el primero, que también es vacío con `formnovalidate`. Si el test muestra lo contrario, mové "Quitar" al primer form.)

En `library.html`, `ocio.html`, `ideas.html`: el `<li class="card...">` lleva `id="card-{{ note.id }}"` y la primera línea dentro del `<li>` (en library, después del bloque `{% if picking %}`) es `{% include "mark-picker.html" %}`.

En `item.html`, envolvé el `<h1>`:

```html
    <div class="title-row">
      <h1 dir="auto">{{ note.title or t('Untitled idea') }}</h1>
      {% include "mark-picker.html" %}
    </div>
```

i18n (`STRINGS["es"]`): `"Mark": "Marcar"`, `"Another emoji": "Otro emoji"`, `"Remove": "Quitar"`, `"OK": "OK"` (sólo si alguna no existe ya; buscá antes con `grep -n '"Remove"' src/oknowledge/i18n.py`).

CSS (al final de `style.css`):

```css
/* The mark: a corner of the card, above the cover, out of the popup's link. */
.card { position: relative; }
.card > .mark { position: absolute; top: 0.4rem; right: 0.4rem; z-index: 2; }
.mark > summary { list-style: none; cursor: pointer; display: grid; place-items: center;
                  min-width: 2.2rem; min-height: 2.2rem; border-radius: 999px;
                  background: var(--card); border: 1px solid var(--line); font-size: 1.1rem; }
.mark > summary::-webkit-details-marker { display: none; }
.mark .none { color: var(--dim); opacity: 0.6; font-size: 0.95rem; }
.card > .mark:not([open]) .none { opacity: 0; }
.card:hover > .mark .none, .card > .mark:focus-within .none { opacity: 0.6; }
.mark-menu { position: absolute; right: 0; top: calc(100% + 0.3rem); width: 15rem;
             background: var(--card); border: 1px solid var(--line); border-radius: 12px;
             padding: 0.5rem; box-shadow: 0 8px 24px rgb(0 0 0 / 0.18); }
.mark-list { display: grid; grid-template-columns: repeat(6, 1fr); gap: 0.2rem; }
.mark-list button { font-size: 1.25rem; min-height: 2.75rem; padding: 0; border-color: transparent; }
.mark-list button.on { border-color: var(--accent); }
.mark-other { display: flex; gap: 0.3rem; margin-top: 0.4rem; }
.mark-other input { flex: 1; min-width: 0; }
.title-row { display: flex; align-items: flex-start; gap: 0.6rem; }
.title-row h1 { flex: 1; }
.title-row .mark { position: relative; margin-top: 0.5rem; }
@media (hover: none) { .card > .mark .none { opacity: 0.6; } }
@media (max-width: 42rem) { .mark > summary { min-width: 2.75rem; min-height: 2.75rem; } }
```

- [ ] **Step 4:** `PY -m pytest tests/test_web_marks.py tests/test_web_read.py tests/test_web_cards.py tests/test_web_ideas_page.py tests/test_web_ocio_page.py tests/test_i18n.py -q` → PASS.
- [ ] **Step 5:** `git add -A && git commit -m "feat: a mark picker on every card and on the note page"`

---

### Task 9: la cabecera en el celular

**Files:**
- Create: `src/oknowledge/web/static/layout.js`
- Modify: `templates/base.html`, `static/style.css`, `i18n.py`
- Test: `tests/test_web_layout.py` (nuevo)

- [ ] **Step 1: tests que fallan.** `tests/test_web_layout.py` (con los mismos fixtures `state_tree`, `cfg` con una nota y `client` que `tests/test_web_marks.py`; copialos, no los importes):

```python
def test_the_paste_box_folds_into_a_plus(client):
    body = client.get("/").text
    assert re.search(r'<details class="paste" open>\s*<summary[^>]*>＋</summary>', body)
    assert 'action="/add"' in body


def test_saving_everything_is_called_complete_not_all(client, isolated_ui_language):
    from oknowledge.i18n import STRINGS
    assert STRINGS["es"]["Full"] == "Completo"


def test_every_page_loads_the_layout_script(client):
    assert '<script src="/static/layout.js"></script>' in client.get("/").text


def test_the_layout_script_closes_and_unfocuses_on_a_phone():
    from oknowledge.web.app import WEB
    js = WEB.joinpath("static", "layout.js").read_text(encoding="utf-8")
    assert "(max-width: 42rem)" in js
    assert "details.filters" in js and "details.paste" in js and "blur" in js
```

- [ ] **Step 2:** `PY -m pytest tests/test_web_layout.py -q` → FAIL.

- [ ] **Step 3: implementación.** En `base.html`, reemplazar `<form class="paste" ...>...</form>` por:

```html
    <details class="paste" open>
      <summary title="{{ t('Paste a link') }}" aria-label="{{ t('Paste a link') }}">＋</summary>
      <form class="paste-form" action="/add" method="post">
        <input type="text" inputmode="url" name="url" autocomplete="off"
               placeholder="https://…" aria-label="{{ t('Paste a link') }}">
        <button type="submit" name="content" value="full">{{ t('Full') }}</button>
        <button type="submit" name="content" value="summary">{{ t('Summary') }}</button>
      </form>
    </details>
```

(conservá el comentario `{# The box the bar panel is on Omarchy ... #}` encima). Antes de `{% block scripts %}`: `<script src="/static/layout.js"></script>` (sin `defer`: tiene que correr antes del primer dibujo).

`i18n.py`: `"Full": "Completo",`.

`static/layout.js`:

```js
// The phone layout: what the CSS cannot do by itself.
//
// A <details> drawn open cannot be closed by a stylesheet, so on a narrow
// screen this closes the filters and the paste box, and keeps the search
// box from pulling the keyboard up the moment a page opens. Without this
// file everything stays open, which is how the pages were before it.
(function () {
  "use strict";
  var phone = window.matchMedia("(max-width: 42rem)");
  function fold(open) {
    document.querySelectorAll("details.filters, details.paste").forEach(function (d) {
      d.open = open;
    });
  }
  function settle() {
    if (!phone.matches) return;
    fold(false);
    var search = document.querySelector("header input[type=search]");
    if (search) { search.removeAttribute("autofocus"); search.blur(); }
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", settle);
  } else {
    settle();
  }
  // Turned sideways into a wide screen: nothing may stay hidden behind a
  // summary the desktop layout does not draw.
  phone.addEventListener("change", function (event) {
    if (!event.matches) fold(true);
  });
})();
```

CSS: cambiar las reglas `.paste`, `.paste input`, `header .paste input`, `.paste button` por `.paste-form` (mismas declaraciones), y agregar:

```css
details.paste { flex: 1 1 100%; }
details.paste > summary { display: none; }
@media (max-width: 42rem) {
  header { padding: 0.8rem 1rem 0.4rem; gap: 0.5rem 0.6rem; }
  header form[role="search"] { flex: 1 1 8rem; }
  details.paste { flex: 0 0 auto; order: 2; }
  details.paste > summary { display: grid; place-items: center; list-style: none;
                            width: 2.75rem; height: 2.75rem; border-radius: 9px;
                            border: 1px solid var(--line); background: var(--card);
                            cursor: pointer; font-size: 1.2rem; }
  details.paste > summary::-webkit-details-marker { display: none; }
  details.paste[open] { flex: 1 1 100%; }
  details.paste[open] > summary { margin-bottom: 0.5rem; }
  header nav { order: 3; flex: 1 1 100%; display: flex; overflow-x: auto;
               white-space: nowrap; scrollbar-width: none; }
  header nav a { margin-left: 0; padding: 0.7rem 0.6rem; }
}
```

Corré `tests/test_web_add.py::...paste input` (busca `".paste input"` en el CSS): si falla, cambiá la aserción a `".paste-form input"` — es el mismo contrato con el nombre nuevo. Ledger: Ruling.

- [ ] **Step 4:** `PY -m pytest tests/test_web_layout.py tests/test_web_add.py tests/test_i18n.py -q` → PASS.
- [ ] **Step 5:** `git add -A && git commit -m "feat: on a phone the header is one row and a plus"`

---

### Task 10: filtros colapsables (librería, ocio, ideas)

**Files:**
- Modify: `templates/library.html`, `templates/ocio.html`, `templates/ideas.html`, `static/style.css`, `i18n.py`
- Test: `tests/test_web_layout.py`

- [ ] **Step 1: tests que fallan:**

```python
@pytest.mark.parametrize("path", ["/", "/ocio", "/ideas"])
def test_the_filters_fold_into_one_line(client, path):
    body = client.get(path).text
    assert re.search(r'<details class="filters" open>\s*<summary', body)


def test_the_summary_says_what_is_on(client):
    body = client.get("/?category=Redes").text
    summary = re.search(r'<details class="filters" open>\s*<summary[^>]*>(.*?)</summary>',
                        body, re.S).group(1)
    assert "Redes" in summary


def test_select_moved_into_the_summary(client):
    body = client.get("/").text
    summary = re.search(r'<details class="filters" open>\s*<summary[^>]*>(.*?)</summary>',
                        body, re.S).group(1)
    assert "pick-mode" in summary
```

(El `cfg` de este archivo tiene un link en la categoría "Redes".)

- [ ] **Step 2:** `PY -m pytest tests/test_web_layout.py -k filters -q` → FAIL.

- [ ] **Step 3: implementación.** En `library.html`, envolvé desde `{% if collections %}` hasta el `{% endif %}` de `tag_groups` en:

```html
    <details class="filters" open>
      <summary>
        <span>{{ t('Filters') }} · {{ collection or category or ('#' ~ tag if tag else t('All')) }}</span>
        {# Here and not on a line of its own: it is a link most visits never use. #}
        <a class="pick-mode" href="{% if picking %}{{ cancel_url }}{% else %}{{ pick_url }}{% endif %}"
           >{{ t('Cancel') if picking else t('Select') }}</a>
      </summary>
      ...los chips, sin el <a class="pick-mode"> que estaba en la fila de categorías...
    </details>
```

En `ocio.html`: los dos bloques `.chips` dentro de `<details class="filters" open><summary><span>{{ t('Filters') }} · {{ t(dict(KINDS).get(kind, 'All')) if kind else t('All') }}</span></summary> ... </details>`. Si `KINDS` no es un dict-able de pares, usá `{% for name, label in KINDS %}{% if name == kind %}{{ t(label) }}{% endif %}{% endfor %}` dentro del span, con `t('All')` si no hay `kind`.

En `ideas.html`: los chips de estado y etiquetas dentro de `<details class="filters" open><summary><span>{{ t('Filters') }} · {{ ('#' ~ tag) if tag else t('All') }}</span></summary> ... </details>`. El `<details class="new-idea">` queda como está: ya arranca cerrado cuando hay ideas (Ruling: la spec lo pide y ya se cumple).

i18n: `"Filters": "Filtros"`.

CSS:

```css
details.filters { margin-bottom: 0.6rem; }
details.filters > summary { display: flex; align-items: center; justify-content: space-between;
                            gap: 1rem; cursor: pointer; list-style: none;
                            color: var(--dim); font-size: 0.85rem; padding: 0.3rem 0; }
details.filters > summary::-webkit-details-marker { display: none; }
details.filters > summary > span::before { content: "▸ "; }
details.filters[open] > summary > span::before { content: "▾ "; }
@media (min-width: 42.01rem) {
  details.filters > summary > span { visibility: hidden; }
}
@media (max-width: 42rem) {
  details.filters > summary { min-height: 2.75rem; font-size: 0.95rem; }
  .chips .chip { padding-top: 0.55rem; padding-bottom: 0.55rem; }
}
```

(En el escritorio el resumen sólo lleva "Seleccionar", alineado a la derecha; el texto queda oculto pero ocupa su lugar para que el link no salte.)

- [ ] **Step 4:** `PY -m pytest tests/test_web_layout.py tests/test_web_read.py tests/test_web_write.py tests/test_web_ocio_page.py tests/test_web_ideas_page.py tests/test_i18n.py -q` → PASS. Tests existentes que buscan `pick-mode` en otro lugar: ajustá el selector, no el comportamiento, y anotalo como Ruling.
- [ ] **Step 5:** `git add -A && git commit -m "feat: the filters fold into one line, closed on a phone"`

---

### Task 11: línea de tiempo, tarjetas y objetivos táctiles en el celular

**Files:**
- Modify: `templates/library.html`, `static/style.css`
- Test: `tests/test_web_layout.py`

- [ ] **Step 1: tests que fallan:**

```python
def test_a_break_comes_before_the_first_month_only(client, cfg):
    body = client.get("/?when=2026").text
    nav = re.search(r'<nav class="timeline".*?</nav>', body, re.S).group(0)
    assert nav.count('<i class="break"') == 1
    assert nav.index('<i class="break"') < nav.index('class="month')


def test_no_year_open_no_break(client):
    nav = re.search(r'<nav class="timeline".*?</nav>', client.get("/").text, re.S).group(0)
    assert '<i class="break"' not in nav


def test_the_phone_css_puts_the_months_on_their_own_row():
    from oknowledge.web.app import WEB
    css = WEB.joinpath("static", "style.css").read_text(encoding="utf-8")
    assert ".timeline .break" in css and "order: 1" in css
    assert "-webkit-line-clamp: 4" in css
```

- [ ] **Step 2:** `PY -m pytest tests/test_web_layout.py -k "break or months" -q` → FAIL.

- [ ] **Step 3: implementación.** En `library.html`, dentro de `{% if when and year == when[:4] %}`, antes del `{% for month in months %}`: `<i class="break" aria-hidden="true"></i>`.

CSS: `.timeline .break { display: none; }` fuera del media query, y dentro del `@media (max-width: 42rem)` existente de la línea de tiempo (línea ~134), reemplazar `overflow-x: auto` de `.timeline` por `flex-wrap: wrap; overflow: visible;` y agregar:

```css
  .timeline .break { display: block; flex-basis: 100%; height: 0; order: 1; }
  .timeline .month { order: 1; }
  .timeline a, .timeline span { padding: 0.55rem 0.6rem; }
```

Tarjetas, al final del archivo:

```css
@media (max-width: 42rem) {
  /* One column: a fixed height only buys empty space under short cards. */
  .card { height: auto; }
  .card .sum { flex: none; display: -webkit-box; -webkit-box-orient: vertical;
               -webkit-line-clamp: 4; overflow: hidden; }
  .card .body { flex: none; }
}
```

- [ ] **Step 4:** `PY -m pytest tests/test_web_layout.py tests/test_web_read.py -q` → PASS (los tests de `strip()` siguen pasando: el corte es `<i>`, no `<a>` ni `<span>`).
- [ ] **Step 5:** `git add -A && git commit -m "feat: on a phone the months get a row of their own and cards lose their empty space"`

---

### Task 12: Categorías en grilla

**Files:**
- Modify: `templates/categories.html`, `static/style.css`, `i18n.py`
- Test: `tests/test_web_layout.py`

- [ ] **Step 1: tests que fallan:**

```python
def test_categories_are_a_grid_not_rows(client):
    body = client.get("/categories").text
    assert '<ul class="cat-grid">' in body and 'class="hits"' not in body


def test_each_category_renames_from_its_own_card(client):
    body = client.get("/categories").text
    card = re.search(r'<li class="cat-card">.*?</li>', body, re.S).group(0)
    assert 'href="/?category=Redes"' in card
    assert re.search(r"<details>\s*<summary[^>]*>✎</summary>", card)
    assert 'name="old" value="Redes"' in card and 'list="known"' in card
```

- [ ] **Step 2:** `PY -m pytest tests/test_web_layout.py -k categor -q` → FAIL.

- [ ] **Step 3: implementación.** `categories.html`, la lista pasa a:

```html
    <ul class="cat-grid">
      {% for name, count in categories.items() %}
        <li class="cat-card">
          <a class="cat-name" href="/?category={{ name|urlencode }}">
            <span>{{ name }}</span><b>{{ count }}</b>
          </a>
          {# Out of the way until wanted: renaming is rare, reading is not. #}
          <details>
            <summary title="{{ t('Rename') }} / {{ t('Merge into') }}"
                     aria-label="{{ t('Rename') }} / {{ t('Merge into') }}">✎</summary>
            <form action="/categories/rename" method="post" class="row">
              <input type="hidden" name="old" value="{{ name }}">
              <input name="new" list="known" required value="{{ name }}"
                     aria-label="{{ t('Rename') }} / {{ t('Merge into') }}">
              <button type="submit">{{ t('Save') }}</button>
            </form>
          </details>
        </li>
      {% endfor %}
    </ul>
```

CSS:

```css
.cat-grid { list-style: none; padding: 0; margin: 1rem 0; display: grid; gap: 0.6rem;
            grid-template-columns: repeat(auto-fill, minmax(11rem, 1fr)); }
.cat-card { position: relative; background: var(--card); border: 1px solid var(--line);
            border-radius: 12px; padding: 0.8rem 2.6rem 0.8rem 0.9rem; }
.cat-name { display: flex; flex-direction: column; text-decoration: none; color: var(--fg); }
.cat-name b { font-size: 1.4rem; font-weight: 600; color: var(--dim); }
.cat-card > details > summary { position: absolute; top: 0.4rem; right: 0.4rem;
                                list-style: none; cursor: pointer; color: var(--dim);
                                width: 2.2rem; height: 2.2rem; display: grid; place-items: center;
                                border-radius: 8px; }
.cat-card > details > summary::-webkit-details-marker { display: none; }
.cat-card > details[open] { margin-top: 0.6rem; }
.cat-card > details .row { padding: 0; }
@media (max-width: 42rem) { .cat-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
```

- [ ] **Step 4:** `PY -m pytest tests/test_web_layout.py tests/test_web_write.py -k "categor" -q` → PASS.
- [ ] **Step 5:** `git add -A && git commit -m "feat: categories as a grid of small cards, rename behind a pencil"`

---

### Task 13: lo que se esconde en el hover, Ajustes, avisos, foco, estrellas

**Files:**
- Modify: `static/style.css`, `templates/base.html`, `templates/settings.html`
- Test: `tests/test_web_layout.py`

- [ ] **Step 1: tests que fallan:**

```python
def css():
    from oknowledge.web.app import WEB
    return WEB.joinpath("static", "style.css").read_text(encoding="utf-8")


def test_on_a_touch_screen_the_actions_are_always_there():
    assert re.search(r"@media \(hover: none\)\s*\{[^}]*\.actions\s*\{\s*opacity: 1", css())


def test_focus_is_always_visible():
    assert ":focus-visible" in css() and "--focus" in css()


def test_the_unreadable_notice_keeps_the_path_out_of_sight(tmp_path, client, cfg):
    (cfg.root / "links" / "roto.md").write_text("---\noknowledge: 1\n---\n", encoding="utf-8")
    body = client.get("/").text
    notice = re.search(r'<p class="quiet"[^>]*>(.*?)</p>', body, re.S)
    assert str(cfg.links_dir) not in notice.group(1)
    assert f'title="{cfg.links_dir}"' in notice.group(0)
```

- [ ] **Step 2:** `PY -m pytest tests/test_web_layout.py -k "touch or focus or unreadable" -q` → FAIL.

- [ ] **Step 3: implementación.**

CSS:

```css
@media (hover: none) { .actions { opacity: 1; } }
```

En `:root` (claro) agregar `--focus: #3b5bdb;` y en el oscuro `--focus: #a3b2d4;`, y:

```css
a:focus-visible, button:focus-visible, summary:focus-visible, input:focus-visible,
select:focus-visible, textarea:focus-visible, .chip:focus-visible {
  outline: 2px solid var(--focus); outline-offset: 2px;
}
@media (max-width: 42rem) {
  .mine .stars button { min-width: 2.75rem; min-height: 2.75rem; font-size: 1.4rem; }
}
```

En `base.html` (línea ~40), el aviso de ilegibles pasa a `<p class="quiet" title="{{ links_dir }}">{% if unreadable == 1 %}{{ t('1 note could not be read and is not shown') }}{% else %}{{ t('%1 notes could not be read and are not shown', unreadable) }}{% endif %}</p>`. En `STRINGS["es"]`, reemplazá las dos claves con `(%1)`/`(%2)` por estas dos, sin la ruta, con la misma traducción sin el paréntesis. Ajustá `test_the_unreadable_count_is_plural_and_translated` y `test_an_unreadable_vault_renders_a_page_with_the_path` si comparan el texto exacto: el contrato es el mismo con la ruta en el `title` (Ruling).

Ajustes: en `templates/settings.html`, el `<p class="row">` de cada motor (dentro de `{% for name in engines %}`) pasa a `<p class="row engine-row">`; tilde, modelo y botón ya están en él. El `<span class="meta">` de "Looked up" va a la fila completa:

```css
.engine-row { display: grid; grid-template-columns: auto 1fr auto; gap: 0.5rem;
              align-items: center; padding: 0.4rem 0; }
.engine-row .meta { grid-column: 1 / -1; }
@media (max-width: 42rem) { .engine-row { grid-template-columns: auto 1fr; }
                            .engine-row button { grid-column: 1 / -1; }
                            .providers label { display: flex; align-items: center;
                                               min-height: 2.75rem; } }
```

(Sin cambiar `name`s ni `value`s de ningún input: `tests/test_web_settings.py` es el contrato.)

- [ ] **Step 4:** `PY -m pytest -q` (suite completa) → PASS.
- [ ] **Step 5:** `git add -A && git commit -m "fix: actions on touch screens, visible focus, compact engines, quieter notices"`

---

### Task 14: verificación visual

**Files:**
- Ninguno del repo (scripts en el scratchpad).

- [ ] **Step 1:** Vault de prueba: el generador `$SP/uxdemo/make.py` y `$SP/uxdemo/serve.py` del brainstorming (70 links, 6 fichas, 3 ideas, puerto 8811; `SP=/tmp/claude-1000/-home-fer-Projects-gym/d89ecc8a-2029-44cb-b47f-742ed00daeae/scratchpad`). Si no existen, recrealos: notas con `id: '...'` entre comillas (un id sólo de dígitos se lee como número y la nota no se lee). Marcá 5 notas con `mark:` en el frontmatter.
- [ ] **Step 2:** Servidor: verificá el PID con `ps -p <pid> -o cmd=` antes de matar cualquier proceso; nunca `pkill -f`.
- [ ] **Step 3:** Capturas con `chromium --headless=new --hide-scrollbars --window-size=390,1800` y `1366,1100`, de `/`, `/?when=2025`, `/categories`, `/ocio`, `/ideas`, `/settings`, `/import`, `/retry`, `/marked?mark=⭐`, una nota, una ficha, una idea; y `/ocio/buscar?q=dune` si responde sin red (si no, saltéalo y anotalo). Repetí `/` y `/categories` con `--force-dark-mode` y sin él.
- [ ] **Step 4:** Mirá cada captura. Criterios: sin scroll horizontal a 390px; la primera tarjeta de `/` visible sin bajar más de ~350px; los meses de 2025 visibles al abrir el año; Categorías en dos columnas; el ＋ de la cabecera cerrado; las acciones de la nota visibles. Lo que falle se corrige con un test que lo pruebe primero (si se puede expresar en HTML/CSS) y se commitea como `fix:`.
- [ ] **Step 5:** `PY -m pytest -q` → PASS. Matá el servidor por PID.
