# Rediseño, entrega 1 (base + Biblioteca) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/` becomes the fixed three-column screen of the handoff (sidebar · list or cards · detail panel), dark only, in Geist, with a unified search-or-save field, inline autosaving edits and "Analizando…" cards for links being read; every other page keeps working inside the new sidebar.

**Architecture:** Server-rendered as today. Pure helpers (the `View` parsed from the query string, category colours, short dates, the notes a view shows, the sidebar groups) live in a new module `web/library_view.py` with unit tests. `base.html` becomes a grid with `sidebar.html` on the left; `/` renders `home.html` (unified field + `list.html` + `panel.html`), and two fragment routes (`/lista`, `/panel/{id}`) return the same partials for `static/shell.js` to swap in place. Writes keep using the existing POST routes; `shell.js` sends forms marked `data-inline` with `fetch` and shows the notice as a toast. Links being analysed come from the queue's held locks plus an in-memory "just added" map filled by `/add`.

**Tech Stack:** Python 3.12, FastAPI + Jinja2, plain JS (no build), pytest + TestClient, node `--check` for JS syntax, headless chromium for screenshots.

**Spec:** `docs/2026-10-14-rediseno-biblioteca-design.md`
**Visual reference:** `design_handoff_oknowledge_redesign/README.md` (exact px, colours, radii) and `design_handoff_oknowledge_redesign/oknowledge App.dc.html` (inline styles of every element; read it when a value is not in this plan). Screenshots `screenshots/01-pantalla.png` (cards) and `02-pantalla.png` (list).

## Global Constraints

- Code, Python names, commits and docstrings in English; every UI string goes through `t()` with its Spanish in `src/oknowledge/i18n.py` `STRINGS["es"]` (voseo, like the rest: "Buscá", "pegalo").
- `tests/test_i18n.py::test_every_string_a_template_asks_for_has_a_spanish_translation` and `::test_every_translated_string_is_one_the_code_asks_for` must stay green: add Spanish for new keys, delete entries whose key nothing asks for any more.
- No `|safe` and no `autoescape` in templates (`tests/test_web_read.py::test_no_template_marks_note_content_safe`).
- Never `datetime.utcnow()` / `utcfromtimestamp()`.
- No attribution lines (Co-Authored-By, Claude-Session, "Generated with") in commits.
- Suite: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider` from `/home/fer/Projects/oknowledge` (≈2 min, 2387 passing before this branch). Redirect output to a file and read its tail.
- Tokens (verbatim from the handoff): app bg `#141519`; surfaces `#17181d`, `#1a1b20` (card), `#1b1c21` (inputs/segmented), `#1f2026` (chips/menus), `#22232a` (active/hover), `#24252c` (floating), `#2a2c34` (segmented active); borders `#22232a`, `#24252b` (card), `#2a2b32` (inputs), `#33353e` (menus), `#565a6a` (selected card); text `#e7e7ea`, `#c9cbd1`, `#b4b6bd`, `#a2a4ac`, `#8b8d96`, `#6d6f78`, `#55575f`; accent `#a9b4de` (hover `#c9d0ee`); favourite `#d9b54a`; destructive `#e59a8f`; primary = bg `#e7e7ea` + text `#141519`; shadow `0 12px 32px #0008`.
- Category colour: dot `oklch(0.74 0.09 H)`, thumbnail fallback `oklch(0.30 0.045 H)`; hues Productividad 80, Programación 160, Redes 265, Salud 25; "no category" = `#6d6f78` / `#24252b`.
- Layout: `grid-template-columns: 216px minmax(0,1fr) 480px; grid-template-rows: minmax(0,1fr); height:100vh`; no `body` scroll on `/`.
- Chunk of the list: 60 items. Live search debounce 250 ms. Analysing poll 3 s. Toast 2.2 s. "Just added" window 120 s.
- Favourite is the mark `⭐` (shown ★), pinned is `📌`.
- Live checks only on a scratch vault under the session scratchpad, never the user's vault. Kill servers by PID after checking the command line.

## Review Focus

1. A pending queue entry whose process died (pending, lock not held) must not show as "Analizando…" forever — `analyzing()` lists only held locks plus the 120 s "just added" window; test in Task 6.
2. A link that finishes analysing within the 120 s window must stop showing as busy at once (the queue entry exists now, so the "just added" entry is ignored) — test in Task 6.
3. `sel` naming a link that is filtered out, deleted, or garbage (`/?sel=../x`) opens the first visible item, never a 500 — test in Task 4.
4. A search query that is only punctuation or only spaces behaves as no search (all notes, no "Nada coincide") — test in Task 2.
5. Pressing Enter in the unified field without JavaScript on a plain word must search (GET), not POST to `/add` — the hidden default submit button comes first in the form; test in Task 4.

---

### Task 1: Dark tokens and the Geist fonts

**Files:**
- Create: `src/oknowledge/web/static/fonts/` (5 `.woff2` + `OFL.txt`)
- Create: `src/oknowledge/web/static/app.css`
- Modify: `src/oknowledge/web/static/style.css:1-15` (`:root` and the dark media query)
- Modify: `src/oknowledge/web/templates/base.html` (load `app.css`)
- Modify: `pyproject.toml:37` (ship `web/static/fonts/*`)
- Test: `tests/test_web_theme.py` (new), `tests/test_packaging.py`

**Interfaces:**
- Produces: CSS custom properties on `:root` used by every later task: `--bg`, `--fg`, `--dim`, `--line`, `--accent`, `--card`, `--focus` (old names, remapped) and the new `--s1 … --s7`, `--b-div`, `--b-card`, `--b-input`, `--b-menu`, `--b-sel`, `--t1 … --t7`, `--acc`, `--acc-hi`, `--fav`, `--danger`, `--shadow`, `--mono`.

- [ ] **Step 1: Write the failing tests**

`tests/test_web_theme.py`:

```python
"""The look every page shares: the handoff's dark tokens and its fonts."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.web.app import create_app

STATIC = Path(__file__).resolve().parent.parent / "src" / "oknowledge" / "web" / "static"
FONTS = ("geist-400.woff2", "geist-500.woff2", "geist-600.woff2",
         "geist-mono-400.woff2", "geist-mono-500.woff2")


@pytest.fixture
def client(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    return TestClient(create_app(Config(vault=vault)))


def test_there_is_no_light_mode_any_more():
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    assert "prefers-color-scheme" not in css


def test_the_old_names_point_at_the_handoff_colours():
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    root = re.search(r":root\s*\{(.*?)\}", css, re.S).group(1)
    assert "--bg: #141519" in root
    assert "--fg: #e7e7ea" in root
    assert "--accent: #a9b4de" in root


def test_every_page_loads_the_new_stylesheet(client):
    body = client.get("/settings").text
    assert '<link rel="stylesheet" href="/static/app.css">' in body


@pytest.mark.parametrize("name", FONTS)
def test_the_fonts_are_served_from_here(client, name):
    answer = client.get(f"/static/fonts/{name}")
    assert answer.status_code == 200
    assert answer.content[:4] == b"wOF2"


def test_the_font_licence_ships_with_the_fonts():
    assert "SIL OPEN FONT LICENSE" in (STATIC / "fonts" / "OFL.txt").read_text(encoding="utf-8").upper()


def test_the_stylesheet_declares_both_families():
    css = (STATIC / "app.css").read_text(encoding="utf-8")
    assert css.count("@font-face") == 5
    assert 'font-family: "Geist Mono"' in css
    assert "font-display: swap" in css
```

Append to `tests/test_packaging.py` (after `test_every_prompt_the_code_loads_is_declared_as_package_data`):

```python
def test_every_static_file_is_declared_as_package_data():
    """The fonts live in a subfolder, and `web/static/*` does not reach it."""
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    globs = data["tool"]["setuptools"]["package-data"]["oknowledge"]
    package = ROOT / "src" / "oknowledge"

    missing = [str(p) for p in (package / "web" / "static").rglob("*")
               if p.is_file() and not shipped(p.relative_to(package).as_posix(), globs)]

    assert missing == [], f"served at runtime, shipped by nothing: {missing}"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_theme.py tests/test_packaging.py`
Expected: FAIL — `prefers-color-scheme` present, `--bg: #fbfbfa`, no `app.css` link, fonts 404, no `OFL.txt`. The packaging test passes for now (no subfolder yet); it fails after Step 3 until Step 4 edits `pyproject.toml`.

- [ ] **Step 3: Get the fonts**

```bash
cd /home/fer/Projects/oknowledge/src/oknowledge/web/static && mkdir -p fonts
SANS=$(curl -s https://registry.npmjs.org/@fontsource/geist-sans/latest | python3 -c 'import json,sys;print(json.load(sys.stdin)["version"])')
MONO=$(curl -s https://registry.npmjs.org/@fontsource/geist-mono/latest | python3 -c 'import json,sys;print(json.load(sys.stdin)["version"])')
for w in 400 500 600; do curl -sfL -o fonts/geist-$w.woff2 "https://cdn.jsdelivr.net/npm/@fontsource/geist-sans@$SANS/files/geist-sans-latin-$w-normal.woff2"; done
for w in 400 500; do curl -sfL -o fonts/geist-mono-$w.woff2 "https://cdn.jsdelivr.net/npm/@fontsource/geist-mono@$MONO/files/geist-mono-latin-$w-normal.woff2"; done
curl -sfL -o fonts/OFL.txt "https://cdn.jsdelivr.net/npm/@fontsource/geist-sans@$SANS/LICENSE"
head -c4 fonts/*.woff2 | cat -v; ls -l fonts
```

Expected: five files starting with `wOF2`, each 15–40 KB, and `OFL.txt` mentioning the SIL Open Font License. If the LICENSE file of the package is not the OFL text, fetch `https://raw.githubusercontent.com/vercel/geist-font/main/OFL.txt` instead.

- [ ] **Step 4: Remap the tokens, add `app.css`, ship the folder**

In `src/oknowledge/web/static/style.css` replace lines 1–15 (`:root { … }` and the whole `@media (prefers-color-scheme: dark) { … }` block with its comment) with:

```css
:root {
  /* The handoff's tokens (design_handoff_oknowledge_redesign/README.md).
     Dark only: its colours are final and there is no light version. */
  --s1: #17181d; --s2: #1a1b20; --s3: #1b1c21; --s4: #1f2026;
  --s5: #22232a; --s6: #24252c; --s7: #2a2c34;
  --b-div: #22232a; --b-card: #24252b; --b-input: #2a2b32;
  --b-menu: #33353e; --b-sel: #565a6a;
  --t1: #e7e7ea; --t2: #c9cbd1; --t3: #b4b6bd; --t4: #a2a4ac;
  --t5: #8b8d96; --t6: #6d6f78; --t7: #55575f;
  --acc: #a9b4de; --acc-hi: #c9d0ee; --fav: #d9b54a; --danger: #e59a8f;
  --shadow: 0 12px 32px #0008;
  --mono: "Geist Mono", ui-monospace, monospace;
  /* The names the older rules use, pointed at the same palette. */
  --bg: #141519; --fg: #e7e7ea; --dim: #8b8d96; --line: #22232a;
  --accent: #a9b4de; --card: #1a1b20; --focus: #a9b4de;
  --measure: 46rem;
  color-scheme: dark;
}
```

and in the `body` rule change the font to `font: 16px/1.65 "Geist", ui-sans-serif, system-ui, sans-serif;`.

Create `src/oknowledge/web/static/app.css`:

```css
/* The redesign (docs/2026-10-14-rediseno-biblioteca-design.md). Loaded after
   style.css: the older pages keep their rules, the new shell lives here. */
@font-face { font-family: "Geist"; font-weight: 400; font-style: normal;
  font-display: swap; src: url("/static/fonts/geist-400.woff2") format("woff2"); }
@font-face { font-family: "Geist"; font-weight: 500; font-style: normal;
  font-display: swap; src: url("/static/fonts/geist-500.woff2") format("woff2"); }
@font-face { font-family: "Geist"; font-weight: 600; font-style: normal;
  font-display: swap; src: url("/static/fonts/geist-600.woff2") format("woff2"); }
@font-face { font-family: "Geist Mono"; font-weight: 400; font-style: normal;
  font-display: swap; src: url("/static/fonts/geist-mono-400.woff2") format("woff2"); }
@font-face { font-family: "Geist Mono"; font-weight: 500; font-style: normal;
  font-display: swap; src: url("/static/fonts/geist-mono-500.woff2") format("woff2"); }

a { color: var(--acc); }
a:hover { color: var(--acc-hi); }
::placeholder { color: var(--t6); }
::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-thumb { background: var(--b-input); border-radius: 4px; }
.mono { font-family: var(--mono); }
```

In `base.html`, after `<link rel="stylesheet" href="/static/style.css">` add `<link rel="stylesheet" href="/static/app.css">`.

In `pyproject.toml` line 37: `oknowledge = ["prompts/*.txt", "web/templates/*.html", "web/static/*", "web/static/fonts/*"]`.

- [ ] **Step 5: Run the tests**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_theme.py tests/test_packaging.py`
Expected: PASS.

- [ ] **Step 6: Run the whole suite**

Run the suite (Global Constraints). Expected: all green. A test that asserted the light palette or the `prefers-color-scheme` block (grep `fbfbfa`, `prefers-color-scheme` in `tests/`) is about removed behaviour: delete that assertion and ledger it.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml src/oknowledge/web/static/fonts src/oknowledge/web/static/app.css \
        src/oknowledge/web/static/style.css src/oknowledge/web/templates/base.html \
        tests/test_web_theme.py tests/test_packaging.py
git commit -m "Go dark with the redesign's palette and ship Geist with the app"
```

---

### Task 2: What a view of the library is

**Files:**
- Create: `src/oknowledge/web/library_view.py`
- Modify: `src/oknowledge/web/app.py` (register the filters `dot`, `tint`, `short_date`, `paragraphs`; import `MONTHS` from the new module instead of defining it)
- Test: `tests/test_library_view.py` (new)

**Interfaces:**
- Consumes: `Library` (`web/index.py`: `.notes`, `.filter(category=, tag=, collection=)`, `.search(q, page=, per_page=) -> (list[Hit], int)`, `.categories()`, `.collections()`), `terms()` from `web/index.py`, `rank_marks()` from `marks.py`.
- Produces:
  - `CHUNK = 60`, `FAVORITE = "⭐"`, `PINNED = "📌"`, `MONTHS` (moved from `app.py:192`, same tuple).
  - `hue(name: str) -> int | None`, `dot(name: str) -> str`, `tint(name: str) -> str`
  - `short_date(saved: str, t) -> str` ("2026-10-04" → `"4 " + t("Oct")`)
  - `reading_minutes(text: str) -> int`
  - `paragraphs(text: str) -> list[str]`
  - `is_url(text: str) -> bool`
  - `@dataclass(frozen=True) class View` with fields `cat, tag, mark, col, q, sel: str = ""`, `vista: str = "tarjetas"`, `hasta: int = CHUNK`; `View.from_query(params: Mapping[str, str]) -> View`; properties `searching -> str` (the query to search, "" when none), `filtered -> bool`; methods `url(path: str = "/", **changes) -> str`, `label(t) -> str`.
  - `choose(library, view: View) -> list[Note]`
  - `side_groups(notes, categories: dict[str, int], collections: dict[str, int], marks) -> dict` with keys `total`, `categories`, `favorites`, `marks` (list of `(mark, count)`, 📌 first), `collections`.

- [ ] **Step 1: Write the failing tests**

`tests/test_library_view.py`:

```python
"""The library as one URL describes it: pure functions, no server."""

import pytest

from oknowledge.model import Note
from oknowledge.web.library_view import (
    CHUNK, View, choose, dot, hue, is_url, paragraphs, reading_minutes,
    short_date, side_groups, tint,
)


def t(text, *args):
    for i, arg in enumerate(args, 1):
        text = text.replace(f"%{i}", str(arg))
    return text


def note(id, category="Redes", tags=(), mark="", collections=(), saved="2026-10-04",
         title=None, summary="s"):
    return Note(id=id, url=f"https://e.com/{id}", title=title or id, category=category,
                tags=list(tags), type="article", source="e.com", saved=saved,
                summary=summary, mark=mark, collections=list(collections))


# --- colours ---------------------------------------------------------------

def test_the_handoff_categories_keep_their_hue():
    assert [hue(n) for n in ("Productividad", "Programación", "Redes", "Salud")] == [80, 160, 265, 25]


def test_any_other_category_gets_a_hue_that_does_not_change():
    assert hue("Cocina") == hue("Cocina")
    assert 0 <= hue("Cocina") < 360


def test_the_dot_and_the_tint_are_the_handoff_formulas():
    assert dot("Redes") == "oklch(0.74 0.09 265)"
    assert tint("Redes") == "oklch(0.30 0.045 265)"


def test_no_category_is_grey():
    assert hue("") is None
    assert dot("") == "#6d6f78"
    assert tint("") == "#24252b"


# --- small formats ---------------------------------------------------------

def test_a_short_date_is_day_and_month():
    assert short_date("2026-10-04", t) == "4 Oct"


@pytest.mark.parametrize("raw", ["", "2026", "someday", "2026-13-01"])
def test_a_date_that_is_not_one_is_shown_as_it_is(raw):
    assert short_date(raw, t) == raw


def test_reading_minutes_never_says_zero():
    assert reading_minutes("") == 1
    assert reading_minutes("palabra " * 450) == 2


def test_paragraphs_split_on_blank_lines():
    assert paragraphs("Uno.\nsigue\n\n  \nDos.") == ["Uno. sigue", "Dos."]


@pytest.mark.parametrize("text,expected", [
    ("https://x.com", True), ("http://x", True), ("www.x.com", True),
    ("  HTTPS://X.COM", True), ("docker", False), ("", False), ("http", False),
])
def test_what_counts_as_a_link_to_save(text, expected):
    assert is_url(text) is expected


# --- the view in the URL ---------------------------------------------------

def test_a_view_reads_its_parameters():
    view = View.from_query({"cat": "Redes", "tag": "vpn", "mark": "⭐", "col": "Casa",
                            "sel": "a1", "vista": "lista"})
    assert (view.cat, view.tag, view.mark, view.col, view.sel, view.vista) == (
        "Redes", "vpn", "⭐", "Casa", "a1", "lista")


def test_the_old_parameter_names_still_work():
    view = View.from_query({"category": "Redes", "collection": "Casa"})
    assert (view.cat, view.col) == ("Redes", "Casa")


def test_an_unknown_layout_is_cards():
    assert View.from_query({"vista": "mosaico"}).vista == "tarjetas"


@pytest.mark.parametrize("raw,expected", [("", CHUNK), ("x", CHUNK), ("-5", CHUNK),
                                          ("120", 120), ("130", 180), ("999999", 6000)])
def test_how_many_to_show_is_whole_chunks_within_limits(raw, expected):
    assert View.from_query({"hasta": raw}).hasta == expected


def test_the_query_is_squeezed():
    assert View.from_query({"q": "  wire   guard "}).q == "wire guard"


@pytest.mark.parametrize("q", ["", "   ", "!!!", "#"])
def test_a_query_with_no_words_is_no_search(q):
    view = View.from_query({"q": q})
    assert view.searching == ""
    assert not view.filtered


def test_a_link_in_the_field_is_not_a_search():
    assert View.from_query({"q": "https://x.com"}).searching == ""


def test_the_url_keeps_the_view_and_applies_changes():
    view = View.from_query({"cat": "Redes", "vista": "lista"})
    assert view.url(sel="a1") == "/?cat=Redes&sel=a1&vista=lista"
    assert view.url("/lista", desde=60) == "/lista?cat=Redes&vista=lista&desde=60"


def test_the_default_url_is_bare():
    assert View().url() == "/"


def test_a_search_drops_the_other_filters_from_the_url():
    assert View(cat="Redes", q="vpn").url() == "/?q=vpn"


@pytest.mark.parametrize("view,label", [
    (View(), "Library"), (View(cat="Redes"), "Redes"), (View(tag="vpn"), "#vpn"),
    (View(mark="⭐"), "Favorites"), (View(mark="📌"), "Pinned"), (View(mark="🔥"), "🔥"),
    (View(col="Casa"), "Casa"), (View(q="vpn"), "Results"),
])
def test_the_header_names_the_view(view, label):
    assert view.label(t) == label


# --- which notes ---------------------------------------------------------

class FakeLibrary:
    def __init__(self, notes):
        self._notes = notes

    @property
    def notes(self):
        return list(self._notes)

    def filter(self, category=None, tag=None, collection=None):
        found = self.notes
        if category:
            found = [n for n in found if n.category == category]
        if tag:
            found = [n for n in found if tag in n.tags]
        if collection:
            found = [n for n in found if collection in n.collections]
        return found

    def search(self, q, page=1, per_page=20):
        class Hit:
            def __init__(self, note):
                self.note = note
        hits = [Hit(n) for n in self._notes if q.lower() in n.title.lower()]
        return hits[:per_page], len(hits)


LIB = FakeLibrary([note("a", tags=["vpn"], mark="⭐", collections=["Casa"]),
                   note("b", category="Salud", mark="📌"),
                   note("c", category="Salud", tags=["vpn"])])


@pytest.mark.parametrize("view,ids", [
    (View(), ["a", "b", "c"]), (View(cat="Salud"), ["b", "c"]),
    (View(tag="vpn"), ["a", "c"]), (View(mark="⭐"), ["a"]),
    (View(col="Casa"), ["a"]), (View(cat="Salud", tag="vpn"), ["c"]),
    (View(q="b"), ["b"]), (View(q="https://b.com"), ["a", "b", "c"]),
])
def test_choose_applies_the_view(view, ids):
    assert [n.id for n in choose(LIB, view)] == ids


def test_a_search_is_not_cut_at_a_page():
    many = FakeLibrary([note(f"n{i}", title=f"vpn {i}") for i in range(150)])
    assert len(choose(many, View(q="vpn"))) == 150


# --- the sidebar ---------------------------------------------------------

def test_the_sidebar_counts_favourites_and_lists_the_other_marks_pinned_first():
    notes = [note("a", mark="⭐"), note("b", mark="🔥"), note("c", mark="🔥"), note("d", mark="📌")]
    groups = side_groups(notes, {"Redes": 4}, {}, ("⭐", "🔥", "📌"))
    assert groups["total"] == 4
    assert groups["favorites"] == 1
    assert groups["marks"] == [("📌", 1), ("🔥", 2)]


def test_pinned_is_there_even_when_nothing_is_pinned():
    groups = side_groups([note("a")], {"Redes": 1}, {"Casa": 1}, ("⭐", "📌"))
    assert groups["marks"] == [("📌", 0)]
    assert groups["collections"] == {"Casa": 1}
    assert groups["categories"] == {"Redes": 1}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_library_view.py`
Expected: FAIL at collection with `ModuleNotFoundError: No module named 'oknowledge.web.library_view'`.

- [ ] **Step 3: Write the module**

`src/oknowledge/web/library_view.py`:

```python
"""The library as one URL describes it, and the small formats the redesign
draws it with. Pure: no request, no disk -- what the routes and templates
in app.py need, testable on its own."""

from __future__ import annotations

import dataclasses
import re
import zlib
from collections.abc import Mapping
from dataclasses import dataclass

from ..marks import rank_marks
from .index import terms

CHUNK = 60
"""Items in the first answer and in each one after it."""

MOST = 100 * CHUNK
"""A URL can ask for this many at most: the page has to end somewhere."""

FAVORITE = "⭐"
PINNED = "📌"

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

HUES = {"Productividad": 80, "Programación": 160, "Redes": 265, "Salud": 25}
"""The handoff's own; any other category gets one from its name."""

NO_CATEGORY = ("#6d6f78", "#24252b")
LAYOUTS = ("tarjetas", "lista")
WORDS_A_MINUTE = 200


def hue(name: str) -> int | None:
    if not name:
        return None
    if name in HUES:
        return HUES[name]
    return zlib.crc32(name.casefold().encode("utf-8")) % 360


def dot(name: str) -> str:
    h = hue(name)
    return NO_CATEGORY[0] if h is None else f"oklch(0.74 0.09 {h})"


def tint(name: str) -> str:
    h = hue(name)
    return NO_CATEGORY[1] if h is None else f"oklch(0.30 0.045 {h})"


def short_date(saved: str, t) -> str:
    """"4 Oct": what a card has room for. Anything else is shown as it is."""
    match = re.fullmatch(r"\d{4}-(\d{2})-(\d{2})", saved or "")
    if not match or not 1 <= int(match.group(1)) <= 12:
        return saved
    return f"{int(match.group(2))} {t(MONTHS[int(match.group(1)) - 1])}"


def reading_minutes(text: str) -> int:
    return max(1, round(len(text.split()) / WORDS_A_MINUTE))


def paragraphs(text: str) -> list[str]:
    return [" ".join(p.split()) for p in re.split(r"\n\s*\n", text or "") if p.strip()]


def is_url(text: str) -> bool:
    """What the unified field saves instead of searching."""
    start = (text or "").strip().lower()
    return start.startswith(("http://", "https://", "www."))


def _count(raw: str) -> int:
    try:
        asked = int(raw)
    except (TypeError, ValueError):
        return CHUNK
    if asked <= CHUNK:
        return CHUNK
    return min(MOST, -(-asked // CHUNK) * CHUNK)


@dataclass(frozen=True)
class View:
    cat: str = ""
    tag: str = ""
    mark: str = ""
    col: str = ""
    q: str = ""
    sel: str = ""
    vista: str = "tarjetas"
    hasta: int = CHUNK

    @classmethod
    def from_query(cls, params: Mapping[str, str]) -> View:
        def get(*names: str) -> str:
            return next((params[n] for n in names if params.get(n)), "")
        vista = get("vista")
        return cls(cat=get("cat", "category"), tag=get("tag"), mark=get("mark"),
                   col=get("col", "collection"), q=" ".join(get("q").split()),
                   sel=get("sel"), vista=vista if vista in LAYOUTS else "tarjetas",
                   hasta=_count(get("hasta")))

    @property
    def searching(self) -> str:
        """The words to search for, or "" for none: a link is saved, not
        searched, and "!!!" has nothing to look for."""
        return self.q if self.q and not is_url(self.q) and terms(self.q) else ""

    @property
    def filtered(self) -> bool:
        return bool(self.searching or self.cat or self.tag or self.mark or self.col)

    def url(self, path: str = "/", **changes) -> str:
        own = {k: v for k, v in changes.items() if k in _FIELDS}
        extra = {k: v for k, v in changes.items() if k not in _FIELDS}
        view = dataclasses.replace(self, **own)
        if view.searching:
            pairs = [("q", view.q)]
        else:
            pairs = [("cat", view.cat), ("tag", view.tag), ("mark", view.mark),
                     ("col", view.col)]
        pairs += [("sel", view.sel),
                  ("vista", view.vista if view.vista != "tarjetas" else ""),
                  ("hasta", str(view.hasta) if view.hasta != CHUNK else "")]
        pairs += [(k, str(v)) for k, v in extra.items()]
        from urllib.parse import urlencode
        query = urlencode([(k, v) for k, v in pairs if v])
        return path + ("?" + query if query else "")

    def label(self, t) -> str:
        if self.searching:
            return t("Results")
        if self.mark == FAVORITE:
            return t("Favorites")
        if self.mark == PINNED:
            return t("Pinned")
        if self.mark:
            return self.mark
        if self.col:
            return self.col
        if self.tag:
            return "#" + self.tag
        return self.cat or t("Library")


_FIELDS = {f.name for f in dataclasses.fields(View)}


def choose(library, view: View) -> list:
    """The notes this view shows, newest first (or best first, searching)."""
    if view.searching:
        hits, _ = library.search(view.searching, page=1,
                                 per_page=max(1, len(library.notes)))
        return [hit.note for hit in hits]
    found = library.filter(category=view.cat or None, tag=view.tag or None,
                           collection=view.col or None)
    if view.mark:
        found = [n for n in found if n.mark == view.mark]
    return found


def side_groups(notes, categories: Mapping[str, int], collections: Mapping[str, int],
                marks) -> dict:
    """What the sidebar lists under the sections, with its counters."""
    notes = list(notes)
    used = [(m, n) for m, n in rank_marks(notes, marks) if m != FAVORITE]
    pinned = dict(used).get(PINNED, 0)
    return {"total": len(notes), "categories": dict(categories),
            "favorites": sum(1 for n in notes if n.mark == FAVORITE),
            "marks": [(PINNED, pinned), *[(m, n) for m, n in used if m != PINNED]],
            "collections": dict(collections)}
```

Move the `from urllib.parse import urlencode` to the module's imports (it is shown inline above only to keep the method readable; put it at the top).

In `app.py`: delete the `MONTHS = (...)` tuple at line ~192 and add `from .library_view import MONTHS, dot, paragraphs, short_date, tint` to the imports. After the existing `templates.env.filters["slug"] = …` line add:

```python
    templates.env.filters["dot"] = dot
    templates.env.filters["tint"] = tint
    templates.env.filters["short_date"] = short_date
    templates.env.filters["paragraphs"] = paragraphs
```

- [ ] **Step 4: Run the tests**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_library_view.py`
Expected: PASS. If `short_date(…)=="4 Oct"` fails because `t` is applied differently, fix the code, not the test.

- [ ] **Step 5: Whole suite, then commit**

Run the suite. Expected: green (nothing uses the module yet; `MONTHS` keeps working through the import).

```bash
git add src/oknowledge/web/library_view.py src/oknowledge/web/app.py tests/test_library_view.py
git commit -m "Describe a view of the library by its URL, with the redesign's colours and dates"
```

---

### Task 3: The sidebar on every page

**Files:**
- Create: `src/oknowledge/web/templates/sidebar.html`
- Modify: `src/oknowledge/web/templates/base.html` (whole file)
- Modify: `src/oknowledge/web/app.py` — `page()` (≈ line 745) adds `side`; the item route passes `section`
- Modify: `src/oknowledge/web/static/app.css` (append)
- Modify: `src/oknowledge/web/static/layout.js` (drop `details.paste` from its selector)
- Test: `tests/test_web_sidebar.py` (new)

**Interfaces:**
- Consumes: `side_groups` (Task 2) — not yet; this task draws only sections and footer. Groups come in Task 4 through the `groups` context key.
- Produces:
  - Context key `side = {"section": "links" | "ocio" | "ideas" | None, "counts": {"links": int, "ocio": int, "ideas": int}}` on every page.
  - `base.html` blocks: `app_class` (default `legacy`), `layout` (default: the legacy main column), plus the existing `title`, `head`, `body_class`, `main`, `scripts`.
  - Context key `groups` (optional): when present, `sidebar.html` draws CATEGORÍAS, MARCAS and COLECCIONES with links built by `view.url(...)` (needs `view` too).
  - Context key `toast` (bool, default False): the notice renders as `<p class="notice toast" role="status">`.

- [ ] **Step 1: Write the failing tests**

`tests/test_web_sidebar.py`:

```python
"""The sidebar that replaces the header on every page."""

import re

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.vault import rebuild_indexes, write_note
from oknowledge.web.app import create_app


def note(id, category="Redes"):
    return Note(id=id, url=f"https://e.com/{id}", title=id, category=category, tags=[],
                type="article", source="e.com", saved="2026-10-03", summary="s")


@pytest.fixture
def client(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    for i in range(3):
        write_note(cfg, note(f"a{i}"), "es")
    rebuild_indexes(cfg, "es")
    return TestClient(create_app(cfg))


def sidebar(body):
    return re.search(r'<aside class="sidebar".*?</aside>', body, re.S).group(0)


@pytest.mark.parametrize("path", ["/settings", "/ocio", "/ideas", "/import",
                                  "/categories", "/retry", "/nothing-here"])
def test_every_page_has_the_sidebar(client, path):
    body = client.get(path).text
    side = sidebar(body)
    assert 'href="/"' in side and 'href="/ocio"' in side and 'href="/ideas"' in side
    assert 'href="/settings"' in side and 'href="/categories"' in side and 'href="/retry"' in side


def test_the_old_header_is_gone(client):
    body = client.get("/settings").text
    assert "<header>" not in body
    assert 'action="/search"' not in body
    assert "paste-form" not in body


def test_the_sections_carry_their_counts(client):
    side = sidebar(client.get("/settings").text)
    assert re.search(r'href="/"[^>]*>.*?<b class="count[^"]*">3</b>', side, re.S)


@pytest.mark.parametrize("path,active", [("/ocio", "/ocio"), ("/ideas", "/ideas")])
def test_the_section_you_are_in_is_marked(client, path, active):
    side = sidebar(client.get(path).text)
    assert f'href="{active}" class="section on"' in side


def test_a_page_outside_the_sections_marks_none(client):
    assert "section on" not in sidebar(client.get("/settings").text)


def test_the_legacy_pages_scroll_in_their_own_column(client):
    body = client.get("/settings").text
    assert '<div class="app legacy">' in body
    assert '<div class="legacy-main">' in body
```

- [ ] **Step 2: Run them to verify they fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_sidebar.py`
Expected: FAIL — no `<aside class="sidebar"`.

- [ ] **Step 3: Write `sidebar.html`**

```jinja
{# The redesign's left column (handoff §1). Sections always; the library's
   groups only where the page passes `groups` and `view` (the library). #}
<aside class="sidebar" aria-label="{{ t('Sections') }}">
  <a class="logo" href="/">oknowledge</a>
  <nav class="sections">
    {% for key, href, name in (("links", "/", t("Library")), ("ocio", "/ocio", t("Leisure")), ("ideas", "/ideas", t("Ideas"))) %}
      <a href="{{ href }}" class="section{% if side.section == key %} on{% endif %}"
         {% if side.section == key %}aria-current="page"{% endif %}>
        <span>{{ name }}</span><b class="count mono">{{ side.counts[key] }}</b></a>
    {% endfor %}
  </nav>
  {% if groups is defined and groups %}
    <nav class="group" aria-label="{{ t('Categories') }}">
      <p class="group-title">{{ t('CATEGORIES') }}</p>
      <a href="{{ view.url(cat='', tag='', mark='', col='', q='', sel='') }}" data-nav
         class="filter{% if not view.filtered %} on{% endif %}"><i class="dot" style="background: #6d6f78"></i><span>{{ t('All') }}</span><b class="count mono">{{ groups.total }}</b></a>
      {% for name, count in groups.categories.items() %}
        <a href="{{ view.url(cat=name, tag='', mark='', col='', q='', sel='') }}" data-nav
           class="filter{% if view.cat == name and not view.searching and not view.tag and not view.mark and not view.col %} on{% endif %}"><i class="dot" style="background: {{ name|dot }}"></i><span>{{ name }}</span><b class="count mono">{{ count }}</b></a>
      {% endfor %}
      <a href="{{ view.url(cat='', tag='', mark='⭐', col='', q='', sel='') }}" data-nav
         class="filter{% if view.mark == '⭐' and not view.searching %} on{% endif %}"><i class="dot" style="background: var(--fav)"></i><span>★ {{ t('Favorites') }}</span><b class="count mono">{{ groups.favorites }}</b></a>
    </nav>
    <nav class="group" aria-label="{{ t('Marks') }}">
      <p class="group-title">{{ t('MARKS') }}</p>
      {% for mark, count in groups.marks %}
        <a href="{{ view.url(cat='', tag='', mark=mark, col='', q='', sel='') }}" data-nav
           class="filter{% if view.mark == mark and not view.searching %} on{% endif %}"><span class="emoji">{{ mark }}</span><span>{{ t('Pinned') if mark == '📌' else '' }}</span><b class="count mono">{{ count }}</b></a>
      {% endfor %}
    </nav>
    {% if groups.collections %}
      <nav class="group" aria-label="{{ t('Collections') }}">
        <p class="group-title">{{ t('COLLECTIONS') }}</p>
        {% for name, count in groups.collections.items() %}
          <a href="{{ view.url(cat='', tag='', mark='', col=name, q='', sel='') }}" data-nav
             class="filter{% if view.col == name and not view.searching %} on{% endif %}"><i class="dot" style="background: var(--t5)"></i><span>{{ name }}</span><b class="count mono">{{ count }}</b></a>
        {% endfor %}
      </nav>
    {% endif %}
  {% endif %}
  <nav class="foot">
    <a href="/categories">{{ t('Categories') }}</a>
    <a href="/retry">{{ t('Activity') }}{% if batch.running %} <b class="mono">{{ batch.done }}/{{ batch.total }}</b>{% elif batch.busy %} <b class="mono">{{ batch.busy|length }}</b>{% endif %}</a>
    <a href="/settings">{{ t('Settings') }}</a>
  </nav>
</aside>
```

- [ ] **Step 4: Rewrite `base.html`**

```jinja
<!doctype html>
<html lang="{{ lang }}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}oknowledge{% endblock %}</title>
  <link rel="stylesheet" href="/static/style.css">
  <link rel="stylesheet" href="/static/app.css">
  {% block head %}{% endblock %}
</head>
<body class="{% block body_class %}{% endblock %}" data-close="{{ t('Close') }}"
      data-redo-failed="{{ t('It could not be analysed. Try again.') }}"
      data-save-failed="{{ t('It could not be saved') }}"
      data-done="{{ t('Done: summary written') }}"
      data-failed="{{ t('The link could not be analysed') }}">
  <div class="app {% block app_class %}legacy{% endblock %}">
    {% include "sidebar.html" %}
    {% block layout %}
    <div class="legacy-main">
      {% if unreadable %}
        <p class="quiet" title="{{ links_dir }}">{% if unreadable == 1 %}{{ t('1 note could not be read and is not shown') }}{% else %}{{ t('%1 notes could not be read and are not shown', unreadable) }}{% endif %}</p>
      {% endif %}
      {% if notice and not toast %}<p class="notice">{{ notice }}</p>{% endif %}
      <main>{% block main %}{% endblock %}</main>
    </div>
    {% endblock %}
  </div>
  {% if notice and toast %}<p class="notice toast" role="status">{{ notice }}</p>{% endif %}
  {# Not deferred: it has to fold the page before the first paint. #}
  <script src="/static/layout.js"></script>
  {% block scripts %}{% endblock %}
</body>
</html>
```

The old header carried `{{ query }}`, the paste form and the marks nav; they are gone (the unified field in Task 4 replaces them on `/`). Templates that override `{% block body_class %}` keep working.

- [ ] **Step 5: Feed `side` from `page()`**

In `page()` (app.py ≈745), compute before building `base`:

```python
        section = context.pop("section", None) or section_of(request.url.path)
```

and add to the context passed to `TemplateResponse` (both the error branch and the normal one):

```python
                "side": {"section": section,
                         "counts": {"links": len(library.entries),
                                    "ocio": len(shelf.entries),
                                    "ideas": len(ideas.entries)}},
                "toast": False,
```

Add the module-level helper near `item_url`:

```python
def section_of(path: str) -> str | None:
    """Which sidebar section a page belongs to, by its path."""
    if path == "/" or path.startswith(("/lista", "/panel/")):
        return "links"
    for key in ("ocio", "ideas"):
        if path == f"/{key}" or path.startswith(f"/{key}/"):
            return key
    return None
```

In the `item` route, pass `section=where.name` to `page(...)` for ocio and ideas notes (`"links"` → `"links"`; the redirect in Task 5 takes that branch away). In `layout.js` change the selector `"details.filters, details.paste"` to `"details.filters"`.

- [ ] **Step 6: Style it**

Append to `app.css`:

```css
/* --- the shell -------------------------------------------------------- */
body { background: #141519; }
.app { display: grid; height: 100vh; grid-template-rows: minmax(0, 1fr); }
.app.legacy { grid-template-columns: 216px minmax(0, 1fr); }
.legacy-main { overflow-y: auto; min-height: 0; padding-top: 1.5rem; }

.sidebar { border-right: 1px solid var(--b-div); padding: 18px 12px 14px;
  display: flex; flex-direction: column; gap: 14px; min-height: 0; overflow-y: auto;
  font-size: 14px; }
.sidebar a { color: var(--t3); text-decoration: none; }
.sidebar .logo { font-weight: 600; font-size: 16px; padding: 0 10px; color: var(--t1); }
.sidebar nav { display: flex; flex-direction: column; gap: 2px; }
.sidebar .section, .sidebar .filter { display: flex; align-items: center; gap: 10px;
  padding: 8px 10px; border-radius: 8px; }
.sidebar .filter { padding: 7px 10px; }
.sidebar .section span, .sidebar .filter span:not(.emoji) { flex: 1; min-width: 0;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sidebar .on { background: var(--s5); color: var(--t1); }
.sidebar a:hover { background: var(--s5); }
.sidebar .count { color: var(--t6); font-size: 12px; font-weight: 400; }
.sidebar .dot, .dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; flex: none; }
.sidebar .group-title { font-size: 11px; letter-spacing: .08em; color: var(--t6);
  padding: 0 10px 6px; margin: 0; }
.sidebar .foot { margin-top: auto; font-size: 13px; }
.sidebar .foot a { padding: 7px 10px; color: var(--t5); }

.toast { position: fixed; top: 16px; left: 50%; transform: translateX(-50%);
  z-index: 50; margin: 0; background: var(--t1); color: #141519; border-radius: 10px;
  padding: 9px 14px; font-size: 13.5px; box-shadow: var(--shadow);
  animation: toast-out .3s ease 2.2s forwards; }
@keyframes toast-out { to { opacity: 0; visibility: hidden; } }

@media (max-width: 60rem) {
  .app, .app.legacy { display: block; height: auto; }
  .sidebar { border-right: 0; border-bottom: 1px solid var(--b-div); }
}
```

- [ ] **Step 7: Run the tests**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_sidebar.py`
Expected: PASS.

- [ ] **Step 8: Whole suite, adjust, commit**

Run the suite. Expected failures are tests that read the old header: the paste form in `base.html` (`tests/test_web_add.py`, `tests/test_web_layout.py`), the marks nav (`tests/test_web_marks.py`), the search box value (`query`). For each one:
- the behaviour still exists elsewhere (posting `/add` works, `/marked?mark=` still answers until Task 4) → change the assertion to the route, not the header markup;
- the behaviour is gone by the spec (header search box, paste `<details>`, marks in the header) → delete the test and ledger `Ruling: deleted <test> — <spec section that removes it>`.

```bash
git add -A src/oknowledge/web tests
git commit -m "Put every page beside the redesign's sidebar instead of under the header"
```

---

### Task 4: The library column

**Files:**
- Create: `src/oknowledge/web/templates/home.html`, `list.html`, `list-more.html`, `shelf-items.html`
- Delete: `src/oknowledge/web/templates/library.html`, `marked.html`, `mark-picker.html` (after checking `grep -rn "mark-picker\|library.html\|marked.html" src/` shows no other user)
- Modify: `src/oknowledge/web/app.py` — routes `/` (≈794), `/search` (≈829), `/marked` (≈841), new `/lista`; `/add` accepts `q`; delete `tag_chips`, `_clustered`, `when_urls`, `TAGS_SHOWN` and `pager`'s callers that only the old home used (keep `pager` if `/ocio` or others still call it — grep)
- Modify: `src/oknowledge/web/static/app.css` (append)
- Test: `tests/test_web_home.py` (new)

**Interfaces:**
- Consumes: `View`, `choose`, `side_groups`, `CHUNK`, `is_url` (Task 2); `side`, `groups`, `toast` (Task 3).
- Produces:
  - `listing(view: View, working: dict[str, str]) -> dict` (closure in `create_app`) with keys `view`, `notes` (the first `view.hasta`), `pending` (list of `(id, url)` not in the library), `busy` (set of ids being analysed), `total`, `more` (bool), `chunk`, `current` (id or ""), `saving` (bool).
  - `analyzing() -> dict[str, str]` (closure) — in this task it returns `{}`; Task 6 fills it.
  - Template macro file `shelf-items.html` with `item(note, view, current, busy)` and `pending(id, url, view, current)`; `list.html` expects the `listing` keys; `home.html` includes `list.html` inside `<div class="list" id="list">` and (Task 5) `panel.html` inside `<section class="detail" id="panel">`.
  - `GET /lista?<view params>[&desde=N]` → `list.html`, or with `desde` → `list-more.html`.

- [ ] **Step 1: Write the failing tests**

`tests/test_web_home.py`:

```python
"""`/`: the redesign's library column, driven by the URL."""

import re

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.vault import rebuild_indexes, write_note
from oknowledge.web.app import create_app


def note(id, title, category="Redes", tags=(), mark="", collections=(), saved="2026-10-03",
         summary="s"):
    return Note(id=id, url=f"https://e.com/{id}", title=title, category=category,
                tags=list(tags), type="article", source="e.com", saved=saved,
                summary=summary, mark=mark, collections=list(collections))


@pytest.fixture
def client(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    write_note(cfg, note("a1", "WireGuard simple", tags=["vpn"], mark="⭐",
                         collections=["Casa conectada"], saved="2026-10-04"), "es")
    write_note(cfg, note("b2", "Masa madre", category="Cocina", mark="📌",
                         saved="2026-09-20"), "es")
    write_note(cfg, note("c3", "Rutinas de fuerza", category="Salud", tags=["vpn"],
                         saved="2026-09-11"), "es")
    rebuild_indexes(cfg, "es")
    return TestClient(create_app(cfg))


@pytest.fixture
def big(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    for i in range(130):
        write_note(cfg, note(f"n{i:03d}", f"Nota {i:03d}", saved=f"2026-{1 + i % 12:02d}-01"), "es")
    rebuild_indexes(cfg, "es")
    return TestClient(create_app(cfg))


def items(body):
    return re.findall(r'<li class="item[^"]*" id="card-([^"]+)"', body)


def test_the_home_is_three_columns(client):
    body = client.get("/").text
    assert '<div class="app home">' in body
    assert '<section class="center"' in body
    assert '<section class="detail" id="panel"' in body


def test_everything_newest_first(client):
    assert items(client.get("/").text) == ["a1", "b2", "c3"]


@pytest.mark.parametrize("query,ids", [
    ("cat=Cocina", ["b2"]), ("tag=vpn", ["a1", "c3"]), ("mark=⭐", ["a1"]),
    ("mark=📌", ["b2"]), ("col=Casa conectada", ["a1"]), ("q=masa", ["b2"]),
    ("category=Salud", ["c3"]), ("collection=Casa conectada", ["a1"]),
])
def test_each_filter(client, query, ids):
    assert items(client.get("/?" + query).text) == ids


def test_the_header_names_the_view_and_counts_it(client):
    body = client.get("/?cat=Cocina").text
    assert re.search(r'class="list-head">\s*<span>Cocina · <b class="mono">1</b>', body)


def test_the_sidebar_lists_categories_marks_and_collections(client):
    side = re.search(r'<aside class="sidebar".*?</aside>', client.get("/").text, re.S).group(0)
    for text in ("Redes", "Cocina", "Salud", "Favorites", "📌", "Casa conectada"):
        assert text in side
    assert 'class="filter on"' in side          # "All" is the one on


def test_the_active_filter_is_marked(client):
    side = re.search(r'<aside class="sidebar".*?</aside>', client.get("/?cat=Salud").text, re.S).group(0)
    assert re.search(r'cat=Salud"[^>]*class="filter on"', side)


def test_cards_by_default_and_rows_on_request(client):
    assert '<ul class="items tiles"' in client.get("/").text
    assert '<ul class="items rows"' in client.get("/?vista=lista").text


def test_a_card_selects_its_note_without_leaving_the_view(client):
    body = client.get("/?cat=Redes").text
    assert 'href="/?cat=Redes&amp;sel=a1" data-sel="a1"' in body


def test_a_card_shows_category_colour_domain_and_favourite(client):
    body = client.get("/").text
    card = re.search(r'id="card-a1".*?</li>', body, re.S).group(0)
    assert "oklch(0.74 0.09 265)" in card       # the Redes dot
    assert "e.com" in card
    assert "★" in card
    assert "4 Oct" in card


def test_the_first_item_is_selected_when_none_is_asked(client):
    assert 'id="card-a1"' in client.get("/").text
    assert re.search(r'<li class="item on" id="card-a1"', client.get("/").text)


@pytest.mark.parametrize("sel", ["zzz", "../x", "b2"])
def test_a_selection_outside_the_view_falls_back_to_the_first(client, sel):
    body = client.get(f"/?cat=Salud&sel={sel}").text
    assert re.search(r'<li class="item on" id="card-c3"', body)


def test_a_search_with_no_hits_says_so(client):
    body = client.get("/?q=zanahoria").text
    assert "Nothing matches “zanahoria”" in body
    assert 'href="/">See everything</a>' in body


def test_an_empty_filter_says_so(client):
    body = client.get("/?tag=nada").text
    assert "There is nothing in #nada" in body


def test_a_query_of_punctuation_is_everything(client):
    assert items(client.get("/?q=!!!").text) == ["a1", "b2", "c3"]


def test_a_link_in_the_field_switches_it_to_saving(client):
    body = client.get("/?q=https://nuevo.com/x").text
    assert '<form class="unified saving"' in body
    assert items(body) == ["a1", "b2", "c3"]


def test_enter_without_javascript_searches(client):
    form = re.search(r'<form class="unified.*?</form>', client.get("/").text, re.S).group(0)
    first = re.search(r"<button[^>]*>", form).group(0)
    assert "formaction" not in first             # the default button is the GET one


def test_the_save_button_posts_to_add(client):
    form = re.search(r'<form class="unified.*?</form>', client.get("/").text, re.S).group(0)
    assert 'formaction="/add"' in form and 'formmethod="post"' in form
    assert 'name="content" value="full"' in form and 'name="content" value="summary"' in form


def test_add_takes_the_link_from_the_unified_field(client, monkeypatch):
    from oknowledge.web import app as module
    monkeypatch.setattr(module, "fetch", lambda *a, **k: None)
    answer = client.post("/add", data={"q": "https://nuevo.com/x", "content": "full"},
                         follow_redirects=False)
    assert answer.status_code == 303
    assert "notice=reading" in answer.headers["location"]


def test_the_list_fragment_is_the_column_alone(client):
    body = client.get("/lista?cat=Cocina").text
    assert "<html" not in body
    assert items(body) == ["b2"]


def test_sixty_at_first_and_a_way_to_more(big):
    body = big.get("/").text
    assert len(items(body)) == 60
    assert re.search(r'<a class="more" href="/\?hasta=120" data-more="/lista\?desde=60"', body)


def test_more_without_javascript_draws_the_longer_list(big):
    assert len(items(big.get("/?hasta=120").text)) == 120


def test_more_with_javascript_is_the_next_chunk_alone(big):
    body = big.get("/lista?desde=120").text
    assert len(items(body)) == 10
    assert 'class="more"' not in body


def test_search_and_marked_redirect_to_the_home(client):
    answer = client.get("/search?q=masa", follow_redirects=False)
    assert answer.status_code == 303 and answer.headers["location"] == "/?q=masa"
    answer = client.get("/marked?mark=⭐", follow_redirects=False)
    assert answer.headers["location"] == "/?mark=%E2%AD%90"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_home.py`
Expected: FAIL — no `app home`, no `items tiles`.

- [ ] **Step 3: The item macros**

`shelf-items.html`:

```jinja
{# One note in the library column, as a card or a row: the same markup, the
   class on the <ul> decides (handoff §2). The whole item selects the note;
   leaving for the original is the panel's job. #}
{% macro item(note, view, current, busy) -%}
<li class="item{% if note.id == current %} on{% endif %}" id="card-{{ note.id }}"
    {%- if note.id in busy %} data-working="{{ note.id }}"{% endif %}>
  <a class="hit" href="{{ view.url(sel=note.id) }}" data-sel="{{ note.id }}">
    <span class="thumb" style="background: {{ note.category|tint }}">
      {% if note.cover %}<img src="/cover/{{ note.id|slug }}" alt="" loading="lazy">{% endif %}
      {% if note.source %}<span class="domain mono">{{ note.source }}</span>{% endif %}
      {% if note.mark %}<span class="flag{% if note.mark == '⭐' %} fav{% endif %}">{{ '★' if note.mark == '⭐' else note.mark }}</span>{% endif %}
    </span>
    <span class="text">
      <span class="title" dir="auto">{{ note.title }}</span>
      <span class="sub"><i class="dot" style="background: {{ note.category|dot }}"></i>
        {%- if note.id in busy %}<em class="busy">{{ t('Analysing…') }}</em>
        {%- else %}{{ note.category or t('No category') }} · {{ note.saved|short_date(t) }}{% endif %}</span>
    </span>
    <span class="date mono">{{ note.saved|short_date(t) }}</span>
  </a>
</li>
{%- endmacro %}

{% macro pending(id, url, view, current) -%}
<li class="item pending{% if id == current %} on{% endif %}" id="card-{{ id }}" data-working="{{ id }}">
  <a class="hit" href="{{ view.url(sel=id) }}" data-sel="{{ id }}">
    <span class="thumb" style="background: #24252b"></span>
    <span class="text">
      <span class="title" dir="auto">{{ url }}</span>
      <span class="sub"><i class="dot" style="background: #6d6f78"></i><em class="busy">{{ t('Analysing…') }}</em></span>
    </span>
    <span class="date mono"></span>
  </a>
</li>
{%- endmacro %}
```

- [ ] **Step 4: The column templates**

`list.html`:

```jinja
{% import "shelf-items.html" as shelf with context %}
<div class="list-head">
  <span>{{ view.label(t) }} · <b class="mono">{{ total }}</b></span>
  <nav class="seg" aria-label="{{ t('Layout') }}">
    <a href="{{ view.url(vista='lista') }}" data-view="lista"
       class="{% if view.vista == 'lista' %}on{% endif %}">{{ t('List') }}</a>
    <a href="{{ view.url(vista='tarjetas') }}" data-view="tarjetas"
       class="{% if view.vista == 'tarjetas' %}on{% endif %}">{{ t('Cards') }}</a>
  </nav>
</div>
<div class="list-body" id="list-body">
  {% if notes or pending %}
    <ul class="items {{ 'rows' if view.vista == 'lista' else 'tiles' }}" id="items" data-current="{{ current }}">
      {% for id, url in pending %}{{ shelf.pending(id, url, view, current) }}{% endfor %}
      {% for note in notes %}{{ shelf.item(note, view, current, busy) }}{% endfor %}
    </ul>
    {% if more %}<a class="more" href="{{ view.url(hasta=view.hasta + chunk) }}" data-more="{{ view.url('/lista', desde=view.hasta) }}">{{ t('Show more') }}</a>{% endif %}
  {% elif view.searching %}
    <div class="empty-state">
      <p class="empty-title">{{ t('Nothing matches “%1”', view.q) }}</p>
      <p>{{ t('Try another word or a tag. If it is a new link, paste it whole with https:// to save it.') }}</p>
      <a class="btn" href="/">{{ t('See everything') }}</a>
    </div>
  {% elif view.filtered %}
    <div class="empty-state">
      <p class="empty-title">{{ t('There is nothing in %1', view.label(t)) }}</p>
      <p>{{ t('Mark a link from its panel, or move it here from the category chip.') }}</p>
      <a class="btn" href="/">{{ t('See everything') }}</a>
    </div>
  {% else %}
    <div class="empty-state"><p class="empty-title">{{ t('Nothing saved yet') }}</p>
      <p>{{ t('Paste a link in the box above to save it.') }}</p></div>
  {% endif %}
</div>
```

`list-more.html`:

```jinja
{% import "shelf-items.html" as shelf with context %}
<ul>{% for note in notes %}{{ shelf.item(note, view, current, busy) }}{% endfor %}</ul>
{% if more %}<a class="more" href="{{ view.url(hasta=next_hasta) }}" data-more="{{ view.url('/lista', desde=next_desde) }}">{{ t('Show more') }}</a>{% endif %}
```

`home.html`:

```jinja
{% extends "base.html" %}
{% block title %}{% if view.searching %}{{ view.q }} - {% endif %}oknowledge{% endblock %}
{% block app_class %}home{% endblock %}
{% block scripts %}<script src="/static/shell.js" defer></script>{% endblock %}
{% block layout %}
<section class="center" aria-label="{{ t('Library') }}">
  {# GET by default, so Enter searches without JavaScript; the hidden first
     button is the form's default one. Save posts the same field to /add. #}
  <form class="unified{% if saving %} saving{% endif %}" id="unified" action="/" method="get" role="search">
    <button type="submit" class="default-submit" tabindex="-1" aria-hidden="true"></button>
    <input type="text" name="q" id="field-q" value="{{ view.q }}" autocomplete="off"
           inputmode="search" aria-label="{{ t('Search or paste a link to save it') }}"
           placeholder="{{ t('Search or paste a link to save it') }}">
    {% if view.vista == 'lista' %}<input type="hidden" name="vista" value="lista">{% endif %}
    <span class="save">
      <span class="seg">
        <label><input type="radio" name="content" value="full"{% if default_content == 'full' %} checked{% endif %}><span>{{ t('Full') }}</span></label>
        <label><input type="radio" name="content" value="summary"{% if default_content == 'summary' %} checked{% endif %}><span>{{ t('Summary') }}</span></label>
      </span>
      <button type="submit" class="btn primary" formmethod="post" formaction="/add" id="save-link">{{ t('Save') }} ↵</button>
    </span>
    <kbd class="hint mono">/</kbd>
  </form>
  <div class="list" id="list">{% include "list.html" %}</div>
</section>
<section class="detail" id="panel" aria-label="{{ t('Detail') }}">
  {% if panel %}{% include "panel.html" %}{% else %}<p class="detail-empty">{{ t('Choose a link to read it here.') }}</p>{% endif %}
</section>
{% endblock %}
```

Until Task 5, create `panel.html` with the single line `<div class="detail-scroll"><h1 dir="auto">{{ note.title }}</h1></div>` so the include works; Task 5 replaces it.

- [ ] **Step 5: The routes**

In `create_app`, replace the `home`, `search` and `marked` routes (≈794–855) with:

```python
    def analyzing() -> dict[str, str]:
        """{id: url} of the links being analysed right now. Task 6."""
        return {}

    def listing(view: View, working: dict[str, str]) -> dict:
        notes = choose(library, view)
        known = {n.id for n in library.notes}
        # Only on the unfiltered list: a link being read has no category,
        # tag or mark yet, so no filter could hold it.
        pending = [] if view.filtered else [(i, u) for i, u in working.items() if i not in known]
        ids = [i for i, _ in pending] + [n.id for n in notes]
        current = view.sel if view.sel in ids else (ids[0] if ids else "")
        return {"view": view, "notes": notes[:view.hasta], "pending": pending,
                "busy": set(working), "total": len(notes) + len(pending),
                "more": len(notes) > view.hasta, "chunk": CHUNK,
                "current": current, "saving": is_url(view.q)}

    def panel_context(link_id: str, view: View, working: dict[str, str]) -> dict | None:
        """Task 5 fills this in; until then the panel shows the title."""
        entry = library.entry(link_id)
        if entry is None:
            return None
        return {"note": entry.note}

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request):
        library.refresh()
        view = View.from_query(request.query_params)
        working = analyzing()
        shown = listing(view, working)
        panel = panel_context(shown["current"], view, working) if shown["current"] else None
        return page(request, "home.html", section="links", toast=True,
                    groups=side_groups(library.notes, library.categories(),
                                       library.collections(), current["cfg"].marks),
                    default_content=current["cfg"].default_content,
                    panel=panel is not None, **shown, **(panel or {}))

    @app.get("/lista", response_class=HTMLResponse)
    def list_column(request: Request, desde: str = ""):
        library.refresh()
        view = View.from_query(request.query_params)
        shown = listing(view, analyzing())
        if not desde:
            return page(request, "list.html", **shown)
        try:
            start = max(0, int(desde))
        except ValueError:
            start = 0
        notes = choose(library, view)
        end = start + CHUNK
        return page(request, "list-more.html", **{**shown, "notes": notes[start:end],
                    "more": len(notes) > end, "next_desde": end,
                    "next_hasta": end + CHUNK})

    @app.get("/search")
    def search(q: str = ""):
        return see_other("/", q=" ".join(q.split()))

    @app.get("/marked")
    def marked(mark: str = ""):
        return see_other("/", mark=mark)
```

`see_other("/", q="")` returns a bare `/` (it drops empty params). Imports: `from .library_view import CHUNK, MONTHS, View, choose, dot, is_url, paragraphs, short_date, side_groups, tint`.

In `/add`, add the parameter `q: str = Form("")` and as the first line of the body `url = url or q`. Delete the now-unused helpers (`tag_chips`, `_clustered`, `TAGS_SHOWN`, `when_urls`, and anything else `grep -n` shows only the old home used) and their unit tests; ledger each deletion.

- [ ] **Step 6: Style the column**

Append to `app.css` (values from handoff §2; check against `screenshots/01-pantalla.png` and `02-pantalla.png`):

```css
/* --- the library ------------------------------------------------------- */
.app.home { grid-template-columns: 216px minmax(0, 1fr) 480px; overflow: hidden; }
.center { display: flex; flex-direction: column; min-height: 0; min-width: 0;
  border-right: 1px solid var(--b-div); }
.unified { display: flex; align-items: center; gap: 8px; padding: 16px 20px;
  border-bottom: 1px solid var(--b-div); position: relative; }
.unified input[type=text] { flex: 1; height: 42px; padding: 0 14px; background: var(--s3);
  border: 1px solid var(--b-input); border-radius: 10px; color: var(--t1); font: inherit;
  font-size: 14px; }
.unified input[type=text]:focus { outline: none; border-color: var(--b-sel); }
.default-submit { position: absolute; width: 1px; height: 1px; opacity: 0;
  pointer-events: none; border: 0; padding: 0; }
.unified .hint { position: absolute; right: 30px; font-size: 11px; color: var(--t7);
  border: 1px solid var(--b-input); border-radius: 4px; padding: 0 5px; }
.unified .save { display: none; align-items: center; gap: 8px; }
.unified.saving .save { display: flex; }
.unified.saving .hint { display: none; }
.seg { display: inline-flex; background: var(--s3); border-radius: 8px; padding: 3px; gap: 2px; }
.seg a, .seg label span { display: block; padding: 3px 9px; border-radius: 6px; font-size: 12.5px;
  color: var(--t5); text-decoration: none; cursor: pointer; }
.seg a.on, .seg input:checked + span { background: var(--s7); color: var(--t1); }
.seg input { position: absolute; opacity: 0; pointer-events: none; }
.btn { display: inline-flex; align-items: center; gap: 6px; height: 32px; padding: 0 12px;
  border-radius: 8px; border: 1px solid var(--b-input); background: var(--s3);
  color: var(--t1); font: inherit; font-size: 13px; cursor: pointer; text-decoration: none;
  white-space: nowrap; }
.btn:hover { background: var(--s5); color: var(--t1); }
.btn.primary { background: var(--t1); color: #141519; border-color: var(--t1); font-weight: 500; }
.btn.primary:hover { background: #fff; color: #141519; }

.list { flex: 1; display: flex; flex-direction: column; min-height: 0; }
.list-head { display: flex; justify-content: space-between; align-items: center;
  padding: 14px 20px 8px; font-size: 13px; color: var(--t5); }
.list-head b { font-weight: 400; }
.list-body { flex: 1; overflow-y: auto; min-height: 0; padding: 4px 20px 80px; }
.items { list-style: none; margin: 0; padding: 0; }
.items .hit { color: inherit; text-decoration: none; display: block; }

.tiles { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px;
  grid-auto-rows: max-content; }
.tiles .item { background: var(--s2); border: 1px solid var(--b-card); border-radius: 10px;
  overflow: hidden; }
.tiles .item.on { border-color: var(--b-sel); }
.tiles .thumb { position: relative; display: block; height: 92px; }
.tiles .thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
.tiles .domain { position: absolute; left: 8px; bottom: 8px; font-size: 11px;
  background: #141519cc; color: var(--t2); padding: 2px 6px; border-radius: 5px; }
.tiles .flag { position: absolute; right: 8px; top: 6px; font-size: 13px; }
.flag.fav { color: var(--fav); }
.tiles .text { display: block; padding: 10px 12px 12px; }
.tiles .title { font-size: 13.5px; font-weight: 500; line-height: 1.35; color: var(--t1);
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.items .sub { display: flex; align-items: center; gap: 6px; margin-top: 6px;
  font-size: 11.5px; color: var(--t6); }
.items .busy { color: var(--acc); font-style: normal; }
.tiles .date { display: none; }

.rows .item { border-radius: 8px; }
.rows .item.on, .rows .item:hover { background: var(--s5); }
.rows .hit { display: grid; grid-template-columns: 8px minmax(0, 1fr) auto; gap: 12px;
  align-items: center; padding: 10px; }
.rows .thumb { display: none; }
.rows .text { grid-column: 2; }
.rows .title { display: block; font-size: 14px; font-weight: 500; color: var(--t1);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.rows .sub { font-size: 12px; margin-top: 2px; }
.rows .date { font-size: 12px; color: var(--t6); }
.rows .hit::before { content: ""; }

.more { display: block; text-align: center; margin: 16px 0; color: var(--t5); font-size: 13px; }
.empty-state { margin: 18vh auto 0; max-width: 26rem; text-align: center; color: var(--t5);
  font-size: 13.5px; }
.empty-title { color: var(--t1); font-size: 16px; font-weight: 500; }

.detail { display: flex; flex-direction: column; min-height: 0; }
.detail-empty { margin: auto; color: var(--t6); font-size: 13.5px; }
```

(The row's leading colour dot is the `.dot` inside `.sub`; if the handoff row shows it in its own grid cell, move it with `order`/grid in this block — screenshot 02 is the reference.)

- [ ] **Step 7: Run the tests**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_home.py tests/test_library_view.py tests/test_web_sidebar.py`
Expected: PASS.

- [ ] **Step 8: Whole suite, adjust, commit**

Run the suite. Expected failures: tests of the old library page (`tests/test_web_read.py`, `test_web_findability.py`, `test_web_write.py` parts about the library grid, tag strip, timeline/`when`, pick mode and `/collections/add` from the library, pagination, search hits list with snippets, `/marked` listing across shelves, `mark-picker`). For each:
- the behaviour survives (filtering by category/tag/collection, search finding by summary/body, newest first, accent-insensitive search) → rewrite the assertion against `/` or `/?q=` and the `items()` helper style;
- the behaviour is removed by the spec (tag strip, year/month timeline, pick mode in the library, pager, search snippets, `/marked` across shelves, the card mark-picker) → delete the test and ledger `Ruling: deleted <test> — spec <section>`.
`/collections/add` and `/collections/remove` routes stay (multi-select in delivery 3 will use them); their route tests stay.

```bash
git add -A src/oknowledge/web tests
git commit -m "Make the library a column of cards or rows that follows the URL"
```

---

### Task 5: The detail panel

**Files:**
- Modify: `src/oknowledge/web/templates/panel.html` (full content)
- Modify: `src/oknowledge/web/app.py` — `panel_context` (from Task 4), new `GET /panel/{link_id}`, the `item` route redirects links, `/item/{id}/tags` accepts `add`
- Modify: `src/oknowledge/web/templates/item.html` — remove the `{% if link %}` blocks (category/tags/collection/idea forms, reprocess select, delete) that only links used, now that links never render it; keep what ocio cards and ideas use
- Modify: `src/oknowledge/web/static/app.css` (append)
- Test: `tests/test_web_panel.py` (new)

**Interfaces:**
- Consumes: `View`, `reading_minutes`, `paragraphs`, `FAVORITE` (Task 2); `listing`, `analyzing`, `home.html` (Task 4).
- Produces: `panel_context(link_id, view, working) -> dict | None` with keys `note` (full `Note` or None), `panel_id`, `pending_url` (str, only when the note does not exist yet), `reading` (bool — not `busy`, which is the list's set of ids and is merged into the same context on `/`), `minutes`, `idea_choices` (list of `(id, title)`), `back` (`view.url(sel=link_id)`); route `GET /panel/{link_id}?<view params>` → `panel.html` fragment, 404 when neither a note nor a link being analysed.

- [ ] **Step 1: Write the failing tests**

`tests/test_web_panel.py`:

```python
"""The detail panel of a link: read, and edit in place."""

import re

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.model import Mention, Note
from oknowledge.vault import rebuild_indexes, write_note
from oknowledge.web.app import create_app


def note(id, title="WireGuard simple", **extra):
    base = dict(id=id, url=f"https://wireguard.com/{id}", title=title, category="Redes",
                tags=["vpn", "redes"], type="article", source="wireguard.com",
                saved="2026-10-04", summary="Uno dos tres.\n\nCuatro cinco.",
                points=["Rápido", "Simple", "Seguro"], collections=["Casa conectada"])
    base.update(extra)
    return Note(**base)


@pytest.fixture
def cfg(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    write_note(cfg, note("a1", mark="⭐",
                         mentions=[Mention(name="Pi-hole", url="https://pi-hole.net")]), "es")
    write_note(cfg, note("b2", title="Masa madre", mark="", collections=[]), "es")
    rebuild_indexes(cfg, "es")
    return cfg


@pytest.fixture
def client(cfg):
    return TestClient(create_app(cfg))


def panel(client, id, query=""):
    answer = client.get(f"/panel/{id}{query}")
    assert answer.status_code == 200
    return answer.text


def test_the_panel_is_a_fragment(client):
    body = panel(client, "a1")
    assert "<html" not in body
    assert '<h1 dir="auto">WireGuard simple</h1>' in body


def test_an_unknown_link_has_no_panel(client):
    assert client.get("/panel/nope").status_code == 404


def test_the_home_draws_the_selected_panel(client):
    body = client.get("/?sel=b2").text
    assert '<h1 dir="auto">Masa madre</h1>' in body


def test_the_meta_row_has_the_category_chip_with_its_menu(client):
    body = panel(client, "a1")
    chip = re.search(r'<details class="menu chip-menu">.*?</details>', body, re.S).group(0)
    assert "Redes" in chip and "oklch(0.74 0.09 265)" in chip
    assert 'action="/item/a1/category"' in chip and "data-inline" in chip
    assert 'name="category" value="Redes"' in chip
    assert "wireguard.com · 4 Oct" in body


def test_summary_in_paragraphs_with_reading_time(client):
    body = panel(client, "a1")
    assert '<p class="body" dir="auto">Uno dos tres.</p>' in body
    assert '<p class="body" dir="auto">Cuatro cinco.</p>' in body
    assert "1 min read of the summary" in body


def test_the_points_box(client):
    body = panel(client, "a1")
    box = re.search(r'<section class="points">.*?</section>', body, re.S).group(0)
    assert "IN THREE LINES" in box
    assert box.count("<li") == 3


def test_mentions_and_collections_keep_their_x(client):
    body = panel(client, "a1")
    assert "Pi-hole" in body and 'action="/item/a1/mentions/delete"' in body
    assert re.search(r'action="/item/a1/collections".*?name="drop" value="Casa conectada"', body, re.S)


def test_tags_are_links_with_an_x_and_a_box_to_add(client):
    body = panel(client, "a1", "?cat=Redes")
    assert 'href="/?tag=vpn"' in body
    assert re.search(r'name="tags" value="redes"', body)          # x on vpn leaves redes
    assert 'name="add"' in body and "+ tag" in body


def test_adding_a_tag_keeps_the_others(client, cfg):
    client.post("/item/b2/tags", data={"tags": "vpn redes", "add": "nuevo"})
    assert "#nuevo" in panel(client, "b2")
    assert "#vpn" in panel(client, "b2")


def test_the_star_toggles_the_favourite_mark(client):
    on = re.search(r'<form[^>]*action="/item/a1/mark".*?</form>', panel(client, "a1"), re.S).group(0)
    assert 'name="mark" value=""' in on and "star on" in on
    off = re.search(r'<form[^>]*action="/item/b2/mark".*?</form>', panel(client, "b2"), re.S).group(0)
    assert 'name="mark" value="⭐"' in off


def test_the_more_menu(client):
    body = panel(client, "a1")
    more = re.search(r'<details class="menu up more">.*?</details>', body, re.S).group(0)
    assert more.count('action="/item/a1/mark"') == 1 and "🔥" in more
    assert 'action="/item/a1/collections"' in more and 'name="add"' in more
    assert 'action="/item/a1/reprocess"' in more
    assert 'action="/item/a1/delete"' in more


def test_to_an_idea_only_with_ideas(client, cfg):
    assert "To an idea" not in panel(client, "a1")
    new_idea(cfg, "VPN familiar propia", "texto", "es")
    body = panel(client, "a1")
    assert "To an idea" in body and "VPN familiar propia" in body
    assert 'action="/item/a1/ideas"' in body


def test_the_original_opens_in_a_new_tab(client):
    assert re.search(r'<a class="btn primary" href="https://wireguard.com/a1" target="_blank"', panel(client, "a1"))


def test_the_item_page_of_a_link_is_the_home_with_it_selected(client):
    answer = client.get("/item/a1?notice=saved", follow_redirects=False)
    assert answer.status_code == 303
    assert answer.headers["location"] == "/?sel=a1&notice=saved"


def test_a_write_lands_on_the_panel_with_a_toast(client):
    body = client.post("/item/b2/category", data={"category": "Cocina"}).text
    assert '<p class="notice toast" role="status">' in body
    assert re.search(r'<li class="item on" id="card-b2"', body)
```

Check `new_idea`'s real signature with `grep -n "def new_idea" src/oknowledge/ideas.py` before running; adapt the call in `test_to_an_idea_only_with_ideas` to it (and ledger the adaptation).

- [ ] **Step 2: Run them to verify they fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_panel.py`
Expected: FAIL — `/panel/a1` 404, `/item/a1` 200.

- [ ] **Step 3: Write `panel.html`**

Copy the mentions block and the original-content `<details>` from `item.html` (the `{% if note.mentions %}` block and the `<details>` with `t('Original content')`) into the marked places below, unchanged except for `data-inline` on their forms.

```jinja
<div class="detail-scroll" data-panel="{{ panel_id }}">
{% if note is none %}
  <h1 dir="auto">{{ pending_url }}</h1>
  <p class="reading-ai">{{ t('The AI is reading the link…') }}</p>
  <div class="skeleton"><i></i><i></i><i></i></div>
{% else %}
  <div class="meta-row">
    <details class="menu chip-menu">
      <summary class="chip"><i class="dot" style="background: {{ note.category|dot }}"></i>{{ note.category or t('No category') }} ▾</summary>
      <div class="menu-list">
        <form method="post" action="/item/{{ note.id|slug }}/category" data-inline>
          {% for name in categories %}
            <button name="category" value="{{ name }}" class="{% if name == note.category %}on{% endif %}"><i class="dot" style="background: {{ name|dot }}"></i>{{ name }}</button>
          {% endfor %}
        </form>
        <form method="post" action="/item/{{ note.id|slug }}/category" data-inline class="menu-new">
          <input name="category" required autocomplete="off" aria-label="{{ t('New category') }}" placeholder="{{ t('New category') }}">
        </form>
      </div>
    </details>
    <span class="where mono">{{ note.source }} · {{ note.saved|short_date(t) }}</span>
    {% if note.status != 'ok' %}<span class="warn">{{ t('Incomplete') }}</span>{% endif %}
  </div>
  <h1 dir="auto">{{ note.title }}</h1>
  {% if reading %}
    <p class="reading-ai">{{ t('The AI is reading the link…') }}</p>
    <div class="skeleton"><i></i><i></i><i></i></div>
  {% else %}
    <p class="reading mono">{{ t('%1 min read of the summary', minutes) }}</p>
    {% for para in note.summary|paragraphs %}<p class="body" dir="auto">{{ para }}</p>{% endfor %}
    {% if note.points %}
      <section class="points">
        <p class="label">{{ t('IN THREE LINES') }}</p>
        <ul>{% for point in note.points %}<li dir="auto">{{ point }}</li>{% endfor %}</ul>
      </section>
    {% endif %}
    {# mentions block from item.html, forms with data-inline #}
    {# original content <details> from item.html #}
  {% endif %}
  {% if note.collections %}
    <div class="chips">
      {% for name in note.collections %}
        <form method="post" action="/item/{{ note.id|slug }}/collections" data-inline class="chip">
          <span>{{ name }}</span><button name="drop" value="{{ name }}" aria-label="{{ t('Leave the collection %1', name) }}" title="{{ t('Leave the collection %1', name) }}">✕</button>
        </form>
      {% endfor %}
    </div>
  {% endif %}
  <div class="chips tags">
    {% for tag in note.tags %}
      <form method="post" action="/item/{{ note.id|slug }}/tags" data-inline class="chip">
        <a href="/?tag={{ tag|urlencode }}" data-nav>#{{ tag }}</a>
        <input type="hidden" name="tags" value="{{ note.tags|reject('equalto', tag)|join(' ') }}">
        <button aria-label="{{ t('Remove the tag %1', tag) }}" title="{{ t('Remove the tag %1', tag) }}">✕</button>
      </form>
    {% endfor %}
    <form method="post" action="/item/{{ note.id|slug }}/tags" data-inline class="tag-new">
      <input type="hidden" name="tags" value="{{ note.tags|join(' ') }}">
      <input name="add" autocomplete="off" aria-label="{{ t('+ tag') }}" placeholder="{{ t('+ tag') }}">
    </form>
  </div>
{% endif %}
</div>
{% if note is not none %}
<div class="detail-bar">
  {% if note.url is web_url %}<a class="btn primary" href="{{ note.url }}" target="_blank" rel="noreferrer">{{ t('Open original') }} ↵</a>{% endif %}
  {% if idea_choices %}
    <details class="menu up">
      <summary class="btn">{{ t('To an idea') }} ▾</summary>
      <form class="menu-list" method="post" action="/item/{{ note.id|slug }}/ideas" data-inline>
        {% for id, title in idea_choices %}<button name="idea" value="{{ id }}">{{ title or t('Untitled idea') }}</button>{% endfor %}
      </form>
    </details>
  {% endif %}
  <form method="post" action="/item/{{ note.id|slug }}/mark" data-inline class="push">
    <input type="hidden" name="back" value="{{ back }}">
    <button name="mark" value="{{ '' if note.mark == '⭐' else '⭐' }}" class="btn icon star{% if note.mark == '⭐' %} on{% endif %}"
            aria-pressed="{{ 'true' if note.mark == '⭐' else 'false' }}" aria-label="{{ t('Favorite') }}" title="{{ t('Favorite') }}">★</button>
  </form>
  <details class="menu up more">
    <summary class="btn icon" aria-label="{{ t('More') }}" title="{{ t('More') }}">⋯</summary>
    <div class="menu-list">
      <form method="post" action="/item/{{ note.id|slug }}/mark" data-inline class="marks">
        <input type="hidden" name="back" value="{{ back }}">
        {% for mark in marks if mark != '⭐' %}<button name="mark" value="{{ mark }}" class="{% if note.mark == mark %}on{% endif %}" title="{{ mark }}">{{ mark }}</button>{% endfor %}
        <button name="mark" value="" class="no-mark">{{ t('No mark') }}</button>
      </form>
      <form method="post" action="/item/{{ note.id|slug }}/collections" data-inline class="menu-new">
        <input name="add" list="known-collections" required autocomplete="off" aria-label="{{ t('Add to a collection') }}" placeholder="{{ t('Add to a collection') }}">
        <datalist id="known-collections">{% for name in collections %}<option value="{{ name }}">{% endfor %}</datalist>
      </form>
      <form method="post" action="/item/{{ note.id|slug }}/reprocess"
            data-ask="{{ t('Re-run the analysis? The title, summary, points, category, tags and mentions are replaced by the new answer.') }}">
        <button onclick="return confirm(this.form.dataset.ask)">{{ t('Reprocess with AI') }}</button>
      </form>
      <form method="post" action="/item/{{ note.id|slug }}/delete" data-ask="{{ t('Move this note to the trash folder?') }}">
        <button class="danger" onclick="return confirm(this.form.dataset.ask)">{{ t('Delete') }}</button>
      </form>
    </div>
  </details>
</div>
{% endif %}
```

(`categories` and `collections` are already in every page's context from `page()`; `marks` too.)

- [ ] **Step 4: The routes**

Replace Task 4's placeholder `panel_context` with:

```python
    def panel_context(link_id: str, view: View, working: dict[str, str]) -> dict | None:
        entry = library.entry(link_id)
        if entry is None:
            url = working.get(link_id)
            return None if url is None else {"note": None, "panel_id": link_id,
                                             "pending_url": url, "reading": True}
        note = read_full(entry)
        ideas.refresh()
        return {"note": note, "panel_id": link_id, "reading": link_id in working,
                "minutes": reading_minutes(note.summary),
                "idea_choices": [(n.id, n.title) for n in ideas.notes if n.state != "dropped"],
                "back": view.url(sel=link_id)}

    @app.get("/panel/{link_id}", response_class=HTMLResponse)
    def detail(request: Request, link_id: str):
        library.refresh()
        view = View.from_query(request.query_params)
        found = panel_context(link_id, view, analyzing())
        if found is None:
            raise HTTPException(status_code=404, detail="no such link")
        return page(request, "panel.html", **found)
```

In `item`, right after `entry, where = anywhere(link_id)` and the 404 check:

```python
        if where.name == "links":
            # One screen for the library now: the note opens in its panel.
            params = request.query_params
            return see_other("/", sel=link_id, notice=params.get("notice"),
                             n=params.get("n"), m=params.get("m"))
```

and delete the `elif where.name == "links":` branch that built `idea_choices`.

In `retag`, add `add: str = Form("")` and make `wanted = [w for w in (tags + " " + add).replace(",", " ").split() if w]`, de-duplicated keeping order: `wanted = list(dict.fromkeys(wanted))`.

Imports: add `reading_minutes` to the `library_view` import.

Remove from `item.html` the `{% if link %} … {% endif %}` blocks and any `link` only branch, then run `grep -n "link\b" src/oknowledge/web/templates/item.html` to confirm nothing link-only is left; the route no longer passes `link=` (drop it).

- [ ] **Step 5: Style it**

Append to `app.css`:

```css
/* --- the panel ---------------------------------------------------------- */
.detail-scroll { flex: 1; overflow-y: auto; min-height: 0; padding: 26px 32px;
  display: flex; flex-direction: column; gap: 18px; }
.detail-scroll > * { margin: 0; }
.detail h1 { font-size: 26px; font-weight: 600; letter-spacing: -0.02em; line-height: 1.2; color: var(--t1); }
.meta-row { display: flex; align-items: center; gap: 10px; font-size: 12px; color: var(--t5); }
.chip { display: inline-flex; align-items: center; gap: 6px; background: var(--s4);
  border-radius: 6px; padding: 3px 8px; font-size: 12px; color: var(--t2); cursor: pointer;
  list-style: none; }
.chip::-webkit-details-marker { display: none; }
.chip button { background: none; border: 0; color: var(--t6); cursor: pointer; padding: 0 0 0 2px; font-size: 11px; }
.chip a { color: var(--t2); text-decoration: none; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.tag-new input { background: none; border: 0; color: var(--t2); font: inherit; font-size: 12px; width: 7rem; }
.reading { font-size: 12px; color: var(--t6); }
.detail .body { font-size: 15px; line-height: 1.65; color: var(--t2); }
.points { background: var(--s2); border-radius: 10px; padding: 14px 16px; }
.points .label { font-size: 11px; letter-spacing: .08em; color: var(--t6); margin: 0 0 6px; }
.points ul { margin: 0; padding: 0; list-style: none; font-size: 13.5px; color: var(--t2); }
.points li::before { content: "— "; color: var(--t6); }
.reading-ai { color: var(--acc); font-size: 14px; }
.skeleton { display: flex; flex-direction: column; gap: 10px; }
.skeleton i { display: block; height: 12px; background: var(--s4); border-radius: 6px; }
.skeleton i:nth-child(2) { width: 85%; } .skeleton i:nth-child(3) { width: 60%; }
.warn { color: var(--danger); }

.detail-bar { display: flex; align-items: center; gap: 8px; padding: 14px 20px;
  border-top: 1px solid var(--b-div); }
.detail-bar .push { margin-left: auto; }
.btn.icon { width: 32px; justify-content: center; padding: 0; background: none; border-color: transparent; color: var(--t5); }
.btn.star.on { color: var(--fav); }

.menu { position: relative; }
.menu > summary { list-style: none; }
.menu > summary::-webkit-details-marker { display: none; }
.menu-list { position: absolute; z-index: 20; top: calc(100% + 6px); left: 0; min-width: 200px;
  max-height: 320px; overflow-y: auto; background: var(--s4); border: 1px solid var(--b-menu);
  border-radius: 8px; box-shadow: var(--shadow); padding: 4px; display: flex; flex-direction: column; gap: 2px; }
.menu.up .menu-list { top: auto; bottom: calc(100% + 6px); }
.menu.more .menu-list { left: auto; right: 0; }
.menu-list form { display: contents; }
.menu-list button { display: flex; align-items: center; gap: 8px; width: 100%; text-align: left;
  background: none; border: 0; border-radius: 6px; padding: 7px 10px; color: var(--t2);
  font: inherit; font-size: 13px; cursor: pointer; }
.menu-list button:hover, .menu-list button.on { background: var(--s5); color: var(--t1); }
.menu-list .danger { color: var(--danger); }
.menu-list .marks { display: flex; flex-wrap: wrap; }
.menu-list .marks button { width: auto; }
.menu-new input { width: 100%; background: var(--s3); border: 1px solid var(--b-input);
  border-radius: 6px; color: var(--t1); font: inherit; font-size: 13px; padding: 6px 8px; }
```

- [ ] **Step 6: Run the tests**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_panel.py tests/test_web_home.py`
Expected: PASS.

- [ ] **Step 7: Whole suite, adjust, commit**

Run the suite. Expected failures: tests that read a link's `item.html` ("Move to category", "Edit tags", the engine `<select>`, "Add to an idea" select, the delete button's markup) and tests asserting `location == "/item/<id>?notice=…"` stay valid (the write routes did not change; only `GET /item/{id}` redirects now). For each failing test: same rule as Task 4 — rewrite against the panel when the behaviour survives, delete + ledger when the spec removes it (spec §5 "Todo lo que se va").

```bash
git add -A src/oknowledge/web tests
git commit -m "Read and edit a link in the panel beside the list"
```

---

### Task 6: Links being analysed

**Files:**
- Modify: `src/oknowledge/queue.py` (new `Queue.busy()`)
- Modify: `src/oknowledge/web/app.py` — `analyzing()`, `/add`, `/item/{id}/state`
- Test: `tests/test_queue.py` (append), `tests/test_web_analyzing.py` (new)

**Interfaces:**
- Consumes: `listing`, `panel_context`, the `pending` macro (Tasks 4–5).
- Produces: `Queue.busy() -> list[QueueEntry]` (pending entries whose lock is held now); `analyzing() -> dict[str, str]`; `FRESH_SECONDS = 120`; `/add` redirects to `/?sel=<id>&notice=reading`; `/item/{id}/state` answers `working: true, status: "pending"` for a link inside the fresh window with no queue entry yet.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_queue.py` (use the file's existing fixture for a `Queue` on `tmp_path`; if it has none, build `Queue(tmp_path)`):

```python
def test_busy_lists_only_the_links_someone_holds(tmp_path):
    q = Queue(tmp_path)
    q.enqueue("aaaa1111", "https://a.com", "full")
    q.enqueue("bbbb2222", "https://b.com", "full")          # pending, nobody holds it
    with q.lock("aaaa1111"):
        assert [e.id for e in q.busy()] == ["aaaa1111"]
    assert q.busy() == []
```

Check `_ID` in `queue.py` for the id format the queue accepts and use ids of that shape.

`tests/test_web_analyzing.py`:

```python
"""Links being read show up at the top as "Analysing…" and leave on their own."""

import re

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.queue import Queue
from oknowledge.urls import link_id, normalize
from oknowledge.vault import rebuild_indexes, write_note
from oknowledge.web import app as module
from oknowledge.web.app import create_app

URL = "https://nuevo.com/articulo"


@pytest.fixture
def cfg(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    write_note(cfg, Note(id="old1", url="https://e.com/old", title="Viejo", category="Redes",
                         tags=[], type="article", source="e.com", saved="2026-10-01",
                         summary="s"), "es")
    rebuild_indexes(cfg, "es")
    return cfg


@pytest.fixture
def client(cfg, monkeypatch):
    monkeypatch.setattr(module, "fetch", lambda *a, **k: None)   # nothing is read
    return TestClient(create_app(cfg))


def items(body):
    return re.findall(r'<li class="item[^"]*" id="card-([^"]+)"', body)


def test_a_saved_link_opens_selected_while_it_is_read(client):
    answer = client.post("/add", data={"q": URL, "content": "full"}, follow_redirects=False)
    new = link_id(normalize(URL))
    assert answer.headers["location"] == f"/?sel={new}&notice=reading"
    body = client.get(answer.headers["location"]).text
    assert items(body)[0] == new
    assert re.search(rf'<li class="item pending on" id="card-{new}" data-working="{new}"', body)
    assert "The AI is reading the link…" in body


def test_the_state_says_working_before_the_queue_knows(client):
    client.post("/add", data={"q": URL})
    assert client.get(f"/item/{link_id(normalize(URL))}/state").json()["working"] is True


def test_the_fresh_window_ends(client, monkeypatch):
    client.post("/add", data={"q": URL})
    clock = module.time.monotonic() + module.FRESH_SECONDS + 1
    monkeypatch.setattr(module.time, "monotonic", lambda: clock)
    assert link_id(normalize(URL)) not in items(client.get("/").text)


def test_once_the_queue_knows_it_is_the_queue_that_answers(client):
    client.post("/add", data={"q": URL})
    new = link_id(normalize(URL))
    q = Queue()
    q.enqueue(new, URL, "full")
    q.set_status(new, "ok")
    assert new not in items(client.get("/").text)


def test_a_pending_entry_nobody_holds_is_not_listed(client):
    Queue().enqueue("dead0000", "https://muerto.com", "full")
    assert "dead0000" not in items(client.get("/").text)


def test_a_held_entry_is_listed_and_a_held_note_is_marked_busy(client):
    q = Queue()
    q.enqueue("live0000", "https://vivo.com", "full")
    q.enqueue("old1", "https://e.com/old", "full")
    with q.lock("live0000"), q.lock("old1"):
        body = client.get("/").text
    assert items(body)[:2] == ["live0000", "old1"]
    assert re.search(r'id="card-old1" data-working="old1"', body)


def test_filters_do_not_list_the_pending(client):
    client.post("/add", data={"q": URL})
    assert items(client.get("/?cat=Redes").text) == ["old1"]
```

Check `_ID` and `set_status`'s signature in `queue.py`; if `"dead0000"`/`"live0000"` are not valid ids, use valid ones (the shape `link_id()` returns) and ledger the change. The conftest already isolates the state tree for `Queue()`; confirm by `grep -n "state_dir\|XDG_STATE" tests/conftest.py`.

- [ ] **Step 2: Run them to verify they fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_queue.py tests/test_web_analyzing.py`
Expected: FAIL — no `Queue.busy`, `/add` redirects to `/?notice=reading`, no `FRESH_SECONDS`.

- [ ] **Step 3: Implement**

In `queue.py`, after `held()`:

```python
    def busy(self) -> list[QueueEntry]:
        """Pending entries some live process holds now: the ones really being
        worked on. A pending entry nobody holds is owed work, not work."""
        found = []
        for entry in self.entries():
            if entry.status != "pending":
                continue
            try:
                if self.held(entry.id):
                    found.append(entry)
            except OSError:
                continue
        return found
```

In `app.py`: `import time` at the top, a module constant

```python
FRESH_SECONDS = 120
"""How long a link just pasted counts as being read before the queue has an
entry for it: the background task that enqueues it starts after the answer."""
```

and in `create_app`, before `analyzing`:

```python
    fresh: dict[str, tuple[str, float]] = {}
```

Replace `analyzing()`:

```python
    def analyzing() -> dict[str, str]:
        """{id: url} of the links being read now, newest first."""
        q = Queue()
        try:
            found = {e.id: e.url for e in q.busy()}
        except (OSError, ValueError):
            found = {}
        now = time.monotonic()
        for key, (url, at) in list(fresh.items()):
            if now - at > FRESH_SECONDS:
                fresh.pop(key, None)
            elif key not in found and q.get(key) is None:
                found = {key: url, **found}
        return found
```

In `/add`, replace the final `background.add_task(...)` / `return see_other("/", notice="reading")` with:

```python
        new = link_id(clean)
        fresh[new] = (clean, time.monotonic())
        background.add_task(fetch, current["cfg"], clean, mode, trace=progress.note)
        return see_other("/", sel=new, notice="reading")
```

In `link_state`, after `entry = q.get(link_id)` and before computing `working`:

```python
            if entry is None and link_id in analyzing():
                return JSONResponse({"working": True, "status": "pending"})
```

(`link_id` is the route parameter there and shadows the imported function inside that route only; that is fine because the route does not call the function.)

- [ ] **Step 4: Run the tests**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_queue.py tests/test_web_analyzing.py tests/test_web_add.py`
Expected: PASS, except `test_web_add.py` assertions on `location == "/?notice=reading"` → update them to the new `sel` location (behaviour changed by spec §6; ledger it).

- [ ] **Step 5: Whole suite, commit**

```bash
git add src/oknowledge/queue.py src/oknowledge/web/app.py tests
git commit -m "Show the links being read at the top of the library, selected when just pasted"
```

---

### Task 7: The page without reloads

**Files:**
- Create: `src/oknowledge/web/static/shell.js`
- Modify: `tests/test_packaging.py` (add `shell.js` to the `node --check` list)
- Test: `tests/test_web_shell_js.py` (new) — the hooks the script relies on

**Interfaces:**
- Consumes (DOM contract from Tasks 3–6): `#unified` form with `#field-q` and `#save-link`; `#list` containing `.list-head` (`a[data-view]`) and `#list-body` with `#items[data-current]`, `li.item` with `a[data-sel]` and optional `[data-working]`, `a.more[data-more]`; sidebar `a[data-nav]` (filters) and panel `a[data-nav]` (tags); `#panel` with `.detail-scroll[data-panel]`; `form[data-inline]`; `details.menu`; `body[data-save-failed][data-done][data-failed]`; toast markup `p.notice.toast`.
- Produces: no server interface.

- [ ] **Step 1: Write the failing tests**

`tests/test_web_shell_js.py`:

```python
"""What shell.js needs from the pages. The script itself is checked by node
(tests/test_packaging.py); these pin the markup it hooks into."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.vault import rebuild_indexes, write_note
from oknowledge.web.app import create_app

SCRIPT = (Path(__file__).resolve().parent.parent / "src" / "oknowledge" / "web" / "static" / "shell.js")


@pytest.fixture
def client(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    write_note(cfg, Note(id="a1", url="https://e.com/a1", title="A", category="Redes",
                         tags=["vpn"], type="article", source="e.com", saved="2026-10-03",
                         summary="s"), "es")
    rebuild_indexes(cfg, "es")
    return TestClient(create_app(cfg))


def test_the_home_loads_the_script(client):
    assert '<script src="/static/shell.js" defer></script>' in client.get("/").text


def test_the_script_is_served(client):
    assert client.get("/static/shell.js").status_code == 200


@pytest.mark.parametrize("hook", ['id="unified"', 'id="field-q"', 'id="save-link"',
                                  'id="list"', 'id="list-body"', 'id="items"', "data-current=",
                                  "data-sel=", "data-view=", "data-nav", 'id="panel"',
                                  "data-panel=", "data-inline", 'class="menu',
                                  "data-save-failed=", "data-done=", "data-failed="])
def test_the_page_has_every_hook(client, hook):
    assert hook in client.get("/").text


@pytest.mark.parametrize("name", ["/lista", "/panel/", "/item/", "/state", "requestSubmit",
                                  "history.replaceState", "IntersectionObserver",
                                  "localStorage", "250", "3000", "Escape"])
def test_the_script_uses_what_the_spec_says(name):
    assert name in SCRIPT.read_text(encoding="utf-8")
```

In `tests/test_packaging.py`, change `@pytest.mark.parametrize("name", ["popup.js", "redo.js"])` to include `"shell.js"`.

- [ ] **Step 2: Run them to verify they fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_shell_js.py tests/test_packaging.py`
Expected: FAIL — script 404 / missing.

- [ ] **Step 3: Write `shell.js`**

```javascript
// The library without reloads (docs/2026-10-14-rediseno-biblioteca-design.md
// §1, §4, §6, §7). Every action here has a plain link or form under it; this
// only swaps the column that changed and keeps the URL in step.
(function () {
  "use strict";
  var list = document.getElementById("list");
  var panel = document.getElementById("panel");
  var form = document.getElementById("unified");
  var field = document.getElementById("field-q");
  if (!list || !panel || !form || !field) return;
  var texts = document.body.dataset;
  var STORE = "oknowledge.vista";

  function toast(text) {
    if (!text) return;
    document.querySelectorAll(".toast").forEach(function (old) { old.remove(); });
    var p = document.createElement("p");
    p.className = "notice toast";
    p.setAttribute("role", "status");
    p.textContent = text;
    document.body.appendChild(p);
    setTimeout(function () { p.remove(); }, 2700);
  }

  function here() { return new URL(location.href); }

  function isUrl(text) {
    var start = text.trim().toLowerCase();
    return start.indexOf("http://") === 0 || start.indexOf("https://") === 0 ||
           start.indexOf("www.") === 0;
  }

  // --- the list column ---------------------------------------------------
  var asked = 0;
  function loadList(url, keepScroll) {
    var mine = ++asked;
    var target = new URL(url, location.href);
    var body = document.getElementById("list-body");
    var top = body ? body.scrollTop : 0;
    return fetch("/lista" + target.search)
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.text(); })
      .then(function (html) {
        if (mine !== asked) return;
        list.innerHTML = html;
        history.replaceState(null, "", target.pathname + target.search);
        if (keepScroll) document.getElementById("list-body").scrollTop = top;
        var items = document.getElementById("items");
        var current = items ? items.dataset.current : "";
        var shown = panel.querySelector("[data-panel]");
        if (current && (!shown || shown.dataset.panel !== current)) loadPanel(current);
        observe();
        watch();
      })
      .catch(function () { location.href = target.href; });
  }

  function markCurrent(id) {
    list.querySelectorAll("li.item.on").forEach(function (li) { li.classList.remove("on"); });
    var li = document.getElementById("card-" + id);
    if (li) li.classList.add("on");
    var items = document.getElementById("items");
    if (items) items.dataset.current = id;
  }

  function loadPanel(id) {
    var url = here();
    url.searchParams.set("sel", id);
    history.replaceState(null, "", url.pathname + url.search);
    markCurrent(id);
    return fetch("/panel/" + encodeURIComponent(id) + url.search)
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.text(); })
      .then(function (html) { panel.innerHTML = html; })
      .catch(function () { location.href = url.href; });
  }

  function setActive(link) {
    document.querySelectorAll(".sidebar .filter.on").forEach(function (a) { a.classList.remove("on"); });
    if (link.closest(".sidebar")) link.classList.add("on");
  }

  document.addEventListener("click", function (event) {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey ||
        event.shiftKey || event.altKey) return;
    var link = event.target.closest("a[data-sel], a[data-nav], a[data-view], a.more");
    if (!link) return;
    event.preventDefault();
    if (link.dataset.sel) {
      loadPanel(link.dataset.sel);
    } else if (link.hasAttribute("data-view")) {
      try { localStorage.setItem(STORE, link.dataset.view); } catch (e) { /* private window */ }
      loadList(link.href, true);
    } else if (link.classList.contains("more")) {
      more(link);
    } else {
      setActive(link);
      field.value = "";
      form.classList.remove("saving");
      var target = new URL(link.href, location.href);
      var vista = here().searchParams.get("vista");
      if (vista) target.searchParams.set("vista", vista);
      loadList(target.href);
    }
  });

  // --- remembered layout --------------------------------------------------
  try {
    var saved = localStorage.getItem(STORE);
    var now = here();
    if (saved === "lista" && !now.searchParams.get("vista")) {
      now.searchParams.set("vista", "lista");
      loadList(now.href);
    }
  } catch (e) { /* no storage: the URL decides */ }

  // --- the unified field ---------------------------------------------------
  var timer = null;
  field.addEventListener("input", function () {
    clearTimeout(timer);
    var text = field.value;
    form.classList.toggle("saving", isUrl(text));
    if (isUrl(text)) return;
    timer = setTimeout(function () {
      var url = new URL("/", location.href);
      var q = text.trim().split(/\s+/).join(" ");
      if (q) url.searchParams.set("q", q);
      var vista = here().searchParams.get("vista");
      if (vista) url.searchParams.set("vista", vista);
      loadList(url.href);
    }, 250);
  });

  form.addEventListener("submit", function (event) {
    if (event.submitter && event.submitter.id === "save-link") return;   // a real POST
    event.preventDefault();
    if (isUrl(field.value)) {
      form.requestSubmit(document.getElementById("save-link"));
      return;
    }
    clearTimeout(timer);
    field.dispatchEvent(new Event("input"));
  });

  // --- more at the end of the list ----------------------------------------
  var observer = "IntersectionObserver" in window ? new IntersectionObserver(function (seen) {
    seen.forEach(function (one) { if (one.isIntersecting) more(one.target); });
  }, { rootMargin: "400px" }) : null;

  function observe() {
    var link = list.querySelector("a.more");
    if (observer && link) observer.observe(link);
  }

  function more(link) {
    if (link.dataset.loading) return;
    link.dataset.loading = "1";
    if (observer) observer.unobserve(link);
    fetch(link.dataset.more)
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.text(); })
      .then(function (html) {
        var box = document.createElement("div");
        box.innerHTML = html;
        var items = document.getElementById("items");
        box.querySelectorAll("li.item").forEach(function (li) { items.appendChild(li); });
        var next = box.querySelector("a.more");
        if (next) link.replaceWith(next); else link.remove();
        observe();
        watch();
      })
      .catch(function () { delete link.dataset.loading; });
  }

  // --- menus --------------------------------------------------------------
  document.addEventListener("toggle", function (event) {
    var opened = event.target;
    if (!opened.matches || !opened.matches("details.menu") || !opened.open) return;
    document.querySelectorAll("details.menu[open]").forEach(function (d) {
      if (d !== opened) d.open = false;
    });
  }, true);

  function closeMenus() {
    document.querySelectorAll("details.menu[open]").forEach(function (d) { d.open = false; });
  }

  document.addEventListener("click", function (event) {
    if (!event.target.closest("details.menu")) closeMenus();
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      closeMenus();
      if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
    }
  });

  // --- edits in place -------------------------------------------------------
  document.addEventListener("submit", function (event) {
    var target = event.target;
    if (!target.matches("form[data-inline]")) return;
    event.preventDefault();
    var data = new FormData(target, event.submitter || undefined);
    closeMenus();
    fetch(target.action, { method: "POST", body: data })
      .then(function (r) {
        if (!r.ok) throw new Error(r.status);
        return r.text();
      })
      .then(function (html) {
        var page = new DOMParser().parseFromString(html, "text/html");
        var said = page.querySelector(".toast");
        toast(said ? said.textContent : "");
        var shown = panel.querySelector("[data-panel]");
        loadList(here().href, true);
        if (shown) loadPanel(shown.dataset.panel);
      })
      .catch(function () { toast(texts.saveFailed); });
  });

  // --- links being read -----------------------------------------------------
  var watched = {};
  function watch() {
    list.querySelectorAll("[data-working]").forEach(function (li) {
      var id = li.dataset.working;
      if (watched[id]) return;
      watched[id] = setInterval(function () {
        fetch("/item/" + encodeURIComponent(id) + "/state")
          .then(function (r) { return r.json(); })
          .then(function (state) {
            if (state.working) return;
            clearInterval(watched[id]);
            delete watched[id];
            toast(state.status === "failed" ? texts.failed : texts.done);
            loadList(here().href, true);
            var shown = panel.querySelector("[data-panel]");
            if (shown && shown.dataset.panel === id) loadPanel(id);
          })
          .catch(function () { /* try again in three seconds */ });
      }, 3000);
    });
  }

  observe();
  watch();
})();
```

- [ ] **Step 4: Run the tests**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_shell_js.py tests/test_packaging.py`
Expected: PASS (node `--check` included).

- [ ] **Step 5: Try it in a browser**

Build a scratch vault under the session scratchpad (re-use or adapt `$SP/shots/serve.py` from the screenshots of 2026-10-14; it seeds 12 links, marks, a collection, ideas, and serves on 127.0.0.1:8812). Then, with headless chromium:

```bash
chromium --headless=new --disable-gpu --hide-scrollbars --user-data-dir="$(mktemp -d -p "$SP")" \
  --virtual-time-budget=3000 --window-size=1440,900 --screenshot="$SP/r1-home.png" http://127.0.0.1:8812/
chromium --headless=new --disable-gpu --hide-scrollbars --user-data-dir="$(mktemp -d -p "$SP")" \
  --virtual-time-budget=3000 --window-size=1440,900 --screenshot="$SP/r1-lista.png" "http://127.0.0.1:8812/?vista=lista&sel=<an id>"
```

Read both PNGs and compare with `design_handoff_oknowledge_redesign/screenshots/01-pantalla.png` and `02-pantalla.png` (those are at 60 %). Fix CSS differences in `app.css` (spacing, sizes, colours) until they match; no page scroll at 1440×900. Exercise the JS by hand only if a browser the user opens is available; otherwise ledger "JS behaviour checked by reading + node --check only".

- [ ] **Step 6: Whole suite, commit**

```bash
git add src/oknowledge/web/static/shell.js src/oknowledge/web/static/app.css tests/test_web_shell_js.py tests/test_packaging.py
git commit -m "Swap the list and the panel in place, search as you type, and save edits without reloading"
```

---

### Task 8: Spanish, cleanup and the record

**Files:**
- Modify: `src/oknowledge/i18n.py` (`STRINGS["es"]`)
- Modify: `docs/2026-10-14-rediseno-biblioteca-design.md` (only if a ruling changed behaviour — note it at the end)
- Test: `tests/test_i18n.py` (existing), `tests/test_web_home.py` (append one Spanish test)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_web_home.py`:

```python
def test_the_home_speaks_spanish(client, isolated_ui_language):
    isolated_ui_language.write_text('{"language": "es"}', encoding="utf-8")
    body = client.get("/").text
    for text in ("Buscá o pegá un link para guardarlo", "Biblioteca", "CATEGORÍAS",
                 "MARCAS", "COLECCIONES", "Tarjetas", "Lista", "★ Favoritos",
                 "Completo", "Resumen", "Abrir el original"):
        assert text in body
```

Check the shared file's real shape in `test_i18n.py::test_the_shared_file_switches_the_interface` and write what it writes.

- [ ] **Step 2: Run it and the i18n suite**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_home.py::test_the_home_speaks_spanish tests/test_i18n.py`
Expected: FAIL — missing translations, and possibly stale ones.

- [ ] **Step 3: Add the Spanish**

Add to `STRINGS["es"]` every new key (search the new templates and `library_view.py` for `t('…')`/`t("…")`). The handoff's texts are the Spanish:

| key | es |
|---|---|
| Sections | Secciones |
| CATEGORIES | CATEGORÍAS |
| MARKS | MARCAS |
| COLLECTIONS | COLECCIONES |
| Favorites | Favoritos |
| Pinned | Fijados |
| Marks | Marcas |
| Collections | Colecciones |
| Results | Resultados |
| Layout | Vista |
| List | Lista |
| Cards | Tarjetas |
| Show more | Ver más |
| Search or paste a link to save it | Buscá o pegá un link para guardarlo |
| Detail | Detalle |
| Choose a link to read it here. | Elegí un link para leerlo acá. |
| Nothing matches “%1” | Nada coincide con “%1” |
| Try another word or a tag. If it is a new link, paste it whole with https:// to save it. | Probá con otra palabra o una etiqueta. Si es un link nuevo, pegalo completo con https:// para guardarlo. |
| There is nothing in %1 | No hay nada en %1 |
| Mark a link from its panel, or move it here from the category chip. | Marcá un link desde su panel, o movelo acá desde el chip de categoría. |
| See everything | Ver todo |
| Paste a link in the box above to save it. | Pegá un link en el campo de arriba para guardarlo. |
| Analysing… | Analizando… |
| No category | Sin categoría |
| The AI is reading the link… | La IA está leyendo el link… |
| %1 min read of the summary | %1 min de lectura del resumen |
| IN THREE LINES | EN TRES LÍNEAS |
| New category | Nueva categoría |
| Remove the tag %1 | Quitar la etiqueta %1 |
| + tag | + etiqueta |
| To an idea | A una idea |
| Favorite | Favorito |
| More | Más |
| No mark | Sin marca |
| Reprocess with AI | Reprocesar con IA |
| It could not be saved | No se pudo guardar |
| Done: summary written | Listo: resumen generado |
| The link could not be analysed | No se pudo analizar el link |

Keys that already exist (e.g. "Library", "Leisure", "Ideas", "All", "Full", "Summary", "Save", "Delete", "Open original", "Categories", "Activity", "Settings", "Incomplete", "Untitled idea", "Leave the collection %1", "Add to a collection", "Nothing saved yet") keep their entries. Then delete every entry `test_every_translated_string_is_one_the_code_asks_for` reports as asked for by nothing (strings of the deleted header, library page, pick mode, timeline, mark picker, the link-only blocks of `item.html`).

- [ ] **Step 4: Run the tests**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_i18n.py tests/test_web_home.py`
Expected: PASS.

- [ ] **Step 5: Whole suite and screenshots**

Run the suite; expected all green. Take the two screenshots of Task 7 Step 5 again with Spanish on (the scratch config, not the user's), read them, and compare with the handoff screenshots one last time.

- [ ] **Step 6: Commit**

```bash
git add src/oknowledge/i18n.py tests docs
git commit -m "Say the redesigned library in Spanish and drop the strings nothing asks for"
```
