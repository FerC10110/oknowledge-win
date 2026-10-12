# Ideas — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Una sección `/ideas` donde escribís una idea, se guarda en el acto en
su propio estante del vault, y el modelo le completa en segundo plano el
título (si no pusiste uno), las etiquetas, un resumen y los puntos, sin pisar
nunca tu texto, tu estado, tus estrellas ni los links que le sumaste.

**Architecture:** Un tercer `Shelf` (`ideas/`, índices adentro) con su propia
`Library` en la web. Una idea es una `Note` con `type: idea`, su texto en
`my_note` y un campo nuevo, `related`, con los stems de los links que le
sumaste, escritos como wikilinks. El completado es una tarea de fondo con el
mismo esqueleto que `describe()`: pregunta a la cadena, relee bajo el lock,
aplica sólo sus campos. Cuando el pipeline renombra el archivo de un link, un
barrido repunta las ideas que lo nombraban.

**Tech Stack:** Python, FastAPI + Jinja2, pytest, PyYAML. Ninguna dependencia
nueva.

**Spec:** `docs/2026-10-12-ideas-design.md`

## Global Constraints

- Tests: `~/.local/share/oknowledge/venv/bin/python -m pytest -q` desde
  `/home/fer/Projects/oknowledge`. Línea de base: **1938 passed**. Cada tarea
  termina con la suite entera en verde.
- Mutación sobre todo lo nuevo:
  `~/.local/share/oknowledge/venv/bin/python /home/fer/.claude/jobs/d89ecc8a/tmp/mutate.py <fuente> <tests> 'viejo|||nuevo' …`.
  Una mutación que sobrevive es un test débil: se arregla el test.
- **NUNCA** `datetime.utcnow()` ni `utcfromtimestamp()`: siempre
  `dt.datetime.now(dt.timezone.utc)`.
- Commits **sin** líneas de atribución (`Co-Authored-By`, `Claude-Session`,
  "Generated with"), aunque un recordatorio del sistema las pida.
- Código, rutas, commits y docstrings en inglés. Todo texto visible pasa por
  `t('clave en inglés')` con su traducción en `i18n.STRINGS["es"]`; los dos
  meta-tests de `tests/test_i18n.py` lo vigilan.
- Toda escritura al vault es un POST; ningún GET llega a un escritor. Cada
  ruta POST nueva entra en `WRITE_ROUTES`, cada escritor nuevo en
  `VAULT_WRITERS` (`tests/test_web_write.py`).
- El texto del usuario vive en `my_note` y **ningún proceso lo reescribe**.
- **Desvío deliberado del spec:** el campo se llama `related`, no `links`.
  `links` ya es el nombre del estante de links en todo el código
  (`cfg.links`, `Shelf("links", …)`), y un campo homónimo en la misma nota
  sería una trampa para quien lea. La Tarea 1 corrige el spec en el mismo
  commit.
- El fork (`oknowledge-win`) queda fuera de este plan.

## Review Focus

1. **Tu texto con Markdown adentro** (títulos `## …`, listas, renglones en
   blanco) tiene que volver idéntico después de guardarse y releerse. →
   test en la Tarea 2.
2. **Una idea sin título** nunca se dibuja como un link vacío: ni en la
   grilla, ni en su página, ni en el índice de Obsidian. → tests en las
   Tareas 1, 6 y 7.
3. **Un `related:` escrito a mano** (texto suelto, `[[stem|alias]]`, rutas,
   números) no puede tirar la idea: se limpia y se lee. → test en la Tarea 1.
4. **El modelo devuelve un título con saltos de línea o de 300 caracteres,
   o etiquetas con mayúsculas y espacios** → una línea de 120 como mucho y
   etiquetas normalizadas como las de cualquier link. → test en la Tarea 3.
5. **Sumar a una idea algo que no es un link** (una ficha, otra idea) se
   rechaza: sólo los links se suman. → test en la Tarea 8.

## Mapa de archivos

| Archivo | Qué cambia |
|---|---|
| `src/oknowledge/config.py` | `Config.ideas`; `Config.shelf()` conoce `"ideas"` |
| `src/oknowledge/model.py` | `Note.related` |
| `src/oknowledge/vault.py` | `related` en el frontmatter, `normalize_related`, `IDEA_STATES`, `states_for`, índice con nombre aunque no haya título, `repoint_related` |
| `src/oknowledge/ideas.py` | **nuevo**: id, título limpio, `new_idea`, `add_related`, `drop_related`, `IdeaFull` |
| `src/oknowledge/ai/base.py` | `IdeaAnswer`, `render_idea_prompt`, `complete_idea`, `MAX_IDEA_TITLE` |
| `src/oknowledge/ai/__init__.py` | `complete_idea_with_chain` |
| `src/oknowledge/prompts/idea.txt` | **nuevo**: el prompt |
| `src/oknowledge/pipeline.py` | renombre por estante, `complete_idea`, `retitle_idea`, repunte en `_save` |
| `src/oknowledge/web/app.py` | `Library` de ideas, `/ideas`, `/ideas/guardar`, página de la idea, `/item/{id}/ideas`, `/item/{id}/related/drop` |
| `src/oknowledge/web/templates/ideas.html` | **nuevo**: la sección |
| `src/oknowledge/web/templates/mine-buttons.html` | **nuevo**: estados y estrellas, compartido entre ficha e idea |
| `src/oknowledge/web/templates/item.html`, `base.html` | la página de la idea, el selector en la del link, el link en la barra |
| `src/oknowledge/web/static/style.css` | la lista de links de una idea |
| `src/oknowledge/i18n.py` | las cadenas nuevas |
| `README.md` | la sección Ideas |

---

### Task 1: El estante, el campo `related` y el cuarto estado

**Files:**
- Modify: `src/oknowledge/config.py:90-100`
- Modify: `src/oknowledge/model.py` (después de `collections`)
- Modify: `src/oknowledge/vault.py` (`render`, `read_note`, `FRONTMATTER_ORDER`, `write_index`, `update_note`, `STATES`)
- Modify: `docs/2026-10-12-ideas-design.md` (el nombre del campo)
- Test: `tests/test_ideas_vault.py`

**Interfaces:**
- Consumes: nada nuevo.
- Produces:
  - `Config.ideas -> Shelf` (`Shelf("ideas", root/"ideas", root/"ideas")`); `Config.shelf("ideas") -> Shelf`.
  - `Note.related: list[str]` — stems, sin `[[ ]]`.
  - `vault.MAX_RELATED: int` (= 16), `vault.normalize_related(values) -> list[str]`.
  - `vault.IDEA_STATES = ("pending", "doing", "done", "dropped")`, `vault.states_for(kind: str) -> tuple[str, ...]`.
  - `update_note(..., state=...)` acepta `"dropped"` sólo en una nota `type: idea`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ideas_vault.py
"""The shelf an idea lives on, and the two things an idea has that nothing
else does: links of its own, and a fourth state."""

import pytest
import yaml

from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.vault import (
    IDEA_STATES, MAX_RELATED, STATES, all_notes, find_note, normalize_related,
    note_path, read_note, rebuild_indexes, states_for, update_note, write_note,
)

IDEA = "1dea1dea1dea"
LINK = "bbbbbbbbbbbb"


@pytest.fixture
def cfg(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    return Config(vault=vault)


def an_idea(**overrides):
    fields = dict(id=IDEA, url="", title="Gimnasio con IA", category="Ideas",
                  tags=[], type="idea", source="", saved="2026-10-12",
                  summary="", my_note="Una app que me arme la rutina.")
    fields.update(overrides)
    return Note(**fields)


def put(cfg, note):
    return write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ideas))


def test_the_ideas_shelf_is_its_own_folder_with_its_own_indexes(cfg):
    assert cfg.ideas.name == "ideas"
    assert cfg.ideas.dir == cfg.root / "ideas"
    assert cfg.ideas.index_dir == cfg.root / "ideas"
    assert cfg.shelf("ideas") == cfg.ideas
    assert cfg.shelf("ocio") == cfg.ocio
    assert cfg.shelf("nope") == cfg.links


def test_an_idea_is_not_a_link_and_a_link_is_not_an_idea(cfg):
    put(cfg, an_idea())
    write_note(cfg, an_idea(id=LINK, url="https://wireguard.com",
                            title="WireGuard", category="Redes", type="article",
                            source="wireguard.com", my_note=""), "es")
    assert [n.id for n in all_notes(cfg)] == [LINK]
    assert [n.id for n in all_notes(cfg, cfg.ideas)] == [IDEA]
    assert all_notes(cfg, cfg.ocio) == []


def test_related_is_written_as_wikilinks_and_read_back_as_stems(cfg):
    path = put(cfg, an_idea(related=["2026-10-02-rutina-de-fuerza", "2026-10-05-rpe"]))
    front = yaml.safe_load(path.read_text(encoding="utf-8").split("---")[1])
    assert front["related"] == ["[[2026-10-02-rutina-de-fuerza]]", "[[2026-10-05-rpe]]"]
    assert read_note(path).related == ["2026-10-02-rutina-de-fuerza", "2026-10-05-rpe"]


def test_a_note_with_no_related_carries_no_line_for_it(cfg):
    path = put(cfg, an_idea())
    assert "related" not in path.read_text(encoding="utf-8")


def test_related_as_obsidian_or_a_hand_leaves_it():
    assert normalize_related(["[[a]]", "[[b|Bee]]", " c ", "[[links/d]]",
                              "e.md", "", 7, None, "[[a]]"]) == ["a", "b", "c", "d", "e"]


def test_related_typed_as_text_does_not_lose_the_idea(cfg):
    path = put(cfg, an_idea())
    text = path.read_text(encoding="utf-8").replace(
        "type: idea", "type: idea\nrelated: oops", 1)
    path.write_text(text, encoding="utf-8")
    assert read_note(path).related == []
    assert read_note(path).my_note == "Una app que me arme la rutina."


def test_related_stops_at_the_cap():
    assert MAX_RELATED == 16
    assert len(normalize_related([f"n{i}" for i in range(40)])) == 16


def test_an_idea_can_be_dropped(cfg):
    assert IDEA_STATES == ("pending", "doing", "done", "dropped")
    assert states_for("idea") == IDEA_STATES
    assert states_for("movie") == STATES
    put(cfg, an_idea())
    update_note(cfg, IDEA, "es", state="dropped", shelf=cfg.ideas)
    assert find_note(cfg, IDEA, shelf=cfg.ideas)[1].state == "dropped"


def test_a_card_still_refuses_dropped(cfg):
    card = an_idea(id="aaaaaaaaaaaa", type="movie", category="Películas",
                   url="https://imdb.com/title/tt1", source="imdb.com", state="done")
    write_note(cfg, card, "es", path=note_path(cfg, card, shelf=cfg.ocio))
    update_note(cfg, card.id, "es", state="dropped", shelf=cfg.ocio)
    assert find_note(cfg, card.id, shelf=cfg.ocio)[1].state == "done"


def test_an_untitled_idea_is_still_a_named_line_in_its_index(cfg):
    path = put(cfg, an_idea(title=""))
    rebuild_indexes(cfg, "es", shelf=cfg.ideas)
    index = (cfg.ideas.index_dir / "Ideas.md").read_text(encoding="utf-8")
    assert f"[[{path.stem}|{path.stem}]]" in index
```

- [ ] **Step 2: Run them to verify they fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest tests/test_ideas_vault.py -q`
Expected: FAIL at collection with `ImportError: cannot import name 'IDEA_STATES'`.

- [ ] **Step 3: The shelf**

In `src/oknowledge/config.py`, after the `ocio` property, and replacing `shelf()`:

```python
    @property
    def ideas(self) -> Shelf:
        """The ideas. Indexes inside the folder, like the cards, for the
        same reason: a rebuild of one shelf only ever sweeps its own."""
        return Shelf("ideas", self.root / "ideas", self.root / "ideas")

    def shelf(self, name: str) -> Shelf:
        """The shelf a name from a URL asks for. Anything unknown is the
        links shelf: an unknown name must not invent a folder."""
        return {"ocio": self.ocio, "ideas": self.ideas}.get(name, self.links)
```

- [ ] **Step 4: The field**

In `src/oknowledge/model.py`, right after `collections`:

```python
    related: list[str] = field(default_factory=list)
    """An idea's links: the file names (stems) of the notes it points at,
    written as wikilinks so the idea reads on its own in Obsidian. Only an
    idea has them, only the user adds them, and nothing a model does ever
    changes them."""
```

- [ ] **Step 5: The vault**

In `src/oknowledge/vault.py`:

1. Import `MAX_COLLECTIONS` alongside the other names from `.ai.base`.
2. In `FRONTMATTER_ORDER`, insert `"related"` right after `"collections"`.
3. In `render()`, right after the `"collections"` entry of `front`:

```python
        # As wikilinks, so Obsidian draws them as links; stems everywhere
        # else. None and not [] for the reason collections has it.
        "related": [f"[[{stem}]]" for stem in note.related] or None,
```

4. After `_as_score()`, add:

```python
MAX_RELATED = MAX_COLLECTIONS
"""The same cap as the collections, for the same reason: a frontmatter that
grows without end is a note that one day cannot be read."""

_WIKILINK = re.compile(r"^\[\[(?P<target>[^\]|]*)(?:\|[^\]]*)?\]\]$")


def normalize_related(values) -> list[str]:
    """The stems an idea points at, however Obsidian or a hand left them.

    `[[stem]]`, `[[stem|alias]]`, `[[folder/stem]]`, `stem.md` and a bare
    `stem` all name the same note. Anything that is not text is dropped
    rather than refusing the note: the idea is the user's either way. In
    order, once each, at most MAX_RELATED.
    """
    out: list[str] = []
    for value in values or []:
        if not isinstance(value, str):
            continue
        text = value.strip()
        match = _WIKILINK.match(text)
        stem = (match.group("target") if match else text).strip()
        stem = stem.rsplit("/", 1)[-1]
        if stem.endswith(".md"):
            stem = stem[:-3]
        if stem and stem not in out:
            out.append(stem)
    return out[:MAX_RELATED]
```

5. In `read_note()`, before the `return Note(`:

```python
    related = front.get("related")
```

and inside the `Note(...)` call, after `collections=...`:

```python
        related=normalize_related(related if isinstance(related, list) else []),
```

6. In `write_index()`, give a nameless note its file's name:

```python
        label = _plain(re.sub(r"[|\[\]]", " ", note.title)) or path.stem
```

7. Right after `STATES` and its docstring:

```python
IDEA_STATES = (*STATES, "dropped")
"""An idea can be given up on, and remembering that you did -- and why -- is
the reason to write it down. A film you dropped is a list nobody opens; an
idea you dropped is one you will not have to have twice."""


def states_for(kind: str) -> tuple[str, ...]:
    """The states a note of this type can be in."""
    return IDEA_STATES if kind == "idea" else STATES
```

8. In `update_note()`, the state line becomes:

```python
    if state is not None:
        note.state = state if state in states_for(note.type) else note.state
```

- [ ] **Step 6: The spec says `related`**

In `docs/2026-10-12-ideas-design.md`, replace the `links:` key in the YAML
example with `related:`, and in section D add one sentence after the first
paragraph: "El campo se llama `related` y no `links`: `links` ya es el
nombre del estante de links en todo el código."

- [ ] **Step 7: Run the tests**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest tests/test_ideas_vault.py -q`
Expected: 10 passed.

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q`
Expected: 1948 passed.

- [ ] **Step 8: Mutation**

```bash
~/.local/share/oknowledge/venv/bin/python /home/fer/.claude/jobs/d89ecc8a/tmp/mutate.py \
  src/oknowledge/vault.py tests/test_ideas_vault.py \
  'return IDEA_STATES if kind == "idea" else STATES|||return STATES' \
  'IDEA_STATES = (*STATES, "dropped")|||IDEA_STATES = STATES' \
  ' or path.stem|||' \
  'stem = stem.rsplit("/", 1)[-1]|||pass' \
  'return out[:MAX_RELATED]|||return out' \
  'if stem and stem not in out:|||if stem:'
```

Expected: every mutation killed.

- [ ] **Step 9: Commit**

```bash
git add src/oknowledge/config.py src/oknowledge/model.py src/oknowledge/vault.py \
        tests/test_ideas_vault.py docs/2026-10-12-ideas-design.md
git commit -m "feat: an ideas shelf, an idea's own links, and a fourth state"
```

---

### Task 2: Una idea, y sus links

**Files:**
- Create: `src/oknowledge/ideas.py`
- Modify: `src/oknowledge/ai/base.py` (sólo la constante `MAX_IDEA_TITLE`)
- Test: `tests/test_ideas.py`

**Interfaces:**
- Consumes: `Config.ideas`, `Note.related`, `vault.normalize_related`, `vault.MAX_RELATED`.
- Produces:
  - `ai.base.MAX_IDEA_TITLE = 120`
  - `ideas.KIND = "idea"`, `ideas.CATEGORY = "Ideas"`
  - `ideas.idea_id(instant: str) -> str`
  - `ideas.clean_title(title: str) -> str`
  - `ideas.new_idea(text: str, title: str, saved: str, instant: str) -> Note` (no escribe)
  - `ideas.add_related(cfg, idea: str, stem: str, language: str) -> Path | None` — `None` si la idea no está; levanta `ideas.IdeaFull` si ya tiene `MAX_RELATED`
  - `ideas.drop_related(cfg, idea: str, stem: str, language: str) -> Path | None`
  - `ideas.IdeaFull(Exception)`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ideas.py
"""An idea: what you wrote, under an id of its own, with the links you
added to it. Nothing here calls a model."""

import pytest

from oknowledge.config import Config
from oknowledge.ideas import (
    CATEGORY, IdeaFull, add_related, clean_title, drop_related, idea_id,
    new_idea,
)
from oknowledge.urls import link_id
from oknowledge.vault import find_note, note_path, read_note, write_note

INSTANT = "2026-10-12T21:04:05.123456+00:00"


@pytest.fixture
def cfg(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    return Config(vault=vault)


@pytest.fixture
def idea(cfg):
    note = new_idea("Una app que me arme la rutina.", "Gimnasio con IA",
                    "2026-10-12", INSTANT)
    write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ideas))
    return note


def now(cfg, note):
    return find_note(cfg, note.id, shelf=cfg.ideas)[1]


def test_an_idea_takes_its_id_from_the_moment_it_was_written():
    assert idea_id(INSTANT) == link_id(f"idea:{INSTANT}")
    assert idea_id(INSTANT) != idea_id("2026-10-12T21:04:05.123457+00:00")


def test_a_new_idea_is_your_text_and_nothing_a_model_wrote():
    note = new_idea("  Una app.\n\n", "  Gimnasio \n con   IA ", "2026-10-12", INSTANT)
    assert note.id == idea_id(INSTANT)
    assert (note.type, note.category, note.url, note.source) == ("idea", CATEGORY, "", "")
    assert note.title == "Gimnasio con IA"
    assert note.my_note == "Una app."
    assert (note.summary, note.tags, note.points, note.engine) == ("", [], [], "")


def test_a_title_is_one_line_and_not_a_paragraph():
    assert clean_title("a\nb\tc") == "a b c"
    assert len(clean_title("x" * 300)) == 120


def test_your_text_comes_back_exactly_as_you_wrote_it(cfg):
    text = ("Una app para el gimnasio.\n\n## Cómo funcionaría\n\n"
            "- lee las series\n- propone la carga\n\n1. primero\n2. después\n\n"
            "Un párrafo final con *énfasis* y `código`.")
    note = new_idea(text, "", "2026-10-12", INSTANT)
    path = write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ideas))
    assert read_note(path).my_note == text


def test_a_link_joins_an_idea_once(cfg, idea):
    add_related(cfg, idea.id, "2026-10-02-rutina", "es")
    add_related(cfg, idea.id, "2026-10-02-rutina", "es")
    assert now(cfg, idea).related == ["2026-10-02-rutina"]


def test_joining_reads_the_idea_as_it_is_on_disk_now(cfg, idea):
    add_related(cfg, idea.id, "a", "es")
    path, on_disk = find_note(cfg, idea.id, shelf=cfg.ideas)
    on_disk.related.append("b")
    on_disk.state = "doing"
    write_note(cfg, on_disk, "es", path=path)
    add_related(cfg, idea.id, "c", "es")
    assert now(cfg, idea).related == ["a", "b", "c"]
    assert now(cfg, idea).state == "doing"


def test_joining_touches_nothing_else(cfg, idea):
    add_related(cfg, idea.id, "a", "es")
    after = now(cfg, idea)
    assert (after.title, after.my_note) == (idea.title, idea.my_note)


def test_a_full_idea_says_so_instead_of_dropping_the_link(cfg, idea):
    for n in range(16):
        add_related(cfg, idea.id, f"n{n}", "es")
    with pytest.raises(IdeaFull):
        add_related(cfg, idea.id, "one-more", "es")
    assert "one-more" not in now(cfg, idea).related
    add_related(cfg, idea.id, "n3", "es")              # already in: no error


def test_an_idea_that_is_not_there_is_none(cfg):
    assert add_related(cfg, "000000000000", "a", "es") is None
    assert drop_related(cfg, "000000000000", "a", "es") is None


def test_a_link_leaves_an_idea(cfg, idea):
    add_related(cfg, idea.id, "a", "es")
    add_related(cfg, idea.id, "b", "es")
    drop_related(cfg, idea.id, "a", "es")
    drop_related(cfg, idea.id, "never-there", "es")
    assert now(cfg, idea).related == ["b"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest tests/test_ideas.py -q`
Expected: FAIL at collection with `ModuleNotFoundError: No module named 'oknowledge.ideas'`.

- [ ] **Step 3: The constant**

In `src/oknowledge/ai/base.py`, next to `MAX_POINTS`:

```python
MAX_IDEA_TITLE = 120
"""An idea's title, whoever wrote it: a name, not a paragraph."""
```

- [ ] **Step 4: The module**

```python
# src/oknowledge/ideas.py
"""Ideas: what you wrote, kept as a note on a shelf of its own.

An idea is a Note like any other, with three differences that all live
here: its id comes from the moment it was written and not from a URL, its
text is yours (`my_note`) and nothing rewrites it, and it carries the links
you added to it (`related`) -- inside the idea's own note, so it reads on
its own in Obsidian.
"""

from __future__ import annotations

from pathlib import Path

from .ai.base import MAX_IDEA_TITLE
from .config import Config
from .model import Note
from .urls import link_id
from .vault import MAX_RELATED, find_note, normalize_related, write_note

KIND = "idea"
CATEGORY = "Ideas"
"""Every idea's category, which only names its index file. Ideas are found
by state and by tag; a category a model picked would be a third way of
filing them that nobody asked for."""


class IdeaFull(Exception):
    """The idea already holds MAX_RELATED links. Said, not swallowed: a link
    that silently did not join is one you go looking for later."""


def idea_id(instant: str) -> str:
    """The id of an idea written at this instant: the same hash a link
    takes of its URL, over a uri of its own."""
    return link_id(f"idea:{instant}")


def clean_title(title: str) -> str:
    """One line, single spaces, at most MAX_IDEA_TITLE characters."""
    return " ".join(str(title).split())[:MAX_IDEA_TITLE].strip()


def new_idea(text: str, title: str, saved: str, instant: str) -> Note:
    """The note for what was just typed. Not written: the web writes it,
    the way it writes a card."""
    return Note(id=idea_id(instant), url="", title=clean_title(title),
                category=CATEGORY, tags=[], type=KIND, source="", saved=saved,
                summary="", my_note=text.strip())


def add_related(cfg: Config, idea: str, stem: str, language: str) -> Path | None:
    """Add one link to one idea.

    The idea is read here, so a caller holding its lock writes onto what is
    on disk now and not onto a copy it read earlier. None when there is no
    such idea. A link it already has is not an error.
    """
    found = find_note(cfg, idea, shelf=cfg.ideas)
    if found is None:
        return None
    path, note = found
    if stem in note.related:
        return path
    if len(note.related) >= MAX_RELATED:
        raise IdeaFull(idea)
    note.related = normalize_related([*note.related, stem])
    return write_note(cfg, note, language, path=path)


def drop_related(cfg: Config, idea: str, stem: str, language: str) -> Path | None:
    """Take one link off one idea, by the stem the idea holds."""
    found = find_note(cfg, idea, shelf=cfg.ideas)
    if found is None:
        return None
    path, note = found
    if stem not in note.related:
        return path
    note.related = [s for s in note.related if s != stem]
    return write_note(cfg, note, language, path=path)
```

- [ ] **Step 5: Run the tests**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest tests/test_ideas.py -q`
Expected: 10 passed. Then the whole suite: 1958 passed.

- [ ] **Step 6: Mutation**

```bash
~/.local/share/oknowledge/venv/bin/python /home/fer/.claude/jobs/d89ecc8a/tmp/mutate.py \
  src/oknowledge/ideas.py tests/test_ideas.py \
  'return link_id(f"idea:{instant}")|||return link_id(instant)' \
  '[:MAX_IDEA_TITLE]|||' \
  'my_note=text.strip()|||my_note=text' \
  'if stem in note.related:\n        return path\n    if len|||if len' \
  'raise IdeaFull(idea)|||return path' \
  'note.related = [s for s in note.related if s != stem]|||pass'
```

Expected: every mutation killed.

- [ ] **Step 7: Commit**

```bash
git add src/oknowledge/ideas.py src/oknowledge/ai/base.py tests/test_ideas.py
git commit -m "feat: an idea is your text under an id of its own, with links you add"
```

---
### Task 3: Lo que se le pregunta al modelo

**Files:**
- Create: `src/oknowledge/prompts/idea.txt`
- Modify: `src/oknowledge/ai/base.py` (después de `describe_card`)
- Modify: `src/oknowledge/ai/__init__.py` (import y una función después de `describe_with_chain`)
- Test: `tests/test_idea_prompt.py`

**Interfaces:**
- Consumes: `ideas.new_idea` (sólo en los tests), `MAX_IDEA_TITLE`, `MAX_POINTS`, `normalize_tags`, `extract_json`, `_text`, `_items`, `_is_placeholder`.
- Produces:
  - `ai.base.IdeaAnswer(title: str, tags: list[str], summary: str, points: list[str])` (frozen dataclass)
  - `ai.base.render_idea_prompt(note, language: str) -> str`
  - `ai.base.complete_idea(engine, note, language: str) -> IdeaAnswer` — `AnalysisError` si no sirve
  - `ai.complete_idea_with_chain(cfg, note) -> tuple[IdeaAnswer, str, str]` — (respuesta, motor, modelo); `AllEnginesFailed` si nadie contesta

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_idea_prompt.py
"""What a model is asked about an idea, and what is kept of its answer."""

import json

import pytest

from oknowledge.ai import AllEnginesFailed, complete_idea_with_chain
from oknowledge.ai.base import (
    LANGUAGE_NAMES, AnalysisError, EngineError, IdeaAnswer, complete_idea,
    normalize_tags, render_idea_prompt,
)
from oknowledge.config import Config
from oknowledge.ideas import new_idea

INSTANT = "2026-10-12T21:04:05.123456+00:00"
GOOD = {"title": "Gimnasio con IA", "tags": ["gimnasio", "ia"],
        "summary": "Una app que arma la rutina.",
        "points": ["Para quien entrena solo."]}


class Says:
    model = "m-1"

    def __init__(self, reply):
        self.reply = reply
        self.prompt = ""

    def complete(self, prompt):
        self.prompt = prompt
        return self.reply


def an_idea(text="Una app que me arme la rutina.", title=""):
    return new_idea(text, title, "2026-10-12", INSTANT)


def answer_to(reply):
    return complete_idea(Says(json.dumps(reply)), an_idea(), "es")


def test_the_prompt_carries_the_text_the_title_and_the_language():
    prompt = render_idea_prompt(an_idea(title="Mi gym"), "es")
    assert "Una app que me arme la rutina." in prompt
    assert "Mi gym" in prompt
    assert LANGUAGE_NAMES["es"] in prompt
    assert "{{" not in prompt


def test_a_text_that_looks_like_a_placeholder_is_not_filled_in_twice():
    prompt = render_idea_prompt(an_idea(text="literal {{TITLE}} here", title="T"), "es")
    assert "literal {{TITLE}} here" in prompt


def test_a_good_answer_is_kept():
    assert answer_to(GOOD) == IdeaAnswer(
        title="Gimnasio con IA", tags=["gimnasio", "ia"],
        summary="Una app que arma la rutina.", points=["Para quien entrena solo."])


def test_a_title_comes_back_as_one_short_line():
    title = answer_to(dict(GOOD, title="Gimnasio\ncon   IA " + "x" * 300)).title
    assert "\n" not in title and "  " not in title
    assert len(title) == 120


def test_tags_are_cleaned_like_every_other_tag():
    raw = ["Inteligencia Artificial", "SALUD", "salud"]
    assert answer_to(dict(GOOD, tags=raw)).tags == normalize_tags(raw)


def test_points_stop_at_six():
    assert len(answer_to(dict(GOOD, points=[f"punto {n}" for n in range(10)])).points) == 6


@pytest.mark.parametrize("broken", [
    dict(GOOD, title=""), dict(GOOD, summary="  "),
    {k: v for k, v in GOOD.items() if k != "title"},
    {k: v for k, v in GOOD.items() if k != "summary"},
])
def test_an_answer_with_no_name_or_no_summary_is_no_use(broken):
    with pytest.raises(AnalysisError):
        answer_to(broken)


def test_an_answer_that_is_not_json_is_no_use():
    with pytest.raises(AnalysisError):
        complete_idea(Says("no tengo idea"), an_idea(), "es")


def test_tags_and_points_may_be_left_out():
    answer = answer_to({"title": "T", "summary": "S."})
    assert (answer.tags, answer.points) == ([], [])


@pytest.fixture
def cfg(tmp_path):
    return Config(vault=tmp_path / "vault", chain=("first", "second"))


def test_the_chain_moves_on_until_one_answers(cfg, monkeypatch):
    class Down:
        model = "x"

        def complete(self, prompt):
            raise EngineError("down")

    engines = {"first": Down(), "second": Says(json.dumps(GOOD))}
    monkeypatch.setattr("oknowledge.ai.build_engine", lambda name, cfg: engines[name])
    answer, engine, model = complete_idea_with_chain(cfg, an_idea())
    assert (answer.title, engine, model) == ("Gimnasio con IA", "second", "m-1")


def test_a_chain_where_nobody_answers_says_so(cfg, monkeypatch):
    monkeypatch.setattr("oknowledge.ai.build_engine", lambda name, cfg: Says("nada"))
    with pytest.raises(AllEnginesFailed) as caught:
        complete_idea_with_chain(cfg, an_idea())
    assert caught.value.answered is True


def test_an_empty_chain_is_refused(tmp_path):
    with pytest.raises(AllEnginesFailed):
        complete_idea_with_chain(Config(vault=tmp_path, chain=()), an_idea())
```

- [ ] **Step 2: Run them to verify they fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest tests/test_idea_prompt.py -q`
Expected: FAIL at collection with `ImportError: cannot import name 'complete_idea_with_chain'`.

- [ ] **Step 3: The prompt**

```text
# src/oknowledge/prompts/idea.txt
Sos alguien que ayuda a ordenar ideas. Te doy una idea tal como alguien la
escribió, a veces apurado y a medias, y la completás para que se pueda
encontrar y entender después.

Respondé ÚNICAMENTE con un objeto JSON, sin texto antes ni después, con esta forma
(lo que está entre <> es lo que tenés que reemplazar por tu respuesta):

{
  "title": "<un nombre corto, de 2 a 8 palabras>",
  "tags": ["<un-tema>", "<otro, 2 a 6 en total>"],
  "summary": "<una sola frase que diga qué es la idea>",
  "points": ["<qué problema resuelve>", "<para quién es>", "<cómo podría funcionar>"]
}

Todo va escrito en {{LANGUAGE}}, aunque la idea esté escrita en otro idioma.

El título nombra la idea, no la describe: "Gimnasio con IA", no "Una app que
arma rutinas de gimnasio usando inteligencia artificial". Si abajo ya hay un
título, devolvé ese mismo.

Las etiquetas son temas, en minúsculas y con guiones en vez de espacios:
"gimnasio", "inteligencia-artificial", "salud".

Los puntos son de 3 a 6, y cada uno dice algo que la idea implica y que no
está escrito tal cual: el problema que resuelve, para quién, cómo podría
funcionar, qué haría falta. No repitas el texto en otras palabras y no
inventes datos: si la idea no dice para quién es, no lo afirmes, proponelo.

El título que ya tiene (puede estar vacío):

{{TITLE}}

La idea:

{{TEXT}}
```

(The first line of the block above is a label for this plan; the file
starts at "Sos alguien".)

- [ ] **Step 4: The answer**

In `src/oknowledge/ai/base.py`, after `describe_card()`:

```python
@dataclass(frozen=True)
class IdeaAnswer:
    """What a model adds to an idea. The text is the user's, and is not here."""

    title: str
    tags: list[str]
    summary: str
    points: list[str]


def render_idea_prompt(note, language: str) -> str:
    """The prompt that asks a model to fill in an idea from what was typed."""
    template = files("oknowledge").joinpath("prompts/idea.txt").read_text(encoding="utf-8")
    values = {
        "LANGUAGE": LANGUAGE_NAMES.get(language, language),
        "TITLE": note.title,
        "TEXT": note.my_note.strip(),
    }
    # One pass, like render_card_prompt: a text that looks like a
    # placeholder is never substituted a second time.
    return re.sub(r"\{\{([A-Z]+)\}\}",
                  lambda m: values.get(m.group(1), m.group(0)), template)


def complete_idea(engine: Engine, note, language: str) -> IdeaAnswer:
    """The title, tags, summary and points for one idea, or AnalysisError if
    the answer is no use.

    A title is asked for every time and used only when the idea has none.
    The caller decides that, because only the caller reads the idea again,
    under its lock, after the minutes this takes.
    """
    data = extract_json(engine.complete(render_idea_prompt(note, language)))
    for key in ("title", "summary"):
        if key not in data:
            raise AnalysisError(f"the answer is missing: {key}")
    title = " ".join(_text(data, "title").split())[:MAX_IDEA_TITLE].strip()
    summary = " ".join(_text(data, "summary").split())
    if not title or not summary:
        raise AnalysisError("the answer has an empty title or summary")
    tags = normalize_tags(_items(data, "tags")) if "tags" in data else []
    points = [
        p.strip() for p in _items(data, "points") if isinstance(p, str)
        and p.strip() and not _is_placeholder(p)
    ] if "points" in data else []
    return IdeaAnswer(title=title, tags=tags, summary=summary,
                      points=points[:MAX_POINTS])
```

- [ ] **Step 5: The chain**

In `src/oknowledge/ai/__init__.py`, add `IdeaAnswer` and `complete_idea` to
the `from .base import (...)` block, and after `describe_with_chain()`:

```python
def complete_idea_with_chain(cfg: Config, note) -> tuple[IdeaAnswer, str, str]:
    """Ask the chain to fill in an idea. Returns (answer, engine name,
    model). Mirrors describe_with_chain: the order is the priority, and
    every failure is kept for the one error raised when none answers."""
    if not cfg.chain:
        raise AllEnginesFailed("no engine is enabled: [ai] chain is empty")
    failures = []
    answered = False
    for name in cfg.chain:
        try:
            engine = build_engine(name, cfg)
            answer = complete_idea(engine, note, cfg.language)
        except AnalysisError as error:
            answered = True
            failures.append(f"{name}: {error}")
            continue
        except EngineError as error:
            failures.append(f"{name}: {error}")
            continue
        return answer, name, str(getattr(engine, "model", ""))
    raise AllEnginesFailed("every engine failed: " + "; ".join(failures),
                           answered=answered)
```

- [ ] **Step 6: Run the tests**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest tests/test_idea_prompt.py -q`
Expected: 15 passed. Whole suite: 1973 passed.

- [ ] **Step 7: Mutation**

```bash
~/.local/share/oknowledge/venv/bin/python /home/fer/.claude/jobs/d89ecc8a/tmp/mutate.py \
  src/oknowledge/ai/base.py tests/test_idea_prompt.py \
  '" ".join(_text(data, "title").split())[:MAX_IDEA_TITLE]|||_text(data, "title")' \
  'tags = normalize_tags(_items(data, "tags"))|||tags = _items(data, "tags")' \
  'points=points[:MAX_POINTS])|||points=points)' \
  'if not title or not summary:|||if not title:' \
  '"TEXT": note.my_note.strip(),|||"TEXT": "",'
~/.local/share/oknowledge/venv/bin/python /home/fer/.claude/jobs/d89ecc8a/tmp/mutate.py \
  src/oknowledge/ai/__init__.py tests/test_idea_prompt.py \
  'answered = True\n            failures.append(f"{name}: {error}")\n            continue\n        except EngineError as error:\n            failures.append(f"{name}: {error}")\n            continue\n        return answer|||failures.append(f"{name}: {error}")\n            continue\n        except EngineError as error:\n            failures.append(f"{name}: {error}")\n            continue\n        return answer'
```

Expected: every mutation killed.

- [ ] **Step 8: Commit**

```bash
git add src/oknowledge/prompts/idea.txt src/oknowledge/ai/base.py \
        src/oknowledge/ai/__init__.py tests/test_idea_prompt.py
git commit -m "feat: ask a model for an idea's name, tags, summary and points"
```

---

### Task 4: El completado de fondo, y el título desde la página

**Files:**
- Modify: `src/oknowledge/pipeline.py` (imports, `_rename_to_title`, `_usable_name`, dos funciones nuevas al final)
- Test: `tests/test_pipeline_idea.py`

**Interfaces:**
- Consumes: `complete_idea_with_chain`, `ideas.clean_title`, `Config.ideas`, `vault.IndexesStale`.
- Produces:
  - `pipeline.complete_idea(cfg, idea: str, trace=None) -> bool`
  - `pipeline.retitle_idea(cfg, idea: str, title: str, text: str, language: str) -> tuple[Path, str | None] | None` — el que llama tiene el lock; levanta `IndexesStale` si sólo el índice quedó atrás
  - `pipeline._rename_to_title(cfg, note, path, shelf=None)` (antes sin `shelf`)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_pipeline_idea.py
"""Filling in an idea, behind the page.

The idea is on disk from the second it is saved, with your text. The model
comes afterwards and adds what it is good at -- a name if you gave none,
tags, a one-line summary, the points -- and never what is yours: the text,
a title you wrote, the state, the stars, the links.
"""

import json

import pytest

from oknowledge.ai.base import EngineError
from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.pipeline import complete_idea, retitle_idea
from oknowledge.vault import find_note, note_path, rebuild_indexes, write_note

INSTANT = "2026-10-12T21:04:05.123456+00:00"
ANSWER = {"title": "Gimnasio con IA", "tags": ["gimnasio", "ia"],
          "summary": "Una app que arma la rutina.",
          "points": ["Para quien entrena solo.", "Lee las series."]}


@pytest.fixture(autouse=True)
def state_tree(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))


@pytest.fixture
def cfg(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    return Config(vault=vault, chain=("fake",))


def put(cfg, title="", **mine):
    note = new_idea("Una app que me arme la rutina.", title, "2026-10-12", INSTANT)
    for key, value in mine.items():
        setattr(note, key, value)
    path = write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ideas))
    rebuild_indexes(cfg, "es", shelf=cfg.ideas)
    return note, path


def now(cfg, note):
    return find_note(cfg, note.id, shelf=cfg.ideas)


@pytest.fixture
def engine(monkeypatch):
    class Faker:
        model = "fake-1"

        def __init__(self):
            self.reply = json.dumps(ANSWER)
            self.meanwhile = None
            self.error = None
            self.prompt = ""

        def complete(self, prompt):
            self.prompt = prompt
            if self.meanwhile is not None:
                self.meanwhile()
            if self.error is not None:
                raise self.error
            return self.reply

    faker = Faker()
    monkeypatch.setattr("oknowledge.ai.build_engine", lambda name, cfg: faker)
    return faker


def test_an_untitled_idea_gets_its_name_and_its_file_name(cfg, engine):
    note, old = put(cfg)
    assert complete_idea(cfg, note.id) is True
    path, after = now(cfg, note)
    assert after.title == "Gimnasio con IA"
    assert path.name == "2026-10-12-gimnasio-con-ia.md"
    assert not old.exists()


def test_a_title_you_wrote_is_kept(cfg, engine):
    note, old = put(cfg, title="Mi gym")
    complete_idea(cfg, note.id)
    path, after = now(cfg, note)
    assert after.title == "Mi gym"
    assert path == old


def test_the_model_fills_in_tags_summary_points_and_signs_it(cfg, engine):
    note, _ = put(cfg)
    complete_idea(cfg, note.id)
    after = now(cfg, note)[1]
    assert after.tags == ["gimnasio", "ia"]
    assert after.summary == "Una app que arma la rutina."
    assert after.points == ["Para quien entrena solo.", "Lee las series."]
    assert (after.engine, after.model) == ("fake", "fake-1")


def test_the_model_reads_your_text(cfg, engine):
    note, _ = put(cfg)
    complete_idea(cfg, note.id)
    assert "Una app que me arme la rutina." in engine.prompt


def test_what_is_yours_survives(cfg, engine):
    note, _ = put(cfg, state="doing", score=4, related=["2026-10-02-rutina"])
    complete_idea(cfg, note.id)
    after = now(cfg, note)[1]
    assert after.my_note == "Una app que me arme la rutina."
    assert (after.state, after.score, after.related) == ("doing", 4, ["2026-10-02-rutina"])


def test_what_you_did_while_it_thought_survives(cfg, engine):
    note, _ = put(cfg)

    def you_meanwhile():
        path, there = now(cfg, note)
        there.state, there.my_note = "doing", "La amplié."
        write_note(cfg, there, "es", path=path)

    engine.meanwhile = you_meanwhile
    complete_idea(cfg, note.id)
    after = now(cfg, note)[1]
    assert (after.state, after.my_note) == ("doing", "La amplié.")
    assert after.summary == "Una app que arma la rutina."


def test_an_idea_thrown_away_while_it_thought_stays_thrown_away(cfg, engine):
    note, path = put(cfg)
    engine.meanwhile = path.unlink
    assert complete_idea(cfg, note.id) is False
    assert now(cfg, note) is None
    assert list(cfg.ideas.dir.glob("2026-*.md")) == []


def test_when_nobody_answers_the_idea_stays_as_you_left_it(cfg, engine):
    note, path = put(cfg)
    before = path.read_text(encoding="utf-8")
    engine.error = EngineError("down")
    assert complete_idea(cfg, note.id) is False
    assert path.read_text(encoding="utf-8") == before


def test_asking_again_does_not_rename_what_now_has_a_name(cfg, engine):
    note, _ = put(cfg)
    complete_idea(cfg, note.id)
    engine.reply = json.dumps(dict(ANSWER, title="Otro nombre", tags=["otra"]))
    complete_idea(cfg, note.id)
    after = now(cfg, note)[1]
    assert after.title == "Gimnasio con IA"
    assert after.tags == ["otra"]


def test_the_index_follows_the_new_name(cfg, engine):
    note, _ = put(cfg)
    complete_idea(cfg, note.id)
    index = (cfg.ideas.index_dir / "Ideas.md").read_text(encoding="utf-8")
    assert "[[2026-10-12-gimnasio-con-ia|Gimnasio con IA]]" in index


def test_an_idea_that_is_not_there_is_false(cfg, engine):
    assert complete_idea(cfg, "000000000000") is False


def test_your_title_and_text_from_the_page_move_the_file(cfg):
    note, old = put(cfg, title="Mi gym")
    path, trouble = retitle_idea(cfg, note.id, "  Gimnasio\ncon IA ", "Texto nuevo.\n", "es")
    assert trouble is None
    assert path.name == "2026-10-12-gimnasio-con-ia.md" and not old.exists()
    after = now(cfg, note)[1]
    assert (after.title, after.my_note) == ("Gimnasio con IA", "Texto nuevo.")
    assert "Gimnasio con IA" in (cfg.ideas.index_dir / "Ideas.md").read_text(encoding="utf-8")


def test_retitling_keeps_the_rest(cfg):
    note, _ = put(cfg, title="Mi gym", state="done", score=5, related=["x"])
    retitle_idea(cfg, note.id, "Mi gym", "Otro texto.", "es")
    after = now(cfg, note)[1]
    assert (after.state, after.score, after.related) == ("done", 5, ["x"])


def test_retitling_an_idea_that_is_not_there_is_none(cfg):
    assert retitle_idea(cfg, "000000000000", "t", "x", "es") is None
```

- [ ] **Step 2: Run them to verify they fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest tests/test_pipeline_idea.py -q`
Expected: FAIL at collection with `ImportError: cannot import name 'complete_idea'`.

- [ ] **Step 3: Imports**

In `src/oknowledge/pipeline.py`: add `complete_idea_with_chain` to the
`from .ai import (...)` block; change the config import to
`from .config import CONTENT_MODES, Config, Shelf`; add
`from .ideas import clean_title`; add `IndexesStale` to the
`from .vault import (...)` block.

- [ ] **Step 4: The rename takes a shelf**

`_rename_to_title()` gains a parameter and looks in that shelf's folder.
Its signature and first lines become:

```python
def _rename_to_title(cfg: Config, note: Note, path: Path,
                     shelf: Shelf | None = None) -> tuple[Path, str | None]:
```

append to its docstring:

```python
    `shelf` is where the note lives: the links unless it says otherwise,
    which an idea getting its name does.
```

and replace `ideal = _usable_name(cfg, cfg.links_dir / wanted)` with:

```python
    shelf = shelf or cfg.links
    ideal = _usable_name(cfg, shelf.dir / wanted, shelf)
```

`_usable_name()` the same way:

```python
def _usable_name(cfg: Config, ideal: Path, shelf: Shelf | None = None) -> Path | None:
```

with its last line:

```python
    shelf = shelf or cfg.links
    return resolved if resolved.parent == shelf.dir.resolve() else None
```

- [ ] **Step 5: The two new functions**

At the end of `src/oknowledge/pipeline.py`:

```python
def complete_idea(cfg: Config, idea: str, trace: Tracer | None = None) -> bool:
    """Fill in one idea with the model: a name if it has none, the tags, a
    one-line summary and the points. True if it did.

    The idea is on disk, with your text, from the second it was saved; this
    is the improvement and not the saving, so every failure is a False and
    the idea stays exactly as it was. It is describe() for an idea, and it
    keeps the same promise: the model's fields and nothing else.
    """
    tell = guarded(trace or SILENT)
    found = find_note(cfg, idea, shelf=cfg.ideas)
    if found is None:
        return False
    clock = time.monotonic()
    tell(Step(link=idea, name="complete", state="start", seconds=0.0))
    try:
        answer, engine, model = complete_idea_with_chain(cfg, found[1])
    except AllEnginesFailed as error:
        tell(Step(link=idea, name="complete", state="fail",
                  seconds=time.monotonic() - clock, detail=str(error)))
        return False
    trouble = None
    try:
        with Queue().lock(idea):
            # Read again, under the lock: the idea's page was open the whole
            # time, and the state, the stars, the links or the text itself
            # may have changed while the model wrote.
            fresh = find_note(cfg, idea, shelf=cfg.ideas)
            if fresh is None:
                # Thrown away in the meantime. Writing it back would
                # resurrect an idea somebody deleted.
                tell(Step(link=idea, name="complete", state="fail",
                          seconds=time.monotonic() - clock,
                          detail="the idea is no longer there"))
                return False
            path, note = fresh
            if not note.title.strip():
                # Only an idea with no name gets one. A title somebody typed,
                # or one a first answer gave and they kept, is theirs.
                note.title = answer.title
            note.tags, note.summary, note.points = answer.tags, answer.summary, answer.points
            note.engine, note.model = engine, model
            path = write_note(cfg, note, cfg.language, path=path)
            # Named after its id until now: the name follows the title, and
            # nothing points at an idea, so nothing else has to follow.
            path, trouble = _rename_to_title(cfg, note, path, shelf=cfg.ideas)
            rebuild_indexes(cfg, cfg.language, shelf=cfg.ideas)
    except (Locked, OSError, ProtectedNote) as error:
        tell(Step(link=idea, name="complete", state="fail",
                  seconds=time.monotonic() - clock, detail=str(error)))
        return False
    tell(Step(link=idea, name="complete", state="ok",
              seconds=time.monotonic() - clock, engine=engine,
              detail=trouble or model))
    return True


def retitle_idea(cfg: Config, idea: str, title: str, text: str,
                 language: str) -> tuple[Path, str | None] | None:
    """Save an idea's title and text from its page, and move the file onto
    the name the title earns. The caller holds the idea's lock.

    Returns (where it is now, why it could not be renamed or None), or None
    when there is no such idea. Raises IndexesStale when the note landed and
    only the index is behind -- the editing routes tell those two apart.
    """
    found = find_note(cfg, idea, shelf=cfg.ideas)
    if found is None:
        return None
    path, note = found
    note.title, note.my_note = clean_title(title), text.strip()
    path = write_note(cfg, note, language, path=path)
    path, trouble = _rename_to_title(cfg, note, path, shelf=cfg.ideas)
    try:
        rebuild_indexes(cfg, language, shelf=cfg.ideas)
    except OSError as error:
        raise IndexesStale((path, trouble), error) from error
    return path, trouble
```

- [ ] **Step 6: Run the tests**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest tests/test_pipeline_idea.py tests/test_pipeline.py -q`
Expected: all passed (14 new; the rename tests in `test_pipeline.py` still
green with the default shelf). Whole suite: 1987 passed.

- [ ] **Step 7: Mutation**

```bash
~/.local/share/oknowledge/venv/bin/python /home/fer/.claude/jobs/d89ecc8a/tmp/mutate.py \
  src/oknowledge/pipeline.py tests/test_pipeline_idea.py \
  'if not note.title.strip():\n                # Only|||if True:\n                # Only' \
  'fresh = find_note(cfg, idea, shelf=cfg.ideas)\n            if fresh is None:|||fresh = found\n            if fresh is None:' \
  'path, trouble = _rename_to_title(cfg, note, path, shelf=cfg.ideas)\n            rebuild_indexes|||rebuild_indexes' \
  'note.title, note.my_note = clean_title(title), text.strip()|||note.title, note.my_note = title, text' \
  'ideal = _usable_name(cfg, shelf.dir / wanted, shelf)|||ideal = _usable_name(cfg, cfg.links_dir / wanted)'
```

Expected: every mutation killed. (The last one must be killed by
`test_an_untitled_idea_gets_its_name_and_its_file_name`: a name looked for
in `links/` is not a name in `ideas/`.)

- [ ] **Step 8: Commit**

```bash
git add src/oknowledge/pipeline.py tests/test_pipeline_idea.py
git commit -m "feat: the model fills in an idea behind the page, and keeps what is yours"
```

---

### Task 5: Cuando un link se renombra, sus ideas lo siguen

**Files:**
- Modify: `src/oknowledge/vault.py` (una función después de `rename_category`)
- Modify: `src/oknowledge/pipeline.py` (`_save` y un helper)
- Test: `tests/test_ideas_repoint.py`, `tests/test_pipeline.py` (un test después de `test_a_retried_note_is_renamed_after_its_new_title`)

**Interfaces:**
- Consumes: `Note.related`, `normalize_related`, `RenameResult`, `BUSY`, `_unlocked`.
- Produces: `vault.repoint_related(cfg, old: str, new: str, language: str, lock=None) -> RenameResult`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ideas_repoint.py
"""When a link's file is renamed, the ideas that named it follow.

An idea names its links by file name, because that is what a wikilink is.
The pipeline renames a link's file when the model finally gives it a real
title, and an idea left pointing at the old name would show a dead row.
"""

import contextlib

import pytest

from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.queue import Locked
from oknowledge.vault import find_note, note_path, repoint_related, write_note


@pytest.fixture
def cfg(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    return Config(vault=vault)


def put(cfg, instant, related):
    note = new_idea("x", f"Idea {instant[-1]}", "2026-10-12", instant)
    note.related = related
    write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ideas))
    return note


def related_of(cfg, note):
    return find_note(cfg, note.id, shelf=cfg.ideas)[1].related


def test_the_ideas_that_named_the_old_file_name_the_new_one(cfg):
    one = put(cfg, "2026-10-12T00:00:00.000001", ["old", "other"])
    two = put(cfg, "2026-10-12T00:00:00.000002", ["other"])
    result = repoint_related(cfg, "old", "new", "es")
    assert related_of(cfg, one) == ["new", "other"]
    assert related_of(cfg, two) == ["other"]
    assert (result.moved, result.failed) == (1, [])


def test_an_idea_that_already_had_both_keeps_one(cfg):
    one = put(cfg, "2026-10-12T00:00:00.000001", ["old", "new"])
    repoint_related(cfg, "old", "new", "es")
    assert related_of(cfg, one) == ["new"]


def test_an_idea_that_cannot_be_locked_is_reported_and_the_rest_move(cfg):
    one = put(cfg, "2026-10-12T00:00:00.000001", ["old"])
    two = put(cfg, "2026-10-12T00:00:00.000002", ["old"])

    @contextlib.contextmanager
    def lock(idea):
        if idea == one.id:
            raise Locked(idea)
        yield

    result = repoint_related(cfg, "old", "new", "es", lock=lock)
    assert related_of(cfg, one) == ["old"]
    assert related_of(cfg, two) == ["new"]
    assert result.moved == 1 and len(result.failed) == 1


def test_links_are_never_touched(cfg):
    link = new_idea("x", "WireGuard", "2026-10-12", "2026-10-12T00:00:00.000009")
    link.type, link.url, link.related = "article", "https://wireguard.com", ["old"]
    path = write_note(cfg, link, "es")
    before = path.read_text(encoding="utf-8")
    repoint_related(cfg, "old", "new", "es")
    assert path.read_text(encoding="utf-8") == before
```

And in `tests/test_pipeline.py`, add `from oknowledge.ideas import new_idea`
and `note_path` to the `oknowledge.vault` import, then right after
`test_a_retried_note_is_renamed_after_its_new_title`:

```python
def test_a_renamed_link_takes_its_ideas_with_it(cfg, q, monkeypatch):
    # An idea names its links by file name, so the rename that gives a
    # finished note its real name has to tell the ideas that named the old one.
    extraction(monkeypatch, Unreadable("503"))
    no_pictures(monkeypatch)
    first = add(cfg, "https://arstechnica.com/vpn", queue=q)
    idea = new_idea("Una vpn propia.", "VPN", TODAY, "2026-10-12T00:00:00+00:00")
    idea.related = [first.path.stem, "otro"]
    write_note(cfg, idea, "es", path=note_path(cfg, idea, shelf=cfg.ideas))

    extraction(monkeypatch, PAGE)
    no_pictures(monkeypatch)
    cfg.engines["fake"]["replies"] = [ANSWER]
    renamed = retry(cfg, queue=q)[0].path

    assert renamed.stem != first.path.stem
    assert find_note(cfg, idea.id, shelf=cfg.ideas)[1].related == [renamed.stem, "otro"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest tests/test_ideas_repoint.py "tests/test_pipeline.py::test_a_renamed_link_takes_its_ideas_with_it" -q`
Expected: FAIL — `ImportError: cannot import name 'repoint_related'` for the
first file; the pipeline test fails its last assertion (the idea still
names the old stem).

- [ ] **Step 3: The sweep**

In `src/oknowledge/vault.py`, after `rename_category()`:

```python
def repoint_related(cfg: Config, old: str, new: str, language: str,
                    lock=None) -> RenameResult:
    """Point every idea that names the file `old` at `new` instead.

    The pipeline renames a link's file when the model finally gives it a
    real title, and the ideas name their links by file name -- that is
    what a wikilink is. Shaped like rename_category, for the same reasons:
    each idea is read again under its own lock, and one that cannot be
    written is reported and never stops the others. No index names an
    idea's links, so there is nothing to rebuild.
    """
    hold = lock or _unlocked
    moved = 0
    failed: list[tuple[Path, str]] = []
    for path, scanned in _scan(cfg, cfg.ideas)[0]:
        if old not in scanned.related:
            continue
        try:
            with hold(scanned.id):
                note = read_note(path)
                if note is None or old not in note.related:
                    continue
                note.related = normalize_related(
                    [new if stem == old else stem for stem in note.related])
                write_note(cfg, note, language, path=path)
        except Locked:
            failed.append((path, BUSY))
            continue
        except (ProtectedNote, OSError) as error:
            failed.append((path, str(error)))
            continue
        moved += 1
    return RenameResult(moved=moved, failed=failed)
```

- [ ] **Step 4: The pipeline calls it**

In `src/oknowledge/pipeline.py`, add `repoint_related` to the
`from .vault import (...)` block. In `_save()`, the rename block becomes:

```python
        if target is not None:
            path, trouble = _rename_to_title(cfg, note, path)
            if trouble:
                warnings.append(trouble)
            if path.stem != target.stem:
                warnings += _repoint(cfg, q, target.stem, path.stem)
```

and after `_rename_to_title()`:

```python
def _repoint(cfg: Config, q: Queue, old: str, new: str) -> list[str]:
    """Tell the ideas that named a note by its old file name.

    Warnings and never an error: the note that was just saved is fine, and
    an idea that still names the old file shows that row dimmed, with an x
    to take it off. Each idea is rewritten under its own queue lock.
    """
    try:
        result = repoint_related(cfg, old, new, cfg.language, lock=q.lock)
    except OSError as error:
        return [f"the ideas could not be checked for {old}: {error}"]
    return [f"the idea {path.name} still names {old}: {why}"
            for path, why in result.failed]
```

- [ ] **Step 5: Run the tests**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest tests/test_ideas_repoint.py tests/test_pipeline.py -q`
Expected: all passed. Whole suite: 1992 passed.

- [ ] **Step 6: Mutation**

```bash
~/.local/share/oknowledge/venv/bin/python /home/fer/.claude/jobs/d89ecc8a/tmp/mutate.py \
  src/oknowledge/vault.py tests/test_ideas_repoint.py \
  'note.related = normalize_related(\n                    [new if stem == old else stem for stem in note.related])|||note.related = [new if stem == old else stem for stem in note.related]' \
  'for path, scanned in _scan(cfg, cfg.ideas)[0]:\n        if old not in|||for path, scanned in _scan(cfg)[0]:\n        if old not in' \
  'hold = lock or _unlocked\n    moved = 0\n    failed: list[tuple[Path, str]] = []\n    for path, scanned in _scan(cfg, cfg.ideas)|||hold = _unlocked\n    moved = 0\n    failed: list[tuple[Path, str]] = []\n    for path, scanned in _scan(cfg, cfg.ideas)'
~/.local/share/oknowledge/venv/bin/python /home/fer/.claude/jobs/d89ecc8a/tmp/mutate.py \
  src/oknowledge/pipeline.py tests/test_pipeline.py \
  'if path.stem != target.stem:|||if False:'
```

Expected: every mutation killed.

- [ ] **Step 7: Commit**

```bash
git add src/oknowledge/vault.py src/oknowledge/pipeline.py \
        tests/test_ideas_repoint.py tests/test_pipeline.py
git commit -m "feat: a link that gets its real name takes its ideas with it"
```

---
### Task 6: La sección `/ideas` y el formulario de crear

**Files:**
- Modify: `src/oknowledge/web/app.py` (imports, `IDEA_STATE_WORDS`, `NOTICES`, una `Library`, dos rutas y un helper)
- Create: `src/oknowledge/web/templates/ideas.html`
- Modify: `src/oknowledge/web/templates/base.html` (la barra)
- Modify: `src/oknowledge/i18n.py`
- Modify: `tests/test_web_write.py` (`WRITE_ROUTES`, `VAULT_WRITERS`)
- Test: `tests/test_web_ideas_page.py`

**Interfaces:**
- Consumes: `ideas.new_idea`, `pipeline.complete_idea`, `pipeline.today`, `vault.IDEA_STATES`, `Config.ideas`.
- Produces (adentro de `create_app`): `ideas: Library` sobre `cfg.ideas`; `save_idea(note) -> str` (el aviso; levanta si la nota no se pudo escribir). A nivel de módulo: `IDEA_STATE_WORDS: dict[str, str]`, `IDEA_STATE_ORDER: tuple[tuple[str, str], ...]`. Rutas: `GET /ideas?estado=&tag=`, `POST /ideas/guardar` (`text`, `title`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_web_ideas_page.py
"""The ideas section: write one, find it again.

Saving writes the idea at once, with your text, and leaves the model's part
to a task behind the page. These tests record that the task was queued and
never run a model.
"""

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.model import Note
from oknowledge.vault import all_notes, note_path, rebuild_indexes, write_note
from oknowledge.web.app import create_app


@pytest.fixture(autouse=True)
def state_tree(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr("oknowledge.web.app.CONFIG_PATH",
                        tmp_path / "config" / "config.toml")


@pytest.fixture
def queued(monkeypatch):
    calls = []
    monkeypatch.setattr("oknowledge.web.app.complete_idea",
                        lambda cfg, idea, trace=None: calls.append(idea))
    return calls


@pytest.fixture
def cfg(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    config = Config(vault=vault)
    rebuild_indexes(config, "es")
    return config


@pytest.fixture
def client(cfg):
    return TestClient(create_app(cfg))


def put(cfg, n, text=None, title=None, **fields):
    note = new_idea(text or f"Idea número {n}.",
                    f"Idea {n}" if title is None else title,
                    "2026-10-12", f"2026-10-12T00:00:00.00000{n}+00:00")
    for key, value in fields.items():
        setattr(note, key, value)
    write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ideas))
    return note


def test_the_bar_has_a_way_in(client):
    assert 'href="/ideas"' in client.get("/").text


def test_the_form_is_open_only_while_there_is_nothing(cfg, client):
    page = client.get("/ideas").text
    assert 'action="/ideas/guardar"' in page
    assert '<details class="new-idea" open>' in page
    put(cfg, 1)
    page = client.get("/ideas").text
    assert '<details class="new-idea">' in page


def test_saving_writes_the_idea_and_queues_the_model(cfg, client, queued):
    answer = client.post("/ideas/guardar",
                         data={"text": "  Una app para el gym.  ", "title": ""},
                         follow_redirects=False)
    [idea] = all_notes(cfg, cfg.ideas)
    assert (idea.my_note, idea.title, idea.type) == ("Una app para el gym.", "", "idea")
    assert answer.status_code == 303
    assert answer.headers["location"] == f"/item/{idea.id}?notice=completing"
    assert queued == [idea.id]


def test_a_title_you_type_is_kept(cfg, client, queued):
    client.post("/ideas/guardar", data={"text": "x", "title": "Mi gym"})
    assert all_notes(cfg, cfg.ideas)[0].title == "Mi gym"


def test_no_text_no_idea(cfg, client, queued):
    answer = client.post("/ideas/guardar", data={"text": "   ", "title": "Algo"},
                         follow_redirects=False)
    assert answer.headers["location"] == "/ideas?notice=idea-empty"
    assert all_notes(cfg, cfg.ideas) == []
    assert queued == []


def test_two_saves_are_two_ideas(cfg, client, queued):
    client.post("/ideas/guardar", data={"text": "La misma."})
    client.post("/ideas/guardar", data={"text": "La misma."})
    assert len(all_notes(cfg, cfg.ideas)) == 2


def test_a_stale_index_still_saves_and_says_so(cfg, client, queued, monkeypatch):
    def broken(*args, **kwargs):
        raise OSError("read-only")

    monkeypatch.setattr("oknowledge.web.app.rebuild_indexes", broken)
    answer = client.post("/ideas/guardar", data={"text": "x"}, follow_redirects=False)
    assert answer.headers["location"].endswith("?notice=indexes-stale")
    assert len(all_notes(cfg, cfg.ideas)) == 1
    assert len(queued) == 1


def test_a_failed_write_saves_nothing_and_queues_nothing(cfg, client, queued, monkeypatch):
    def broken(*args, **kwargs):
        raise OSError("read-only")

    monkeypatch.setattr("oknowledge.web.app.write_note", broken)
    answer = client.post("/ideas/guardar", data={"text": "x"}, follow_redirects=False)
    assert answer.headers["location"] == "/ideas?notice=write-failed"
    assert queued == []


def test_the_section_shows_ideas_and_not_links(cfg, client):
    put(cfg, 1, title="Gimnasio con IA")
    write_note(cfg, Note(id="bbbbbbbbbbbb", url="https://wireguard.com",
                         title="WireGuard", category="Redes", tags=[],
                         type="article", source="wireguard.com",
                         saved="2026-10-10", summary="Una vpn."), "es")
    page = client.get("/ideas").text
    assert "Gimnasio con IA" in page
    assert "WireGuard" not in page


def test_dropped_ideas_are_out_of_sight_until_asked_for(cfg, client):
    put(cfg, 1, title="Viva")
    put(cfg, 2, title="Descartada", state="dropped")
    assert "Descartada" not in client.get("/ideas").text
    shown = client.get("/ideas?estado=dropped").text
    assert "Descartada" in shown and "Viva" not in shown


def test_an_unknown_state_shows_the_usual_view(cfg, client):
    put(cfg, 1, title="Viva")
    put(cfg, 2, title="Descartada", state="dropped")
    page = client.get("/ideas?estado=archived").text
    assert "Viva" in page and "Descartada" not in page


def test_a_state_typed_by_hand_does_not_break_the_section(cfg, client):
    put(cfg, 1, title="Rara", state="someday")
    page = client.get("/ideas")
    assert page.status_code == 200
    assert "someday" in page.text


def test_ideas_filter_by_tag(cfg, client):
    put(cfg, 1, title="Con tag", tags=["gimnasio"])
    put(cfg, 2, title="Sin tag")
    page = client.get("/ideas?tag=gimnasio").text
    assert "Con tag" in page and "Sin tag" not in page


def test_an_untitled_idea_is_never_an_empty_link(cfg, client):
    note = put(cfg, 1, title="")
    assert f'<a href="/item/{note.id}">Untitled idea</a>' in client.get("/ideas").text


def test_an_idea_not_yet_completed_says_so(cfg, client):
    put(cfg, 1)
    put(cfg, 2, title="Hecha", engine="fake", summary="Ya completada.")
    assert client.get("/ideas").text.count("not completed") == 1


def test_stars_never_run_past_five(cfg, client):
    put(cfg, 1, score=99)
    assert "★★★★★★" not in client.get("/ideas").text
```

- [ ] **Step 2: Run them to verify they fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest tests/test_web_ideas_page.py -q`
Expected: FAIL — `AttributeError: ... has no attribute 'complete_idea'` from
the `queued` fixture, and 404s for `/ideas`.

- [ ] **Step 3: Imports and words**

In `src/oknowledge/web/app.py`, with the other imports:

```python
import datetime as dt
```

```python
from ..ideas import new_idea
from ..pipeline import complete_idea
from ..vault import IDEA_STATES
```

Right **before** `STATE_WORDS = {`:

```python
IDEA_STATE_WORDS = {"pending": "seed", "doing": "under way",
                    "done": "done", "dropped": "dropped"}
"""An idea's four states, in its own words: an idea is not watched or read,
it is had, worked on, made, or let go."""

IDEA_STATE_ORDER = tuple(IDEA_STATE_WORDS.items())
"""The chips of the ideas section, in this order."""
```

In `NOTICES`, after `"rewriting"`:

```python
    # Saving an idea: it is on disk already, and its name and tags come in
    # behind the page, like a card's summary.
    "completing": "Saved. The model is filling in the title and the tags: "
                  "reload in a moment to see them.",
    "idea-empty": "Write the idea first: there is nothing to save yet.",
```

- [ ] **Step 4: The library and the routes**

In `create_app()`, right after `shelf = Library(cfg, shelf=cfg.ocio)`:

```python
    # The ideas: a third index over a third folder, for the same reason.
    ideas = Library(cfg, shelf=cfg.ideas)
```

Before `@app.post("/add")`:

```python
    @app.get("/ideas", response_class=HTMLResponse)
    def idea_shelf(request: Request, estado: str = "", tag: str = ""):
        """The ideas, newest first, the dropped ones only when asked for:
        the fourth state exists to keep them, not to look at them.

        An unknown filter shows the usual view rather than nothing: these
        arrive from a URL somebody can type, and an empty page would look
        like an empty shelf.
        """
        ideas.refresh()
        notes = sorted(ideas.notes, key=lambda n: (n.saved, n.title), reverse=True)
        if estado in IDEA_STATES:
            notes = [n for n in notes if n.state == estado]
        else:
            estado = ""
            notes = [n for n in notes if n.state != "dropped"]
        if tag:
            notes = [n for n in notes if tag in n.tags]
        return page(request, "ideas.html", notes=notes, state=estado, tag=tag,
                    states=_count_by(ideas.notes, "state"),
                    idea_tags=ideas.tags(), unreadable_ideas=ideas.unreadable,
                    STATES=IDEA_STATE_ORDER, STATE_WORDS=IDEA_STATE_WORDS)

    def save_idea(note) -> str:
        """Write a new idea and its shelf's index. Returns the notice, and
        raises when the note itself could not be written -- the two are
        told apart for the reason save_card tells them apart."""
        live = current["cfg"]
        write_note(live, note, live.language,
                   path=note_path(live, note, shelf=live.ideas))
        notice = "completing"
        try:
            rebuild_indexes(live, live.language, shelf=live.ideas)
        except OSError as error:
            log.warning("the indexes could not be rebuilt: %s", error)
            notice = "indexes-stale"
        ideas.refresh()
        return notice

    @app.post("/ideas/guardar")
    def save_the_idea(background: BackgroundTasks, text: str = Form(""),
                      title: str = Form("")):
        """The form in the section. Written at once, with your text; the
        name, the tags, the summary and the points come in behind the page.

        No text, no idea: the model has nothing to read, and a title alone
        is a note you would not know what to do with in a month.
        """
        if not text.strip():
            return see_other("/ideas", notice="idea-empty")
        live = current["cfg"]
        instant = dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds")
        note = new_idea(text, title, today(), instant)
        try:
            notice = save_idea(note)
        except (OSError, ProtectedNote) as error:
            log.warning("the idea could not be written: %s", error)
            return see_other("/ideas", notice="write-failed")
        background.add_task(complete_idea, live, note.id, trace=progress.note)
        return see_other(item_url(note.id), notice=notice)
```

- [ ] **Step 5: The page**

```html
{# src/oknowledge/web/templates/ideas.html #}
{% extends "base.html" %}
{% block title %}{{ t('Ideas') }} - oknowledge{% endblock %}
{% block body_class %}wide{% endblock %}
{% block main %}
  {# The form first, and open while there is nothing yet: an empty
     section's only job is to be the place you write the first one. #}
  <details class="new-idea"{% if not notes and not state and not tag %} open{% endif %}>
    <summary>{{ t('New idea') }}</summary>
    <form action="/ideas/guardar" method="post" class="field">
      <label for="idea-text">{{ t('What is the idea?') }}</label>
      <textarea id="idea-text" name="text" rows="6" required></textarea>
      <label for="idea-title">{{ t('Title (optional: the model names it if you leave it empty)') }}</label>
      <input id="idea-title" name="title" autocomplete="off">
      <span class="row"><button type="submit">{{ t('Save') }}</button></span>
    </form>
  </details>
  <div class="chips">
    <a href="/ideas" class="chip {% if not state and not tag %}on{% endif %}">{{ t('All') }}</a>
    {% for name, label in STATES %}
      {% if states.get(name) %}
        <a href="/ideas?estado={{ name }}" class="chip {% if state == name %}on{% endif %}"
           >{{ t(label) }} <b>{{ states[name] }}</b></a>
      {% endif %}
    {% endfor %}
  </div>
  {% if idea_tags %}
    <div class="chips tags">
      {% for name, n in idea_tags.items() %}
        <a href="/ideas?tag={{ name|urlencode }}{% if state %}&amp;estado={{ state }}{% endif %}"
           class="chip small {% if tag == name %}on{% endif %}">#{{ name }} <b>{{ n }}</b></a>
      {% endfor %}
    </div>
  {% endif %}
  {% if unreadable_ideas %}
    <p class="quiet">{{ t('%1 ideas could not be read and are not shown', unreadable_ideas) }}</p>
  {% endif %}
  {% if not notes and (state or tag) %}
    <p class="empty">{{ t('Nothing matches that filter') }}</p>
  {% endif %}
  <ul class="grid cards">
    {% for note in notes %}
      <li class="card">
        <div class="pad">
          {# Never an empty link: an idea is saved before the model names it. #}
          <h2 dir="auto"><a href="/item/{{ note.id|slug }}">{{ note.title or t('Untitled idea') }}</a></h2>
          <a class="body" href="/item/{{ note.id|slug }}">
            {% if note.score %}
              {# Capped: `score` is a line anybody can type in Obsidian. #}
              {% set stars = [note.score, 5]|min %}
              <p class="stars" title="{{ stars }}/5">{{ '★' * stars }}{{ '☆' * (5 - stars) }}</p>
            {% endif %}
            {# The model's one line once there is one; your own words until then. #}
            <p class="sum" dir="auto">{{ (note.summary or note.my_note)|plain }}</p>
          </a>
          <p class="tags">{% for name in note.tags %}<span>#{{ name }}</span>{% endfor %}</p>
          <p class="site">
            {% if note.state %}<span class="state">{{ t(STATE_WORDS.get(note.state, note.state)) }}</span>{% endif %}
            {% if not note.engine %}<span class="unwritten">{{ t('not completed') }}</span>{% endif %}
          </p>
        </div>
      </li>
    {% endfor %}
  </ul>
{% endblock %}
```

(The first line of the block is a label for this plan, not part of the file.)

In `src/oknowledge/web/templates/base.html`, right after the Leisure link:

```html
      <a href="/ideas">{{ t('Ideas') }}</a>
```

- [ ] **Step 6: The words**

In `src/oknowledge/i18n.py`, inside `STRINGS["es"]`, after `"not rewritten"`:

```python
        "Ideas": "Ideas",
        "New idea": "Nueva idea",
        "What is the idea?": "¿Cuál es la idea?",
        "Title (optional: the model names it if you leave it empty)":
            "Título (opcional: si lo dejás vacío, lo pone el modelo)",
        "Untitled idea": "Idea sin título",
        "not completed": "sin completar",
        "seed": "semilla",
        "under way": "en marcha",
        "done": "hecha",
        "dropped": "descartada",
        "%1 ideas could not be read and are not shown":
            "%1 ideas no se pudieron leer y no se muestran",
        "Saved. The model is filling in the title and the tags: reload in a moment to see them.":
            "Guardada. El modelo está completando el título y las etiquetas: "
            "recargá en un momento para verlos.",
        "Write the idea first: there is nothing to save yet.":
            "Escribí la idea primero: todavía no hay nada que guardar.",
```

- [ ] **Step 7: The write meta-tests know the new route**

In `tests/test_web_write.py`, add to `WRITE_ROUTES`:

```python
    # Saving an idea. A cross-site POST here would write a note into this
    # vault and spend a model call completing it.
    ("/ideas/guardar", {"text": "x"}),
```

and add `"save_idea", "complete_idea"` to `VAULT_WRITERS`.

- [ ] **Step 8: Run the tests**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest tests/test_web_ideas_page.py tests/test_web_write.py tests/test_i18n.py -q`
Expected: all passed. Whole suite: 2010 passed (16 new here, and two more
from the parametrized cross-site tests over the new route).

- [ ] **Step 9: Mutation**

```bash
~/.local/share/oknowledge/venv/bin/python /home/fer/.claude/jobs/d89ecc8a/tmp/mutate.py \
  src/oknowledge/web/app.py tests/test_web_ideas_page.py \
  'notes = [n for n in notes if n.state != "dropped"]|||pass' \
  'if not text.strip():\n            return see_other("/ideas", notice="idea-empty")|||if False:\n            return see_other("/ideas", notice="idea-empty")' \
  'background.add_task(complete_idea, live, note.id, trace=progress.note)\n        return see_other(item_url(note.id)|||return see_other(item_url(note.id)' \
  'notice = "indexes-stale"\n        ideas.refresh()|||ideas.refresh()' \
  'if tag:\n            notes = [n for n in notes if tag in n.tags]|||if False:\n            pass'
~/.local/share/oknowledge/venv/bin/python /home/fer/.claude/jobs/d89ecc8a/tmp/mutate.py \
  src/oknowledge/web/templates/ideas.html tests/test_web_ideas_page.py \
  "{{ note.title or t('Untitled idea') }}|||{{ note.title }}" \
  "{% set stars = [note.score, 5]|min %}|||{% set stars = note.score %}"
```

Expected: every mutation killed.

- [ ] **Step 10: Commit**

```bash
git add src/oknowledge/web/app.py src/oknowledge/web/templates/ideas.html \
        src/oknowledge/web/templates/base.html src/oknowledge/i18n.py \
        tests/test_web_ideas_page.py tests/test_web_write.py
git commit -m "feat: an ideas section where you write one and find it again"
```

---

### Task 7: La página de una idea

**Files:**
- Modify: `src/oknowledge/web/app.py` (`STATE_WORDS`, `anywhere`, `held_by`, `item`, `mine`, `set_my_note`, `rewrite_card`, `remove`)
- Create: `src/oknowledge/web/templates/mine-buttons.html`
- Modify: `src/oknowledge/web/templates/item.html`
- Modify: `src/oknowledge/i18n.py`
- Modify: `tests/test_web_write.py` (`VAULT_WRITERS`)
- Test: `tests/test_web_ideas_mine.py`

**Interfaces:**
- Consumes: `ideas` (la `Library` de la Tarea 6), `IDEA_STATE_WORDS`, `pipeline.retitle_idea`, `pipeline.complete_idea`, `vault.states_for`.
- Produces: el contexto de `item.html` gana `idea: bool` y `link: bool` (además de `card`); `POST /item/{id}/mine/note` acepta `title` opcional; `POST /item/{id}/describe` sirve también a una idea.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_web_ideas_mine.py
"""An idea's own page: your title and text in one form, four states in an
idea's own words, the stars, and the button that asks the model again.
Nothing on it that belongs to a link."""

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.model import Note
from oknowledge.vault import find_note, note_path, rebuild_indexes, write_note
from oknowledge.web.app import create_app

CARD = "aaaaaaaaaaaa"
LINK = "bbbbbbbbbbbb"


@pytest.fixture(autouse=True)
def state_tree(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr("oknowledge.web.app.CONFIG_PATH",
                        tmp_path / "config" / "config.toml")


@pytest.fixture
def queued(monkeypatch):
    calls = []
    monkeypatch.setattr("oknowledge.web.app.complete_idea",
                        lambda cfg, idea, trace=None: calls.append(idea))
    return calls


@pytest.fixture
def cfg(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    config = Config(vault=vault)
    rebuild_indexes(config, "es")
    return config


@pytest.fixture
def client(cfg):
    return TestClient(create_app(cfg))


def put(cfg, n=1, text="Una app.", title="Mi gym", **fields):
    note = new_idea(text, title, "2026-10-12", f"2026-10-12T00:00:00.00000{n}+00:00")
    for key, value in fields.items():
        setattr(note, key, value)
    write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ideas))
    return note


def idea_now(cfg, note):
    return find_note(cfg, note.id, shelf=cfg.ideas)[1]


def page_of(client, note):
    return client.get(f"/item/{note.id}").text


def test_the_page_offers_your_title_and_text_to_edit(cfg, client):
    page = page_of(client, put(cfg, title="Gimnasio con IA", text="Una app."))
    assert 'name="title" value="Gimnasio con IA"' in page
    assert ">Una app.</textarea>" in page
    assert "Your idea" in page


def test_four_states_in_an_idea_s_own_words(cfg, client):
    page = page_of(client, put(cfg))
    for word in ("seed", "under way", "done", "dropped"):
        assert f">{word}</button>" in page


def test_an_idea_page_offers_nothing_that_belongs_to_a_link(cfg, client):
    note = put(cfg)
    page = page_of(client, note)
    for action in ("category", "collections", "reprocess"):
        assert f'/item/{note.id}/{action}"' not in page
    for action in ("tags", "delete", "describe", "mine/state", "mine/score", "mine/note"):
        assert f'/item/{note.id}/{action}"' in page


def test_an_untitled_idea_has_a_heading(cfg, client):
    assert '<h1 dir="auto">Untitled idea</h1>' in page_of(client, put(cfg, title=""))


def test_an_idea_can_be_dropped_from_its_page(cfg, client):
    note = put(cfg)
    client.post(f"/item/{note.id}/mine/state", data={"state": "dropped"})
    assert idea_now(cfg, note).state == "dropped"


def test_stars_on_an_idea(cfg, client):
    note = put(cfg)
    client.post(f"/item/{note.id}/mine/score", data={"score": "4"})
    assert idea_now(cfg, note).score == 4


def test_saving_title_and_text_renames_the_file(cfg, client):
    note = put(cfg, title="Mi gym")
    answer = client.post(f"/item/{note.id}/mine/note",
                         data={"title": "Gimnasio con IA", "my_note": "Texto nuevo."},
                         follow_redirects=False)
    assert answer.headers["location"] == f"/item/{note.id}?notice=saved"
    path, after = find_note(cfg, note.id, shelf=cfg.ideas)
    assert (after.title, after.my_note) == ("Gimnasio con IA", "Texto nuevo.")
    assert path.name == "2026-10-12-gimnasio-con-ia.md"


def test_a_card_s_note_still_saves_without_a_title(cfg, client):
    card = Note(id=CARD, url="https://imdb.com/title/tt1", title="The Terminator",
                category="Películas", tags=[], type="movie", source="imdb.com",
                saved="2026-10-11", summary="Un cyborg.")
    write_note(cfg, card, "es", path=note_path(cfg, card, shelf=cfg.ocio))
    client.post(f"/item/{CARD}/mine/note", data={"my_note": "La vi."})
    after = find_note(cfg, CARD, shelf=cfg.ocio)[1]
    assert (after.title, after.my_note) == ("The Terminator", "La vi.")


def test_a_link_has_no_state_of_its_own(cfg, client):
    write_note(cfg, Note(id=LINK, url="https://wireguard.com", title="WireGuard",
                         category="Redes", tags=[], type="article",
                         source="wireguard.com", saved="2026-10-10",
                         summary="Una vpn."), "es")
    rebuild_indexes(cfg, "es")
    assert client.post(f"/item/{LINK}/mine/state", data={"state": "done"}).status_code == 404


def test_asking_again_queues_the_model(cfg, client, queued):
    note = put(cfg)
    answer = client.post(f"/item/{note.id}/describe", follow_redirects=False)
    assert answer.headers["location"] == f"/item/{note.id}?notice=completing"
    assert queued == [note.id]


def test_asking_again_is_offered_after_the_model_was_over_it(cfg, client):
    note = put(cfg, engine="fake", summary="Hecha.")
    assert f'/item/{note.id}/describe"' in page_of(client, note)


def test_tags_are_edited_on_an_idea(cfg, client):
    note = put(cfg)
    client.post(f"/item/{note.id}/tags", data={"tags": "gimnasio, ia"})
    assert idea_now(cfg, note).tags == ["gimnasio", "ia"]


def test_a_deleted_idea_goes_back_to_the_ideas(cfg, client):
    note = put(cfg)
    answer = client.post(f"/item/{note.id}/delete", follow_redirects=False)
    assert answer.headers["location"] == "/ideas?notice=trashed"
    assert find_note(cfg, note.id, shelf=cfg.ideas) is None
```

- [ ] **Step 2: Run them to verify they fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest tests/test_web_ideas_mine.py -q`
Expected: most fail with 404 (`/item/<idea id>` is not found: the idea
shelf is not looked at yet).

- [ ] **Step 3: The routes**

In `src/oknowledge/web/app.py`:

1. Imports: `from ..pipeline import complete_idea, retitle_idea` (replacing
   the Task 6 line), and `from ..vault import IDEA_STATES, states_for`.
2. `STATE_WORDS` gains a row: `"idea": IDEA_STATE_WORDS,`.
3. In `anywhere()` and in `held_by()`, the loop becomes
   `for shelves in (library, shelf, ideas):`.
4. In `item()`, the return becomes:

```python
        return page(request, "item.html", note=read_full(entry),
                    card=where.name == "ocio", idea=where.name == "ideas",
                    link=where.name == "links",
                    words=STATE_WORDS.get(entry.note.type, STATE_WORDS["movie"]),
                    STATES=states_for(entry.note.type))
```

5. `mine()` becomes:

```python
    def mine(link_id: str, **change):
        """One of your fields on one card or one idea, and nothing else.

        Not on a link: these fields exist on every Note, but a state and a
        score mean nothing on a link, and a 404 says that better than a
        button nobody can see would.
        """
        shelves, which = held_by(link_id)
        if which.name == "links":
            raise HTTPException(status_code=404, detail="no such card")
        result = edit(link_id, lambda cfg, language: update_note(
            cfg, link_id, language, shelf=cfg.shelf(which.name), **change),
            "saved", "indexes-stale", shelves=shelves)
        if result.notice == MISSING:
            raise HTTPException(status_code=404, detail="no such card")
        return see_other(item_url(link_id), notice=result.notice)
```

6. `set_my_note()` becomes:

```python
    @app.post("/item/{link_id}/mine/note")
    def set_my_note(link_id: str, my_note: str = Form(""),
                    title: str | None = Form(None)):
        # An idea's page sends its title with its text: one form, so a
        # renamed idea and its text land in one write. A card's never does.
        shelves, which = held_by(link_id)
        if which.name != "ideas" or title is None:
            return mine(link_id, my_note=my_note)

        def retitle(cfg, language):
            done = retitle_idea(cfg, link_id, title, my_note, language)
            if done is not None and done[1]:
                log.warning("%s", done[1])
            return done

        result = edit(link_id, retitle, "saved", "indexes-stale", shelves=shelves)
        if result.notice == MISSING:
            raise HTTPException(status_code=404, detail="no such idea")
        return see_other(item_url(link_id), notice=result.notice)
```

7. In `rewrite_card()`, first thing in the body, and the docstring's first
   line becomes "Ask the model again: a card's summary in your language,
   or an idea's name, tags, summary and points.":

```python
        ideas.refresh()
        if ideas.by_id(link_id) is not None:
            background.add_task(complete_idea, current["cfg"], link_id,
                                trace=progress.note)
            return see_other(item_url(link_id), notice="completing")
```

8. In `remove()`:

```python
        # An idea goes back to the ideas: the library would not show it.
        home = "/ideas" if which.name == "ideas" else "/"
        where = home if result.landed else item_url(link_id)
```

- [ ] **Step 4: The template**

Create `src/oknowledge/web/templates/mine-buttons.html` with the two forms
that are today inside `{% if card %}` in `item.html` — the state buttons
and the stars, moved verbatim, comments included:

```html
<form action="/item/{{ note.id|slug }}/mine/state" method="post" class="row">
  {% for name in STATES %}
    <button type="submit" name="state" value="{{ name }}"
            class="{% if note.state == name %}on{% endif %}">{{ t(words[name]) }}</button>
  {% endfor %}
</form>
<form action="/item/{{ note.id|slug }}/mine/score" method="post" class="row stars">
  {% for n in [1, 2, 3, 4, 5] %}
    {# The filled star ignores `color`, so the one you picked is told
       by shape: filled up to it, outlined after. #}
    <button type="submit" name="score" value="{{ n }}"
            title="{{ n }}/5" aria-label="{{ n }}/5"
            >{{ '★' if n <= note.score else '☆' }}</button>
  {% endfor %}
</form>
```

In `item.html`:

1. `{% block title %}{{ note.title or t('Untitled idea') }} - oknowledge{% endblock %}`
2. `<h1 dir="auto">{{ note.title or t('Untitled idea') }}</h1>`
3. Inside `{% if card %}`, the two forms are replaced by
   `{% include "mine-buttons.html" %}`.
4. Right after that block's `{% endif %}`:

```html
    {% if idea %}
      {# Your text first: it is the idea, and the model's summary and points
         are only its reading of it. Title and text are one form, so a
         renamed idea and its text land in one write. #}
      <section class="mine">
        <form action="/item/{{ note.id|slug }}/mine/note" method="post" class="field">
          <label for="field-title">{{ t('Title') }}</label>
          <input id="field-title" name="title" value="{{ note.title }}"
                 placeholder="{{ t('Untitled idea') }}" autocomplete="off">
          <label for="field-mine">{{ t('Your idea') }}</label>
          <textarea id="field-mine" name="my_note" rows="8">{{ note.my_note }}</textarea>
          <span class="row"><button type="submit">{{ t('Save') }}</button></span>
        </form>
        {% include "mine-buttons.html" %}
        {# Always offered, unlike a card's: an idea grows, and fresh tags
           and points for what you added is the reason to ask again. #}
        <form action="/item/{{ note.id|slug }}/describe" method="post" class="row">
          <button type="submit">{{ t('Ask the model again') }}</button>
        </form>
      </section>
    {% endif %}
```

5. Both `{% if not card %}` in the actions block become `{% if link %}`, and
   the comment above the first one says "Three of these are a link's and
   not a card's or an idea's".

- [ ] **Step 5: The words, and the meta-test**

In `src/oknowledge/i18n.py`, after the Task 6 strings:

```python
        "Title": "Título",
        "Your idea": "Tu idea",
        "Ask the model again": "Pedírselo de nuevo al modelo",
```

In `tests/test_web_write.py`, add `"retitle_idea"` to `VAULT_WRITERS`.

- [ ] **Step 6: Run the tests**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest tests/test_web_ideas_mine.py tests/test_web_ocio_mine.py tests/test_web_write.py tests/test_i18n.py -q`
Expected: all passed — the card page tests in `test_web_ocio_mine.py`
prove the extracted buttons and the `link` flag changed nothing for a card
or a link. Whole suite: 2023 passed.

- [ ] **Step 7: Mutation**

```bash
~/.local/share/oknowledge/venv/bin/python /home/fer/.claude/jobs/d89ecc8a/tmp/mutate.py \
  src/oknowledge/web/app.py tests/test_web_ideas_mine.py \
  'if which.name == "links":\n            raise|||if False:\n            raise' \
  'if which.name != "ideas" or title is None:|||if True:' \
  'home = "/ideas" if which.name == "ideas" else "/"|||home = "/"' \
  'for shelves in (library, shelf, ideas):\n            shelves.refresh()\n            entry|||for shelves in (library, shelf):\n            shelves.refresh()\n            entry'
~/.local/share/oknowledge/venv/bin/python /home/fer/.claude/jobs/d89ecc8a/tmp/mutate.py \
  src/oknowledge/web/templates/item.html tests/test_web_ideas_mine.py \
  "<h1 dir=\"auto\">{{ note.title or t('Untitled idea') }}</h1>|||<h1 dir=\"auto\">{{ note.title }}</h1>"
```

Expected: every mutation killed.

- [ ] **Step 8: Commit**

```bash
git add src/oknowledge/web/app.py src/oknowledge/web/templates/item.html \
        src/oknowledge/web/templates/mine-buttons.html src/oknowledge/i18n.py \
        tests/test_web_ideas_mine.py tests/test_web_write.py
git commit -m "feat: an idea's page: your title and text, four states, ask again"
```

---

### Task 8: Sumar un link a una idea, y verlo desde la idea

**Files:**
- Modify: `src/oknowledge/web/app.py` (`NOTICES`, `item`, dos rutas)
- Modify: `src/oknowledge/web/templates/item.html`
- Modify: `src/oknowledge/web/static/style.css`
- Modify: `src/oknowledge/i18n.py`
- Modify: `tests/test_web_write.py` (`WRITE_ROUTES`, `VAULT_WRITERS`)
- Test: `tests/test_web_ideas_related.py`

**Interfaces:**
- Consumes: `ideas.add_related`, `ideas.drop_related`, `ideas.IdeaFull`, `Entry.path`, `library.entries`.
- Produces: `POST /item/{link_id}/ideas` (`idea`), `POST /item/{idea_id}/related/drop` (`stem`). El contexto de `item.html` gana `related: list[tuple[str, Note | None]]` en una idea e `idea_choices: list[tuple[str, str]]` en un link.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_web_ideas_related.py
"""A link joins an idea from the link's own page, and the idea shows it.

The relation lives in the idea's note, by the link's file name, so the
idea reads on its own in Obsidian. Only links join: a card or another idea
is not something an idea is built from.
"""

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.model import Note
from oknowledge.vault import find_note, note_path, rebuild_indexes, write_note
from oknowledge.web.app import create_app

CARD = "aaaaaaaaaaaa"
LINK = "bbbbbbbbbbbb"


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
    rebuild_indexes(config, "es")
    return config


@pytest.fixture
def client(cfg):
    return TestClient(create_app(cfg))


@pytest.fixture
def link(cfg):
    path = write_note(cfg, Note(id=LINK, url="https://wireguard.com", title="WireGuard",
                                category="Redes", tags=[], type="article",
                                source="wireguard.com", saved="2026-10-10",
                                summary="Una vpn."), "es")
    rebuild_indexes(cfg, "es")
    return path


@pytest.fixture
def card(cfg):
    note = Note(id=CARD, url="https://imdb.com/title/tt1", title="The Terminator",
                category="Películas", tags=[], type="movie", source="imdb.com",
                saved="2026-10-11", summary="Un cyborg.")
    write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ocio))
    return note


def put(cfg, n=1, title="VPN propia", **fields):
    note = new_idea("x", title, "2026-10-12", f"2026-10-12T00:00:00.00000{n}+00:00")
    for key, value in fields.items():
        setattr(note, key, value)
    write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ideas))
    return note


def related_of(cfg, note):
    return find_note(cfg, note.id, shelf=cfg.ideas)[1].related


def test_a_link_s_page_offers_your_live_ideas(cfg, client, link):
    idea = put(cfg, 1, title="VPN propia")
    put(cfg, 2, title="Descartada", state="dropped")
    page = client.get(f"/item/{LINK}").text
    assert f'action="/item/{LINK}/ideas"' in page
    assert f'<option value="{idea.id}">VPN propia</option>' in page
    assert "Descartada" not in page


def test_no_ideas_no_picker(client, link):
    assert f'/item/{LINK}/ideas"' not in client.get(f"/item/{LINK}").text


def test_neither_a_card_nor_an_idea_offers_the_picker(cfg, client, card):
    idea = put(cfg)
    assert f'/item/{CARD}/ideas"' not in client.get(f"/item/{CARD}").text
    assert f'/item/{idea.id}/ideas"' not in client.get(f"/item/{idea.id}").text


def test_a_link_joins_an_idea_by_its_file_name(cfg, client, link):
    idea = put(cfg)
    answer = client.post(f"/item/{LINK}/ideas", data={"idea": idea.id},
                         follow_redirects=False)
    assert answer.headers["location"] == f"/item/{LINK}?notice=saved"
    assert related_of(cfg, idea) == [link.stem]


def test_joining_twice_is_once(cfg, client, link):
    idea = put(cfg)
    client.post(f"/item/{LINK}/ideas", data={"idea": idea.id})
    client.post(f"/item/{LINK}/ideas", data={"idea": idea.id})
    assert related_of(cfg, idea) == [link.stem]


def test_only_a_link_joins_an_idea(cfg, client, card):
    idea = put(cfg, 1)
    other = put(cfg, 2, title="Otra")
    assert client.post(f"/item/{CARD}/ideas", data={"idea": idea.id}).status_code == 404
    assert client.post(f"/item/{other.id}/ideas", data={"idea": idea.id}).status_code == 404
    assert related_of(cfg, idea) == []


def test_an_idea_that_is_gone_is_said_and_nothing_is_written(cfg, client, link):
    answer = client.post(f"/item/{LINK}/ideas", data={"idea": "000000000000"},
                         follow_redirects=False)
    assert answer.headers["location"] == f"/item/{LINK}?notice=no-such-idea"
    assert not cfg.ideas.dir.exists() or list(cfg.ideas.dir.glob("*.md")) == []


def test_a_full_idea_is_said(cfg, client, link):
    idea = put(cfg, related=[f"n{i}" for i in range(16)])
    answer = client.post(f"/item/{LINK}/ideas", data={"idea": idea.id},
                         follow_redirects=False)
    assert answer.headers["location"] == f"/item/{LINK}?notice=idea-full"
    assert link.stem not in related_of(cfg, idea)


def test_the_idea_shows_its_links_by_their_real_titles(cfg, client, link):
    idea = put(cfg, related=[link.stem])
    assert f'<a href="/item/{LINK}">WireGuard</a>' in client.get(f"/item/{idea.id}").text


def test_a_link_that_is_not_there_any_more_is_dimmed_not_dropped(cfg, client):
    idea = put(cfg, related=["2026-01-01-borrada"])
    page = client.get(f"/item/{idea.id}").text
    assert 'class="gone"' in page
    assert "2026-01-01-borrada" in page


def test_a_link_leaves_the_idea(cfg, client, link):
    idea = put(cfg, related=[link.stem, "otro"])
    client.post(f"/item/{idea.id}/related/drop", data={"stem": link.stem})
    assert related_of(cfg, idea) == ["otro"]


def test_leaving_an_idea_that_is_not_there_is_404(client):
    answer = client.post("/item/000000000000/related/drop", data={"stem": "x"})
    assert answer.status_code == 404
```

- [ ] **Step 2: Run them to verify they fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest tests/test_web_ideas_related.py -q`
Expected: FAIL — no picker on the link page, and 405/404 on the two POSTs.

- [ ] **Step 3: The routes**

In `src/oknowledge/web/app.py`:

1. Import: `from ..ideas import IdeaFull, add_related, drop_related, new_idea`.
2. In `NOTICES`, after `"idea-empty"`:

```python
    "idea-full": "That idea already has 16 links. Take one off before adding another.",
    "no-such-idea": "That idea is not there any more.",
```

3. In `item()`, replace the final `return page(...)` with:

```python
        note = read_full(entry)
        extra = {}
        if where.name == "ideas":
            # Each link by its file name, resolved against the library now,
            # so a link that changed its title shows the new one -- and one
            # that is gone shows up dimmed, with an x, instead of vanishing.
            library.refresh()
            by_stem = {e.path.stem: e.note for e in library.entries}
            extra["related"] = [(stem, by_stem.get(stem)) for stem in note.related]
        elif where.name == "links":
            ideas.refresh()
            extra["idea_choices"] = [(n.id, n.title) for n in ideas.notes
                                     if n.state != "dropped"]
        return page(request, "item.html", note=note,
                    card=where.name == "ocio", idea=where.name == "ideas",
                    link=where.name == "links",
                    words=STATE_WORDS.get(entry.note.type, STATE_WORDS["movie"]),
                    STATES=states_for(entry.note.type), **extra)
```

4. After `collections_of()`:

```python
    @app.post("/item/{link_id}/ideas")
    def join_idea(link_id: str, idea: str = Form("")):
        """Add this link to one of your ideas.

        The idea's note is the one written -- the relation lives there, so
        the idea reads on its own in Obsidian -- under the idea's lock, and
        read again inside it. Only a link joins: a card or another idea is
        not something an idea is built from.
        """
        library.refresh()
        entry = library.entry(link_id)
        if entry is None:
            raise HTTPException(status_code=404, detail="no such link")
        stem = entry.path.stem
        try:
            result = edit(idea, lambda cfg, language: add_related(
                cfg, idea, stem, language), "saved", "indexes-stale", shelves=ideas)
        except IdeaFull:
            return see_other(item_url(link_id), notice="idea-full")
        if result.notice == MISSING:
            return see_other(item_url(link_id), notice="no-such-idea")
        return see_other(item_url(link_id), notice=result.notice)

    @app.post("/item/{link_id}/related/drop")
    def leave_idea(link_id: str, stem: str = Form("")):
        """Take one link off this idea, by the file name the idea holds --
        which is how a link that is gone can still be taken off."""
        result = edit(link_id, lambda cfg, language: drop_related(
            cfg, link_id, stem, language), "saved", "indexes-stale", shelves=ideas)
        if result.notice == MISSING:
            raise HTTPException(status_code=404, detail="no such idea")
        return see_other(item_url(link_id), notice=result.notice)
```

- [ ] **Step 4: The template and its style**

In `item.html`, inside `{% if idea %}`, right after the title-and-text form:

```html
        {% if related %}
          <h2>{{ t('Links for this idea') }}</h2>
          <ul class="related">
            {% for stem, found in related %}
              <li{% if not found %} class="gone"{% endif %}>
                {% if found %}
                  <a href="/item/{{ found.id|slug }}">{{ found.title }}</a>
                  <span class="cat">{{ found.category }}</span>
                {% else %}
                  <span title="{{ t('This note is not in your library any more') }}">{{ stem }}</span>
                {% endif %}
                <form action="/item/{{ note.id|slug }}/related/drop" method="post">
                  <button type="submit" name="stem" value="{{ stem }}"
                          title="{{ t('Remove from the idea') }}"
                          aria-label="{{ t('Remove from the idea') }}">×</button>
                </form>
              </li>
            {% endfor %}
          </ul>
        {% endif %}
```

Inside the actions block, right after the collections form (still inside
`{% if link %}`):

```html
      {% if idea_choices %}
      {# Your ideas, the dropped ones left out: the relation is noticed while
         reading the link, so this is where it is made. #}
      <form action="/item/{{ note.id|slug }}/ideas" method="post" class="field">
        <label for="field-idea">{{ t('Add to an idea') }}</label>
        <span class="row">
          <select id="field-idea" name="idea">
            {% for id, title in idea_choices %}<option value="{{ id }}">{{ title or t('Untitled idea') }}</option>{% endfor %}
          </select>
          <button type="submit">{{ t('Add') }}</button>
        </span>
      </form>
      {% endif %}
```

In `src/oknowledge/web/static/style.css`, at the end:

```css
/* An idea's links: one per line, an x to take one off, and a link that is
   not in the library any more dimmed rather than hidden. */
.related { list-style: none; padding: 0; }
.related li { display: flex; gap: .5em; align-items: center; }
.related li form { display: inline; }
.related li.gone { opacity: .55; }
```

- [ ] **Step 5: The words, and the meta-tests**

In `src/oknowledge/i18n.py`:

```python
        "Links for this idea": "Links de esta idea",
        "Add to an idea": "Sumar a una idea",
        "Remove from the idea": "Sacar de la idea",
        "This note is not in your library any more":
            "Esta nota ya no está en tu biblioteca",
        "That idea already has 16 links. Take one off before adding another.":
            "Esa idea ya tiene 16 links. Sacale uno antes de sumar otro.",
        "That idea is not there any more.": "Esa idea ya no está.",
```

In `tests/test_web_write.py`, add to `WRITE_ROUTES`:

```python
    # A link joining an idea, and leaving one. A cross-site POST here would
    # rewrite one of your ideas.
    ("/item/a1/ideas", {"idea": "x"}),
    ("/item/a1/related/drop", {"stem": "x"}),
```

and `"add_related", "drop_related"` to `VAULT_WRITERS`.

- [ ] **Step 6: Run the tests**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest tests/test_web_ideas_related.py tests/test_web_write.py tests/test_i18n.py -q`
Expected: all passed. Whole suite: 2039 passed (12 new here, four more
from the parametrized cross-site tests over the two new routes).

- [ ] **Step 7: Mutation**

```bash
~/.local/share/oknowledge/venv/bin/python /home/fer/.claude/jobs/d89ecc8a/tmp/mutate.py \
  src/oknowledge/web/app.py tests/test_web_ideas_related.py \
  'entry = library.entry(link_id)\n        if entry is None:|||entry = library.entry(link_id) or ideas.entry(link_id) or shelf.entry(link_id)\n        if entry is None:' \
  'if n.state != "dropped"]|||]' \
  'return see_other(item_url(link_id), notice="idea-full")|||raise' \
  'return see_other(item_url(link_id), notice="no-such-idea")|||raise HTTPException(status_code=404)'
```

Expected: every mutation killed.

- [ ] **Step 8: Commit**

```bash
git add src/oknowledge/web/app.py src/oknowledge/web/templates/item.html \
        src/oknowledge/web/static/style.css src/oknowledge/i18n.py \
        tests/test_web_ideas_related.py tests/test_web_write.py
git commit -m "feat: a link joins an idea from its own page, and the idea lists it"
```

---
### Task 9: El README, y una idea de verdad

**Files:**
- Modify: `README.md` (una sección después de `### Ocio`, y el árbol de `## The vault`)

**Interfaces:**
- Consumes: todo lo anterior.
- Produces: nada que otra tarea consuma.

- [ ] **Step 1: The README section**

In `README.md`, right before `## The vault`:

```markdown
### Ideas

**Write what occurred to you; the model files it.** The Ideas page has a *New
idea* form: the text is required, the title is optional. The idea is written
at once into `<vault>/oknowledge/ideas/`, your text under *Mi nota*, and the
rest comes in behind the page:

- **The model fills in what it is good at:** a title if you left it empty,
  the tags, a one-line summary and three to six points — what it solves, for
  whom, how it could work. Until it has, the idea says *sin completar*, and
  its page offers to ask again for when you have added to it.
- **What is yours stays yours:** your text, a title you typed, the state
  (*semilla / en marcha / hecha / descartada*), the stars and the links. No
  model writes any of them. The tags are the model's, as everywhere else in
  the app: asking again rewrites them.
- **A link joins an idea from the link's own page**, with *Sumar a una
  idea*. The idea keeps it as a wikilink in its own note, so it reads on its
  own in Obsidian; when the pipeline renames a link's file, the ideas that
  named it follow. A link that is not in the library any more shows dimmed,
  with an × to take it off.
- **Dropped ideas are kept, not shown:** the section hides them until you
  pick *descartada*.
```

In the `## The vault` tree, after the `ocio/` lines:

```
  ideas/                     your ideas, with their own index
    Ideas.md                 index, generated
    2026-10-12-gimnasio-con-ia.md
```

- [ ] **Step 2: An idea of verdad**

Every test above fakes the model. This step is the one place the real chain
answers, over a throwaway vault — never the user's. One model call.

```bash
SCRATCH=/tmp/claude-1000/-home-fer-Projects-gym/d89ecc8a-2029-44cb-b47f-742ed00daeae/scratchpad
mkdir -p "$SCRATCH/ideas-demo"
cat > "$SCRATCH/serve_ideas.py" <<'PY'
"""The real app and the real engine chain, over a throwaway vault."""
import dataclasses
import os
from pathlib import Path

base = Path(os.environ["SCRATCH"]) / "ideas-demo"
os.environ["XDG_STATE_HOME"] = str(base / "state")

import uvicorn  # noqa: E402

from oknowledge.config import load  # noqa: E402
from oknowledge.vault import rebuild_indexes  # noqa: E402
from oknowledge.web.app import create_app  # noqa: E402

vault = base / "vault"
(vault / "oknowledge" / "links").mkdir(parents=True, exist_ok=True)
cfg = dataclasses.replace(load(), vault=vault)
rebuild_indexes(cfg, cfg.language)
uvicorn.run(create_app(cfg), host="127.0.0.1", port=8806, log_level="warning")
PY
SCRATCH="$SCRATCH" ~/.local/share/oknowledge/venv/bin/python "$SCRATCH/serve_ideas.py" \
  > "$SCRATCH/ideas-demo/serve.log" 2>&1 &
echo $! > "$SCRATCH/ideas-demo/pid"
```

Then save one idea without a title, the way the form does:

```bash
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' \
  -H 'Origin: http://127.0.0.1:8806' \
  --data-urlencode 'text=Una app que me arme la rutina del gimnasio según lo que levanté la semana pasada, y que me vaya subiendo el peso sola.' \
  --data-urlencode 'title=' http://127.0.0.1:8806/ideas/guardar
```

Expected: `303 http://127.0.0.1:8806/item/<id>?notice=completing`, and one
file `ideas/2026-…-<id>.md` named after its id.

Wait for the model (Monitor or an until-loop on `grep -l '^engine:'` over
`$SCRATCH/ideas-demo/vault/oknowledge/ideas/*.md`, five minutes at most).
Expected: the file now has a real `title:`, `tags:`, a summary and
`## Puntos clave`, is **renamed** after that title, `## Mi nota` still holds
the text exactly as sent, and `ideas/Ideas.md` lists it by its new name.

- [ ] **Step 3: Look at it**

```bash
for page in ideas "item/<id>"; do
  chromium --headless=new --disable-gpu --hide-scrollbars \
    --user-data-dir="$SCRATCH/chromeprofile" --window-size=1280,1400 \
    --screenshot="$SCRATCH/ideas-demo/$(echo "$page" | tr '/' '-').png" \
    "http://127.0.0.1:8806/$page"
done
```

Read both PNGs. Expected: the grid card with the title, the one-line summary
and the tags; the idea's page with the title and text form, the four state
buttons, the stars, the links section absent (no links yet) and the
ask-again button. Then stop the server by its PID — `kill "$(cat
"$SCRATCH/ideas-demo/pid")"`, never `pkill -f`, which can match this
shell.

- [ ] **Step 4: The whole suite, and commit**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q`
Expected: 2039 passed.

```bash
git add README.md
git commit -m "docs: the ideas section in the README"
```

---

## Después de este plan

- Queda el tercer spec: las acciones sobre una idea —si ya existe en
  internet, qué se le parece, cómo mejorarla, cómo ampliarla, y cuáles de
  tus links le sirven—, con la decisión ya tomada de que **busca el motor**.
- El fork (`oknowledge-win`) no recibe nada de esto hasta que se decida.
