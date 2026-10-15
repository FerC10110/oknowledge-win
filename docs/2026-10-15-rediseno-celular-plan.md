# Rediseño, entrega 4 (el celular) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Under 60rem every page is one column: a top bar with "oknowledge" and "Ajustes", the unified field, a sideways row of filter chips, the list, and a tab bar at the bottom (Biblioteca · Ocio · Ideas · Favoritos). The detail opens as a full-screen layer that the browser's back closes. Ajustes is full screen. Menus open as bottom sheets. A "Seleccionar" mode replaces hover for multi-selection. The desktop at ≥60rem stays pixel-identical.

**Architecture:** Server-rendered, as in deliveries 1–3.
- **Markup.** Four new partials (`topbar.html`, `tabbar.html`, `filter-chips.html`, `detail-back.html`, plus the tiny `batch-count.html`) are drawn on every desktop page too, hidden by CSS. `#panel` carries `data-open` when the URL names a pick. The `↵` hints become `span.enter-hint`.
- **CSS.** One `@media (max-width: 60rem)` block at the end of `app.css` holds the whole phone. A second, `(max-width: 60rem) and (min-width: 42rem)`, only widens grids. `(hover: none)` and `(pointer: coarse)` are separate from the width.
- **Scripts.**
  - `app.js` gains `oknowledge.phone()` and `oknowledge.layers`: one history entry per open layer, one `popstate`.
  - `shell.js` opens the detail as a layer, and keeps `sel` out of the URL while the layer is shut.
  - `select.js` gains the selection mode.
  - `layout.js` loses its dead phone code.

**Tech Stack:** Python 3.12, FastAPI + Jinja2, plain JS (no build), pytest + TestClient, `node --check` and node harnesses for JS, Playwright for node driving `/usr/bin/chromium` for layout checks at 390×844 with touch emulation.

**Spec:** `docs/2026-10-15-rediseno-celular-design.md` (binding). Earlier deliveries: `docs/2026-10-14-rediseno-biblioteca-plan.md`, `docs/2026-10-14-rediseno-ocio-ideas-plan.md`, `docs/2026-10-14-rediseno-modales-teclado-plan.md` (the conventions this builds on).
**Visual reference:** `design_handoff_oknowledge_redesign/README.md`, the paragraph "Responsive (celular…)" under "Interactions & Behavior", and the tokens. Also `design_handoff_oknowledge_redesign/oknowledge Rediseño.dc.html` → `data-screen-label="1a celular"` (390×844).

## Rulings in this plan

The spec left these open. Each is decided here, for review:

1. **A bigger scratch vault: `serve4.py`.**
   - The spec's browser checks need more than delivery 2's seed: chips that overflow, 30 links, a link being analysed, a title and a URL with no place to break.
   - `$SP/shots/serve4.py` (Task 1) copies delivery 2's `serve.py` into `$SP/shots4/` and runs it there, in Spanish, on 127.0.0.1:8812. Before uvicorn starts it adds:
     - 18 links in 8 more categories (`l00000000013` … `l00000000030`);
     - `l00000000013`, a 140-character title without spaces;
     - `l00000000014`, a 60-character domain and a 150-character URL;
     - a queued link `p00000000001` whose lock the server process holds, so it stays "Analizando…";
     - Cinemeta and Open Library stubs, so a catalog search never reaches the network.
   - `serve3.py` and `$SP/shots/vault` stay as delivery 3 left them.
2. **The desktop regression is a pixel comparison, made in one sitting.**
   - `$SP/d4/desk-compare.sh` (Task 1) serves the tree of the commit this branch starts from (`$SP/d4/base-rev`, taken from `git archive`), then the working tree, each from a fresh `serve4.py` vault.
   - It screenshots the same 18 desktop states at 1440×900 and counts the differing pixels. Every count must be `0`.
   - Both runs happen in the same minute, so relative dates cannot differ. Tasks 5, 6 and 7 run it as a guard; Task 11 owns it.
3. **`↵` hints keep the desktop's pixels.**
   - Markup: `{{ t('Save') }}<span class="enter-hint" aria-hidden="true">&nbsp;↵</span>`.
   - CSS: `.btn:has(> .enter-hint) { gap: 0; }`. The no-break space advances like the space it replaces, and a `.btn`'s 6px gap must not open between the two items.
   - If `desk-compare.sh` reports a difference on the `saving`, `finding` or `home-sel` shots, stop and report it. Do not nudge margins by eye.
4. **`batch-count.html`.** The `3/10` counter is one partial, included by the sidebar's "Ajustes" and the top bar's. The sidebar's markup comes out byte-identical (Jinja drops the partial's trailing newline).
5. **Which tab is lit.**
   - **Favoritos:** `side.section == 'links' and view.mark == '⭐' and not view.searching`. That is the sidebar's own ★ condition.
   - **Biblioteca:** the rest of `links`.
   - **Ocio / Ideas:** by `side.section`.
   - `/settings`, `/import`, `/retry` and a 404 light none. Their `section_of()` is `None`.
6. **The chip row in Ocio's column answer.**
   - `ocio-list.html` draws a second template, `template#chip-filters`, beside `template#side-filters`.
   - `sideFilters()` swaps both, each in its own place.
   - The library's marks group always shows (📌 is always listed, as in the sidebar). An empty collections group, or an Ocio/Ideas group with no rows, is not drawn.
7. **Twins by `href`.** `setActive(link)` lights the clicked link and the link with the same `href` in the other drawing (`.sidebar` ↔ `.chip-row`). It clears only `a.filter.on, a.fchip.on` in the group's `[data-apart]` scope or the whole drawing. A section link in the sidebar keeps its `.on`.
8. **"← Biblioteca" / "← Ocio" take their words from the template that includes them** (`back_to`), not from `side.section`. `/panel/{id}` also serves Ocio cards, and `section_of("/panel/…")` is `links`.
   - Its `href` is a new context key, `list_url` (`view.url(sel="")`), in `panel_context` (both branches) and `card_context`.
   - The catalog panel's is `/ocio`, or `/ocio?tipo=<grid>` when the grid was filtered.
9. **`data-open`** is drawn when `view.sel and view.sel == current` (the pick named by the URL is in the list), and in Ocio also when `catalog`.
10. **On the phone, `sel` is in the URL only while the layer is open.**
    - `loadPanel` without `push`, `keepShown` and the load-time "pick in the URL" block do not write `sel` while the layer is shut.
    - Without this, the list's server pick would land in the URL, and a reload (or a back to that entry) would open a layer nobody asked for.
11. **`shell.js` keeps `history.state` on every `replaceState`.** A `replaceState(null, …)` while the layer is open would erase `{layer: "panel"}`. "← Biblioteca" would then close in place and leave a dead entry behind it. `layout.js`'s notice clean-up does the same.
12. **`oknowledge.layers`:**
    - `open(name, onClose, url)` pushes `{layer: name}` at `url` and returns `false` when a layer is already open.
    - `adopt(name, onClose)` takes a layer the page started with. It counts as "pushed" when `history.state.layer === name`, which is the case for a forward or a reload of our own entry.
    - `close()` returns a Promise. It is a `back()` when the layer has its entry, otherwise it closes in place.
    - `top()` returns the name or `""`. `settled()` returns the Promise of a `back()` under way.
    - `onClose(how)` gets `"back"` or `"close"`.
    - A forward into a panel entry is re-opened by `shell.js`'s own `popstate` listener. It runs after `app.js`'s, which loads first.
13. **Esc and a text field.** With the focus in a text field, Esc blurs it first, even over a layer, so a note being typed saves before the layer goes. The next Esc closes any open menu and the layer together. A sheet must not stay open in a hidden layer.
14. **Settings as a layer.**
    - `app.js`'s `openModal` pushes the layer for `#settings-modal` on the phone, and does not open it over another layer.
    - `app.js` binds the dialog's `close` listener at load, before `settings.js` binds its own, so ✕, Esc and the backdrop go `back()` once.
    - `settings.js` reloads after a rename only once `ok.layers.settled()` resolves.
15. **No flash of the previous note.** While a pushed layer waits for its panel, `#panel` carries `aria-busy="true"` and its content is `visibility: hidden`.
16. **The tab bar steps aside for the keyboard.** Under 60rem, while a text field, textarea or select has the focus, `.tabbar` is not drawn. A fixed bar would otherwise ride on top of the iOS keyboard and cover the field's own row.
17. **Rows keep "Categoría · fecha" under the title.** The mockup's domain line would need markup the row does not have (the domain lives in the hidden thumb). The date column stays on the right, as the spec says.
18. **`keyed` goes on `#list`, not `#items`.** `#items` is replaced on every list reload; the class must survive a `j` that reloads nothing.
19. **"★ Favorito" in the bulk bar is ★ by CSS alone** (`font-size: 0` and `::before { content: "★" }`). The markup and its accessible name stay, so delivery 3's words test keeps passing.
20. **The selection mode.**
    - `clear()` also leaves the mode, so every way out the spec lists (✕, Esc, a filter, a bulk action that went through, Cancelar) is one path.
    - A tap on an item with no checkbox (one being analysed) does nothing in the mode.
    - The button is redrawn after every list reload, because it lives in `.list-head` inside `#list`.
21. **Touch zones grow by `::after`** where the drawing must stay small (chips, Lista/Tarjetas, "Seleccionar", the checkbox). The browser helper measures the element's box plus its `::after` insets.
22. **The idea screen's AI bar** is a grid. Every child sits on row 1 and scrolls sideways. `.working` sits on row 2, `position: sticky; left: 16px`, so "Mejoras…" drops to its own line without the bar wrapping.
23. **Old harnesses.**
    - `tests/test_web_app_js.py`'s two harnesses gain `global.addEventListener = () => {};`, because `app.js` now listens for `popstate` on `window`.
    - `tests/test_web_select.py`'s `SENDING_HARNESS` list stub gains `querySelector: () => null` and `classList.contains`.
24. **A delete from the layer on the phone.**
    - The toast with Deshacer shows at once.
    - The list reloads after the layer's `back()` has landed, so its `replaceState` lands on the list's entry.
    - Deshacer reloads the list and opens nothing.
25. **`emptyPanel()` on the phone closes the layer** (a 404 for the shown note, or a bulk action that left nothing). A layer saying "Elegí un link" has nothing to read.

Spec gaps found while planning (also above): the row's domain line (17); "sin envolver" vs. the work state on its own line (22); Esc's order against a field being typed in (13).

## Global Constraints

- **Language.**
  - Code, Python names, commits and docstrings in English.
  - Every UI string goes through `t()`. Its Spanish goes into `src/oknowledge/i18n.py` `STRINGS["es"]` **in the same task that adds the string** (voseo, the spec's §15 words verbatim).
  - `tests/test_i18n.py::test_every_string_a_template_asks_for_has_a_spanish_translation` and `::test_every_translated_string_is_one_the_code_asks_for` run in every suite. A task that removes a string also deletes the entry nothing asks for any more.
  - JS files are not scanned by those tests, so every string a script shows travels in a `data-*` attribute drawn by a template.
  - New in this delivery: "Filters" → "Filtros" (Task 3), "Back to %1" → "Volver a %1" (Task 4) and "Cancel" → "Cancelar" (Task 10). Reused: "Library", "Leisure", "Ideas", "Favorites", "Settings", "Sections", "Select", "Pinned", "All".
- No `|safe` and no `autoescape` in templates (`tests/test_web_read.py::test_no_template_marks_note_content_safe`).
- Never `datetime.datetime.utcnow()` / `utcfromtimestamp()`; use `datetime.datetime.now(datetime.timezone.utc)` (`app.py` imports it as `dt`).
- Commit messages in English, with no `Co-Authored-By`, `Claude-Session` or "Generated with" lines.
- **Suite.**
  - Run `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider` from `/home/fer/Projects/oknowledge` (≈3 min, **≈3019 passing** before this branch).
  - Redirect the output to a file and read its tail.
  - Every task ends with the whole suite green.
- **Tests never reach the network or run a program.** `conftest.py` refuses both and isolates:
  - `XDG_STATE_HOME`;
  - the config path;
  - `i18n.SHARED_FILE` (`isolated_ui_language`).

  Node harnesses run under `shutil.which("node")` and skip without it.
- **The desktop does not change.**
  - Every rule for the phone sits inside `@media (max-width: 60rem)`, `(hover: none)` or `(pointer: coarse)`. The only rules outside are `display: none` for the new parts and `.btn:has(> .enter-hint) { gap: 0; }`.
  - `$SP/d4/desk-compare.sh` must print only zeros (Ruling 2).
- **Tokens** (verbatim from the handoff, already on `:root` in `style.css`):
  - surfaces `--s1 #17181d` … `--s7 #2a2c34`;
  - borders `--b-div #22232a`, `--b-card #24252b`, `--b-input #2a2b32`, `--b-menu #33353e`, `--b-sel #565a6a`;
  - text `--t1 #e7e7ea` … `--t7 #55575f`;
  - `--acc #a9b4de`, `--fav #d9b54a`, `--danger #e59a8f`, `--shadow`.

  New in this delivery (spec §2–§9):
  - tab bar bg `#141519`, top border `1px #22232a`, links 12px `#8b8d96` (`--t5`), on `#e7e7ea` 500;
  - chips 13px, `padding: 7px 12px`, radius 999, border `1px #2a2b32`, on bg `#22232a`, divider `1px × 20px #2a2b32`;
  - field 46px, radius 12, 16px text;
  - row borders `#1d1e23`;
  - layer bg `#141519`, z-index 40; sheet radius `14px 14px 0 0`, backdrop `#0009`, z-index 44/45; tab bar z-index 30; bulk bar z-index 35; toast z-index 50.
- **Sizes:** `--tabbar-h: calc(60px + env(safe-area-inset-bottom))`; touch targets ≥44×44px (spec §12); every input under 60rem is 16px; breakpoints 60rem and 42rem.
- **Live checks only on the scratch vault.**
  - `SP=/tmp/claude-1000/-home-fer-Projects-gym/d89ecc8a-2029-44cb-b47f-742ed00daeae/scratchpad`.
  - Task 1 creates `$SP/shots/serve4.py`, which runs delivery 2's seed (via a copy of `$SP/shots/serve.py` in `$SP/shots4/`) on 127.0.0.1:8812 in Spanish, with `i18n.SHARED_FILE` inside the scratchpad, plus Ruling 1's additions.
  - Start and stop it only with `$SP/d4/srv.sh start [src-dir]` / `$SP/d4/srv.sh stop`. That script resets `$SP/shots4`, waits for the port, and kills by the PID in `$SP/serve.pid` after checking the command line is `serve4.py`.
  - Never the user's vault, `~/.config/oknowledge`, `.env` or `~/.config/omarchy/plugin-language.json`.
- **Browser checks.**
  - They use Playwright for node in `$SP/pw` (`cd "$SP/pw" && [ -d node_modules/playwright ] || npm install --no-save --silent playwright`), launched with `executablePath: "/usr/bin/chromium"`, through the helpers in `$SP/pw/phone.js` (Task 1).
  - A phone is 390×844, `isMobile`, `hasTouch`, `deviceScaleFactor: 3`, with CDP touch emulation.
  - Each check prints one JSON line to compare with the plan's expected line.
- **This branch is `feat/rediseno-celular`, stacked on `feat/rediseno-modales-teclado`.** Another agent may still commit small fixes to `select.js`, `shell.js`, `app.js`, `app.css` and `settings.js` on the base branch. Find code by its text, never by the line numbers quoted here.

## Review Focus

Five ways the phone can bite a user that no single happy-path test exercises. Each is pinned by a test in its owning task:

1. **Sideways scroll from a long title or URL.** A 140-character title with no spaces, a 60-character domain or a pending link's long URL must wrap or clip, never widen the page: `scrollWidth <= innerWidth` on every screen.
   - Pinned in Task 5 (every list page holds `l00000000013`, `l00000000014` and `p00000000001`).
   - Task 6 (the layer over each of the three).
   - Task 7 (Ajustes, the old pages, an open sheet).
2. **The tab bar against the keyboard, the bulk bar and the toast.**
   - Typing hides the tabs (Task 5, `tabsWhileTyping`).
   - In selection mode the bulk bar takes their place inside the screen and the tabs are gone (Task 10, `bar`).
   - The toast sits at the top, under the safe area, and never overlaps the bulk bar (Task 10, `toastClear`; Task 7, `toast`).
3. **History back with the detail and Ajustes.**
   - Back closes exactly one layer and never leaves the page while one was open.
   - A second back leaves for the page before. No dead entry is left behind by "← Biblioteca", Esc, ✕ or a reload with `?sel=`.
   - Pinned in Task 8 (node harness: `afterBack`, `closeWentBack`, `backClosedModal`, `adoptedClose`) and Task 9 (browser: `backs`, `inPlace`).
4. **A tap in selection mode that both ticks and opens.**
   - The tap ticks, the layer stays shut, no `sel` lands in the URL, `history.length` does not grow.
   - On `/ideas` the page does not navigate.
   - Pinned in Task 10 (harness `tapTicks`; browser `ticked`, `ideas`).
5. **The desktop at 1440×900 moving by a pixel**, from a partial drawn on every page, a `↵` wrapped in a span, or a rule that leaked out of the media query. Pinned in Task 11 (`desk-compare.sh` all zeros), and run as a guard at the end of Tasks 5, 6 and 7.

---
### Task 1: The scratch bench, the viewport, and layout.js without its old phone

**Files:**
- Modify: `src/oknowledge/web/templates/base.html` (the `<meta name="viewport">`, line ≈5)
- Modify: `src/oknowledge/web/static/layout.js` (whole file, 59 lines → ≈17)
- Test: `tests/test_web_phone.py` (new)
- Test: `tests/test_web_layout.py`. Rewrite `test_the_layout_script_closes_and_unfocuses_on_a_phone` and `test_the_filters_fold_before_the_first_paint`. Delete `test_the_search_box_is_let_go_after_the_browser_focuses_it` and `test_a_focus_nobody_asked_for_is_dropped_but_a_tap_is_not`: the code they pin is gone (spec §13).
- Create (scratch, not committed):
  - `$SP/d4/base-rev`;
  - `$SP/shots/serve4.py`;
  - `$SP/d4/srv.sh`;
  - `$SP/d4/desk-compare.sh`;
  - `$SP/pw/phone.js`;
  - `$SP/pw/desk.js`;
  - `$SP/pw/same.js`.

**Interfaces:**
- Consumes: delivery 2's `$SP/shots/serve.py` (seeds `l00000000001`…`l00000000012`, `o00000000001`…`o00000000006`, four ideas, writes the first idea's id to `<its dir>/idea`).
- Produces:
  - `tests/test_web_phone.py` with the fixtures `seeded`, `cfg` and `client` (`client.idea` = the idea's id; links `a1` Redes ⭐ in collection "Casa", `b2` Cocina 📌, `c3` Redes; card `c00000000001`), and the helpers `static(name) -> str` and `block(css, head) -> str`. Later tasks append to this file.
  - `$SP/d4/srv.sh start [src-dir]` / `stop`.
  - `$SP/d4/desk-compare.sh` prints one JSON object `{"<shot>.png": <differing pixels>, …}`.
  - `$SP/pw/phone.js` exports `BASE, SP, IDEA(), launch(), phone(browser, {js, width, height}), desktop(browser, {width, height, touch}), go(page, path), media(page), noSideScroll(page), rect(page, sel) -> [x, y, w, h] | null, shown(page, sel) -> bool, smallest(page, sel) -> int` (the smallest touch zone among the matches, ::after included; 0 when none is drawn).
  - Seeded ids: `l00000000013` (long title), `l00000000014` (long domain and URL), `p00000000001` (being analysed).

- [ ] **Step 1: Branch, and record where it starts**

```bash
SP=/tmp/claude-1000/-home-fer-Projects-gym/d89ecc8a-2029-44cb-b47f-742ed00daeae/scratchpad
mkdir -p "$SP/d4"
cd /home/fer/Projects/oknowledge
git rev-parse --verify -q feat/rediseno-celular >/dev/null || git checkout -b feat/rediseno-celular
git rev-parse HEAD > "$SP/d4/base-rev" && cat "$SP/d4/base-rev"
```

Expected: one commit hash, the tip of `feat/rediseno-modales-teclado`. Run this before the first commit of this branch: it is the tree the desktop is compared against (Ruling 2). If the branch already has commits of this plan, take `git merge-base HEAD feat/rediseno-modales-teclado` instead.

- [ ] **Step 2: Write the failing tests**

`tests/test_web_phone.py`:

```python
"""Delivery 4, the phone (docs/2026-10-15-rediseno-celular-design.md): what has
to be in the HTML, the CSS and the scripts for a 390px screen. How it looks
and moves is checked in a browser (the plan's Playwright steps)."""

import re

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.model import Note
from oknowledge.vault import note_path, rebuild_indexes, write_note
from oknowledge.web.app import WEB, create_app

CARD = "c00000000001"


def static(name):
    return WEB.joinpath("static", name).read_text(encoding="utf-8")


def block(css, head):
    """The rules of the first `head { … }` in `css`, braces balanced."""
    start = css.index(head)
    depth = 0
    for at in range(start, len(css)):
        if css[at] == "{":
            depth += 1
        elif css[at] == "}":
            depth -= 1
            if depth == 0:
                return css[start:at + 1]
    raise AssertionError(f"{head} is not closed")


@pytest.fixture
def seeded(tmp_path):
    """Three links (a1 Redes ⭐ in "Casa", b2 Cocina 📌, c3 Redes), a card and
    an idea: (config, the idea's id)."""
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    config = Config(vault=vault)
    for id, category, mark, cols in (("a1", "Redes", "⭐", ["Casa"]), ("b2", "Cocina", "📌", []),
                                     ("c3", "Redes", "", [])):
        write_note(config, Note(id=id, url=f"https://e.com/{id}", title=f"T {id}", category=category,
                                tags=[], type="article", source="e.com", saved="2026-10-03",
                                summary="s", mark=mark, collections=cols), "es")
    card = Note(id=CARD, url="https://www.imdb.com/title/tt1", title="Dune", category="Películas",
                tags=[], type="movie", source="imdb.com", saved="2026-10-02", summary="s",
                state="pending")
    write_note(config, card, "es", path=note_path(config, card, shelf=config.ocio))
    idea = new_idea("Una idea.", "VPN", "2026-10-13", "2026-10-13T00:00:00.000001+00:00")
    write_note(config, idea, "es", path=note_path(config, idea, shelf=config.ideas))
    for shelf in (config.links, config.ocio, config.ideas):
        rebuild_indexes(config, "es", shelf=shelf)
    return config, idea.id


@pytest.fixture
def cfg(seeded):
    return seeded[0]


@pytest.fixture
def client(seeded):
    client = TestClient(create_app(seeded[0]))
    client.idea = seeded[1]
    return client


# --- Task 1: the viewport (spec §12) ---------------------------------------------------

def test_the_page_may_use_the_whole_screen(client):
    body = client.get("/").text
    assert ('<meta name="viewport" content="width=device-width, initial-scale=1, '
            'viewport-fit=cover">') in body
    # Pinch to zoom keeps working.
    assert "maximum-scale" not in body and "user-scalable" not in body
```

In `tests/test_web_layout.py`, replace the four layout-script tests (`test_the_layout_script_closes_and_unfocuses_on_a_phone`, `test_the_search_box_is_let_go_after_the_browser_focuses_it`, `test_a_focus_nobody_asked_for_is_dropped_but_a_tap_is_not`, `test_the_filters_fold_before_the_first_paint`) with:

```python
def test_the_layout_script_has_no_phone_of_its_own():
    """Delivery 4 (docs/2026-10-15-rediseno-celular-design.md §13): the
    folding of details.filters and the search box's autofocus went with the
    old header. The phone is CSS now, and app.js's oknowledge.phone()."""
    js = WEB.joinpath("static", "layout.js").read_text(encoding="utf-8")
    for gone in ("details.filters", "matchMedia", "autofocus", '"pointerdown"', ".blur("):
        assert gone not in js, gone
    assert 'classList.add("js")' in js
    assert '["notice", "n", "m", "undo"]' in js
    # The entry may be a layer's (Ruling 11): its state is kept.
    assert "history.replaceState(history.state," in js


def test_the_js_class_is_set_before_the_first_paint():
    """At the end of <body>'s head the page is still loading: waiting for
    DOMContentLoaded would draw the JavaScript-only parts hidden first."""
    js = WEB.joinpath("static", "layout.js").read_text(encoding="utf-8")
    assert 'addEventListener("DOMContentLoaded"' not in js
```

- [ ] **Step 3: Run them to see them fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_phone.py tests/test_web_layout.py`
Expected: FAIL. `test_the_page_may_use_the_whole_screen` finds no `viewport-fit=cover`; `test_the_layout_script_has_no_phone_of_its_own` finds `details.filters`.

- [ ] **Step 4: Implement**

`base.html`, the viewport line:

```html
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
```

`src/oknowledge/web/static/layout.js`, whole file:

```js
// What has to run before the first paint, on every page.
//
// The class `js` shows what only works with JavaScript (checkboxes, key
// hints, "Seleccionar"), which is drawn hidden. The phone is CSS now
// (docs/2026-10-15-rediseno-celular-design.md §13); the one breakpoint the
// scripts share is app.js's oknowledge.phone().
(function () {
  "use strict";
  document.documentElement.classList.add("js");
  // A notice is said once, and its Deshacer is offered once. Left in the URL,
  // a reload would say it again. The entry keeps its state: it may be a
  // layer's (docs/2026-10-15-rediseno-celular-design.md §6.3).
  var said = new URL(location.href);
  if (said.searchParams.has("notice") || said.searchParams.has("undo")) {
    ["notice", "n", "m", "undo"].forEach(function (name) { said.searchParams.delete(name); });
    history.replaceState(history.state, "", said.pathname + said.search + said.hash);
  }
})();
```

- [ ] **Step 5: Run the tests**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_phone.py tests/test_web_layout.py tests/test_web_leftovers.py tests/test_web_undo.py tests/test_web_settings_tabs.py tests/test_packaging.py`
Expected: PASS. `test_packaging` runs `node --check` on every script.

- [ ] **Step 6: The scratch server**

`$SP/shots/serve4.py`:

```python
"""Delivery 4's scratch server (plan, Ruling 1): delivery 2's seed in
$SP/shots4, in Spanish, plus what the phone checks need -- eight more
categories (the chip row overflows), 30 links in all, a title and a URL with
no place to break, a link being analysed, and catalogs that answer without
the network. Never the user's vault or config."""
import json
import os
import runpy
import shutil
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent / "shots4"
ROOT.mkdir(exist_ok=True)
os.environ["XDG_STATE_HOME"] = str(ROOT / "state")
os.environ["XDG_CONFIG_HOME"] = str(ROOT / "config")
shutil.copy(HERE / "serve.py", ROOT / "serve.py")     # its HERE is then ROOT
shared = ROOT / "state" / "plugin-language.json"
shared.parent.mkdir(parents=True, exist_ok=True)
if not shared.exists():
    shared.write_text(json.dumps({"language": "es"}), encoding="utf-8")

import oknowledge.i18n as i18n  # noqa: E402
import uvicorn  # noqa: E402
from oknowledge.catalog import Candidate, cinemeta, openlibrary  # noqa: E402

i18n.SHARED_FILE = shared


def answers(kind, query, via=""):
    """Three made-up answers, no network, no posters."""
    return [Candidate(ref=f"tt900000{n}", kind=kind, via=via or "movie", title=f"{query} {n}",
                      year=str(1990 + n), people="Alguien") for n in range(1, 4)], ""


cinemeta.search = answers
openlibrary.search = answers

real_run = uvicorn.run
held = []          # the lock of the link "being analysed", kept for the server's life


def seeded_run(app, **kw):
    from oknowledge.config import Config
    from oknowledge.model import Note
    from oknowledge.queue import Queue
    from oknowledge.vault import rebuild_indexes, write_note
    cfg = Config(vault=ROOT / "vault", chain=("opencode",), language="es")
    marker = ROOT / "seeded4"
    if not marker.exists():
        extra = ["Cocina", "Música", "Fotografía", "Finanzas", "Viajes", "Diseño", "Historia",
                 "Idiomas"]
        for n in range(13, 31):
            category = extra[(n - 13) % len(extra)]
            title = ("Supercalifragilisticoespialidosoextraordinariamentelarguísimotítulo" * 2
                     if n == 13 else f"Nota {n} sobre {category}")
            source = ("subdominio-larguisimo.ejemplo-de-dominio-sin-cortes.example.com"
                      if n == 14 else "ejemplo.com")
            path = "x" * 150 if n == 14 else str(n)
            write_note(cfg, Note(id=f"l{n:011d}", url=f"https://{source}/{path}", title=title,
                                 category=category, tags=["extra"], type="article", source=source,
                                 saved=f"2026-08-{n - 10:02d}",
                                 summary="Una nota más para que la lista sea larga. " * 3,
                                 points=["Uno.", "Dos."]), "es")
        rebuild_indexes(cfg, "es", shelf=cfg.links)
        marker.write_text("ok")
    queue = Queue()
    pending = "p00000000001"
    if queue.get(pending) is None:
        queue.enqueue(pending, "https://un-link-que-se-esta-analizando.example.com/" + "y" * 80,
                      "full")
    lock = queue.lock(pending)
    lock.__enter__()
    held.append(lock)
    return real_run(app, **kw)


uvicorn.run = seeded_run
runpy.run_path(str(ROOT / "serve.py"), run_name="__main__")
```

`$SP/d4/srv.sh` (then `chmod +x`):

```bash
#!/bin/bash
# start [src-dir] | stop -- delivery 4's scratch server on 127.0.0.1:8812.
# With a src dir, that tree's oknowledge is served (the desktop baseline).
SP=/tmp/claude-1000/-home-fer-Projects-gym/d89ecc8a-2029-44cb-b47f-742ed00daeae/scratchpad
PY="$HOME/.local/share/oknowledge/venv/bin/python"
case "$1" in
  start)
    "$0" stop
    rm -rf "$SP/shots4"
    if [ -n "$2" ]; then
      PYTHONPATH="$2" "$PY" "$SP/shots/serve4.py" > "$SP/serve.log" 2>&1 &
    else
      "$PY" "$SP/shots/serve4.py" > "$SP/serve.log" 2>&1 &
    fi
    echo $! > "$SP/serve.pid"
    for _ in $(seq 1 150); do
      curl -sf http://127.0.0.1:8812/ >/dev/null && exit 0
      sleep 0.2
    done
    echo "the server did not start"; tail -20 "$SP/serve.log"; exit 1 ;;
  stop)
    pid=$(cat "$SP/serve.pid" 2>/dev/null) || exit 0
    if ps -p "$pid" -o args= | grep -q serve4.py; then
      kill "$pid"
      while ps -p "$pid" >/dev/null; do sleep 0.2; done
    fi ;;
esac
```

`$SP/pw/phone.js`:

```js
// Delivery 4's browser helpers: a phone, a desktop, and what every check measures.
const { chromium } = require("playwright");
const fs = require("fs");
const BASE = "http://127.0.0.1:8812";
const SP = "/tmp/claude-1000/-home-fer-Projects-gym/d89ecc8a-2029-44cb-b47f-742ed00daeae/scratchpad";
const IDEA = () => fs.readFileSync(`${SP}/shots4/idea`, "utf8").trim();

const launch = () => chromium.launch({ executablePath: "/usr/bin/chromium" });

async function touch(context, page) {
  const cdp = await context.newCDPSession(page);
  await cdp.send("Emulation.setTouchEmulationEnabled", { enabled: true, maxTouchPoints: 5 });
}

// 390×844 with a finger: (hover: none) and (pointer: coarse) match.
async function phone(browser, { js = true, width = 390, height = 844 } = {}) {
  const context = await browser.newContext({ viewport: { width, height }, isMobile: true,
    hasTouch: true, deviceScaleFactor: 3, javaScriptEnabled: js });
  const page = await context.newPage();
  await touch(context, page);
  return page;
}

async function desktop(browser, { width = 1440, height = 900, touch: finger = false } = {}) {
  const context = await browser.newContext({ viewport: { width, height }, hasTouch: finger });
  const page = await context.newPage();
  if (finger) await touch(context, page);
  return page;
}

async function go(page, path) {
  await page.goto(BASE + path, { waitUntil: "networkidle" });
  await page.evaluate(() => document.fonts.ready);
}

const media = (page) => page.evaluate(() => ({
  coarse: matchMedia("(pointer: coarse)").matches, hoverNone: matchMedia("(hover: none)").matches }));

const noSideScroll = (page) => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth);

const rect = (page, sel) => page.evaluate((sel) => {
  const el = document.querySelector(sel);
  if (!el) return null;
  const r = el.getBoundingClientRect();
  return [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)];
}, sel);

const shown = (page, sel) => page.evaluate((sel) => {
  const el = document.querySelector(sel);
  if (!el) return false;
  const s = getComputedStyle(el);
  const r = el.getBoundingClientRect();
  return s.display !== "none" && s.visibility !== "hidden" && r.width > 0 && r.height > 0;
}, sel);

// The smallest touch zone among the matches drawn: the box, grown by an
// absolutely placed ::after (Ruling 21). min(width, height).
const smallest = (page, sel) => page.evaluate((sel) => {
  let least = Infinity;
  document.querySelectorAll(sel).forEach((el) => {
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height || getComputedStyle(el).visibility === "hidden") return;
    let w = r.width, h = r.height;
    const after = getComputedStyle(el, "::after");
    if (after.content !== "none" && after.position === "absolute") {
      const px = (v) => parseFloat(v) || 0;
      w = Math.max(w, r.width - px(after.left) - px(after.right));
      h = Math.max(h, r.height - px(after.top) - px(after.bottom));
    }
    least = Math.min(least, w, h);
  });
  return least === Infinity ? 0 : Math.round(least);
}, sel);

module.exports = { BASE, SP, IDEA, launch, phone, desktop, go, media, noSideScroll, rect, shown,
                   smallest };
```

`$SP/pw/desk.js`:

```js
// The desktop at 1440×900, every state a delivery-4 change could move
// (Ruling 2). node desk.js OUTDIR
const { launch, desktop, go, IDEA } = require("./phone.js");
const OUT = process.argv[2];
(async () => {
  const browser = await launch();
  const page = await desktop(browser);
  const shot = (name) => page.screenshot({ path: `${OUT}/${name}.png`, animations: "disabled" });
  const pages = [["home", "/"], ["home-list", "/?vista=lista"], ["home-sel", "/?sel=l00000000013"],
    ["fav", "/?mark=%E2%AD%90"], ["ocio", "/ocio"], ["ocio-sel", "/ocio?sel=o00000000001"],
    ["ocio-buscar", "/ocio?buscar=Dune&catalogo=movie"], ["ideas", "/ideas"],
    ["ideas-list", "/ideas?vista=lista"], ["idea", "/ideas/" + IDEA()], ["settings", "/settings"],
    ["import", "/import"], ["retry", "/retry"], ["notfound", "/no-such-page"]];
  for (const [name, path] of pages) { await go(page, path); await shot(name); }
  // What a script draws: the field saving and finding, Settings, the keys
  // help, a menu, the bulk bar.
  await go(page, "/");
  await page.fill("#field-q", "https://example.com/algo");
  await shot("saving");
  await go(page, "/ocio");
  await page.fill("#field-q", "Terminator");
  await page.waitForTimeout(600);
  await shot("finding");
  await go(page, "/");
  await page.click('.sidebar [data-modal="settings"]');
  await page.waitForSelector("#settings-modal .settings-body");
  await shot("modal-settings");
  await page.keyboard.press("Escape");
  await page.keyboard.press("?");
  await shot("modal-keys");
  await page.keyboard.press("Escape");
  await page.click("#panel details.menu.more > summary");
  await shot("menu-more");
  await page.keyboard.press("Escape");
  const ids = await page.$$eval('#items input[name="ids"]', (b) => b.slice(0, 2).map((x) => x.value));
  for (const id of ids) { await page.hover(`#card-${id}`); await page.check(`#card-${id} input[name="ids"]`); }
  await page.mouse.move(700, 450);
  await shot("bulk");
  await browser.close();
})();
```

`$SP/pw/same.js`:

```js
// node same.js DIR_A DIR_B -> {"name.png": pixels that differ}; -1 another
// size, -2 missing in B.
const { launch } = require("./phone.js");
const fs = require("fs");
const path = require("path");
(async () => {
  const [a, b] = process.argv.slice(2);
  const browser = await launch();
  const page = await browser.newPage();
  const out = {};
  for (const name of fs.readdirSync(a).filter((n) => n.endsWith(".png")).sort()) {
    const one = fs.readFileSync(path.join(a, name));
    if (!fs.existsSync(path.join(b, name))) { out[name] = -2; continue; }
    const other = fs.readFileSync(path.join(b, name));
    if (one.equals(other)) { out[name] = 0; continue; }
    out[name] = await page.evaluate(async ([x, y]) => {
      const load = (d) => new Promise((ok) => { const i = new Image(); i.onload = () => ok(i); i.src = "data:image/png;base64," + d; });
      const [i, j] = await Promise.all([load(x), load(y)]);
      if (i.width !== j.width || i.height !== j.height) return -1;
      const data = (img) => { const c = document.createElement("canvas"); c.width = img.width; c.height = img.height;
        const g = c.getContext("2d"); g.drawImage(img, 0, 0); return g.getImageData(0, 0, img.width, img.height).data; };
      const p = data(i), q = data(j);
      let n = 0;
      for (let k = 0; k < p.length; k += 4) if (p[k] !== q[k] || p[k + 1] !== q[k + 1] || p[k + 2] !== q[k + 2]) n++;
      return n;
    }, [one.toString("base64"), other.toString("base64")]);
  }
  console.log(JSON.stringify(out));
  await browser.close();
})();
```

`$SP/d4/desk-compare.sh` (then `chmod +x`):

```bash
#!/bin/bash
# The desktop before this branch and now, drawn in the same minute (Ruling 2).
set -e
SP=/tmp/claude-1000/-home-fer-Projects-gym/d89ecc8a-2029-44cb-b47f-742ed00daeae/scratchpad
REPO=/home/fer/Projects/oknowledge
rm -rf "$SP/d4/base" "$SP/d4/desk-base" "$SP/d4/desk-head"
mkdir -p "$SP/d4/base" "$SP/d4/desk-base" "$SP/d4/desk-head"
git -C "$REPO" archive "$(cat "$SP/d4/base-rev")" src | tar -x -C "$SP/d4/base"
cd "$SP/pw" && { [ -d node_modules/playwright ] || npm install --no-save --silent playwright; }
"$SP/d4/srv.sh" start "$SP/d4/base/src"
node desk.js "$SP/d4/desk-base"
"$SP/d4/srv.sh" start
node desk.js "$SP/d4/desk-head"
"$SP/d4/srv.sh" stop
node same.js "$SP/d4/desk-base" "$SP/d4/desk-head"
```

- [ ] **Step 7: Check the bench**

```bash
SP=/tmp/claude-1000/-home-fer-Projects-gym/d89ecc8a-2029-44cb-b47f-742ed00daeae/scratchpad
chmod +x "$SP/d4/srv.sh" "$SP/d4/desk-compare.sh"
cat > "$SP/pw/t1.js" <<'EOF'
const { launch, phone, go, media, BASE } = require("./phone.js");
(async () => {
  const browser = await launch();
  const page = await phone(browser);
  await go(page, "/");
  const out = await media(page);
  out.links = await page.$$eval("#items > li.item", (li) => li.length);
  out.pending = await page.evaluate(() => !!document.getElementById("card-p00000000001"));
  const r = await page.request.get(BASE + "/ocio/candidatos?q=Dune&tipo=movie");
  out.catalog = (await r.text()).split('class="candidate"').length - 1;
  console.log(JSON.stringify(out));
  await browser.close();
})();
EOF
"$SP/d4/srv.sh" start && (cd "$SP/pw" && node t1.js); "$SP/d4/srv.sh" stop
"$SP/d4/desk-compare.sh"
```

Expected:
- `{"coarse":true,"hoverNone":true,"links":31,"pending":true,"catalog":3}`.
- Then one JSON object of 18 shots, every value `0`. Base and head serve the same `layout.js` behaviour on a desktop, and the viewport meta does not change a desktop render.

If `coarse` or `hoverNone` is `false`, add this to `phone()` after `touch(context, page)`, then run again:

```js
await (await context.newCDPSession(page)).send("Emulation.setEmulatedMedia", { features: [
  { name: "pointer", value: "coarse" }, { name: "hover", value: "none" },
  { name: "any-pointer", value: "coarse" }, { name: "any-hover", value: "none" }] });
```

If a desktop shot differs, the bench is not deterministic. Find what moves (a time, an animation, the poller) before going on: a later task's zero means nothing without this one's.

- [ ] **Step 8: Whole suite, commit**

Run the suite; expected green.

```bash
git add src/oknowledge/web/templates/base.html src/oknowledge/web/static/layout.js \
        tests/test_web_phone.py tests/test_web_layout.py
git commit -m "Let pages use the whole phone screen, and drop layout.js's dead phone code"
```

---
### Task 2: A top bar and a tab bar on every page

**Files:**
- Create: `src/oknowledge/web/templates/topbar.html`, `tabbar.html`, `batch-count.html`
- Modify: `src/oknowledge/web/templates/base.html` (inside `<div class="app …">`: `topbar.html` before `sidebar.html`, `tabbar.html` after `{% endblock %}` of `layout`)
- Modify: `src/oknowledge/web/templates/sidebar.html` (the foot's "Ajustes" link uses `batch-count.html`)
- Modify: `src/oknowledge/web/static/app.css` (a new section at the end of the file)
- Test: `tests/test_web_phone.py` (append)

**Interfaces:**
- Consumes: `side.section`, `view` (library `View` on `/`), `batch` (`progress.snapshot()`): all already in every `page()` context.
- Produces:
  - `header.topbar` holding `a.logo` and `a.topbar-settings[data-modal="settings"]`;
  - `nav.tabbar` with four `a` in the order `/`, `/ocio`, `/ideas`, `/?mark=%E2%AD%90`, the lit one `class="on" aria-current="page"`;
  - the CSS section header `/* --- delivery 4: the phone … */` at the end of `app.css`. Tasks 3, 4, 5 and 10 add to it.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_web_phone.py`:

```python
# --- Task 2: the top bar and the tabs (spec §2.1) ------------------------------------------

PAGES = ["/", "/?vista=lista", "/ocio", "/ideas", "IDEA", "/settings", "/import", "/retry",
         "/no-such-page"]


def get(client, path):
    return client.get(f"/ideas/{client.idea}" if path == "IDEA" else path)


def tabs(body):
    return re.search(r'<nav class="tabbar" aria-label="Sections">.*?</nav>', body, re.S).group(0)


@pytest.mark.parametrize("path", PAGES)
def test_every_page_has_the_top_bar_and_the_four_tabs(client, path):
    body = get(client, path).text
    top = re.search(r'<header class="topbar">.*?</header>', body, re.S).group(0)
    assert '<a class="logo" href="/">oknowledge</a>' in top
    assert '<a href="/settings" class="topbar-settings" data-modal="settings">Settings</a>' in top
    assert re.findall(r'<a href="([^"]+)"', tabs(body)) == ["/", "/ocio", "/ideas",
                                                            "/?mark=%E2%AD%90"]
    assert [t.strip() for t in re.findall(r">([^<]+)</a>", tabs(body))] == [
        "Library", "Leisure", "Ideas", "Favorites"]


def test_the_bars_are_inside_the_app_around_the_columns(client):
    body = client.get("/").text
    app = body[body.index('<div class="app'):body.index('<div id="toast"')]
    assert (app.index('<header class="topbar">') < app.index('<aside class="sidebar"')
            < app.index('id="panel"') < app.index('<nav class="tabbar"'))


@pytest.mark.parametrize("path, lit", [
    ("/", ["/"]), ("/?cat=Redes", ["/"]), ("/?mark=%E2%AD%90", ["/?mark=%E2%AD%90"]),
    ("/?mark=%E2%AD%90&q=wireguard", ["/"]), ("/?mark=%F0%9F%93%8C", ["/"]),
    ("/ocio", ["/ocio"]), ("/ideas", ["/ideas"]), ("IDEA", ["/ideas"]),
    ("/settings", []), ("/import", []), ("/no-such-page", [])])
def test_one_tab_is_lit_and_favorites_is_the_starred_library(client, path, lit):
    found = re.findall(r'<a href="([^"]+)" class="on" aria-current="page">', tabs(get(client, path).text))
    assert found == lit


def test_the_top_bar_counts_the_batch_as_the_sidebar_does(cfg, monkeypatch):
    from oknowledge.web import batch

    class Running(batch.Batch):
        def snapshot(self):
            return batch.State(running=True, total=10, done=3, failed=0, error=None,
                               lines=(), busy=())

    monkeypatch.setattr("oknowledge.web.app.Batch", Running)
    body = TestClient(create_app(cfg)).get("/").text
    top = re.search(r'<header class="topbar">.*?</header>', body, re.S).group(0)
    foot = re.search(r'<nav class="foot">.*?</nav>', body, re.S).group(0)
    assert 'data-modal="settings">Settings <b class="mono">3/10</b></a>' in top
    assert 'data-modal="settings">Settings <b class="mono">3/10</b></a>' in foot


def test_the_bars_are_not_drawn_on_a_desktop():
    css = static("app.css")
    assert ".topbar, .tabbar { display: none; }" in css
    assert css.index(".topbar, .tabbar { display: none; }") > css.index("/* --- delivery 4: the phone")
```

- [ ] **Step 2: Run them to see them fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_phone.py`
Expected: FAIL. There is no `header.topbar` (`AttributeError: 'NoneType' object has no attribute 'group'`).

- [ ] **Step 3: Implement**

`templates/batch-count.html` (one line, no trailing text: the sidebar's markup must stay byte-identical):

```html
{% if batch.running %} <b class="mono">{{ batch.done }}/{{ batch.total }}</b>{% elif batch.busy %} <b class="mono">{{ batch.busy|length }}</b>{% endif %}
```

`templates/sidebar.html`, the foot's link becomes:

```html
    <a href="/settings" class="foot-link" data-modal="settings">{{ t('Settings') }}{% include "batch-count.html" %}</a>
```

`templates/topbar.html`:

```html
{# The phone's top bar (docs/2026-10-15-rediseno-celular-design.md §2.1): on
   every page, shown only under 60rem. "Ajustes" opens the modal (app.js) and
   says how far a batch is, as the sidebar's does. #}
<header class="topbar">
  <a class="logo" href="/">oknowledge</a>
  <a href="/settings" class="topbar-settings" data-modal="settings">{{ t('Settings') }}{% include "batch-count.html" %}</a>
</header>
```

`templates/tabbar.html`:

```html
{# The phone's sections (spec §2.1), on every page, shown only under 60rem.
   Favoritos is the library filtered by ★ (the sidebar's own condition):
   lit instead of Biblioteca there. The old pages light none. #}
{% set fav = side.section == 'links' and view is defined and view.mark == '⭐' and not view.searching %}
<nav class="tabbar" aria-label="{{ t('Sections') }}">
  {%- for key, href, name in (("links", "/", t("Library")), ("ocio", "/ocio", t("Leisure")),
                              ("ideas", "/ideas", t("Ideas")), ("fav", "/?mark=%E2%AD%90", t("Favorites"))) %}
    {%- set on = fav if key == 'fav' else (side.section == key and not (key == 'links' and fav)) %}
  <a href="{{ href }}"{% if on %} class="on" aria-current="page"{% endif %}>{{ name }}</a>
  {%- endfor %}
</nav>
```

`templates/base.html`, inside `.app`:

```html
  <div class="app {% block app_class %}legacy{% endblock %}">
    {% include "topbar.html" %}
    {% include "sidebar.html" %}
    {% block layout %}
    …unchanged…
    {% endblock %}
    {% include "tabbar.html" %}
  </div>
```

`static/app.css`, at the very end of the file:

```css
/* --- delivery 4: the phone (docs/2026-10-15-rediseno-celular-design.md) --- */
/* Drawn on every page, shown only under 60rem: off on a desktop, where
   display: none keeps them out of the grid. */
.topbar, .tabbar { display: none; }
```

- [ ] **Step 4: Run the tests**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_phone.py tests/test_web_sidebar.py tests/test_i18n.py tests/test_web_settings_tabs.py`
Expected: PASS. If `State` takes other fields than `running, total, done, failed, error, lines, busy`, read `src/oknowledge/web/batch.py`'s `State` and pass what it takes: the test is about the `3/10`.

- [ ] **Step 5: Whole suite, commit**

Run the suite; expected green. A test that pinned "the first `<a href="/settings"`" now meets the top bar's first: make it look inside `<nav class="foot">`, and name it in the commit.

```bash
git add src/oknowledge/web/templates/topbar.html src/oknowledge/web/templates/tabbar.html \
        src/oknowledge/web/templates/batch-count.html src/oknowledge/web/templates/base.html \
        src/oknowledge/web/templates/sidebar.html src/oknowledge/web/static/app.css \
        tests/test_web_phone.py
git commit -m "Draw the phone's top bar and tab bar on every page, hidden on a desktop"
```

---
### Task 3: The filters as one row of chips

**Files:**
- Create: `src/oknowledge/web/templates/filter-chips.html`
- Modify: `src/oknowledge/web/templates/home.html`, `ocio-shelf.html`, `idea-shelf.html` (include the row between the unreadable notice and `<div class="list" id="list">`)
- Modify: `src/oknowledge/web/templates/ocio-list.html` (a second template, `template#chip-filters`)
- Modify: `src/oknowledge/web/static/shell.js`:
  - `setActive`;
  - `sideFilters`;
  - a new `litChipInView`;
  - a call at the end of the IIFE.
- Modify: `src/oknowledge/web/static/app.css` (one line in the delivery-4 section)
- Modify: `src/oknowledge/i18n.py` ("Filters")
- Test: `tests/test_web_phone.py` (append), `tests/test_web_shell_js.py::test_a_filter_click_lights_its_row_only_in_its_own_group` (rewritten: Ruling 7)

**Interfaces:**
- Consumes:
  - `groups` (`side_groups()`: `total`, `categories`, `marks` as `[(mark, n)]` with 📌 first, `collections`) and `view` on `/`;
  - `filters` (`[{"title", "rows": [{"href", "label", "dot", "count", "on"}]}]`) on `/ocio` and `/ideas`;
  - `side_filters` in `/ocio/lista`.
- Produces:
  - `nav.chip-row[aria-label="Filters"] > div.chip-group[data-apart?] > a.fchip[data-nav][title=<count>]`, the lit one with class `on`;
  - `template#chip-filters` in `/ocio/lista`;
  - `shell.js`'s `litChipInView()`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_web_phone.py`:

```python
# --- Task 3: the chip row (spec §3) ----------------------------------------------------------

def chips(body):
    return re.search(r'<nav class="chip-row" aria-label="Filters">.*?</nav>', body, re.S).group(0)


def groups(row):
    return re.findall(r'<div class="chip-group"( data-apart)?[^>]*>(.*?)</div>', row, re.S)


def test_the_library_row_has_all_categories_marks_and_collections_but_no_star(client):
    row = chips(client.get("/").text)
    found = groups(row)
    assert len(found) == 3
    names = [re.sub(r"<[^>]+>", "", a).strip() for a in re.findall(r"<a [^>]*>(.*?)</a>", found[0][1], re.S)]
    assert names == ["All", "Cocina", "Redes"]
    assert "📌" in found[1][1] and "Pinned" in found[1][1] and "⭐" not in found[1][1]
    assert ">Casa</a>" in found[2][1]
    assert "Favorites" not in row and "★" not in row
    # The count is in the title, never drawn.
    assert re.search(r'<a href="/\?cat=Redes" data-nav title="2" class="fchip">', row)
    assert re.search(r'title="3" class="fchip on">All</a>', row)


@pytest.mark.parametrize("path, lit", [("/?cat=Redes", "Redes"), ("/?mark=%F0%9F%93%8C", "📌"),
                                       ("/?col=Casa", "Casa"), ("/?mark=%E2%AD%90", None)])
def test_the_chip_lit_is_the_filter_in_the_url(client, path, lit):
    row = chips(client.get(path).text)
    on = re.findall(r'class="fchip on">(.*?)</a>', row, re.S)
    if lit is None:
        assert on == []           # ★ lights the Favoritos tab, not a chip
    else:
        assert len(on) == 1 and lit in on[0]


def test_an_empty_group_is_not_drawn(tmp_path):
    vault = tmp_path / "solo"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    config = Config(vault=vault)
    write_note(config, Note(id="z1", url="https://e.com/z1", title="Z", category="Redes", tags=[],
                            type="article", source="e.com", saved="2026-10-03", summary="s"), "es")
    rebuild_indexes(config, "es")
    row = chips(TestClient(create_app(config)).get("/").text)
    assert len(groups(row)) == 2      # categories and marks (📌 always); no collections


def test_ocio_and_ideas_rows_are_their_sidebar_groups_each_apart(client):
    ocio = groups(chips(client.get("/ocio").text))
    assert len(ocio) == 2 and all(apart for apart, _ in ocio)
    ideas = groups(chips(client.get("/ideas").text))
    assert len(ideas) == 1 and ideas[0][0]


def test_ocio_s_column_answer_brings_the_row(client):
    body = client.get("/ocio/lista?tipo=movie").text
    template = re.search(r'<template id="chip-filters">(.*?)</template>', body, re.S).group(1)
    assert '<nav class="chip-row"' in template
    assert re.search(r'class="fchip on">.*?</a>', template, re.S)
    assert '<template id="side-filters">' in body


def test_the_row_sits_between_the_field_and_the_list(client):
    for path in ("/", "/ocio", "/ideas"):
        body = client.get(path).text
        assert body.index('id="unified"') < body.index('<nav class="chip-row"') < body.index('id="list"'), path


def test_a_filter_lights_its_twin_in_the_other_drawing():
    js = static("shell.js")
    head = js.index("function setActive")
    body = js[head:js.index("\n  }\n", head)]
    assert '".sidebar, .chip-row"' in body
    assert 'getAttribute("href") === href' in body
    assert 'closest("[data-apart]")' in body
    assert '"a.filter.on, a.fchip.on"' in body
    assert "litChipInView();" in body


def test_ocio_s_answer_swaps_the_row_too():
    js = static("shell.js")
    head = js.index("function sideFilters")
    body = js[head:js.index("\n  }\n", head)]
    assert 'list.querySelector("template#chip-filters")' in body
    assert "replaceWith(chips.content)" in body


def test_the_lit_chip_is_brought_into_view_without_moving_the_page():
    js = static("shell.js")
    assert 'scrollIntoView({ inline: "nearest", block: "nearest" })' in js


def test_the_row_is_not_drawn_on_a_desktop():
    assert ".chip-row { display: none; }" in static("app.css")
```

In `tests/test_web_shell_js.py`, replace `test_a_filter_click_lights_its_row_only_in_its_own_group` with:

```python
def test_a_filter_click_lights_its_row_only_in_its_own_group():
    """Ocio's groups are apart (data-apart): a TIPO click leaves ESTADO lit.
    The library's groups are one choice, so a click there clears them all,
    in the sidebar and in the phone's chip row (Ruling 7 of delivery 4)."""
    body = between(SCRIPT.read_text(encoding="utf-8"), "function setActive", "\n  }\n")
    assert 'twin.closest("[data-apart]") || root' in body
    assert '"a.filter.on, a.fchip.on"' in body
```

- [ ] **Step 2: Run them to see them fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_phone.py tests/test_web_shell_js.py`
Expected: FAIL. There is no `nav.chip-row`.

- [ ] **Step 3: Implement the markup**

`templates/filter-chips.html`:

```html
{# The phone's filters (docs/2026-10-15-rediseno-celular-design.md §3): the
   sidebar's groups as one row of chips that scrolls sideways. The library's
   from `groups` and `view`, any other section's from `filters`. ★ Favoritos
   is a tab, not a chip. The count is in the title. A group with nothing in
   it is not drawn. #}
<nav class="chip-row" aria-label="{{ t('Filters') }}">
{%- if groups is defined and groups %}
  <div class="chip-group" role="group" aria-label="{{ t('Categories') }}">
    <a href="{{ view.url(cat='', tag='', mark='', col='', q='', sel='') }}" data-nav title="{{ groups.total }}" class="fchip{% if not view.filtered %} on{% endif %}">{{ t('All') }}</a>
    {%- for name, count in groups.categories.items() %}
    <a href="{{ view.url(cat=name, tag='', mark='', col='', q='', sel='') }}" data-nav title="{{ count }}" class="fchip{% if view.cat == name and not view.searching and not view.tag and not view.mark and not view.col %} on{% endif %}"><i class="dot" style="background: {{ name|dot }}"></i>{{ name }}</a>
    {%- endfor %}
  </div>
  {%- if groups.marks %}
  <div class="chip-group" role="group" aria-label="{{ t('Marks') }}">
    {%- for mark, count in groups.marks %}
    <a href="{{ view.url(cat='', tag='', mark=mark, col='', q='', sel='') }}" data-nav title="{{ count }}" class="fchip{% if view.mark == mark and not view.searching %} on{% endif %}"><span class="emoji">{{ mark }}</span>{% if mark == '📌' %} {{ t('Pinned') }}{% endif %}</a>
    {%- endfor %}
  </div>
  {%- endif %}
  {%- if groups.collections %}
  <div class="chip-group" role="group" aria-label="{{ t('Collections') }}">
    {%- for name, count in groups.collections.items() %}
    <a href="{{ view.url(cat='', tag='', mark='', col=name, q='', sel='') }}" data-nav title="{{ count }}" class="fchip{% if view.col == name and not view.searching %} on{% endif %}">{{ name }}</a>
    {%- endfor %}
  </div>
  {%- endif %}
{%- else %}
  {%- for group in filters|default([]) if group.rows %}
  <div class="chip-group" data-apart role="group" aria-label="{{ t(group.title) }}">
    {%- for row in group.rows %}
    <a href="{{ row.href }}" data-nav title="{{ row.count }}" class="fchip{% if row.on %} on{% endif %}"><i class="dot" style="background: {{ row.dot }}"></i>{{ t(row.label) }}</a>
    {%- endfor %}
  </div>
  {%- endfor %}
{%- endif %}
</nav>
```

In `home.html`, `ocio-shelf.html` and `idea-shelf.html`, right before `<div class="list" id="list"…>`:

```html
  {% include "filter-chips.html" %}
```

In `ocio-list.html`, the last line becomes:

```html
{% if side_filters is defined %}<template id="side-filters">{% with filters = side_filters %}{% include "sidebar-filters.html" %}{% endwith %}</template><template id="chip-filters">{% with filters = side_filters %}{% include "filter-chips.html" %}{% endwith %}</template>{% endif %}
```

`i18n.py`, `STRINGS["es"]`, beside "Sections":

```python
        "Filters": "Filtros",
```

`app.css`, in the delivery-4 section after the bars' line:

```css
.chip-row { display: none; }
```

- [ ] **Step 4: Implement the script**

In `shell.js`, replace `setActive` with:

```js
  // The library's groups are one choice: a click clears them all. Ocio's
  // TIPO and ESTADO are apart: a click lights its row in its own group.
  // The sidebar and the phone's chip row draw the same filters: the link
  // clicked and its twin (the same href) light together (delivery 4, §3).
  function setActive(link) {
    // A sort link in the list head is not a filter: the filters keep their row.
    if (!link.closest(".sidebar, .chip-row")) return;
    var href = link.getAttribute("href");
    document.querySelectorAll(".sidebar, .chip-row").forEach(function (root) {
      var twin = root.contains(link) ? link : Array.prototype.find.call(
        root.querySelectorAll("a[data-nav]"),
        function (a) { return a.getAttribute("href") === href; });
      if (!twin) return;
      (twin.closest("[data-apart]") || root).querySelectorAll("a.filter.on, a.fchip.on")
        .forEach(function (a) { a.classList.remove("on"); });
      twin.classList.add("on");
    });
    litChipInView();
  }

  // The chip row scrolls sideways: the lit chip is brought into view, and
  // "nearest" on both axes never moves the page. On a desktop the row is
  // not drawn and this does nothing.
  function litChipInView() {
    var lit = document.querySelector(".chip-row .fchip.on");
    if (lit && lit.scrollIntoView) lit.scrollIntoView({ inline: "nearest", block: "nearest" });
  }
```

In `sideFilters`, first thing in the function:

```js
    // The phone's row comes with it, drawn for the same filter (delivery 4, §3).
    var chips = list.querySelector("template#chip-filters");
    if (chips) {
      chips.remove();
      var row = document.querySelector(".chip-row");
      if (row) row.replaceWith(chips.content);
      litChipInView();
    }
```

At the end of the IIFE, beside `observe(); watch();`:

```js
  litChipInView();
```

- [ ] **Step 5: Run the tests**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_phone.py tests/test_web_shell_js.py tests/test_web_sidebar.py tests/test_i18n.py tests/test_packaging.py`
Expected: PASS. `test_the_library_row_has_all_categories_marks_and_collections_but_no_star` orders the categories as the sidebar does (`library.categories()`); if that order is by count, not by name, change the expected list to the sidebar's order: the row must match the sidebar, not the alphabet. The chips are tapped in a browser in Task 5, once the CSS draws them.

- [ ] **Step 6: Whole suite, commit**

Run the suite; expected green.

```bash
git add src/oknowledge/web/templates/filter-chips.html src/oknowledge/web/templates/home.html \
        src/oknowledge/web/templates/ocio-shelf.html src/oknowledge/web/templates/idea-shelf.html \
        src/oknowledge/web/templates/ocio-list.html src/oknowledge/web/static/shell.js \
        src/oknowledge/web/static/app.css src/oknowledge/i18n.py \
        tests/test_web_phone.py tests/test_web_shell_js.py
git commit -m "Draw each section's filters as a row of chips, lit together with the sidebar"
```

---
### Task 4: The detail knows when it is open and how to go back, and the ↵ hints are spans

**Files:**
- Create: `src/oknowledge/web/templates/detail-back.html`
- Modify: `src/oknowledge/web/app.py`:
  - `panel_context` (both returned dicts);
  - `card_context`;
  - `candidates_context` (both returned dicts).
- Modify: `src/oknowledge/web/templates/home.html`, `ocio-shelf.html` (the `<section class="detail" id="panel"…>` tag; the `↵` of the field's buttons)
- Modify: `src/oknowledge/web/templates/idea-shelf.html` (the `↵`)
- Modify: `src/oknowledge/web/templates/panel.html` (first line; "Open original ↵")
- Modify: `src/oknowledge/web/templates/card-panel.html`, `catalog-panel.html` (first line before `<div class="card-top">`)
- Modify: `src/oknowledge/web/static/app.css` (two lines in the delivery-4 section)
- Modify: `src/oknowledge/i18n.py` ("Back to %1")
- Test: `tests/test_web_phone.py` (append)
- Test: `tests/test_web_ideas_list.py::test_the_field_searches_and_offers_a_new_idea` and `tests/test_web_ocio_catalogs.py::test_the_field_offers_the_catalogs`. Each pins `"… ↵"` as text and now looks for the span.

**Interfaces:**
- Consumes: `View.url`, `CardView.url`, `current` (from `listing()` / `card_listing()`), `catalog` (Ocio page).
- Produces:
  - context key `list_url: str` (the list without `sel`) in every panel context;
  - `#panel[data-open]` when the URL's pick is the one shown, or Ocio shows the catalogs;
  - `a.detail-back[data-back]` first in every panel fragment;
  - `span.enter-hint[aria-hidden="true"]` holding `&nbsp;↵`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_web_phone.py`:

```python
# --- Task 4: the detail's markup (spec §6.1) and the ↵ hints (spec §4) ----------------------

@pytest.fixture
def no_catalogs(monkeypatch):
    monkeypatch.setattr("oknowledge.catalog.cinemeta.search", lambda kind, query, via="": ([], ""))
    monkeypatch.setattr("oknowledge.catalog.openlibrary.search", lambda kind, query, via="": ([], ""))


def panel_tag(body):
    return re.search(r'<section class="detail" id="panel"[^>]*>', body).group(0)


@pytest.mark.parametrize("path, opened", [
    ("/?sel=a1", True), ("/?cat=Cocina&sel=b2", True), ("/", False), ("/?sel=zzz", False),
    ("/?cat=Cocina&sel=a1", False),          # a1 is not in Cocina: the first one is shown, shut
    (f"/ocio?sel={CARD}", True), ("/ocio", False), ("/ocio?buscar=Dune&catalogo=movie", True)])
def test_the_detail_is_open_when_the_url_names_the_pick_shown(client, no_catalogs, path, opened):
    assert (" data-open" in panel_tag(client.get(path).text)) is opened


def back(text):
    return re.search(r'<a class="detail-back"[^>]*>[^<]*</a>', text).group(0)


def test_the_library_panel_starts_with_its_way_back(client):
    body = client.get("/?cat=Redes&sel=a1&vista=lista").text
    panel = body[body.index('id="panel"'):]
    assert panel.index('class="detail-back"') < panel.index("data-panel=")
    link = back(panel)
    assert 'href="/?cat=Redes&amp;vista=lista"' in link
    assert " data-back" in link and 'aria-label="Back to Library"' in link
    assert link.endswith(">← Library</a>")


def test_a_panel_fetched_alone_goes_back_to_the_list_it_came_from(client):
    link = back(client.get("/panel/a1?cat=Redes&sel=a1").text)
    assert 'href="/?cat=Redes"' in link and "← Library" in link


def test_a_card_panel_goes_back_to_ocio(client):
    link = back(client.get(f"/panel/{CARD}?tipo=movie&sel={CARD}").text)
    assert 'href="/ocio?tipo=movie"' in link and "← Leisure" in link
    body = client.get(f"/ocio?sel={CARD}").text
    assert "← Leisure" in back(body[body.index('id="panel"'):])


def test_the_catalogs_go_back_to_the_grid(client, no_catalogs):
    assert 'href="/ocio?tipo=series"' in back(client.get("/ocio/candidatos?q=Dune&tipo=movie&grid=series").text)
    assert 'href="/ocio"' in back(client.get("/ocio/candidatos?q=Dune&tipo=movie").text)


def test_a_link_being_analysed_has_its_way_back_too():
    """panel_context's first return (no note yet) carries list_url as well."""
    app = WEB.joinpath("app.py").read_text(encoding="utf-8")
    head = app.index("def panel_context")
    body = app[head:app.index("def card_context", head)]
    assert body.count('"list_url": view.url(sel="")') == 2


HINT = '<span class="enter-hint" aria-hidden="true">&nbsp;↵</span>'


@pytest.mark.parametrize("path, words", [("/", "Save"), ("/ocio", "Save"),
                                         ("/ocio", "Search the catalogs"), ("/ideas", "New idea"),
                                         ("/?sel=a1", "Open original")])
def test_the_enter_hints_are_spans_a_finger_does_not_see(client, path, words):
    body = client.get(path).text
    assert f"{words}{HINT}" in body
    assert f"{words} ↵" not in body


def test_neither_the_hint_nor_the_way_back_moves_the_desktop():
    css = static("app.css")
    assert ".btn:has(> .enter-hint) { gap: 0; }" in css
    assert ".detail-back { display: none; }" in css
```

In `tests/test_web_ideas_list.py::test_the_field_searches_and_offers_a_new_idea`, the last assertion becomes:

```python
    assert 'formaction="/ideas/guardar"' in button.group(0)
    assert 'New idea<span class="enter-hint" aria-hidden="true">&nbsp;↵</span>' in button.group(1)
```

In `tests/test_web_ocio_catalogs.py::test_the_field_offers_the_catalogs`:

```python
    assert 'Search the catalogs<span class="enter-hint" aria-hidden="true">&nbsp;↵</span>' in button.group(1)
```

- [ ] **Step 2: Run them to see them fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_phone.py tests/test_web_ideas_list.py tests/test_web_ocio_catalogs.py`
Expected: FAIL. There is no `data-open`, no `a.detail-back`, and the hints are text.

- [ ] **Step 3: Implement the server side**

`app.py`, `panel_context`: the first `return` (a link being read) and the last both gain the key:

```python
            return None if url is None else {"note": None, "panel_id": link_id,
                                             "pending_url": url, "reading": True,
                                             "list_url": view.url(sel="")}
```

```python
                "back": view.url(sel=link_id),
                # The phone's "← Biblioteca" (docs/2026-10-15-rediseno-celular-design.md §6.1).
                "list_url": view.url(sel="")}
```

`card_context`, in its dict after `"back": view.url(sel=card_id),`:

```python
                "list_url": view.url(sel=""),
```

`candidates_context`: before the first `return`, add `back = f"/ocio?tipo={grid}" if grid else "/ocio"`, and give both returned dicts `"list_url": back`.

`templates/detail-back.html`:

```html
{# The phone's way back from the detail (docs/2026-10-15-rediseno-celular-design.md
   §6.1). Not drawn on a desktop. The words come from the panel that
   includes it (`back_to`), the href from `list_url`. Without JavaScript it
   is a plain link to the list; shell.js makes it the browser's back. #}
<a class="detail-back" href="{{ list_url }}" data-back aria-label="{{ t('Back to %1', t(back_to)) }}">← {{ t(back_to) }}</a>
```

First line of `panel.html`:

```html
{% with back_to = 'Library' %}{% include "detail-back.html" %}{% endwith %}
```

In `card-panel.html` and `catalog-panel.html`, right before `<div class="card-top">`:

```html
{% with back_to = 'Leisure' %}{% include "detail-back.html" %}{% endwith %}
```

`home.html`, the panel's tag:

```html
<section class="detail" id="panel"{% if view.sel and view.sel == current %} data-open{% endif %} aria-label="{{ t('Detail') }}"
```

`ocio-shelf.html`, the panel's tag:

```html
<section class="detail" id="panel"{% if catalog or (view.sel and view.sel == current) %} data-open{% endif %} aria-label="{{ t('Detail') }}"
```

The `↵` in five places: `home.html` (Save), `ocio-shelf.html` (Save, "Search the catalogs"), `idea-shelf.html` ("New idea") and `panel.html` ("Open original"). Each `{{ t('…') }} ↵` becomes:

```html
{{ t('…') }}<span class="enter-hint" aria-hidden="true">&nbsp;↵</span>
```

`i18n.py`, `STRINGS["es"]`:

```python
        "Back to %1": "Volver a %1",
```

`app.css`, delivery-4 section:

```css
.detail-back { display: none; }
/* A ↵ hint is a span (spec §4): no gap may open between it and its words. */
.btn:has(> .enter-hint) { gap: 0; }
```

- [ ] **Step 4: Run the tests**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_phone.py tests/test_web_ideas_list.py tests/test_web_ocio_catalogs.py tests/test_web_home.py tests/test_web_panel.py tests/test_web_ocio_panel.py tests/test_i18n.py tests/test_web_redesign_spanish.py`
Expected: PASS. A test elsewhere that counts the panel's first child, or matches its first line, now meets `a.detail-back`. Make it skip that link, and name it in the commit message.

- [ ] **Step 5: Whole suite, commit**

Run the suite; expected green.

```bash
git add src/oknowledge/web/app.py src/oknowledge/web/templates src/oknowledge/web/static/app.css \
        src/oknowledge/i18n.py tests/test_web_phone.py tests/test_web_ideas_list.py \
        tests/test_web_ocio_catalogs.py
git commit -m "Mark the detail open when the URL names its pick, give it a way back, and wrap the enter hints"
```

---
### Task 5: The phone's frame: bars, field, chips and lists

**Files:**
- Modify: `src/oknowledge/web/static/app.css`:
  - delete the unpolished block under `/* --- the shell` (`@media (max-width: 60rem) { .app, .app.legacy { display: block; height: auto; } .sidebar { … } }`);
  - append the phone block, the 42–60rem block, `(hover: none)` and `(pointer: coarse)` to the delivery-4 section.
- Test: `tests/test_web_phone.py` (append)
- Create (scratch): `$SP/pw/t5.js`

**Interfaces:**
- Consumes: Tasks 2–4's markup (`.topbar`, `.tabbar`, `.chip-row`, `.fchip`, `#panel[data-open]`); `shell.js`'s `setActive` / `sideFilters` / `litChipInView` (Task 3).
- Produces:
  - `--tabbar-h` on `:root`;
  - the single `@media (max-width: 60rem) {` block, ending with the line `} /* end of the phone */`. Tasks 6, 7 and 10 insert their rules right before that line;
  - `@media (pointer: coarse) {`, which Task 7 adds to.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_web_phone.py`:

```python
# --- Task 5: the frame (spec §1, §2.2, §3, §4, §5, §12) ------------------------------------

PHONE = "@media (max-width: 60rem) {"
WIDE = "@media (max-width: 60rem) and (min-width: 42rem) {"


def test_one_phone_block_replaces_the_unpolished_one():
    css = static("app.css")
    assert css.count(PHONE) == 1
    assert ".app, .app.legacy { display: block; height: auto; }" not in css
    assert "--tabbar-h: calc(60px + env(safe-area-inset-bottom));" in css
    phone = block(css, PHONE)
    assert "height: 100vh; height: 100dvh;" in phone
    assert "overflow-x: clip" in phone
    assert "env(safe-area-inset-top)" in phone
    assert "max(8px, env(safe-area-inset-bottom))" in phone
    assert ".sidebar { display: none; }" in phone
    assert ".detail:not([data-open]) { display: none; }" in phone
    assert phone.rstrip().endswith("} /* end of the phone */")


def test_every_phone_field_is_16px_so_ios_does_not_zoom():
    phone = block(static("app.css"), PHONE)
    assert re.search(r"\.unified input\[type=text\] \{[^}]*height: 46px;[^}]*font-size: 16px;", phone)


def test_the_tabs_step_aside_while_typing():
    phone = block(static("app.css"), PHONE)
    assert re.search(r"textarea, select\):focus\) \.tabbar \{ display: none; \}", phone)


def test_between_42_and_60rem_only_the_grids_widen():
    wide = block(static("app.css"), WIDE)
    assert ".tiles { grid-template-columns: repeat(3, minmax(0, 1fr)); }" in wide
    assert ".posters { grid-template-columns: repeat(auto-fill, minmax(168px, 1fr)); }" in wide
    assert ".idea-shelf .tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); }" in wide


def test_a_finger_sees_the_checkbox_and_not_the_keys():
    css = static("app.css")
    assert ".check { opacity: 1; }" in block(css, "@media (hover: none) {")
    coarse = block(css, "@media (pointer: coarse) {")
    for sel in (".key", ".enter-hint", ".unified .hint", '[data-modal="keys"]'):
        assert sel in coarse, sel
```

- [ ] **Step 2: Run them to see them fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_phone.py`
Expected: FAIL. There is no `--tabbar-h`, and the unpolished block is still there.

- [ ] **Step 3: Implement**

In `app.css`, delete these four lines under `/* --- the shell`:

```css
@media (max-width: 60rem) {
  .app, .app.legacy { display: block; height: auto; }
  .sidebar { border-right: 0; border-bottom: 1px solid var(--b-div); }
}
```

Append to the delivery-4 section (after Task 4's lines):

```css
:root { --tabbar-h: calc(60px + env(safe-area-inset-bottom)); }

/* The phone: one column (spec §1-§12). Every rule for it lives in this
   block, in (hover: none) or in (pointer: coarse): the desktop above 60rem
   does not move by a pixel. */
@media (max-width: 60rem) {
  /* §2 the frame: top bar, the column, the tabs. The list scrolls inside. */
  .app, .app.home, .app.ocio, .app.idea-shelf, .app.idea-screen, .app.legacy {
    display: flex; flex-direction: column; height: 100vh; height: 100dvh;
    overflow: hidden; overflow-x: clip; }
  .sidebar { display: none; }
  .topbar { display: flex; flex: none; align-items: center; justify-content: space-between;
    padding: calc(18px + env(safe-area-inset-top)) 16px 10px; line-height: normal; }
  .topbar .logo { font-size: 16px; font-weight: 600; color: var(--t1); text-decoration: none; }
  .topbar-settings { display: inline-flex; align-items: center; gap: 6px; min-height: 44px;
    margin: -12px -8px; padding: 0 8px; font-size: 13px; color: var(--t5); text-decoration: none; }
  .topbar-settings b { font-weight: 400; font-size: 12px; color: var(--t6); }
  .center { flex: 1; min-height: 0; border-right: 0; }
  .detail:not([data-open]) { display: none; }
  .tabbar { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); position: fixed;
    left: 0; right: 0; bottom: 0; z-index: 30; background: #141519;
    border-top: 1px solid var(--b-div); padding: 8px 8px max(8px, env(safe-area-inset-bottom));
    line-height: normal; }
  .tabbar a { display: flex; align-items: center; justify-content: center; min-height: 44px;
    font-size: 12px; color: var(--t5); text-decoration: none; }
  .tabbar a.on { color: var(--t1); font-weight: 500; }
  /* The keyboard is up: a fixed bar would ride on it (Ruling 16). */
  body:has(:is(input:not([type=checkbox]):not([type=radio]):not([type=file]), textarea, select):focus) .tabbar { display: none; }
  /* Pages that scroll as pages (§2.2): an idea, the old pages. */
  .app.idea-screen, .app.legacy { height: auto; overflow: visible; overflow-x: clip; }
  body:has(> .app.idea-screen) { padding-bottom: var(--tabbar-h); }
  .legacy-main { overflow: visible; min-width: 0; padding: 12px 16px var(--tabbar-h); }

  /* §3 the chip row: scrolls by itself, never the page. Each chip is drawn
     34px tall and touched 44px tall (::after, Ruling 21). */
  .chip-row { display: flex; flex: none; align-items: center; gap: 6px; overflow-x: auto;
    scrollbar-width: none; padding: 5px 16px; scroll-padding-inline: 16px; line-height: normal; }
  .chip-row::-webkit-scrollbar { display: none; }
  .chip-group { display: flex; flex: none; align-items: center; gap: 6px; }
  .chip-group + .chip-group::before { content: ""; flex: none; width: 1px; height: 20px;
    margin: 0 2px; background: var(--b-input); }
  .fchip { position: relative; display: inline-flex; flex: none; align-items: center; gap: 6px;
    min-height: 34px; padding: 7px 12px; border: 1px solid var(--b-input); border-radius: 999px;
    font-size: 13px; color: var(--t3); text-decoration: none; white-space: nowrap; }
  .fchip::after { content: ""; position: absolute; inset: -5px -3px; }
  .fchip.on { background: #22232a; color: var(--t1); }

  /* §4 the field: 16px (iOS zooms on less); saving takes a row of its own. */
  .unified { flex: none; flex-wrap: wrap; padding: 0 16px 12px; border-bottom: 0; }
  .unified input[type=text] { min-width: 0; height: 46px; border-radius: 12px; font-size: 16px; }
  .unified .hint { display: none; }
  .unified.saving .save { display: grid; flex-basis: 100%; gap: 8px;
    grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .unified .save:not(:has(.seg)) { grid-template-columns: minmax(0, 1fr); }
  .unified .save .seg { display: contents; }
  .unified .save .seg label { display: block; }
  .unified .save .seg label span, .unified .save .btn, .unified .find .btn {
    display: flex; align-items: center; justify-content: center; height: auto; min-height: 44px;
    padding: 11px; border: 1px solid var(--b-input); border-radius: 10px; font-size: 14px; }
  .unified .save .seg input:checked + span { background: var(--s7); color: var(--t1); }
  .unified.finding .find { flex-basis: 100%; }
  .unified .find .btn { width: 100%; }

  /* §4 the list head: "{filtro} · N", then Seleccionar and Lista | Tarjetas. */
  .list-head { flex: none; flex-wrap: wrap; gap: 8px; padding: 0 16px 8px; }
  .list-head > span { display: flex; flex-wrap: wrap; align-items: center; gap: 0 6px; min-width: 0; }
  .list-head .unrewritten { flex-basis: 100%; margin: 6px 0 0; }
  .list-head .seg a { position: relative; display: flex; align-items: center; min-height: 30px;
    padding: 0 14px; }
  .list-head .seg a::after { content: ""; position: absolute; inset: -7px 0; }
  .list-head .sort > summary { position: relative; }
  .list-head .sort > summary::after { content: ""; position: absolute; inset: -6px 0; }

  /* §5 the lists: they end above the tabs. */
  .list-body { padding: 0 16px calc(12px + var(--tabbar-h)); }
  .list-body:has(> .rows) { padding: 0 8px calc(12px + var(--tabbar-h)); }
  .list-body:has(> .posters) { padding: 0 0 calc(12px + var(--tabbar-h)); }
  .tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
  .tiles .thumb { height: 84px; }
  .tiles .domain { font-size: 10px; }
  .tiles .text { padding: 9px 10px 11px; }
  .rows .item { border-radius: 0; border-bottom: 1px solid #1d1e23; }
  .rows .hit { min-height: 44px; }
  .rows .title { font-size: 15px; }
  .rows .date { font-size: 11px; }
  .posters { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; padding: 4px 16px 20px; }
  .idea-shelf .tiles { grid-template-columns: minmax(0, 1fr); }
  .empty-state { margin-top: 10vh; padding: 0 16px; }
  /* No panel beside the list to explain a lit item: only keys draw it (§10). */
  #list:not(.keyed) .rows .item.on { background: none; }
  #list:not(.keyed) .tiles .item.on { border-color: var(--b-card); }
  #list:not(.keyed) .poster.on .art { border-color: transparent; }
} /* end of the phone */

/* A phone on its side, a tablet: the same column, wider grids (§1, §5). */
@media (max-width: 60rem) and (min-width: 42rem) {
  .tiles { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .posters { grid-template-columns: repeat(auto-fill, minmax(168px, 1fr)); }
  .idea-shelf .tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

/* A finger at any width (§1, §9): what waited for a mouse is there. */
@media (hover: none) {
  .check { opacity: 1; }
}

/* A finger: what only a keyboard uses is not drawn (§1, §4). */
@media (pointer: coarse) {
  .key, .enter-hint, .unified .hint, [data-modal="keys"] { display: none; }
}
```

- [ ] **Step 4: Run the tests**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_phone.py tests/test_web_layout.py`
Expected: PASS.

- [ ] **Step 5: Check it at 390×844**

`$SP/pw/t5.js`:

```js
const { launch, phone, go, media, noSideScroll, rect, shown, smallest } = require("./phone.js");
(async () => {
  const browser = await launch();
  const page = await phone(browser);
  const out = {};
  await go(page, "/");
  out.media = await media(page);
  // Review Focus 1: every list holds l…13 (a 140-letter word), l…14 (a long
  // domain) or the pending link's long URL.
  out.sideScroll = [];
  for (const p of ["/", "/?vista=lista", "/?mark=%E2%AD%90", "/?col=Casa%20conectada", "/ocio",
                   "/ideas", "/ideas?vista=lista"]) {
    await go(page, p);
    if (!(await noSideScroll(page))) out.sideScroll.push(p);
  }
  await go(page, "/");
  out.sidebar = await shown(page, ".sidebar");
  out.topbar = (await rect(page, ".topbar")).slice(0, 3);
  out.tabbar = await page.evaluate(() => [Math.round(document.querySelector(".tabbar").getBoundingClientRect().bottom),
    document.querySelectorAll(".tabbar a").length, document.querySelector(".tabbar a.on").textContent.trim()]);
  out.tabs44 = (await smallest(page, ".tabbar a")) >= 44;
  out.top44 = (await smallest(page, ".topbar-settings")) >= 44;
  out.chipsScroll = await page.evaluate(() => { const row = document.querySelector(".chip-row");
    return [row.scrollWidth > row.clientWidth, getComputedStyle(row).overflowX]; });
  out.chips44 = (await smallest(page, ".chip-row .fchip")) >= 44;
  out.seg44 = (await smallest(page, ".list-head .seg a")) >= 44;
  out.tiles = await page.evaluate(() => getComputedStyle(document.getElementById("items")).gridTemplateColumns.split(" ").length);
  out.pickHidden = await page.evaluate(() => getComputedStyle(document.querySelector("#items > li.item.on")).borderTopColor);
  out.field = await page.evaluate(() => { const f = document.getElementById("field-q");
    return [Math.round(f.getBoundingClientRect().height), getComputedStyle(f).fontSize]; });
  out.hint = await shown(page, ".unified .hint");
  // A link pasted: Completo · Resumen · Guardar, a row of their own, three equal parts.
  await page.fill("#field-q", "https://example.com/algo");
  out.saveRow = await page.evaluate(() => {
    const parts = [...document.querySelectorAll(".unified .save label span, .unified .save .btn")].map((e) => e.getBoundingClientRect());
    const field = document.getElementById("field-q").getBoundingClientRect();
    const widths = parts.map((r) => r.width);
    return [parts.length, parts.every((r) => r.top >= field.bottom), Math.max(...widths) - Math.min(...widths) < 2];
  });
  out.saveSideScroll = await noSideScroll(page);
  // Review Focus 2: typing, the keyboard is up, the tabs step aside.
  out.tabsWhileTyping = await shown(page, ".tabbar");
  await page.evaluate(() => document.activeElement.blur());
  out.tabsAfter = await shown(page, ".tabbar");
  await go(page, "/");
  out.listClearsTabs = await page.evaluate(() => { const body = document.getElementById("list-body");
    body.scrollTop = body.scrollHeight; const items = document.querySelectorAll("#items > li");
    return items[items.length - 1].getBoundingClientRect().bottom <= document.querySelector(".tabbar").getBoundingClientRect().top; });
  // Task 3's chips, tapped: the twin in the sidebar lights too.
  await page.tap(".chip-row .fchip:has-text('Cocina')");
  await page.waitForFunction(() => document.querySelector(".list-head span").textContent.includes("Cocina"));
  out.chipTap = await page.evaluate(() => [document.querySelector(".chip-row .fchip.on").textContent.trim(),
    document.querySelectorAll(".chip-row .fchip.on").length === 1,
    document.querySelector(".sidebar a.filter.on").textContent.trim().split(/\s+/)[0]]);
  await go(page, "/?col=Casa%20conectada");
  out.farChip = await page.evaluate(() => { const r = document.querySelector(".chip-row .fchip.on").getBoundingClientRect();
    return r.left >= 0 && r.right <= innerWidth; });
  await go(page, "/ocio");
  const apartOn = () => page.evaluate(() => [...document.querySelectorAll(".chip-row [data-apart]")].map((g) => (g.querySelector(".fchip.on") || {}).textContent));
  const before = await apartOn();
  const second = await page.evaluate(() => document.querySelector(".chip-row [data-apart] .fchip:nth-child(2)").getAttribute("href"));
  await page.tap(".chip-row [data-apart] .fchip:nth-child(2)");
  // The row is swapped for the server's (sideFilters): wait for the new one.
  await page.waitForFunction((href) => [...document.querySelectorAll(".chip-row [data-apart] .fchip.on")]
    .some((a) => a.getAttribute("href") === href), second);
  const after = await apartOn();
  out.ocioChip = [after[0] !== before[0], after[1] === before[1], await page.evaluate(() => document.querySelectorAll(".chip-row").length)];
  out.posters = await page.evaluate(() => getComputedStyle(document.getElementById("items")).gridTemplateColumns.split(" ").length);
  await go(page, "/ideas");
  out.ideaColumns = await page.evaluate(() => getComputedStyle(document.getElementById("items")).gridTemplateColumns.split(" ").length);
  await go(page, "/");
  await Promise.all([page.waitForURL("**/ocio"), page.tap(".tabbar a[href='/ocio']")]);
  out.tapTab = new URL(page.url()).pathname;
  // 42-60rem: a phone on its side, a tablet.
  const wide = await phone(browser, { width: 768, height: 1024 });
  const columns = () => wide.evaluate(() => getComputedStyle(document.getElementById("items")).gridTemplateColumns.split(" ").length);
  out.tablet = [];
  for (const p of ["/", "/ocio", "/ideas"]) { await go(wide, p); out.tablet.push(await columns()); }
  out.tablet.push(await noSideScroll(wide));
  console.log(JSON.stringify(out));
  await browser.close();
})();
```

Run:

```bash
SP=/tmp/claude-1000/-home-fer-Projects-gym/d89ecc8a-2029-44cb-b47f-742ed00daeae/scratchpad
"$SP/d4/srv.sh" start && (cd "$SP/pw" && node t5.js); "$SP/d4/srv.sh" stop
```

Expected, one line:
`{"media":{"coarse":true,"hoverNone":true},"sideScroll":[],"sidebar":false,"topbar":[0,0,390],"tabbar":[844,4,"Biblioteca"],"tabs44":true,"top44":true,"chipsScroll":[true,"auto"],"chips44":true,"seg44":true,"tiles":2,"pickHidden":"rgb(36, 37, 43)","field":[46,"16px"],"hint":false,"saveRow":[3,true,true],"saveSideScroll":true,"tabsWhileTyping":false,"tabsAfter":true,"listClearsTabs":true,"chipTap":["Cocina",true,"Cocina"],"farChip":true,"ocioChip":[true,true,1],"posters":2,"ideaColumns":1,"tapTab":"/ocio","tablet":[3,4,2,true]}`

If a value differs, fix the CSS (or Task 3's `setActive` / `sideFilters` for `chipTap`, `farChip` and `ocioChip`) and run again. A `sideScroll` entry names the page. To find what is wider than the screen, run in that page:

```js
[...document.querySelectorAll("*")].filter((e) => e.getBoundingClientRect().right > innerWidth + 1)
```

Then give that element `min-width: 0`, `overflow-wrap: anywhere` or a scroll of its own, inside the phone block.

- [ ] **Step 6: The desktop has not moved**

Run: `"$SP/d4/desk-compare.sh"`
Expected: 18 shots, every value `0`. A non-zero shot means a rule outside the three media blocks reached the desktop: find it before committing.

- [ ] **Step 7: Whole suite, commit**

Run the suite; expected green.

```bash
git add src/oknowledge/web/static/app.css tests/test_web_phone.py
git commit -m "Lay every page out as one column under 60rem: top bar, chips, list and tabs"
```

---
### Task 6: The detail as a full-screen layer, and an idea's screen in one column

**Files:**
- Modify: `src/oknowledge/web/static/app.css` (rules inserted before `} /* end of the phone */`)
- Test: `tests/test_web_phone.py` (append)
- Create (scratch): `$SP/pw/t6.js`

**Interfaces:**
- Consumes: `#panel[data-open]`, `a.detail-back` (Task 4); the phone block (Task 5).
- Produces: `.detail[data-open]` covers the screen at z-index 40. `.detail[aria-busy="true"]` hides everything but `.detail-back`; Task 9 sets that attribute while a tapped note loads (Ruling 15).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_web_phone.py`:

```python
# --- Task 6: the layer and an idea's screen (spec §6.2, §7) ---------------------------------

def test_the_open_detail_covers_the_screen_above_the_tabs():
    phone = block(static("app.css"), PHONE)
    rule = re.search(r"\.detail\[data-open\] \{[^}]*\}", phone).group(0)
    for part in ("position: fixed;", "inset: 0;", "z-index: 40;", "background: #141519;",
                 "padding-top: env(safe-area-inset-top);"):
        assert part in rule, part
    assert '.detail[aria-busy="true"] > :not(.detail-back) { visibility: hidden; }' in phone


def test_long_words_wrap_inside_the_detail():
    phone = block(static("app.css"), PHONE)
    assert re.search(r"\.detail h1, \.detail \.where[^{]*\{ overflow-wrap: anywhere; \}", phone)
    assert ".detail pre { max-width: 100%; overflow-x: auto; }" in phone


def test_an_idea_scrolls_as_a_page_with_its_rows_scrolling_sideways():
    phone = block(static("app.css"), PHONE)
    assert re.search(r"\.idea-ai \{[^}]*overflow-x: auto;", phone)
    assert ".idea-ai .label { display: none; }" in phone
    assert re.search(r"\.idea-text textarea \{[^}]*min-height: 40dvh;[^}]*font-size: 16px;", phone)
    assert re.search(r"\.idea-results \.tabs \{[^}]*overflow-x: auto;", phone)
```

- [ ] **Step 2: Run them to see them fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_phone.py`
Expected: FAIL. There is no `.detail[data-open]` rule.

- [ ] **Step 3: Implement**

In `app.css`, right before `} /* end of the phone */`:

```css
  /* §6 the detail: a layer over the whole screen while the URL names a
     pick. The tabs stay under it; the toast (z 50) stays over it. */
  .detail[data-open] { position: fixed; inset: 0; z-index: 40; display: flex;
    flex-direction: column; background: #141519; padding-top: env(safe-area-inset-top); }
  /* A tapped note on its way: not the last one's words meanwhile (Ruling 15). */
  .detail[aria-busy="true"] > :not(.detail-back) { visibility: hidden; }
  .detail-back { display: flex; flex: none; align-items: center; min-height: 44px; padding: 0 16px;
    font-size: 14px; color: var(--acc); text-decoration: none; }
  .detail-scroll, .detail-scroll.card, .detail-scroll.candidates { padding: 12px 16px 24px; gap: 16px; }
  .detail h1 { font-size: 22px; }
  .detail h1, .detail .where, .detail .body, .detail li, .detail a { overflow-wrap: anywhere; }
  .detail pre { max-width: 100%; overflow-x: auto; }
  .meta-row { flex-wrap: wrap; }
  .meta-row .chip-menu > summary { position: relative; }
  .meta-row .chip-menu > summary::after { content: ""; position: absolute; inset: -10px 0; }
  .detail-bar { flex: none; flex-wrap: wrap; padding: 10px 16px max(10px, env(safe-area-inset-bottom)); }
  .detail .btn { height: 44px; }
  .detail .btn.icon { width: 44px; }
  .detail .chips .chip button { position: relative; min-width: 32px; }
  .detail .chips .chip button::after { content: ""; position: absolute; inset: -14px 0; }
  .detail .tag-new input { min-height: 44px; font-size: 16px; }
  /* Ocio's card: state and ⋯ on one row, the stars on the next. */
  .card-top { flex: none; flex-wrap: wrap; gap: 8px; padding: 10px 16px; }
  .card-top .seg button, .card-top .seg a { display: flex; align-items: center; min-height: 44px; }
  .card-top .more { order: 2; margin-left: auto; }
  .card-top .stars.big { order: 3; flex-basis: 100%; }
  .stars.big button, .idea-controls .stars button { display: inline-flex; align-items: center;
    justify-content: center; width: 44px; height: 44px; }
  .card-head { grid-template-columns: 88px minmax(0, 1fr); }
  .detail .card-head h1 { font-size: 20px; }
  .candidate { min-width: 0; }

  /* §7 an idea: one column that scrolls as a page. */
  .idea-main { min-height: auto; }
  .idea-head { padding: 12px 16px; }
  .idea-title-row { flex-direction: column; align-items: stretch; gap: 10px; }
  .idea-title input { font-size: 22px; text-overflow: ellipsis; }
  .idea-controls { flex-wrap: wrap; gap: 8px; max-width: 100%; }
  .idea-controls .seg { max-width: 100%; overflow-x: auto; scrollbar-width: none; }
  .idea-controls .seg button { min-height: 44px; }
  .idea-head .tag-new input { min-height: 44px; font-size: 16px; }
  /* The AI bar scrolls sideways; what is running drops to a row of its own
     (Ruling 22). */
  .idea-ai { display: grid; grid-auto-flow: column; grid-auto-columns: max-content;
    align-items: center; gap: 8px; overflow-x: auto; scrollbar-width: none; padding: 10px 16px; }
  .idea-ai > *:not(.working), .idea-ai > form > * { grid-row: 1; }
  .idea-ai .label { display: none; }
  .ai-btn, .idea-ai .scope > summary { min-height: 44px; }
  .idea-ai .working { grid-row: 2; grid-column: 1; width: 0; margin: 0; white-space: nowrap;
    position: sticky; left: 16px; }
  .idea-ai .working:empty { display: none; }
  .idea-body { display: flex; flex-direction: column; }
  .idea-text { padding: 16px; border-right: 0; }
  .idea-text textarea { min-height: 40dvh; font-size: 16px; }
  .idea-results { padding: 16px; }
  .idea-results .tabs { overflow-x: auto; scrollbar-width: none; }
  .idea-results .tabs a { flex: none; display: flex; align-items: center; min-height: 44px;
    padding: 0; white-space: nowrap; }
  .links-column { min-height: auto; border-left: 0; border-top: 1px solid var(--b-div); }
  .links-head { padding: 16px 16px 0; }
  .links-search input { height: 44px; font-size: 16px; }
  .links-scroll { overflow: visible; padding: 8px 16px 16px; }
  .links-column .row { min-height: 44px; }
  .links-column .row .x, .links-column .row .add { min-width: 44px; min-height: 44px; }
```

- [ ] **Step 4: Run the tests**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_phone.py`
Expected: PASS.

- [ ] **Step 5: Check it at 390×844**

The layer here is opened by the server (`?sel=`). Opening it by a tap is Task 9.

`$SP/pw/t6.js`:

```js
const { launch, phone, go, noSideScroll, rect, shown, smallest, IDEA } = require("./phone.js");
(async () => {
  const browser = await launch();
  const page = await phone(browser);
  const out = {};
  const text = (sel) => page.evaluate((sel) => document.querySelector(sel).textContent.trim(), sel);
  // Review Focus 1: the long title, the long domain, the pending link's URL.
  out.sideScroll = [];
  for (const p of ["/?sel=l00000000013", "/?sel=l00000000014", "/?sel=p00000000001",
                   "/ocio?sel=o00000000001", "/ocio?buscar=Dune&catalogo=movie", "/ideas/" + IDEA()]) {
    await go(page, p);
    if (!(await noSideScroll(page))) out.sideScroll.push(p);
  }
  await go(page, "/?sel=l00000000013");
  out.layer = await rect(page, "#panel");
  out.back = [await shown(page, "#panel .detail-back"), await text("#panel .detail-back")];
  out.title = await page.evaluate(() => { const h = document.querySelector("#panel h1");
    return [getComputedStyle(h).fontSize, h.scrollWidth <= h.clientWidth]; });
  out.bar44 = (await smallest(page, "#panel .detail-bar .btn")) >= 44;
  out.back44 = (await smallest(page, "#panel .detail-back")) >= 44;
  out.barAtBottom = await page.evaluate(() => Math.round(document.querySelector("#panel .detail-bar").getBoundingClientRect().bottom));
  out.tabsCovered = await page.evaluate(() => !document.elementFromPoint(195, 835).closest(".tabbar"));
  await go(page, "/");
  out.shutWithoutSel = await shown(page, "#panel");
  await go(page, "/ocio?sel=o00000000001");
  out.ocio = [await rect(page, "#panel"), await text("#panel .detail-back"),
    (await smallest(page, "#panel .card-top button")) >= 44,
    await page.evaluate(() => document.querySelector("#panel .stars.big").getBoundingClientRect().top >=
                              document.querySelector("#panel .card-top .seg").getBoundingClientRect().bottom)];
  await go(page, "/ocio?buscar=Dune&catalogo=movie");
  out.catalog = [await shown(page, "#panel"), await page.$$eval("#panel .candidate", (c) => c.length),
                 await text("#panel .detail-back")];
  await go(page, "/ideas/" + IDEA());
  out.idea = await page.evaluate(() => {
    const area = document.querySelector(".idea-text textarea");
    return [document.documentElement.scrollHeight > innerHeight, getComputedStyle(area).fontSize,
      area.getBoundingClientRect().height >= 337, getComputedStyle(document.querySelector(".idea-ai")).overflowX,
      getComputedStyle(document.querySelector(".idea-ai .label")).display,
      document.querySelector(".links-column").getBoundingClientRect().top >=
        document.querySelector(".idea-results").getBoundingClientRect().bottom - 1];
  });
  out.idea44 = (await smallest(page, ".idea-controls .stars button, .idea-controls .seg button, .ai-btn")) >= 44;
  out.ideaTabs = await shown(page, ".tabbar");
  console.log(JSON.stringify(out));
  await browser.close();
})();
```

Run:

```bash
SP=/tmp/claude-1000/-home-fer-Projects-gym/d89ecc8a-2029-44cb-b47f-742ed00daeae/scratchpad
"$SP/d4/srv.sh" start && (cd "$SP/pw" && node t6.js); "$SP/d4/srv.sh" stop
```

Expected, one line:
`{"sideScroll":[],"layer":[0,0,390,844],"back":[true,"← Biblioteca"],"title":["22px",true],"bar44":true,"back44":true,"barAtBottom":844,"tabsCovered":true,"shutWithoutSel":false,"ocio":[[0,0,390,844],"← Ocio",true,true],"catalog":[true,3,"← Ocio"],"idea":[true,"16px",true,"auto","none",true],"idea44":true,"ideaTabs":true}`

If a value differs, fix the CSS above and run again. For a `sideScroll` entry, use Task 5 Step 5's finder.

- [ ] **Step 6: The desktop has not moved**

Run: `"$SP/d4/desk-compare.sh"`. Expected: every value `0`.

- [ ] **Step 7: Whole suite, commit**

Run the suite; expected green.

```bash
git add src/oknowledge/web/static/app.css tests/test_web_phone.py
git commit -m "Open the detail as a full-screen layer on the phone, and lay an idea out as one column"
```

---
### Task 7: Ajustes full screen, menus as sheets, the toast and the old pages

**Files:**
- Modify: `src/oknowledge/web/static/app.css` (before `} /* end of the phone */`; one selector added to `@media (pointer: coarse)`)
- Test: `tests/test_web_phone.py` (append)
- Create (scratch): `$SP/pw/t7.js`

**Interfaces:**
- Consumes:
  - `dialog.modal.settings` and its fragment (`.settings-head`, `.settings-note`, `.settings-close`, `.settings-tabs a[data-settings-tab]`, `.settings-pane`, `.engine-row`, `.setting`, `.cat-row`, `.drop`, `.drop-title`);
  - `details.menu > .menu-list`, `.submenu`;
  - `#toast`.
- Produces: the sheet geometry (`.menu-list` fixed to the bottom, full width, z-index 45; the backdrop `summary::before` at z-index 44), which Task 10's "Mover a ▾" relies on.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_web_phone.py`:

```python
# --- Task 7: Ajustes, menus, toast, old pages (spec §8, §9, §11) ------------------------------

def test_settings_fills_the_phone():
    phone = block(static("app.css"), PHONE)
    rule = re.search(r"\.modal\.settings \{[^}]*\}", phone).group(0)
    for part in ("width: 100vw;", "height: 100dvh;", "max-width: none;", "max-height: none;",
                 "margin: 0;", "border: 0;", "border-radius: 0;"):
        assert part in rule, part
    assert re.search(r"\.settings-tabs \{[^}]*overflow-x: auto;", phone)
    assert re.search(r"\.setting \{[^}]*flex-direction: column;", phone)


def test_a_menu_opens_as_a_sheet_from_the_bottom():
    phone = block(static("app.css"), PHONE)
    sheet = re.search(r"\.menu-list, [^{]*\{[^}]*\}", phone).group(0)
    for part in ("position: fixed;", "left: 0;", "right: 0;", "bottom: 0;", "top: auto;",
                 "min-width: 0;", "max-height: 60dvh;", "border-radius: 14px 14px 0 0;",
                 "max(8px, env(safe-area-inset-bottom))", "z-index: 45;"):
        assert part in sheet, part
    # Every placement the desktop gives a menu is overridden by name.
    for sel in (".menu.up .menu-list", ".menu.more .menu-list", ".idea-ai .menu-list",
                ".list-head .sort .menu-list", ".bulk .menu-list"):
        assert sel in sheet, sel
    assert re.search(r'\.menu\[open\] > summary::before \{ content: ""; position: fixed; inset: 0;'
                     r' background: #0009; z-index: 44;', phone)


def test_the_toast_stays_at_the_top_and_may_wrap():
    rule = re.search(r"\.toast \{[^}]*\}", block(static("app.css"), PHONE)).group(0)
    assert "top: calc(env(safe-area-inset-top) + 12px);" in rule
    assert "max-width: calc(100vw - 32px);" in rule and "white-space: normal;" in rule


def test_a_finger_is_not_asked_to_drop_a_file():
    assert ".drop-title" in block(static("app.css"), "@media (pointer: coarse) {")
```

- [ ] **Step 2: Run them to see them fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_phone.py`
Expected: FAIL. There is no `.modal.settings` rule in the phone block.

- [ ] **Step 3: Implement**

In `app.css`, right before `} /* end of the phone */`:

```css
  /* §8 Ajustes: the same <dialog>, the whole screen. */
  .modal.settings { width: 100vw; height: 100vh; height: 100dvh; max-width: none; max-height: none;
    margin: 0; border: 0; border-radius: 0;
    padding: env(safe-area-inset-top) 0 env(safe-area-inset-bottom); }
  .settings-head { flex-wrap: wrap; gap: 4px 12px; padding: 8px 8px 0 16px; }
  .settings-note { flex-basis: 100%; order: 3; margin: 0; }
  .settings-close { width: 44px; height: 44px; margin-left: auto; }
  .settings-tabs { overflow-x: auto; scrollbar-width: none; gap: 18px; padding: 8px 16px 0; }
  .settings-tabs a { flex: none; display: flex; align-items: center; min-height: 44px;
    padding: 0; white-space: nowrap; }
  .settings-pane { padding: 16px; }
  .settings-pane .engine-row { grid-template-columns: 20px minmax(0, 1fr); }
  .settings-pane .engine-row .model-box, .settings-pane .engine-tools { grid-column: 1 / -1; }
  .settings-pane .engine-tools { flex-wrap: wrap; white-space: normal; }
  .settings-pane input:not([type=checkbox]):not([type=radio]):not([type=file]),
  .settings-pane select { font-size: 16px; min-height: 44px; }
  .setting { flex-direction: column; align-items: stretch; gap: 8px; }
  .setting .seg { display: flex; }
  .setting .seg label { flex: 1; }
  .setting .seg label span { display: flex; align-items: center; justify-content: center; min-height: 44px; }
  .cat-row { grid-template-columns: 8px minmax(0, 1fr) auto; }
  .cat-row input { grid-column: 1 / -1; }
  .drop { padding: 20px 16px; }
  .drop .btn, .settings-pane .link-button { min-height: 44px; }

  /* §8 menus: a sheet from the bottom, the whole width; a tap on the
     backdrop lands on the summary and closes it. */
  .menu-list, .menu.up .menu-list, .menu.more .menu-list, .idea-ai .menu-list,
  .list-head .sort .menu-list, .bulk .menu-list {
    position: fixed; left: 0; right: 0; bottom: 0; top: auto; min-width: 0; max-height: 60dvh;
    border-radius: 14px 14px 0 0; padding: 8px 8px max(8px, env(safe-area-inset-bottom));
    z-index: 45; }
  .menu[open] > summary::before { content: ""; position: fixed; inset: 0; background: #0009; z-index: 44; cursor: default; }
  .menu-list button, .menu-list a, .submenu > summary { min-height: 44px; }
  .menu-new input { font-size: 16px; min-height: 44px; }

  /* §9 the toast: at the top, under the notch, two lines if it must. */
  .toast { top: calc(env(safe-area-inset-top) + 12px); max-width: calc(100vw - 32px); white-space: normal; width: max-content; }
  .toast button { min-height: 44px; margin: -12px 0; }

  /* §11 the old pages: nothing wider than the screen. */
  .legacy-main { overflow-wrap: anywhere; }
  .legacy-main table { display: block; max-width: 100%; overflow-x: auto; }
  .legacy-main pre { max-width: 100%; overflow-x: auto; }
```

In `@media (pointer: coarse)`, the rule becomes:

```css
  .key, .enter-hint, .unified .hint, [data-modal="keys"], .drop-title { display: none; }
```

- [ ] **Step 4: Run the tests**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_phone.py`
Expected: PASS.

- [ ] **Step 5: Check it at 390×844**

`$SP/pw/t7.js`:

```js
const { launch, phone, go, noSideScroll, rect, shown, smallest } = require("./phone.js");
(async () => {
  const browser = await launch();
  const page = await phone(browser);
  const out = {};
  // Review Focus 1: the old pages.
  out.sideScroll = [];
  for (const p of ["/settings", "/settings?tab=motores", "/settings?tab=categorias", "/import", "/retry", "/no-such-page"]) {
    await go(page, p);
    if (!(await noSideScroll(page))) out.sideScroll.push(p);
  }
  await go(page, "/settings");
  out.legacy = [await shown(page, ".tabbar"), await shown(page, ".topbar"),
    await page.evaluate(() => getComputedStyle(document.querySelector(".app")).height !== innerHeight + "px")];
  // The modal, from the top bar: the whole screen (its history entry is Task 8).
  await go(page, "/");
  await page.tap(".topbar-settings");
  await page.waitForSelector("#settings-modal .settings-body");
  out.modal = [await rect(page, "#settings-modal"), await noSideScroll(page),
    await page.evaluate(() => getComputedStyle(document.querySelector("#settings-modal .settings-tabs")).overflowX),
    (await smallest(page, "#settings-modal .settings-tabs a")) >= 44,
    (await smallest(page, "#settings-modal .settings-close")) >= 44];
  out.panes = [];
  for (const tab of await page.$$eval("#settings-modal [data-settings-tab]", (a) => a.map((x) => x.dataset.settingsTab))) {
    await page.tap(`#settings-modal [data-settings-tab="${tab}"]`);
    out.panes.push(await page.evaluate(() => {
      const pane = document.querySelector("#settings-modal .settings-pane:not([hidden])");
      const fields = [...pane.querySelectorAll("input:not([type=checkbox]):not([type=radio]):not([type=file]), select")];
      return [document.documentElement.scrollWidth <= innerWidth, fields.every((f) => getComputedStyle(f).fontSize === "16px")];
    }));
  }
  await page.tap('#settings-modal [data-settings-tab="idioma"]');
  out.stacked = await page.evaluate(() => getComputedStyle(document.querySelector("#settings-modal .setting")).flexDirection);
  await page.tap('#settings-modal [data-settings-tab="importar"]');
  out.noDrop = !(await shown(page, "#settings-modal .drop-title"));
  await page.keyboard.press("Escape");
  // A menu: a sheet from the bottom, the whole width, ≥44px items; the backdrop closes it.
  await go(page, "/?sel=l00000000001");
  await page.tap("#panel details.menu.more > summary");
  out.sheet = [await page.evaluate(() => { const r = document.querySelector("#panel details.menu.more > .menu-list").getBoundingClientRect();
    return [Math.round(r.left), Math.round(r.right), Math.round(r.bottom)]; }),
    (await smallest(page, "#panel details.menu.more > .menu-list button")) >= 44, await noSideScroll(page)];
  await page.touchscreen.tap(195, 60);
  out.backdropCloses = await page.evaluate(() => !document.querySelector("#panel details.menu.more").open);
  await go(page, "/ocio");
  await page.tap(".list-head details.sort > summary");
  out.sortSheet = await page.evaluate(() => { const r = document.querySelector(".list-head details.sort > .menu-list").getBoundingClientRect();
    return [Math.round(r.left), Math.round(r.right), Math.round(r.bottom)]; });
  // The server's toast: at the top, inside the screen, words that wrap.
  await page.goto("http://127.0.0.1:8812/?notice=saved");
  out.toast = await page.evaluate(() => { const t = document.getElementById("toast"); const r = t.getBoundingClientRect();
    return [!t.hidden, r.top >= 12, r.left >= 16 && r.right <= innerWidth - 16, getComputedStyle(t).whiteSpace]; });
  console.log(JSON.stringify(out));
  await browser.close();
})();
```

Run:

```bash
SP=/tmp/claude-1000/-home-fer-Projects-gym/d89ecc8a-2029-44cb-b47f-742ed00daeae/scratchpad
"$SP/d4/srv.sh" start && (cd "$SP/pw" && node t7.js); "$SP/d4/srv.sh" stop
```

Expected, one line (four panes):
`{"sideScroll":[],"legacy":[true,true,true],"modal":[[0,0,390,844],true,"auto",true,true],"panes":[[true,true],[true,true],[true,true],[true,true]],"stacked":"column","noDrop":true,"sheet":[[0,390,844],true,true],"backdropCloses":true,"sortSheet":[0,390,844],"toast":[true,true,true,"normal"]}`

Check the tab keys first with `grep -n SETTINGS_TABS -A2 src/oknowledge/web/app.py`. If they are not `motores`, `idioma`, `importar`, `categorias`, use the real ones in the script. If a value differs, fix the CSS and run again.

- [ ] **Step 6: The desktop has not moved**

Run: `"$SP/d4/desk-compare.sh"`. Expected: every value `0`.

- [ ] **Step 7: Whole suite, commit**

Run the suite; expected green.

```bash
git add src/oknowledge/web/static/app.css tests/test_web_phone.py
git commit -m "Give Ajustes the whole phone, open menus as sheets, and keep the toast and old pages on screen"
```

---
### Task 8: app.js — one breakpoint, layers that back closes, and Ajustes as one

**Files:**
- Modify: `src/oknowledge/web/static/app.js`:
  - a new section "the phone" before `// --- keys`;
  - `openModal`;
  - the Escape branch of the `keydown` listener;
  - the exports at the end (`ok.phone`, `ok.layers`).
- Modify: `src/oknowledge/web/static/settings.js` (the modal's `close` listener)
- Test: `tests/test_web_app_js.py`:
  - append `LAYERS_HARNESS` and its tests;
  - add `global.addEventListener = () => {};` after `global.window = global;` in `HARNESS` and `UNDO_HARNESS` (Ruling 23).
- Test: `tests/test_web_phone.py` (append: the `settings.js` source check)
- Create (scratch): `$SP/pw/t8.js`

**Interfaces:**
- Consumes: `#settings-modal` (`dialog`), `ok.openSettings` (`settings.js`), `history`, `window.matchMedia`.
- Produces:
  - `ok.phone() -> bool`: `matchMedia("(max-width: 60rem)")`, false where there is no `matchMedia`.
  - `ok.layers.open(name: string, onClose: (how) => void, url?: string) -> bool`.
  - `ok.layers.adopt(name, onClose) -> bool`.
  - `ok.layers.close() -> Promise<void>`.
  - `ok.layers.top() -> string`.
  - `ok.layers.settled() -> Promise<void>`.
  - `how` is `"back"` (the browser went back) or `"close"` (closed in place).

- [ ] **Step 1: Write the failing tests**

In `tests/test_web_app_js.py`, in both `HARNESS` and `UNDO_HARNESS`, right after `global.window = global;`:

```js
global.addEventListener = () => {};
```

Append to `tests/test_web_app_js.py`:

```python
# --- delivery 4: layers (docs/2026-10-15-rediseno-celular-design.md §6.3, §8) --------------

LAYERS_HARNESS = r"""
const source = require("fs").readFileSync(process.argv[2], "utf8");
const out = {};
const win = {};
const handlers = {};
global.window = global;
global.addEventListener = (type, fn) => { (win[type] = win[type] || []).push(fn); };
// A history of same-document entries: back() pops one and fires popstate later.
const entries = [{ state: null, url: "/" }];
let at = 0;
global.location = { get href() { return "http://x" + entries[at].url; }, pathname: "/",
                    reload() { out.reloaded = true; } };
global.history = {
  get state() { return entries[at].state; },
  pushState(state, _, url) { entries.splice(at + 1); entries.push({ state, url: url.replace("http://x", "") }); at++; },
  replaceState(state, _, url) { entries[at] = { state, url: url.replace("http://x", "") }; },
  back() {
    if (at === 0) { out.leftSite = true; return; }
    at--;
    setTimeout(() => (win.popstate || []).forEach((fn) => fn({ state: entries[at].state })), 0);
  },
};
let narrow = true;
global.matchMedia = () => ({ get matches() { return narrow; } });
const modalOn = {};
const modal = {
  id: "settings-modal", open: false,
  showModal() { this.open = true; },
  close() { if (!this.open) return; this.open = false; (modalOn.close || []).forEach((fn) => fn()); },
  addEventListener: (type, fn) => { (modalOn[type] = modalOn[type] || []).push(fn); },
};
global.document = {
  body: { dataset: {}, tagName: "BODY" },
  addEventListener: (type, fn) => { (handlers[type] = handlers[type] || []).push(fn); },
  getElementById: (id) => (id === "settings-modal" ? modal : null),
  querySelector: () => null,
  querySelectorAll: () => [],
};
document.activeElement = document.body;
eval(source);
const ok = window.oknowledge;
const tick = () => new Promise((r) => setTimeout(r, 5));
function press(key) {
  const event = { key, defaultPrevented: false, isComposing: false, metaKey: false, ctrlKey: false,
                  altKey: false, preventDefault() { this.defaultPrevented = true; } };
  (handlers.keydown || []).forEach((fn) => fn(event));
}
(async () => {
  out.phone = ok.phone();
  // 1. A panel layer: its own entry; back closes it and the URL is the list's.
  const closed = [];
  out.opened = ok.layers.open("panel", (how) => closed.push(how), "/?sel=a1");
  out.urlOpen = entries[at].url;
  out.second = ok.layers.open("settings", () => closed.push("settings"));   // one at a time
  history.back();
  await tick();
  out.afterBack = [closed.slice(), ok.layers.top(), entries[at].url];
  // 2. Ajustes on the phone: ✕ (the dialog's close) goes back once.
  ok.openModal(modal);
  out.settingsPushed = [modal.open, ok.layers.top(), entries.length, at];
  modal.close();
  await ok.layers.settled();
  await tick();
  out.closeWentBack = [ok.layers.top(), at, out.leftSite === true];
  // ... and the browser's back closes the dialog.
  ok.openModal(modal);
  history.back();
  await tick();
  out.backClosedModal = [modal.open, ok.layers.top(), at];
  // 3. A layer the page started with (a reload with sel=): closed in place.
  const adopted = [];
  ok.layers.adopt("panel", (how) => adopted.push(how));
  const where = at;
  await ok.layers.close();
  out.adoptedClose = [adopted, at === where, out.leftSite === true];
  // ... unless the entry is ours (a forward, a reload of our entry): then back.
  ok.layers.open("panel", (how) => closed.push("p:" + how), "/?sel=b2");
  history.back(); await tick();
  history.state;                                   // the list's entry again
  at++;                                            // forward, by hand
  ok.layers.adopt("panel", (how) => closed.push("fwd:" + how));
  await ok.layers.close();
  await tick();
  out.adoptedOwnEntry = [closed[closed.length - 1], at];
  // 4. Esc: a field being typed in is blurred first; the next Esc closes.
  ok.layers.open("panel", (how) => closed.push("esc:" + how), "/?sel=a1");
  document.activeElement = { tagName: "INPUT", type: "text", isContentEditable: false, closest: () => null,
                             blur() { out.blurred = true; document.activeElement = document.body; } };
  press("Escape");
  await tick();
  out.escInField = [out.blurred === true, ok.layers.top()];
  press("Escape");
  await tick();
  out.escClosesLayer = [ok.layers.top(), closed[closed.length - 1]];
  // 5. A desktop: Ajustes makes no entry.
  narrow = false;
  const length = entries.length;
  ok.openModal(modal);
  out.desktop = [modal.open, entries.length === length, ok.layers.top()];
  console.log(JSON.stringify(out));
  process.exit(0);
})();
"""


@pytest.fixture(scope="module")
def layers(tmp_path_factory):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    harness = tmp_path_factory.mktemp("layers") / "harness.js"
    harness.write_text(LAYERS_HARNESS, encoding="utf-8")
    done = subprocess.run([node, str(harness), str(APP)], capture_output=True, text=True,
                          timeout=30, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_the_phone_is_one_breakpoint(layers):
    assert layers["phone"] is True
    assert 'matchMedia("(max-width: 60rem)")' in APP.read_text(encoding="utf-8")


def test_a_layer_has_its_entry_and_back_closes_it(layers):
    assert layers["opened"] is True and layers["urlOpen"] == "/?sel=a1"
    assert layers["afterBack"] == [["back"], "", "/"]


def test_one_layer_at_a_time(layers):
    assert layers["second"] is False


def test_settings_on_the_phone_is_a_layer_closed_by_x_or_back(layers):
    """Review Focus 3: ✕ goes back exactly once, and never off the site."""
    assert layers["settingsPushed"] == [True, "settings", 2, 1]
    assert layers["closeWentBack"] == ["", 0, False]
    assert layers["backClosedModal"] == [False, "", 0]


def test_a_layer_the_page_started_with_closes_in_place(layers):
    assert layers["adoptedClose"] == [["close"], True, False]


def test_a_layer_on_its_own_entry_goes_back_even_when_adopted(layers):
    assert layers["adoptedOwnEntry"] == ["fwd:back", 0]


def test_esc_blurs_a_field_before_it_closes_the_layer(layers):
    assert layers["escInField"] == [True, "panel"]
    assert layers["escClosesLayer"] == ["", "esc:back"]


def test_a_desktop_makes_no_history_for_settings(layers):
    assert layers["desktop"] == [True, True, ""]
```

Check that the file's imports include `json`, `shutil` and `subprocess`, and that `APP` is `app.js`'s path. Add whichever is missing at the top of `tests/test_web_app_js.py`.

Append to `tests/test_web_phone.py`:

```python
# --- Task 8: Ajustes waits for its back before reloading (Ruling 14) --------------------------

def test_a_rename_reloads_only_after_the_layer_has_gone():
    js = static("settings.js")
    head = js.index('modal.addEventListener("close"')
    body = js[head:js.index("});", head)]
    assert "ok.layers ? ok.layers.settled() : Promise.resolve()" in body
    assert "after.then(function () { location.reload(); })" in body
```

- [ ] **Step 2: Run them to see them fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_app_js.py tests/test_web_phone.py`
Expected: FAIL. `ok.phone` is not a function (the harness exits non-zero); the `settings.js` check finds no `settled()`.

- [ ] **Step 3: Implement `app.js`**

Before `// --- keys (spec §4)`:

```js
  // --- the phone (docs/2026-10-15-rediseno-celular-design.md §1, §6.3, §8) -----------
  // One breakpoint for the CSS and every script.
  var narrow = window.matchMedia ? window.matchMedia("(max-width: 60rem)") : null;
  function phone() { return !!(narrow && narrow.matches); }

  // A layer is a screen drawn over the page (the detail, Ajustes) that the
  // browser's back closes. One at a time. `open` gives it a history entry;
  // `adopt` takes one the page started with, which has an entry of its own
  // only if history.state says so (a forward, a reload of our entry).
  var layer = null;          // {name, onClose, pushed}
  var leaving = null;        // a back() under way, as a Promise
  var landed = null;         // ...and its resolve

  function openLayer(name, onClose, url) {
    if (layer) return false;
    history.pushState({ layer: name }, "", url || location.href);
    layer = { name: name, onClose: onClose, pushed: true };
    return true;
  }

  function adoptLayer(name, onClose) {
    if (layer) return false;
    layer = { name: name, onClose: onClose,
              pushed: !!(history.state && history.state.layer === name) };
    return true;
  }

  // The layer on top goes: by back() when it has its entry (popstate below
  // does the rest), else at once, in place. Never off the site.
  function closeLayer() {
    if (!layer) return leaving || Promise.resolve();
    if (layer.pushed && history.state && history.state.layer === layer.name) {
      if (!leaving) leaving = new Promise(function (resolve) { landed = resolve; });
      history.back();
      return leaving;
    }
    var top = layer;
    layer = null;
    top.onClose("close");
    return Promise.resolve();
  }

  window.addEventListener("popstate", function () {
    var top = layer;
    layer = null;
    if (top) top.onClose("back");
    if (landed) { var done = landed; landed = null; leaving = null; done(); }
  });

  // ✕, Esc and a tap on the backdrop close the dialog; on the phone its
  // entry goes with it. Bound now, before settings.js binds its own "close"
  // (which reloads after a rename once this back() has landed, Ruling 14).
  var settingsDialog = document.getElementById("settings-modal");
  if (settingsDialog) settingsDialog.addEventListener("close", function () {
    if (layer && layer.name === "settings") closeLayer();
  });
```

`openModal` becomes:

```js
  function openModal(dialog) {
    if (!dialog || dialog.open) return;
    // On the phone Ajustes is a layer: back closes it (delivery 4, §8). Not
    // over another layer -- the detail covers the top bar anyway.
    if (dialog.id === "settings-modal" && phone() &&
        !openLayer("settings", function () { if (dialog.open) dialog.close(); })) return;
    closeMenus();
    dialog.showModal();
  }
```

`openModal` is declared before the new section. Function declarations are hoisted inside the IIFE, so it may call `phone()` and `openLayer()`. The `var`s they read (`narrow`, `layer`) are set before any click can reach `openModal`.

In the `keydown` listener, the Escape branch becomes:

```js
    if (key === "Escape") {
      // A layer (delivery 4, §6.3): after the modal (which closes itself),
      // before the menus -- and a sheet open over it goes with it. A field
      // being typed in is let go first, so its text saves (Ruling 13).
      if (layer && !typing(active)) { closeMenus(); closeLayer(); return; }
      if (closeMenus()) return;
      if (typing(active)) { active.blur(); return; }
      if (ok.keys.Escape) ok.keys.Escape(event);
      return;
    }
```

With the other exports at the end:

```js
  ok.phone = phone;
  ok.layers = { open: openLayer, adopt: adoptLayer, close: closeLayer,
                top: function () { return layer ? layer.name : ""; },
                settled: function () { return leaving || Promise.resolve(); } };
```

- [ ] **Step 4: Implement `settings.js`**

The modal's `close` listener becomes:

```js
    // A category renamed changes the list and the sidebar under the modal.
    // Closing blurs the box first, so a rename may still be out: the page
    // reloads once it lands -- and, on the phone, once the modal's history
    // entry has gone (app.js goes back first, delivery 4 Ruling 14).
    modal.addEventListener("close", function () {
      var after = ok.layers ? ok.layers.settled() : Promise.resolve();
      if (renamed) { after.then(function () { location.reload(); }); return; }
      if (pendingRename) pendingRename.then(function (landed) {
        if (landed) after.then(function () { location.reload(); });
      });
    });
```

- [ ] **Step 5: Run the tests**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_app_js.py tests/test_web_phone.py tests/test_web_settings_saves.py tests/test_web_settings_tabs.py tests/test_packaging.py`
Expected: PASS. The old harnesses run with the stub. `phone()` is false where they define no `matchMedia`, so nothing they check changes.

- [ ] **Step 6: Check it in a browser**

`$SP/pw/t8.js`:

```js
const { launch, phone, desktop, go } = require("./phone.js");
(async () => {
  const browser = await launch();
  const page = await phone(browser);
  const out = {};
  const len = () => page.evaluate(() => history.length);
  const isOpen = () => page.evaluate(() => document.getElementById("settings-modal").open);
  await go(page, "/ocio");
  await go(page, "/");
  const before = await len();
  await page.tap(".topbar-settings");
  await page.waitForSelector("#settings-modal .settings-body");
  out.opened = [await isOpen(), (await len()) - before];
  await page.evaluate(() => history.back());
  await page.waitForFunction(() => !document.getElementById("settings-modal").open);
  out.back = [new URL(page.url()).pathname, await page.evaluate(() => history.state)];
  await page.tap(".topbar-settings");
  await page.waitForSelector("#settings-modal .settings-body");
  await page.tap("#settings-modal .settings-close");
  await page.waitForFunction(() => !document.getElementById("settings-modal").open);
  await page.waitForTimeout(200);
  out.x = [new URL(page.url()).pathname, await page.evaluate(() => history.state)];
  // One more back leaves for the page before: no dead entry was left.
  await Promise.all([page.waitForURL("**/ocio"), page.evaluate(() => history.back())]);
  out.leaves = new URL(page.url()).pathname;
  const desk = await desktop(browser);
  await go(desk, "/");
  const d0 = await desk.evaluate(() => history.length);
  await desk.click('.sidebar [data-modal="settings"]');
  await desk.waitForSelector("#settings-modal .settings-body");
  out.desktop = (await desk.evaluate(() => history.length)) - d0;
  console.log(JSON.stringify(out));
  await browser.close();
})();
```

Run:

```bash
SP=/tmp/claude-1000/-home-fer-Projects-gym/d89ecc8a-2029-44cb-b47f-742ed00daeae/scratchpad
"$SP/d4/srv.sh" start && (cd "$SP/pw" && node t8.js); "$SP/d4/srv.sh" stop
```

Expected, one line:
`{"opened":[true,1],"back":["/",null],"x":["/",null],"leaves":"/ocio","desktop":0}`

If a value differs, fix `app.js` and run again.

- [ ] **Step 7: Whole suite, commit**

Run the suite; expected green.

```bash
git add src/oknowledge/web/static/app.js src/oknowledge/web/static/settings.js \
        tests/test_web_app_js.py tests/test_web_phone.py
git commit -m "Give the phone one breakpoint and layers that back closes, and make Ajustes one"
```

---
### Task 9: shell.js — a tap opens the detail as a layer, and back closes it

**Files:**
- Modify: `src/oknowledge/web/static/shell.js`:
  - new helpers after `function pick`: `phone`, `isOpen`, `writePick`, `openLayer`, `closedLayer`;
  - `loadPanel` (signature `loadPanel(id, gone, opts)`);
  - `keepShown`;
  - `loadCatalog` / `showCatalog` (a `push` argument);
  - `emptyPanel`;
  - the click listener (`push`, `[data-back]`);
  - the field's submit (the catalogs push);
  - the inline-submit handler (a delete on the phone);
  - `step`;
  - the "pick in the URL" block;
  - a `pointerdown` listener, the load-time adopt and a `popstate` listener at the end of the IIFE;
  - every `history.replaceState(null,` becomes `history.replaceState(history.state,`.
- Test: `tests/test_web_phone.py` (append)
- Create (scratch): `$SP/pw/t9.js`

**Interfaces:**
- Consumes: `ok.phone()`, `ok.layers.open/adopt/close/top` (Task 8); `#panel[data-open]`, `a.detail-back[data-back]` (Task 4); `.detail[aria-busy]` (Task 6).
- Produces:
  - `loadPanel(id: string, gone?: bool, opts?: {push: bool})`;
  - `loadCatalog(q, kind, push?: bool)`.
  - The rule that a shut layer keeps `sel` and `buscar` out of the URL on the phone (`writePick`).
  - `#list.keyed` while keys move the pick.
  - Task 10's capture listener runs before this file's click listener, because it is on `#list` in the capture phase.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_web_phone.py`:

```python
# --- Task 9: the layer in shell.js (spec §6.3, §10) -----------------------------------------

def between(text, start, end):
    head = text.index(start)
    return text[head:text.index(end, head)]


def test_a_tap_opens_the_layer_and_a_key_does_not():
    js = static("shell.js")
    click = between(js, 'document.addEventListener("click"', "// --- remembered layout")
    assert "loadPanel(link.dataset.sel, false, { push: true })" in click
    body = between(js, "function loadPanel", "function loadCatalog")
    assert "opts && opts.push && phone() && !isOpen() && openLayer(url)" in body
    assert 'panel.setAttribute("aria-busy", "true")' in body
    assert 'panel.removeAttribute("aria-busy")' in body
    # j/k (pick), the poller and loadList never push.
    assert re.search(r"function pick\(id\) \{\n[^}]*loadPanel\(id\);", js)


def test_a_shut_layer_keeps_the_pick_out_of_the_url():
    js = static("shell.js")
    assert "if (phone() && !isOpen()) return;" in between(js, "function writePick", "\n  }\n")
    assert "writePick(url)" in between(js, "function keepShown", "\n  }\n")
    assert "if (phone()) return;" in between(js, "// --- the pick in the URL", "observe();")


def test_shell_keeps_the_entry_s_state():
    js = static("shell.js")
    assert "replaceState(null" not in js
    assert "history.replaceState(history.state," in js


def test_back_forward_and_the_way_back_go_through_the_layers():
    js = static("shell.js")
    assert 'ok.layers.open("panel", closedLayer, url.pathname + url.search)' in js
    assert js.count('ok.layers.adopt("panel", closedLayer)') == 2      # on load, and forward
    forward = between(js, 'window.addEventListener("popstate"', "});")
    assert 'event.state.layer !== "panel"' in forward
    click = between(js, 'document.addEventListener("click"', "// --- remembered layout")
    assert 'closest("a[data-back]")' in click and 'ok.layers.top() === "panel"' in click


def test_a_delete_from_the_layer_goes_back_to_the_list_and_opens_nothing():
    handler = between(static("shell.js"), "// --- edits in place", "// --- links being read")
    assert 'deleting && phone() && ok.layers && ok.layers.top() === "panel"' in handler
    assert "ok.offerUndo(answer.notice, answer.undo, function () { ok.list.reload(); });" in handler
    assert 'ok.layers.close().then(function () { loadList(here().href, true, "refresh"); });' in handler


def test_an_empty_panel_does_not_stay_open():
    assert 'if (phone() && isOpen() && ok.layers) ok.layers.close();' in between(
        static("shell.js"), "function emptyPanel", "\n  }\n")


def test_the_catalogs_open_the_layer_too():
    js = static("shell.js")
    assert "push && phone() && !isOpen() && openLayer(url)" in between(js, "function showCatalog", "function emptyPanel")
    submit = between(js, 'form.addEventListener("submit"', "// --- more at the end")
    assert 'loadCatalog(field.value.trim().split(/\\s+/).join(" "), undefined, true)' in submit


def test_keys_draw_the_pick_until_a_finger_touches():
    js = static("shell.js")
    assert 'list.classList.add("keyed")' in between(js, "function step", "\n  }\n")
    assert 'document.addEventListener("pointerdown", function () { list.classList.remove("keyed"); }, true);' in js
```

- [ ] **Step 2: Run them to see them fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_phone.py`
Expected: FAIL. There is no `{ push: true }`, and `replaceState(null` is still there.

- [ ] **Step 3: Implement**

All in `src/oknowledge/web/static/shell.js`.

1. **`replaceState`.** Replace every `history.replaceState(null, "",` with `history.replaceState(history.state, "",`. They are in `loadList`, `keepShown`, `loadPanel`, `showCatalog`, `emptyPanel`, `more` and the "pick in the URL" block. A `replaceState(null, …)` while the layer is open would wipe `{layer: "panel"}` (Ruling 11).

2. **The helpers**, right after `function pick(id) { … }` (before `// --- the list column`):

```js
  // --- the phone's layer (docs/2026-10-15-rediseno-celular-design.md §6.3) ----------
  // app.js owns the breakpoint and the history entries; this opens and
  // shuts the detail over the list.
  function phone() { return !!(ok.phone && ok.phone()); }

  function isOpen() { return !!panel && panel.hasAttribute("data-open"); }

  // Where a pick goes in the URL. On the phone a pick that is not open
  // stays out of it (Ruling 10): a reload, or a back to this entry, would
  // open a layer nobody asked for.
  function writePick(url) {
    if (phone() && !isOpen()) return;
    history.replaceState(history.state, "", url.pathname + url.search);
  }

  // The detail over the list, with an entry of its own at `url`.
  function openLayer(url) {
    if (!panel || !ok.layers || !ok.layers.open("panel", closedLayer, url.pathname + url.search)) return false;
    panel.setAttribute("data-open", "");
    return true;
  }

  // The layer went: by back (the URL is the list's already), or in place
  // (a page that started with sel=: it loses it here, and stays on the site).
  function closedLayer(how) {
    panel.removeAttribute("data-open");
    panel.removeAttribute("aria-busy");
    if (how !== "close") return;
    var url = here();
    ["sel", "buscar", "catalogo", "year"].forEach(function (name) { url.searchParams.delete(name); });
    history.replaceState(history.state, "", url.pathname + url.search);
  }
```

3. **`loadPanel`.** The signature becomes `function loadPanel(id, gone, opts) {`. Its `history.replaceState(…)` line becomes:

```js
    // A tap on the phone opens the layer, with its own entry; anything else
    // (keys, the poller, a list reload) loads the panel and leaves it shut.
    if (opts && opts.push && phone() && !isOpen() && openLayer(url)) panel.setAttribute("aria-busy", "true");
    else writePick(url);
```

In its second `.then(function (html) {`, right after `if (html === STOP || mine !== shownAsked) return;`:

```js
        panel.removeAttribute("aria-busy");
```

In `keepShown`, its `history.replaceState(…)` line becomes `writePick(url);`, and add `panel.removeAttribute("aria-busy");` as its first line.

4. **The catalogs.** `function loadCatalog(q, kind, push) {`, passing it on with `showCatalog(q, kind, mine, push);`. In `showCatalog(q, kind, mine, push)`, its `history.replaceState(…)` line becomes:

```js
    if (push && phone() && !isOpen() && openLayer(url)) panel.setAttribute("aria-busy", "true");
    else writePick(url);
```

In its `.then(function (html) {`, after `if (mine !== shownAsked) return;`, add `panel.removeAttribute("aria-busy");`.

In the field's `submit` listener, the catalog call becomes:

```js
      if (field.value.trim()) loadCatalog(field.value.trim().split(/\s+/).join(" "), undefined, true);
```

5. **`emptyPanel`.** As its second line (after `if (!panel) return;`):

```js
    // Nothing left to read: the phone's layer goes too (Ruling 25).
    if (phone() && isOpen() && ok.layers) ok.layers.close();
```

6. **The click listener.** After the `a[data-kind]` block:

```js
    // "← Biblioteca" over the layer: the browser's back, or a close in place
    // (delivery 4, §6.3). Without a layer it stays a link to the list.
    var back = event.target.closest("a[data-back]");
    if (back && panel && panel.contains(back) && ok.layers && ok.layers.top() === "panel") {
      event.preventDefault();
      ok.layers.close();
      return;
    }
```

And `loadPanel(link.dataset.sel);` becomes `loadPanel(link.dataset.sel, false, { push: true });`.

7. **A delete from the layer.** In the inline-submit handler, right before `if (deleting) {`:

```js
        if (deleting && phone() && ok.layers && ok.layers.top() === "panel") {
          // The phone: back to the list, which no longer has the note
          // (delivery 4, §6.3). Deshacer brings it back to the list and opens
          // nothing. The list reloads once the back has landed (Ruling 24).
          ok.offerUndo(answer.notice, answer.undo, function () { ok.list.reload(); });
          ok.layers.close().then(function () { loadList(here().href, true, "refresh"); });
          return;
        }
```

8. **Keys.** In `step(by)`, first line:

```js
    list.classList.add("keyed");      // the pick is drawn while keys move it (delivery 4, §10)
```

9. **The "pick in the URL" block.** First line inside its IIFE:

```js
    if (phone()) return;            // a shut layer keeps sel out (Ruling 10)
```

10. **The end of the IIFE**, before `observe();`:

```js
  // A finger lets go of the key cursor (delivery 4, §10).
  document.addEventListener("pointerdown", function () { list.classList.remove("keyed"); }, true);

  // A page that starts with the layer open (sel= in the URL, a reload, a
  // shared link, the redirect after saving): it is the layer on top.
  if (isOpen() && phone() && ok.layers) ok.layers.adopt("panel", closedLayer);

  // Forward again into the layer's entry: open it with what the URL names.
  // app.js's popstate runs first and has shut whatever was on top.
  window.addEventListener("popstate", function (event) {
    if (!panel || !phone() || isOpen() || !ok.layers) return;
    if (!event.state || event.state.layer !== "panel") return;
    var url = here();
    var sel = url.searchParams.get("sel");
    var buscar = url.searchParams.get("buscar");
    if (!sel && !buscar) return;
    if (!ok.layers.adopt("panel", closedLayer)) return;
    panel.setAttribute("data-open", "");
    if (sel) loadPanel(sel); else loadCatalog(buscar, url.searchParams.get("catalogo"));
  });
```

`test_no_local_shadows_the_list_helpers` (in `test_web_shell_js.py`) forbids a local named `current` or `shown`, and reading either as a value. The helpers above use neither.

- [ ] **Step 4: Run the tests**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_phone.py tests/test_web_shell_js.py tests/test_web_list_keys.py tests/test_web_leftovers.py tests/test_web_ocio_scripts.py tests/test_packaging.py`
Expected: PASS.

- [ ] **Step 5: Check it at 390×844**

`$SP/pw/t9.js`:

```js
const { launch, phone, go, rect } = require("./phone.js");
(async () => {
  const browser = await launch();
  let page = await phone(browser);
  const out = {};
  const opened = () => page.evaluate(() => document.getElementById("panel").hasAttribute("data-open"));
  const waitOpen = () => page.waitForFunction(() => document.getElementById("panel").hasAttribute("data-open"));
  const waitShut = () => page.waitForFunction(() => !document.getElementById("panel").hasAttribute("data-open"));
  const url = () => { const u = new URL(page.url()); return u.pathname + u.search; };
  const len = () => page.evaluate(() => history.length);
  const back = () => page.evaluate(() => history.back());
  const ids = () => page.$$eval("#items > li.item:not(.pending)", (li) => li.map((x) => x.id.replace(/^card-/, "")));
  await go(page, "/ocio");
  await go(page, "/");
  out.startClosed = [await opened(), new URL(page.url()).searchParams.has("sel")];
  // A tap: the layer covers the screen, the URL has sel, one more entry.
  await page.evaluate(() => { document.getElementById("list-body").scrollTop = 400; });
  const id = await page.evaluate(() => [...document.querySelectorAll("#items > li.item:not(.pending)")]
    .find((li) => li.getBoundingClientRect().top > 250).id.replace(/^card-/, ""));
  const before = await len();
  await page.tap(`#card-${id} a.hit`);
  await page.waitForFunction((id) => document.querySelector(`#panel [data-panel="${id}"]`) &&
    !document.getElementById("panel").hasAttribute("aria-busy"), id);
  out.tapped = [await opened(), await rect(page, "#panel"), new URL(page.url()).searchParams.get("sel") === id,
                (await len()) - before];
  // Back: shut, the list where it was. Forward: open again.
  await back(); await waitShut();
  out.back = [url(), await page.evaluate(() => document.getElementById("list-body").scrollTop)];
  await page.evaluate(() => history.forward()); await waitOpen();
  out.forward = new URL(page.url()).searchParams.get("sel") === id;
  // "← Biblioteca" over a pushed layer: the same as back.
  await page.tap("#panel .detail-back"); await waitShut();
  out.backLink = url();
  // Esc, from a keyboard.
  await page.tap(`#card-${id} a.hit`); await waitOpen();
  await page.keyboard.press("Escape"); await waitShut();
  out.esc = url();
  // j moves the pick without opening, and keeps sel out of the URL.
  await page.keyboard.press("j"); await page.waitForTimeout(400);
  out.j = [await opened(), url()];
  // A reload with sel: open; "← Biblioteca" shuts it in place, on the site.
  await go(page, "/?sel=" + id);
  out.reload = await opened();
  const reloaded = await len();
  await page.tap("#panel .detail-back"); await waitShut();
  out.inPlace = [url(), (await len()) === reloaded, new URL(page.url()).port];
  // Ocio: a poster, then the catalogs.
  await go(page, "/ocio");
  await page.tap("#items > li.item a.hit"); await waitOpen();
  const ocioOpen = await opened();
  await back(); await waitShut();
  out.ocio = [ocioOpen, url()];
  await page.fill("#field-q", "Dune");
  await page.waitForTimeout(400);
  await page.tap("#catalog-search");
  await page.waitForFunction(() => document.querySelector("#panel [data-search]") &&
    document.getElementById("panel").hasAttribute("data-open"));
  out.catalog = [new URL(page.url()).searchParams.get("buscar") === "Dune", await page.$$eval("#panel .candidate", (c) => c.length)];
  await back(); await waitShut();
  out.catalog.push(new URL(page.url()).searchParams.has("buscar"));
  // A delete from the layer's ⋯: back to the list, Deshacer in the toast.
  await go(page, "/");
  const gone = (await ids())[1];
  await page.tap(`#card-${gone} a.hit`); await waitOpen();
  await page.waitForFunction((id) => document.querySelector(`#panel [data-panel="${id}"]`), gone);
  await page.tap("#panel details.menu.more > summary");
  await page.tap("#panel details.menu.more button.danger");
  await waitShut();
  await page.waitForFunction((id) => !document.getElementById("card-" + id), gone);
  out.deleted = [url(), await page.evaluate(() => { const t = document.getElementById("toast"); const r = t.getBoundingClientRect();
    return [!t.hidden, !!t.querySelector("button"), r.left >= 0 && r.right <= innerWidth && r.top >= 0]; })];
  await page.tap("#toast button");
  await page.waitForFunction((id) => !!document.getElementById("card-" + id), gone);
  out.undone = [await opened(), url()];
  // Ajustes, and Review Focus 3: one back per layer, then off to the page before.
  page = await phone(browser);
  await go(page, "/ocio");
  await go(page, "/");
  const isModal = () => page.evaluate(() => document.getElementById("settings-modal").open);
  await page.tap(".topbar-settings");
  await page.waitForSelector("#settings-modal .settings-body");
  out.settings = [await rect(page, "#settings-modal"), await page.$$eval("#settings-modal [data-settings-tab]", (a) => a.length)];
  await page.tap('#settings-modal [data-settings-tab="idioma"]');
  const [saved] = await Promise.all([
    page.waitForResponse((r) => new URL(r.url()).pathname === "/settings" && r.request().method() === "POST"),
    page.tap('#settings-modal label:has(input[name="default_content"][value="summary"])')]);
  out.settings.push(saved.ok());
  await back();
  await page.waitForFunction(() => !document.getElementById("settings-modal").open);
  out.settings.push([new URL(page.url()).pathname, await isModal()]);
  const first = (await ids())[0];
  await page.tap(`#card-${first} a.hit`); await waitOpen();
  await back(); await waitShut();
  const panelAfter = await opened();
  await page.tap(".topbar-settings");
  await page.waitForSelector("#settings-modal .settings-body");
  await back();
  await page.waitForFunction(() => !document.getElementById("settings-modal").open);
  const modalAfter = await isModal();
  const still = new URL(page.url()).pathname;
  await Promise.all([page.waitForURL("**/ocio"), back()]);
  out.backs = [panelAfter, modalAfter, still, new URL(page.url()).pathname];
  console.log(JSON.stringify(out));
  await browser.close();
})();
```

Run:

```bash
SP=/tmp/claude-1000/-home-fer-Projects-gym/d89ecc8a-2029-44cb-b47f-742ed00daeae/scratchpad
"$SP/d4/srv.sh" start && (cd "$SP/pw" && node t9.js); "$SP/d4/srv.sh" stop
```

Expected, one line:
`{"startClosed":[false,false],"tapped":[true,[0,0,390,844],true,1],"back":["/",400],"forward":true,"backLink":"/","esc":"/","j":[false,"/"],"reload":true,"inPlace":["/",true,"8812"],"ocio":[true,"/ocio"],"catalog":[true,3,false],"deleted":["/",[true,true,true]],"undone":[false,"/"],"settings":[[0,0,390,844],4,true,["/",false]],"backs":[false,false,"/","/ocio"]}`

If a value differs, fix `shell.js` (or `app.js`'s layers) and run again. `back` reads the list's own scroll: 400 means the list was not reloaded under the layer.

- [ ] **Step 6: Whole suite, commit**

Run the suite; expected green.

```bash
git add src/oknowledge/web/static/shell.js tests/test_web_phone.py
git commit -m "Open the detail as a layer on a tap, close it with back, and keep a shut pick out of the URL"
```

---
### Task 10: Seleccionar — multi-selection without hover

**Files:**
- Modify: `src/oknowledge/web/templates/list.html`, `ocio-list.html`, `idea-list.html` (a button in `.list-head`)
- Modify: `src/oknowledge/web/static/select.js`:
  - `clear`;
  - the `oknowledge:list` listener;
  - `ok.keys.Escape`;
  - a new mode section and a capture listener on `#list`;
  - `drawMode()` at the end.
- Modify: `src/oknowledge/web/static/app.css`:
  - one line in the delivery-4 section;
  - rules before `} /* end of the phone */`.
- Modify: `src/oknowledge/i18n.py` ("Cancel")
- Test: `tests/test_web_phone.py` (append)
- Test: `tests/test_web_select.py`:
  - append `MODE_HARNESS` and its tests;
  - in `SENDING_HARNESS`, the `list` stub gains `querySelector: () => null` and `contains: () => false` in its `classList` (Ruling 23).
- Create (scratch): `$SP/pw/t10.js`

**Interfaces:**
- Consumes:
  - `#bulk`, the boxes `input[type=checkbox][name=ids]` and `oknowledge:list` (delivery 3's `select.js`);
  - `.menu-list` as a sheet (Task 7);
  - shell.js's click listener on `document` (Task 9), which a capture listener on `#list` runs before.
- Produces:
  - `button.btn.select-mode.js-only[data-select-mode][data-on="Cancel"][aria-pressed]` in every list head;
  - `#list.selecting`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_web_phone.py`:

```python
# --- Task 10: selection without hover (spec §9) -----------------------------------------

BUTTON = ('<button type="button" class="btn select-mode js-only" data-select-mode data-on="Cancel" '
          'aria-pressed="false">Select</button>')


@pytest.mark.parametrize("path", ["/", "/lista", "/?vista=lista", "/ocio", "/ocio/lista", "/ideas",
                                  "/ideas/lista"])
def test_every_list_head_offers_seleccionar(client, path):
    head = re.search(r'<div class="list-head">.*?<div class="list-body"', client.get(path).text, re.S).group(0)
    assert BUTTON in head
    # Left of the layout switch or the sort.
    assert head.index(BUTTON) < max(head.find('<nav class="seg"'), head.find('<details class="menu sort"'))


def test_the_checkboxes_wait_for_seleccionar_on_the_phone():
    css = static("app.css")
    assert ".select-mode { display: none; }" in css
    phone = block(css, PHONE)
    assert ".check { display: none; }" in phone
    assert re.search(r"#list\.selecting \.check \{[^}]*display: grid;[^}]*width: 44px; height: 44px;", phone)
    assert "body:has(#list.selecting, #bulk:not([hidden])) .tabbar { display: none; }" in phone
    bar = re.search(r"\n  \.bulk \{[^}]*\}", phone).group(0)
    for part in ("position: fixed;", "left: 8px;", "right: 8px;",
                 "bottom: max(8px, env(safe-area-inset-bottom));", "transform: none;"):
        assert part in bar, part
```

In `tests/test_web_select.py`, in `SENDING_HARNESS`, the `list` line becomes:

```js
const list = { addEventListener: on("list"), querySelectorAll: () => boxes, querySelector: () => null,
               classList: { toggle() {}, contains: () => false } };
```

Append to `tests/test_web_select.py`:

```python
# --- delivery 4: the phone's selection mode, in node --------------------------------------

MODE_HARNESS = r"""
const source = require("fs").readFileSync(process.argv[2], "utf8");
const out = {};
const listeners = {};
const on = (name) => (type, fn) => { (listeners[name + ":" + type] = listeners[name + ":" + type] || []).push(fn); };
const classes = new Set();
const classList = {
  toggle(c, force) { const want = force === undefined ? !classes.has(c) : !!force; if (want) classes.add(c); else classes.delete(c); return want; },
  contains: (c) => classes.has(c), add: (c) => classes.add(c), remove: (c) => classes.delete(c),
};
const button = { dataset: { on: "Cancelar" }, textContent: "Seleccionar", attrs: {},
                 setAttribute(k, v) { this.attrs[k] = v; },
                 closest: (sel) => (sel === "[data-select-mode]" ? button : null) };
function item(id) {
  const li = { classList: { toggle() {} }, querySelector: () => box };
  const box = { value: id, checked: false, matches: () => true, closest: () => li };
  const hit = { closest: (sel) => (sel === "a.hit" ? hit : sel === "li.item" ? li : null) };
  return { box, li, hit };
}
const a = item("a1"), b = item("b2");
const pending = { closest: (sel) => (sel === "a.hit" ? pending : sel === "li.item" ? { querySelector: () => null } : null) };
const bar = { hidden: true, dataset: { one: "1", many: "%1" }, elements: { back: { value: "" } },
              addEventListener: on("bar"), getAttribute: () => "/bulk/category",
              querySelector: (sel) => (sel === "[data-count]" ? { textContent: "" } : null),
              querySelectorAll: () => [], classList: { toggle() {} } };
const list = { addEventListener: on("list"), querySelectorAll: () => [a.box, b.box],
               querySelector: (sel) => (sel === "[data-select-mode]" ? button : null), classList };
global.window = global;
global.location = { pathname: "/", search: "" };
global.document = { getElementById: (id) => ({ bulk: bar, list: list }[id] || null) };
window.oknowledge = { keys: {}, closeMenus() {}, toast() {}, list: { current: () => "", shown: () => [] } };
eval(source);
const ok = window.oknowledge;
function tap(target) {
  const event = { target, defaultPrevented: false, stopped: false,
                  preventDefault() { this.defaultPrevented = true; }, stopPropagation() { this.stopped = true; } };
  (listeners["list:click"] || []).forEach((fn) => fn(event));
  return event;
}
const told = (reason) => listeners["list:oknowledge:list"].forEach((fn) => fn({ detail: { reason } }));
out.drawn = [button.textContent, button.attrs["aria-pressed"]];
out.off = tap(a.hit).defaultPrevented;                       // not selecting: shell.js opens it
tap(button);
out.on = [classes.has("selecting"), button.textContent, button.attrs["aria-pressed"]];
const ticked = tap(a.hit);
out.tapTicks = [ticked.defaultPrevented, ticked.stopped, a.box.checked, bar.hidden];
tap(a.hit);
out.tapAgainUnticks = [a.box.checked, bar.hidden];
const busy = tap(pending);
out.pendingIgnored = [busy.defaultPrevented, a.box.checked, b.box.checked];
tap(b.hit);
ok.keys.Escape();
out.escLeaves = [classes.has("selecting"), b.box.checked, button.textContent, bar.hidden];
tap(button);
out.escEmpty = [ok.keys.Escape() !== false, classes.has("selecting")];
tap(button); tap(a.hit);
told("filter");
out.filterLeaves = [classes.has("selecting"), a.box.checked];
tap(button);
button.textContent = "Seleccionar";                          // the server drew the head again
told("refresh");
out.refreshKeeps = [classes.has("selecting"), button.textContent];
tap(button);
out.cancel = [classes.has("selecting"), button.textContent, button.attrs["aria-pressed"]];
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def mode(tmp_path_factory):
    import json
    import shutil
    import subprocess
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    harness = tmp_path_factory.mktemp("mode") / "harness.js"
    harness.write_text(MODE_HARNESS, encoding="utf-8")
    done = subprocess.run([node, str(harness), str(SELECT)], capture_output=True, text=True,
                          timeout=30, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_the_button_is_drawn_off(mode):
    assert mode["drawn"] == ["Seleccionar", "false"]


def test_seleccionar_turns_the_mode_on(mode):
    assert mode["off"] is False
    assert mode["on"] == [True, "Cancelar", "true"]


def test_a_tap_in_the_mode_ticks_and_never_opens(mode):
    """Review Focus 4: prevented and stopped before shell.js sees it."""
    assert mode["tapTicks"] == [True, True, True, False]
    assert mode["tapAgainUnticks"] == [False, True]
    assert mode["pendingIgnored"] == [True, False, False]


def test_every_way_out_leaves_the_mode_and_clears(mode):
    assert mode["escLeaves"] == [False, False, "Seleccionar", True]
    assert mode["escEmpty"] == [True, False]
    assert mode["filterLeaves"] == [False, False]
    assert mode["cancel"] == [False, "Seleccionar", "false"]


def test_a_refresh_keeps_the_mode_and_redraws_the_new_button(mode):
    assert mode["refreshKeeps"] == [True, "Cancelar"]
```

- [ ] **Step 2: Run them to see them fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_phone.py tests/test_web_select.py`
Expected: FAIL. There is no button, and the harness finds no mode (`out.on` is `[false, "Seleccionar", undefined]`).

- [ ] **Step 3: Implement the markup and the words**

In `list.html` and `idea-list.html`, inside `.list-head` right before `<nav class="seg" …>`; in `ocio-list.html` right before `<details class="menu sort">`:

```html
  <button type="button" class="btn select-mode js-only" data-select-mode data-on="{{ t('Cancel') }}" aria-pressed="false">{{ t('Select') }}</button>
```

`i18n.py`, `STRINGS["es"]`:

```python
        "Cancel": "Cancelar",
```

- [ ] **Step 4: Implement `select.js`**

`clear` becomes:

```js
  // Every way out of a selection (✕, Esc, a new filter, a bulk action that
  // went through, Cancelar) is this one: the phone's mode goes with it.
  function clear() {
    picked = [];
    mode(false);
    draw();
  }
```

After `clear`, the mode:

```js
  // --- the phone's mode (docs/2026-10-15-rediseno-celular-design.md §9) ------------
  // No hover, so no checkbox to find: "Seleccionar" turns each tap on an
  // item into a tick until one of clear()'s ways out.
  function selecting() { return list.classList.contains("selecting"); }

  // The button lives in the list head, which every list reload draws again.
  function drawMode() {
    var button = list.querySelector("[data-select-mode]");
    if (!button) return;
    var on = selecting();
    if (!button.dataset.off) button.dataset.off = button.textContent;
    button.textContent = on ? button.dataset.on : button.dataset.off;
    button.setAttribute("aria-pressed", on ? "true" : "false");
  }

  function mode(on) {
    list.classList.toggle("selecting", on);
    drawMode();
  }

  // On #list, in the capture phase: before shell.js's click on the document,
  // so a tap in the mode ticks and never opens the item.
  list.addEventListener("click", function (event) {
    var target = event.target;
    if (!target || !target.closest) return;
    if (target.closest("[data-select-mode]")) {
      event.preventDefault();
      if (selecting()) clear(); else mode(true);
      return;
    }
    if (!selecting()) return;
    var hit = target.closest("a.hit");
    if (!hit) return;
    event.preventDefault();
    event.stopPropagation();
    var li = hit.closest("li.item");
    var box = li && li.querySelector('input[type="checkbox"][name="ids"]');
    if (box) toggle(box.value, !box.checked);      // one being analysed has none
  }, true);
```

The `oknowledge:list` listener's last line, after `draw();`, adds `drawMode();`.

`ok.keys.Escape` becomes:

```js
  ok.keys.Escape = function () {
    if (!picked.length && !selecting()) return false;
    clear();
  };
```

At the end, after `draw();`:

```js
  drawMode();
```

`clear` calls `mode`, and `mode` is declared after it. Function declarations are hoisted inside the IIFE, so this is fine. Check that `node --check` passes (`test_packaging`).

- [ ] **Step 5: Implement the CSS**

In the delivery-4 section, outside the media blocks:

```css
.select-mode { display: none; }
```

Right before `} /* end of the phone */`:

```css
  /* §9 selection: no checkbox until "Seleccionar"; then each is a 44px zone
     around a 22px box, and a tap ticks (select.js). */
  .select-mode { display: inline-flex; position: relative; margin-left: auto; }
  .select-mode::after { content: ""; position: absolute; inset: -6px 0; }
  .check { display: none; }
  #list.selecting .check { display: grid; opacity: 1; top: 0; left: 0; width: 44px; height: 44px; }
  #list.selecting .check input { width: 22px; height: 22px; }
  .js .rows .hit { padding-left: 10px; }
  .js .rows .sub .dot { left: 10px; }
  .js .idea-shelf .rows .hit { padding-left: 30px; }
  #list.selecting .rows .check { top: 50%; margin-top: -22px; }
  #list.selecting .rows .hit { padding-left: 44px; }
  #list.selecting .rows .sub .dot { left: 44px; }
  .idea-shelf #list.selecting .rows .hit { padding-left: 58px; }
  #list.selecting .poster .chip.kind { left: 48px; }
  /* The bar takes the tabs' place, the whole width (§9). */
  .bulk { position: fixed; left: 8px; right: 8px; bottom: max(8px, env(safe-area-inset-bottom));
    transform: none; width: auto; justify-content: space-between; z-index: 35; }
  .bulk > button, .bulk summary { display: inline-flex; align-items: center; min-height: 44px; }
  .bulk .bulk-clear { min-width: 44px; justify-content: center; }
  .bulk > .bulk-star { font-size: 0; }
  .bulk > .bulk-star::before { content: "★"; font-size: 15px; }
  body:has(#list.selecting, #bulk:not([hidden])) .tabbar { display: none; }
```

- [ ] **Step 6: Run the tests**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_phone.py tests/test_web_select.py tests/test_web_redesign_spanish.py tests/test_i18n.py tests/test_packaging.py`
Expected: PASS.

- [ ] **Step 7: Check it at 390×844**

`$SP/pw/t10.js`:

```js
const { launch, phone, go, noSideScroll, shown, smallest } = require("./phone.js");
(async () => {
  const browser = await launch();
  const page = await phone(browser);
  const out = {};
  const len = () => page.evaluate(() => history.length);
  const text = (sel) => page.evaluate((sel) => document.querySelector(sel).textContent.trim(), sel);
  const opened = () => page.evaluate(() => document.getElementById("panel").hasAttribute("data-open"));
  await go(page, "/");
  out.button = [await shown(page, "[data-select-mode]"), await text("[data-select-mode]"),
                (await smallest(page, "[data-select-mode]")) >= 44];
  out.checksHidden = !(await shown(page, "#items label.check"));
  await page.tap("[data-select-mode]");
  out.mode = [await text("[data-select-mode]"), await shown(page, "#items label.check"),
              (await smallest(page, "#items label.check")) >= 44, await shown(page, ".tabbar")];
  // Review Focus 4: a tap ticks, never opens.
  const ids = await page.$$eval("#items > li.item:not(.pending)", (li) => li.slice(0, 2).map((x) => x.id.replace(/^card-/, "")));
  const before = await len();
  for (const id of ids) await page.tap(`#card-${id} a.hit`);
  await page.waitForTimeout(300);
  out.ticked = [await page.evaluate((ids) => ids.map((id) => document.querySelector(`#card-${id} input[name="ids"]`).checked), ids),
                await opened(), new URL(page.url()).searchParams.has("sel"), (await len()) === before];
  // Review Focus 2: the bar in the tabs' place, inside the screen; a toast above it.
  out.bar = [await shown(page, "#bulk"),
    await page.evaluate(() => { const r = document.getElementById("bulk").getBoundingClientRect();
      return r.left >= 0 && r.right <= innerWidth && r.bottom <= innerHeight; }),
    await shown(page, ".tabbar"),
    (await smallest(page, "#bulk > button:not(.default-submit), #bulk summary")) >= 44, await noSideScroll(page)];
  await page.evaluate(() => window.oknowledge.toast("Un aviso bastante largo para ver si entra en dos renglones sin salirse de la pantalla"));
  out.toastClear = await page.evaluate(() => { const t = document.getElementById("toast").getBoundingClientRect();
    const b = document.getElementById("bulk").getBoundingClientRect();
    return [t.bottom <= b.top, t.left >= 0 && t.right <= innerWidth]; });
  await page.tap("#bulk .bulk-move > summary");
  out.sheet = await page.evaluate(() => { const r = document.querySelector("#bulk .bulk-move > .menu-list").getBoundingClientRect();
    return [Math.round(r.left), Math.round(r.right), Math.round(r.bottom)]; });
  await page.touchscreen.tap(195, 200);
  out.sheetClosed = await page.evaluate(() => !document.querySelector("#bulk .bulk-move").open);
  await page.tap("#bulk .bulk-delete");
  await page.waitForFunction((id) => !document.getElementById("card-" + id), ids[0]);
  out.deleted = [await page.evaluate(() => { const t = document.getElementById("toast"); return !t.hidden && !!t.querySelector("button"); }),
                 await text("[data-select-mode]"), await shown(page, ".tabbar")];
  await page.tap("#toast button");
  await page.waitForFunction((id) => !!document.getElementById("card-" + id), ids[0]);
  out.undone = await opened();
  // Cancelar with nothing ticked: the tabs come back.
  await page.tap("[data-select-mode]");
  out.cancel = [await text("[data-select-mode]"), await shown(page, ".tabbar")];
  await page.tap("[data-select-mode]");
  out.cancel.push(await text("[data-select-mode]"), await shown(page, ".tabbar"));
  // Ideas: a tap in the mode never navigates; a chip leaves the mode.
  await go(page, "/ideas");
  await page.tap("[data-select-mode]");
  await page.tap("#items > li.item a.hit");
  await page.waitForTimeout(400);
  out.ideas = [new URL(page.url()).pathname,
               await page.evaluate(() => document.querySelector('#items > li.item input[name="ids"]').checked)];
  await page.tap(".chip-row .fchip:not(.on)");
  await page.waitForFunction(() => !document.getElementById("list").classList.contains("selecting"));
  out.ideas.push(await text("[data-select-mode]"));
  // Ocio: a tap ticks, the layer stays shut.
  await go(page, "/ocio");
  await page.tap("[data-select-mode]");
  await page.tap("#items > li.item a.hit");
  await page.waitForTimeout(300);
  out.ocio = [await page.evaluate(() => document.querySelector('#items > li.item input[name="ids"]').checked), await opened()];
  console.log(JSON.stringify(out));
  await browser.close();
})();
```

Run:

```bash
SP=/tmp/claude-1000/-home-fer-Projects-gym/d89ecc8a-2029-44cb-b47f-742ed00daeae/scratchpad
"$SP/d4/srv.sh" start && (cd "$SP/pw" && node t10.js); "$SP/d4/srv.sh" stop
```

Expected, one line:
`{"button":[true,"Seleccionar",true],"checksHidden":true,"mode":["Cancelar",true,true,false],"ticked":[[true,true],false,false,true],"bar":[true,true,false,true,true],"toastClear":[true,true],"sheet":[0,390,844],"sheetClosed":true,"deleted":[true,"Seleccionar",true],"undone":false,"cancel":["Cancelar",false,"Seleccionar",true],"ideas":["/ideas",true,"Seleccionar"],"ocio":[true,false]}`

If a value differs, fix `select.js` or the CSS and run again.

- [ ] **Step 8: Whole suite, commit**

Run the suite; expected green.

```bash
git add src/oknowledge/web/templates/list.html src/oknowledge/web/templates/ocio-list.html \
        src/oknowledge/web/templates/idea-list.html src/oknowledge/web/static/select.js \
        src/oknowledge/web/static/app.css src/oknowledge/i18n.py \
        tests/test_web_phone.py tests/test_web_select.py
git commit -m "Select on the phone with a Seleccionar mode, the bar in the tabs' place"
```

---
### Task 11: The desktop has not moved, a desktop with a finger, and the phone without JavaScript

This task owns Review Focus 5.

**Files:**
- Modify: whatever the checks below show is off (`src/oknowledge/web/static/app.css`, a template). No planned production change.
- Test: `tests/test_web_phone.py` (append)
- Create (scratch): `$SP/pw/t11.js`

**Interfaces:**
- Consumes: everything above; `$SP/d4/desk-compare.sh` (Task 1).
- Produces: no new names.

- [ ] **Step 1: Write the test**

Append to `tests/test_web_phone.py`:

```python
# --- Task 11: the desktop (Review Focus 5) ------------------------------------------------

def test_outside_its_media_blocks_delivery_4_only_hides():
    """Every rule of the delivery-4 section that a desktop reads: the parts
    the phone adds are hidden, the ↵ hint keeps its button's width, and a
    custom property nobody above 60rem uses. Anything else is a leak."""
    css = static("app.css")
    section = css[css.index("/* --- delivery 4: the phone"):]
    for head in (PHONE, WIDE, "@media (hover: none) {", "@media (pointer: coarse) {"):
        section = section.replace(block(section, head), "")
    section = re.sub(r"/\*.*?\*/", "", section, flags=re.S)
    rules = {" ".join(rule.split()) for rule in section.split("}") if rule.strip()}
    assert rules == {
        ".topbar, .tabbar { display: none;", ".chip-row { display: none;",
        ".detail-back { display: none;", ".btn:has(> .enter-hint) { gap: 0;",
        ".select-mode { display: none;",
        ":root { --tabbar-h: calc(60px + env(safe-area-inset-bottom));"}
```

- [ ] **Step 2: Run it**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_phone.py::test_outside_its_media_blocks_delivery_4_only_hides`
Expected: PASS if Tasks 2–10 put every phone rule inside the blocks. A failure lists the extra rule: move it into the phone block.

- [ ] **Step 3: The desktop, pixel by pixel**

Run: `"$SP/d4/desk-compare.sh"`
Expected: one JSON object of 18 shots, every value `0`. For a non-zero shot:
1. Open `$SP/d4/desk-base/<shot>.png` and `$SP/d4/desk-head/<shot>.png` side by side.
2. Find the rule or markup that moved.
3. Fix it, and run again.

Do not commit with a non-zero shot. If the only difference is on `saving`, `finding` or `home-sel` (the `↵` buttons), see Ruling 3: stop and report.

- [ ] **Step 4: A desktop with a finger, a desktop without, the phone without JavaScript**

`$SP/pw/t11.js`:

```js
const { launch, phone, desktop, go, rect, shown } = require("./phone.js");
(async () => {
  const browser = await launch();
  const out = {};
  // A wide tablet with a finger (spec §1): the desktop, with nothing hidden behind hover.
  const touch = await desktop(browser, { width: 1280, height: 800, touch: true });
  await go(touch, "/");
  out.touchDesk = [await touch.evaluate(() => getComputedStyle(document.querySelector("#items label.check")).opacity),
    await shown(touch, '.sidebar [data-modal="keys"]'), await shown(touch, ".sidebar"), await shown(touch, ".tabbar")];
  // A desktop: none of the phone's parts, the panel in its column.
  const desk = await desktop(browser);
  await go(desk, "/?sel=l00000000001");
  out.desk = [];
  for (const sel of [".topbar", ".tabbar", ".chip-row", "#panel .detail-back", "[data-select-mode]"]) out.desk.push(await shown(desk, sel));
  out.deskPanel = (await rect(desk, "#panel")).slice(0, 3);
  out.deskKeys = await shown(desk, '.sidebar [data-modal="keys"]');
  // The phone without JavaScript (spec §14).
  const page = await phone(browser, { js: false });
  await go(page, "/");
  out.nojsSelect = await shown(page, "[data-select-mode]");
  const id = await page.$eval("#items > li.item:not(.pending)", (li) => li.id.replace(/^card-/, ""));
  await Promise.all([page.waitForURL(/sel=/), page.tap(`#card-${id} a.hit`)]);
  out.nojsOpen = [await page.evaluate(() => document.getElementById("panel").hasAttribute("data-open")), await rect(page, "#panel")];
  await Promise.all([page.waitForURL((u) => !u.searchParams.has("sel")), page.tap("#panel .detail-back")]);
  out.nojsBack = [new URL(page.url()).pathname, await page.evaluate(() => document.getElementById("panel").hasAttribute("data-open"))];
  await Promise.all([page.waitForURL(/cat=/), page.tap(".chip-row .fchip:has-text('Cocina')")]);
  out.nojsChip = [new URL(page.url()).searchParams.get("cat"),
    await page.evaluate(() => document.querySelector(".chip-row .fchip.on").textContent.trim())];
  await Promise.all([page.waitForURL("**/ideas"), page.tap(".tabbar a[href='/ideas']")]);
  out.nojsTab = new URL(page.url()).pathname;
  console.log(JSON.stringify(out));
  await browser.close();
})();
```

Run:

```bash
SP=/tmp/claude-1000/-home-fer-Projects-gym/d89ecc8a-2029-44cb-b47f-742ed00daeae/scratchpad
"$SP/d4/srv.sh" start && (cd "$SP/pw" && node t11.js); "$SP/d4/srv.sh" stop
```

Expected, one line:
`{"touchDesk":["1",false,true,false],"desk":[false,false,false,false,false],"deskPanel":[960,0,480],"deskKeys":true,"nojsSelect":false,"nojsOpen":[true,[0,0,390,844]],"nojsBack":["/",false],"nojsChip":["Cocina","Cocina"],"nojsTab":"/ideas"}`

`deskPanel` is the panel's column: x = 1440 − 480 and width 480 (`.app.home`'s `216px minmax(0, 1fr) 480px`). If a value differs, fix the CSS or template it names and run Steps 3 and 4 again.

- [ ] **Step 5: Whole suite, commit**

Run the suite; expected green.

```bash
git add tests/test_web_phone.py   # and whatever Steps 3-4 fixed
git commit -m "Pin that the desktop stays as it was, and check the phone without JavaScript"
```

---
### Task 12: The phone in the handoff's words, beside the handoff

**Files:**
- Modify: `tests/test_web_redesign_spanish.py` (append)
- Modify: `src/oknowledge/web/static/app.css`, `src/oknowledge/i18n.py`, only where the screenshots or the words differ
- Create (scratch): `$SP/pw/shots4.js`, `$SP/d4/phone/*.png`, `$SP/d4/phone/handoff-1a.png`

**Interfaces:**
- Consumes: everything above.
- Produces: no new names.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_web_redesign_spanish.py` (its `client` fixture is in Spanish, with `l00000000001` and the card `c00000000001`):

```python
# --- delivery 4 (docs/2026-10-15-rediseno-celular-design.md §15) --------------------------

PHONE = ['<nav class="tabbar" aria-label="Secciones">', ">Biblioteca</a>", ">Ocio</a>",
         ">Ideas</a>", ">Favoritos</a>",
         'class="topbar-settings" data-modal="settings">Ajustes',
         '<nav class="chip-row" aria-label="Filtros">', ">Todo</a>",
         'data-on="Cancelar"', ">Seleccionar</button>"]


@pytest.mark.parametrize("text", PHONE)
def test_the_phone_says_it_as_the_spec_does(client, text):
    assert text in client.get("/").text


def test_the_way_back_says_where_it_goes(client):
    assert 'aria-label="Volver a Biblioteca">← Biblioteca</a>' in client.get("/?sel=l00000000001").text
    assert 'aria-label="Volver a Ocio">← Ocio</a>' in client.get("/ocio?sel=c00000000001").text
```

- [ ] **Step 2: Run them**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_redesign_spanish.py`
Expected: PASS if Tasks 2–10 used the spec's words. A failure names the string: fix its entry in `i18n.py` (the spec's §15 words win) and run again.

- [ ] **Step 3: The screenshots**

`$SP/pw/shots4.js`:

```js
// node shots4.js OUTDIR -- every phone screen at 390×844, and the handoff's
// "1a celular" for comparison.
const { launch, phone, go, IDEA } = require("./phone.js");
const path = require("path");
const OUT = process.argv[2];
(async () => {
  const browser = await launch();
  const page = await phone(browser);
  const shot = (name) => page.screenshot({ path: `${OUT}/${name}.png`, animations: "disabled" });
  for (const [name, p] of [["01-biblioteca", "/"], ["02-lista", "/?vista=lista"], ["03-favoritos", "/?mark=%E2%AD%90"],
      ["04-detalle", "/?sel=l00000000001"], ["05-ocio", "/ocio"], ["06-ficha", "/ocio?sel=o00000000001"],
      ["07-catalogos", "/ocio?buscar=Dune&catalogo=movie"], ["08-ideas", "/ideas"], ["09-idea", "/ideas/" + IDEA()],
      ["10-ajustes-pagina", "/settings"], ["11-importar", "/import"]]) {
    await go(page, p); await shot(name);
  }
  await go(page, "/");
  await page.fill("#field-q", "https://example.com/algo"); await shot("12-pegado");
  await go(page, "/");
  await page.tap(".topbar-settings"); await page.waitForSelector("#settings-modal .settings-body"); await shot("13-ajustes");
  await go(page, "/?sel=l00000000001");
  await page.tap("#panel details.menu.more > summary"); await shot("14-menu");
  await go(page, "/");
  await page.tap("[data-select-mode]");
  for (const id of await page.$$eval("#items > li.item:not(.pending)", (li) => li.slice(0, 2).map((x) => x.id)))
    await page.tap(`#${id} a.hit`);
  await shot("15-seleccion");
  // The handoff's phone, drawn by its own page.
  const handoff = await browser.newPage({ viewport: { width: 1800, height: 1400 } });
  await handoff.goto("file://" + path.resolve("/home/fer/Projects/oknowledge/design_handoff_oknowledge_redesign/oknowledge Rediseño.dc.html"));
  await handoff.waitForTimeout(1500);
  const frame = await handoff.$('[data-screen-label="1a celular"]');
  if (frame) await frame.screenshot({ path: `${OUT}/handoff-1a.png` });
  console.log(JSON.stringify({ handoff: !!frame }));
  await browser.close();
})();
```

Run:

```bash
SP=/tmp/claude-1000/-home-fer-Projects-gym/d89ecc8a-2029-44cb-b47f-742ed00daeae/scratchpad
mkdir -p "$SP/d4/phone"
"$SP/d4/srv.sh" start && (cd "$SP/pw" && node shots4.js "$SP/d4/phone"); "$SP/d4/srv.sh" stop
```

Expected: `{"handoff":true}`, and 15 PNGs plus `handoff-1a.png` in `$SP/d4/phone`. If the handoff page draws nothing (`false`), compare against the numbers in `design_handoff_oknowledge_redesign/README.md` "Responsive (celular…)" and the spec instead.

- [ ] **Step 4: Compare and fix**

Read `01-biblioteca.png` beside `handoff-1a.png`, then every other shot on its own. Check, in this order:
1. **Placement.**
   - Top bar: logo left, Ajustes right.
   - The field, then the chips, then "{filtro} · N" with Seleccionar and Lista | Tarjetas.
   - Two columns of cards, and the four tabs at the bottom.
   - In `04`/`06`/`07`, the layer covers everything, with "← …" on top.
   - In `14`, the sheet comes from the bottom over a darkened page.
   - In `15`, the bar sits where the tabs were.
2. **Sizes.** Field 46px; chips 34px drawn; tabs 12px text; the detail title 22px; the card's title 20px.
3. **Colours.** Use the tokens in Global Constraints.
4. **Words.** As in Step 1.

Fix the CSS inside the phone block and repeat Step 3 until they match. These differences are expected and stay:
- the field's placeholder (spec §15: "Buscá o pegá un link para guardarlo", not the mockup's);
- the rows' subtitle (Ruling 17);
- "Seleccionar" in the list head (spec §9: the mockup has none).

After any CSS change, run `"$SP/d4/desk-compare.sh"` again: every value `0`.

- [ ] **Step 5: Whole suite, commit**

Run the suite; expected green, ≈3019 + this branch's new tests.

```bash
git add tests/test_web_redesign_spanish.py src/oknowledge/web/static/app.css src/oknowledge/i18n.py
git commit -m "Say delivery 4 in the spec's words and match the phone to the handoff"
```

---

## Self-review

- **Spec coverage.**
  - §1 breakpoints → Task 5 (the blocks), Task 8 (`ok.phone()`).
  - §2.1 top bar and tabs → Task 2. §2.2 the frame, page-scrolling pages → Task 5.
  - §3 chips → Task 3 (markup, `setActive`, `sideFilters`, into view) and Task 5 (CSS, taps).
  - §4 field, list head, `↵` → Task 4 (spans), Task 5 (CSS), Task 10 ("Seleccionar").
  - §5 lists → Task 5.
  - §6.1 markup → Task 4. §6.2 the layer → Task 6. §6.3 open / back / Esc / delete / catalogs / `layers` → Tasks 8 and 9.
  - §7 an idea → Task 6.
  - §8 Ajustes as a layer → Tasks 7 (CSS) and 8 (history); Atajos untouched; menus as sheets → Task 7.
  - §9 checkbox, mode, bar, toast → Tasks 5 (`hover: none`), 7 (toast) and 10.
  - §10 keys (`keyed`, `j` without opening, Esc) → Tasks 5 (CSS), 8 (Esc) and 9.
  - §11 old pages → Tasks 5 and 7. §12 viewport, targets, safe areas, sideways scroll → Tasks 1, 5, 6, 7 and 10.
  - §13 `layout.js` → Task 1. §14 without JS → Task 11. §15 words → Tasks 3, 4, 10 and 12. §16 tests → each task's Step 1 and its browser check.
  - Out of scope (PWA, gestures, a tablet layout, the light theme) is untouched.
- **Review Focus.** Each of the five has a named test in its owning task:
  1. `sideScroll` in Tasks 5, 6 and 7, over `l00000000013`, `l00000000014` and `p00000000001`;
  2. `tabsWhileTyping` (Task 5), `bar` and `toastClear` (Task 10), `toast` (Task 7);
  3. the Task 8 harness (`afterBack`, `closeWentBack`, `backClosedModal`, `adoptedClose`, `adoptedOwnEntry`) and Task 9's `backs` and `inPlace`;
  4. the Task 10 harness (`tapTicks`, `pendingIgnored`) and the browser's `ticked`, `ideas` and `ocio`;
  5. `test_outside_its_media_blocks_delivery_4_only_hides` and `desk-compare.sh` (Task 11), run as a guard in Tasks 5, 6 and 7.
- **Names that cross tasks:**
  - `list_url`, `back_to`, `data-open` (4 → 6, 9);
  - `.chip-row` / `.fchip` / `template#chip-filters` (3 → 5);
  - `litChipInView` (3 → 9's file, unchanged);
  - `ok.phone`, `ok.layers.open/adopt/close/top/settled` (8 → 9);
  - `loadPanel(id, gone, opts)`, `loadCatalog(q, kind, push)`, `writePick`, `openLayer`, `closedLayer`, `isOpen` (9);
  - `aria-busy` (6 ↔ 9);
  - `[data-select-mode]`, `#list.selecting`, `drawMode`, `mode` (10);
  - `} /* end of the phone */` (5 → 6, 7, 10);
  - `--tabbar-h` (5);
  - `$SP/pw/phone.js` helpers and `$SP/d4/srv.sh` (1 → all).

  Each is defined where its task's Interfaces says.
- **Ledger.** Every existing test this branch changes is named in the task that changes it:
  - `test_web_layout` (1);
  - `test_web_shell_js::test_a_filter_click_lights_its_row_only_in_its_own_group` (3);
  - `test_web_ideas_list` and `test_web_ocio_catalogs` (4);
  - `test_web_app_js`'s two harnesses (8);
  - `test_web_select`'s `SENDING_HARNESS` (10).

  Task 2 may meet a test that takes the first `href="/settings"` on the page; it says what to do.
- **No placeholders.** Every step has its code or its command, and every browser check prints one JSON line given in full. Two values depend on the seed and the steps say how to confirm them: the sidebar's category order (Task 3) and the Settings tab keys (Task 7).
- **Script order** on a page is unchanged: `layout.js` (head, not deferred), then `app.js`, then `settings.js`, then the page's scripts. `app.js` binds the Settings dialog's `close` before `settings.js` (Ruling 14). Its `popstate` is registered before `shell.js`'s, so a back shuts the layer before `shell.js` looks for a forward (Ruling 12).
