# Rediseño, entrega 2 (Ocio e Ideas) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An idea opens on a screen of its own (`/ideas/{id}`: header, AI bar with a scope, text beside tabbed results, a column of links), `/ideas` becomes a full-width list, and `/ocio` becomes the three-column shell of the handoff (sidebar TIPO/ESTADO · poster grid · card panel with catalog search), everything autosaving and with no page scroll.

**Architecture:** Server-rendered as in delivery 1. The writes stay the routes of today; a helper `answer()` makes each of them answer `{"ok": …}` to a request with `Accept: application/json` and a 303 to a form. Pure helpers for the two shelves (`IdeaView`, `CardView`, filters, sorting, poster fill) live in a new `web/shelf_view.py`, the section-to-cards parser in `web/markup.py`, and the AI's scope in `idea_actions.py`. Three scripts: `shell.js` (delivery 1, generalised so the ideas list and Ocio reuse it), a new `autosave.js` (debounced saves with one request in flight, JSON posts, toast) and a new `idea.js` (tabs, scope, links column, polling). The old idea and card pages, `popup.js`, `/embed`, `redo.js` and their templates are deleted as soon as nothing reaches them.

**Tech Stack:** Python 3.12, FastAPI + Jinja2, plain JS (no build), pytest + TestClient, `node --check` for JS syntax, Playwright for node driving `/usr/bin/chromium` for behaviour checks and screenshots.

**Spec:** `docs/2026-10-14-rediseno-ocio-ideas-design.md` (binding). Delivery 1: `docs/2026-10-14-rediseno-biblioteca-design.md` and `docs/2026-10-14-rediseno-biblioteca-plan.md` (the shell, tokens and conventions this builds on).
**Visual reference:** `design_handoff_oknowledge_redesign/README.md` section "Pantallas dedicadas (versión final)", `Idea detalle.dc.html`, `Ocio.dc.html` (inline styles of every element: read them when a value is not in this plan), `screenshots/12-ocio.png`, `screenshots/13-idea.png` (60 %).

## Global Constraints

- Code, Python names, commits and docstrings in English. Every UI string goes through `t()`; its Spanish goes into `src/oknowledge/i18n.py` `STRINGS["es"]` **in the same task that adds the string** (voseo, the handoff's words verbatim — spec §5). `tests/test_i18n.py::test_every_string_a_template_asks_for_has_a_spanish_translation` and `::test_every_translated_string_is_one_the_code_asks_for` run in every suite: a task that deletes a template also deletes the entries nothing asks for any more.
- No `|safe` and no `autoescape` in templates (`tests/test_web_read.py::test_no_template_marks_note_content_safe`). `Markup` built in Python (`web/markup.py`) is the only HTML that reaches a page unescaped.
- Never `datetime.datetime.utcnow()` / `utcfromtimestamp()`; use `datetime.datetime.now(datetime.timezone.utc)` (`app.py` imports it as `dt`).
- Commit messages in English, with no `Co-Authored-By`, `Claude-Session` or "Generated with" lines.
- Suite: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider` from `/home/fer/Projects/oknowledge` (≈2 min, **2520 passing** before this branch). Redirect the output to a file and read its tail. Every task ends with the whole suite green.
- Dark only, the handoff's tokens (already on `:root` in `style.css` since delivery 1): surfaces `--s1 #17181d` … `--s7 #2a2c34`, borders `--b-div #22232a`, `--b-card #24252b`, `--b-input #2a2b32`, `--b-menu #33353e`, `--b-sel #565a6a`, text `--t1 #e7e7ea` … `--t7 #55575f`, `--acc #a9b4de`, `--fav #d9b54a`, `--danger #e59a8f`, primary = bg `#e7e7ea` + text `#141519`, `--shadow`. New in this delivery, verbatim from the handoff: state dots Vista/hecha `#8fc29a`, Viendo/en marcha `#a9b4de`, Por ver/semilla `#6d6f78`; AI buttons bg `#1f2026`, border `#2e3038`, radius 9; AI bar bg `#17181d`; dashed suggestion border `#2a2b32`; chip on a poster bg `#141519cc`; selected poster border 2px `#e7e7ea`; unselected stars `#33353e`. Poster fill without a cover: `linear-gradient(160deg, oklch(0.42 0.06 H), oklch(0.18 0.03 H))` with H = Películas 300, Series 200, Anime 20, Libros 60 (`Ocio.dc.html`).
- No page scroll: every redesigned screen is `height: 100vh` with `grid-template-rows: minmax(0, 1fr)`; only inner columns scroll. Grids: ideas list `216px minmax(0,1fr)`; an idea `216px minmax(0,1fr) 400px`; Ocio `216px minmax(0,1fr) 460px` (the sidebar stays 216, spec §1).
- No Save button, no 💾 and no "Editar etiquetas" in the redesigned screens. Without JavaScript each form keeps a Save button marked `data-nojs`; `autosave.js` hides every `[data-nojs]`.
- Timings: autosave 1000 ms after the last key or on blur; live search 250 ms; polling 3000 ms; list chunk 60 (`library_view.CHUNK`).
- Tests never reach the network (conftest refuses it) and never run a model: catalogs are stubbed with the `fake_catalog` pattern of `tests/test_web_ocio_search.py`, the AI with `monkeypatch.setattr("oknowledge.web.app.run_idea_action", …)`, `"oknowledge.web.app.complete_idea"`, `"oknowledge.web.app.describe"` or `acts.ai.ask_with_chain`.
- Live checks only on a scratch vault under the session scratchpad (`SP=/tmp/claude-1000/-home-fer-Projects-gym/d89ecc8a-2029-44cb-b47f-742ed00daeae/scratchpad`; `$SP/shots/serve.py` from delivery 1 seeds links, cards and ideas and serves on 127.0.0.1:8812). Never the user's vault or config. Browser checks use Playwright for node in `$SP/pw` (`cd "$SP/pw" && [ -d node_modules/playwright ] || npm install --no-save --silent playwright`) launched with `executablePath: "/usr/bin/chromium"`. Kill servers by PID after checking the command line.

## Review Focus

1. **Autosave racing a second edit.** Typing, a save in flight, then more typing: the newer text must be the one left on disk and in the field, never overwritten by the older reply — one request in flight per field, the newest value sent when it returns. Pinned in Task 6 (script test plus a browser check).
2. **An `alcance` nobody defined, or `vinculados` with no link left.** An unknown value reads the linked links; linked links that are all gone from the library mean no links block and no "Con N links" line, not an error. Pinned in Task 2.
3. **An idea deleted while its screen polls.** `/item/{id}/actions/state` answers a JSON 404 and the script stops polling and goes to `/ideas?notice=no-such-idea` instead of polling for ever or showing "Listo". Pinned in Task 2 (route) and Task 6 (script).
4. **An Ocio sort with missing years or scores.** "Año" and "Tus estrellas" put the cards with no year (or a `published` that is not one) and with 0 stars last, newest first among themselves; nothing raises on `published: "s/f"`. Pinned in Task 8.
5. **A card with no cover.** The poster is the kind's gradient with the title on it, no `<img>` and no `/cover` request; a hand-edited `type` nobody knows gets the neutral fill instead of a broken style. Pinned in Task 8.

---
### Task 1: The writes answer JSON, and an idea's title has a route

**Files:**
- Modify: `src/oknowledge/web/app.py` — `NOTICES` (≈84), new `GONE`, `FAILURES`, `wants_json()`, `answer()` after `see_other()` (≈457); `not_found` (≈747); routes `move` (≈1076), `retag` (≈1088), `mine` (≈1103) and its three callers (≈1142–1172), `set_mark` (≈1174), `drop_mention` (≈1200), `collections_of` (≈1324), `join_idea` (≈1343), `leave_idea` (≈1372); new `POST /item/{link_id}/title`
- Modify: `src/oknowledge/vault.py:790-792` (`update_note`: a score of `"0"` clears the stars)
- Modify: `src/oknowledge/pipeline.py:1401-1419` (`retitle_idea`: `text=None` keeps the text)
- Modify: `src/oknowledge/i18n.py`
- Test: `tests/test_web_inline_saves.py` (new), `tests/test_pipeline_idea.py` (append), `tests/test_web_ocio_mine.py:96` (drop `"0"` from the bad scores)

**Interfaces:**
- Produces:
  - `wants_json(request: Request) -> bool` (module level in `app.py`).
  - `answer(request: Request, where: str, notice: str = "", **params) -> Response` — a 303 like `see_other(where, notice=notice, **params)` for a form; for JSON `{"ok": true, "notice": "<the notice in words>"}` (200) or `{"ok": false, "error": "<words>"}` with the status in `FAILURES`.
  - `FAILURES: dict[str, int]`, `GONE = "That is not there any more."` (the JSON 404's error).
  - `POST /item/{link_id}/title` (form field `title`): ideas only (404 otherwise); a blank title answers `title-empty` (400 for JSON) and writes nothing.
  - `update_note(..., score="0")` sets `score = 0`; `retitle_idea(cfg, idea, title, text: str | None, language)` with `text=None` leaving `my_note` alone.

- [ ] **Step 1: Write the failing tests**

`tests/test_web_inline_saves.py`:

```python
"""Saving in place (spec §1): every write the redesigned screens make answers
JSON to a script and the redirect of today to a form."""

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.model import Note
from oknowledge.vault import find_note, note_path, rebuild_indexes, write_note
from oknowledge.web.app import create_app

JSON = {"Accept": "application/json"}
LINK = "aaaaaaaaaaaa"
CARD = "cccccccccccc"


@pytest.fixture
def cfg(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    config = Config(vault=vault)
    write_note(config, Note(id=LINK, url="https://wireguard.com", title="WireGuard",
                            category="Redes", tags=["vpn"], type="article",
                            source="wireguard.com", saved="2026-10-10",
                            summary="Una vpn."), "es")
    card = Note(id=CARD, url="https://imdb.com/title/tt0088247", title="The Terminator",
                category="Películas", tags=["accion"], type="movie", source="imdb.com",
                saved="2026-10-11", summary="Algo pasa.", score=3)
    write_note(config, card, "es", path=note_path(config, card, shelf=config.ocio))
    for shelf in (config.links, config.ocio):
        rebuild_indexes(config, "es", shelf=shelf)
    return config


@pytest.fixture
def idea(cfg):
    note = new_idea("Una vpn para la familia.", "VPN propia", "2026-10-12",
                    "2026-10-12T00:00:00.000001+00:00")
    write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ideas))
    rebuild_indexes(cfg, "es", shelf=cfg.ideas)
    return note


@pytest.fixture
def client(cfg):
    return TestClient(create_app(cfg))


def card_now(cfg):
    return find_note(cfg, CARD, shelf=cfg.ocio)[1]


def idea_now(cfg, idea):
    return find_note(cfg, idea.id, shelf=cfg.ideas)[1]


WRITES = [
    (f"/item/{CARD}/mine/state", {"state": "done"}),
    (f"/item/{CARD}/mine/score", {"score": "4"}),
    (f"/item/{CARD}/mine/note", {"my_note": "La vi."}),
    (f"/item/{CARD}/tags", {"tags": "accion", "add": "culto"}),
    (f"/item/{LINK}/category", {"category": "Seguridad"}),
    (f"/item/{LINK}/collections", {"add": "Casa"}),
    (f"/item/{LINK}/mark", {"mark": "⭐"}),
]


@pytest.mark.parametrize("path,data", WRITES)
def test_a_script_gets_json(client, path, data):
    answer = client.post(path, data=data, headers=JSON, follow_redirects=False)
    assert answer.status_code == 200
    assert answer.headers["content-type"] == "application/json"
    assert answer.json()["ok"] is True


@pytest.mark.parametrize("path,data", WRITES)
def test_a_form_still_gets_a_redirect(client, path, data):
    assert client.post(path, data=data, follow_redirects=False).status_code == 303


def test_the_json_says_what_the_page_would_have(client):
    assert client.post(f"/item/{CARD}/mine/state", data={"state": "done"},
                       headers=JSON).json() == {"ok": True, "notice": "Saved."}


def test_the_change_lands_either_way(client, cfg):
    client.post(f"/item/{CARD}/mine/state", data={"state": "doing"}, headers=JSON)
    assert card_now(cfg).state == "doing"


def test_a_refused_write_is_an_error_with_its_reason(client):
    answer = client.post(f"/item/{LINK}/category", data={"category": "a/b"}, headers=JSON)
    assert answer.status_code == 400
    assert answer.json()["ok"] is False
    assert "cannot be used as a category" in answer.json()["error"]


def test_a_note_that_is_not_there_is_a_json_404(client):
    answer = client.post("/item/zzzzzzzzzzzz/mine/state", data={"state": "done"},
                         headers=JSON)
    assert answer.status_code == 404
    assert answer.json() == {"ok": False, "error": "That is not there any more."}


def test_a_page_that_is_not_there_is_still_the_page(client):
    assert "<html" in client.get("/item/zzzzzzzzzzzz").text


def test_a_vault_that_cannot_be_written_is_a_500(client, monkeypatch):
    def broken(*args, **kwargs):
        raise OSError("read-only")
    monkeypatch.setattr("oknowledge.web.app.update_note", broken)
    answer = client.post(f"/item/{CARD}/mine/state", data={"state": "done"}, headers=JSON)
    assert answer.status_code == 500
    assert answer.json()["ok"] is False


def test_the_current_star_again_clears_the_score(client, cfg):
    client.post(f"/item/{CARD}/mine/score", data={"score": "0"}, headers=JSON)
    assert card_now(cfg).score == 0


@pytest.mark.parametrize("bad", ["9", "-1", "cinco", "", "4.5"])
def test_a_score_that_is_not_zero_to_five_writes_nothing(client, cfg, bad):
    client.post(f"/item/{CARD}/mine/score", data={"score": bad})
    assert card_now(cfg).score == 3


def test_adding_and_dropping_a_link_answer_json(client, cfg, idea):
    stem = find_note(cfg, LINK)[0].stem
    added = client.post(f"/item/{LINK}/ideas", data={"idea": idea.id, "back": "idea"},
                        headers=JSON)
    assert added.json()["ok"] is True
    assert idea_now(cfg, idea).related == [stem]
    dropped = client.post(f"/item/{idea.id}/related/drop", data={"stem": stem}, headers=JSON)
    assert dropped.json()["ok"] is True
    assert idea_now(cfg, idea).related == []


def test_a_full_idea_is_a_409_with_the_reason(client, cfg, idea):
    note = idea_now(cfg, idea)
    note.related = [f"2026-01-{n:02d}-x" for n in range(1, 17)]
    write_note(cfg, note, "es", path=find_note(cfg, idea.id, shelf=cfg.ideas)[0])
    answer = client.post(f"/item/{LINK}/ideas", data={"idea": idea.id, "back": "idea"},
                         headers=JSON)
    assert answer.status_code == 409
    assert "16 links" in answer.json()["error"]


# --- the idea's title -------------------------------------------------------

def test_the_title_has_a_route_of_its_own(client, cfg, idea):
    answer = client.post(f"/item/{idea.id}/title", data={"title": "  VPN\nfamiliar "},
                         headers=JSON)
    assert answer.json()["ok"] is True
    after = idea_now(cfg, idea)
    assert (after.title, after.my_note) == ("VPN familiar", "Una vpn para la familia.")


def test_the_title_moves_the_file_like_the_old_form_did(client, cfg, idea):
    client.post(f"/item/{idea.id}/title", data={"title": "Otra cosa"})
    assert find_note(cfg, idea.id, shelf=cfg.ideas)[0].stem == "2026-10-12-otra-cosa"


@pytest.mark.parametrize("empty", ["", "   ", "\n"])
def test_an_empty_title_is_not_saved(client, cfg, idea, empty):
    answer = client.post(f"/item/{idea.id}/title", data={"title": empty}, headers=JSON)
    assert answer.status_code == 400
    assert answer.json()["ok"] is False
    assert idea_now(cfg, idea).title == "VPN propia"


def test_without_a_script_an_empty_title_comes_back_with_the_reason(client, idea):
    answer = client.post(f"/item/{idea.id}/title", data={"title": ""},
                         follow_redirects=False)
    assert answer.status_code == 303
    assert "notice=title-empty" in answer.headers["location"]


def test_only_an_idea_has_this_title_box(client):
    assert client.post(f"/item/{CARD}/title", data={"title": "x"}).status_code == 404


def test_the_text_alone_keeps_the_title(client, cfg, idea):
    client.post(f"/item/{idea.id}/mine/note", data={"my_note": "Texto nuevo."},
                headers=JSON)
    after = idea_now(cfg, idea)
    assert (after.title, after.my_note) == ("VPN propia", "Texto nuevo.")
```

Append to `tests/test_pipeline_idea.py`:

```python
def test_a_title_alone_keeps_the_text(cfg):
    note, _ = put(cfg, title="Mi gym")
    path, trouble = retitle_idea(cfg, note.id, "Gimnasio", None, "es")
    assert trouble is None and path.name == "2026-10-12-gimnasio.md"
    assert now(cfg, note)[1].my_note == "Una app que me arme la rutina."
```

In `tests/test_web_ocio_mine.py:96` change the parametrize to `["9", "-1", "cinco", "", "4.5"]` (spec §2: "clic en la actual = 0" — `"0"` now clears the stars; ledger it).

- [ ] **Step 2: Run them to verify they fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_inline_saves.py tests/test_pipeline_idea.py`
Expected: FAIL — the JSON tests get a 303, `/title` is a 404/405, `"0"` leaves the score at 3, `retitle_idea(..., None, ...)` raises `AttributeError` on `None.strip()`.

- [ ] **Step 3: The answer helper and the JSON 404**

In `app.py`, add to `NOTICES` (after `"no-such-idea"`):

```python
    "title-empty": "Write a title: an empty one is not saved.",
```

After `see_other()` add:

```python
GONE = "That is not there any more."
"""What a script is told when the note it was editing has gone."""

FAILURES = {"bad-category": 400, "bad-mark": 400, "bad-collection": 400,
            "title-empty": 400, "busy": 409, "idea-full": 409,
            "cannot-search": 409, "no-such-idea": 404, "write-failed": 500}
"""The notices that mean nothing was written, and the status each is
answered with when a script asked for JSON. Every other notice landed."""


def wants_json(request: Request) -> bool:
    """A script asking for the answer as data: the redesigned screens save in
    place and need to know how it went, not a page to go to (spec §1)."""
    return "application/json" in request.headers.get("accept", "")


def answer(request: Request, where: str, notice: str = "", **params) -> Response:
    """The answer to a write: a 303 for a form, JSON for a script.

    The JSON carries the notice in words, so the toast says what the page
    would have said after the redirect.
    """
    if not wants_json(request):
        return see_other(where, notice=notice, **params)
    t = translator(ui_language())
    text = NOTICES.get(notice)
    said = t(text, params.get("n", 0), params.get("m", 0)) if text else ""
    status = FAILURES.get(notice)
    if status is not None:
        return JSONResponse({"ok": False, "error": said}, status_code=status)
    return JSONResponse({"ok": True, "notice": said})
```

In `not_found`, before the existing `if`:

```python
        if exc.status_code == 404 and wants_json(request):
            t = translator(ui_language())
            return JSONResponse({"ok": False, "error": t(GONE)}, status_code=404)
```

- [ ] **Step 4: Every inline write goes through `answer()`**

Give each of these routes a `request: Request` first parameter and replace its `see_other(...)` returns with `answer(request, ...)` (same arguments): `move` (both returns), `retag`, `set_mark` (below), `drop_mention`, `collections_of` (both), `join_idea` (all three), `leave_idea`. `mine` becomes `def mine(request: Request, link_id: str, **change)` returning `answer(request, item_url(link_id), result.notice)`; its callers pass `request`:

```python
    @app.post("/item/{link_id}/mine/state")
    def set_state(request: Request, link_id: str, state: str = Form("")):
        return mine(request, link_id, state=state)

    @app.post("/item/{link_id}/mine/score")
    def set_score(request: Request, link_id: str, score: str = Form("")):
        return mine(request, link_id, score=score)
```

and in `set_my_note` (also `request: Request` first): `return mine(request, link_id, my_note=my_note)` and the last line `return answer(request, item_url(link_id), result.notice)`.

`set_mark`'s `to_card` keeps the `#card-` fragment for a form only:

```python
        def to_card(notice: str):
            if wants_json(request):
                return answer(request, home, notice)
            answer_ = see_other(home, notice=notice)
            answer_.headers["location"] += "#card-" + quote(link_id, safe="")
            return answer_
```

- [ ] **Step 5: The title route, the score and the text**

After `set_my_note` add:

```python
    @app.post("/item/{link_id}/title")
    def retitle(request: Request, link_id: str, title: str = Form("")):
        """An idea's name, from the box in its header (spec §2). An empty box
        is not a name: the one on disk stays and the screen keeps what you
        typed. The file moves onto the name the title earns, as before."""
        ideas.refresh()
        if ideas.by_id(link_id) is None:
            raise HTTPException(status_code=404, detail="no such idea")
        if not title.strip():
            return answer(request, item_url(link_id), "title-empty")

        def rename(cfg, language):
            done = retitle_idea(cfg, link_id, title, None, language)
            if done is not None and done[1]:
                log.warning("%s", done[1])
            return done

        result = edit(link_id, rename, "saved", "indexes-stale", shelves=ideas)
        if result.notice == MISSING:
            raise HTTPException(status_code=404, detail="no such idea")
        return answer(request, item_url(link_id), result.notice)
```

In `vault.update_note` replace

```python
    if score is not None:
        picked = _stars(score)
        note.score = picked if picked else note.score
```

with

```python
    if score is not None:
        # "0" is the stars taken off (clicking the one you had, spec §2);
        # anything else that is not one to five leaves them as they were.
        picked = _stars(score)
        if picked or str(score).strip() == "0":
            note.score = picked
```

In `pipeline.retitle_idea`, type the parameter `text: str | None` and replace `note.my_note = text.strip()` with:

```python
    if text is not None:
        note.my_note = text.strip()
```

and add to its docstring: "A text of None keeps the one on disk: the title box saves on its own."

Add to `STRINGS["es"]`:

| key | es |
|---|---|
| Write a title: an empty one is not saved. | Escribí un título: uno vacío no se guarda. |
| That is not there any more. | Eso ya no está. |

- [ ] **Step 6: Run the tests**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_inline_saves.py tests/test_pipeline_idea.py tests/test_web_ocio_mine.py`
Expected: PASS.

- [ ] **Step 7: Whole suite, commit**

Run the suite. Expected: green (no route changed what it answers to a form).

```bash
git add src/oknowledge/web/app.py src/oknowledge/vault.py src/oknowledge/pipeline.py \
        src/oknowledge/i18n.py tests/test_web_inline_saves.py tests/test_pipeline_idea.py \
        tests/test_web_ocio_mine.py
git commit -m "Answer the inline writes with JSON when a script asks, and give an idea's title its own route"
```

---
### Task 2: The AI's scope, and what is running on an idea

**Files:**
- Modify: `src/oknowledge/idea_actions.py` — `SCOPES`, `MAX_SCOPED`, `candidates()` (≈190) gains `keep_linked`, new `in_common()`, `may_serve()`, `scoped_links()`; `compose()` (≈276) takes `scope` instead of `use`
- Modify: `src/oknowledge/pipeline.py:1435-1461` (`run_idea_action(..., scope=...)` instead of `use`)
- Modify: `src/oknowledge/web/app.py` — `act()` (≈1406), `ask_about_idea()` (≈1419), new `complete()` beside `act()`, new `GET /item/{link_id}/actions/state`, `rewrite_card()` (≈1121) and `save_the_idea()` (≈1950) start `complete()` through `working`
- Test: `tests/test_idea_actions.py` (append; rewrite the two `use=` tests), `tests/test_web_idea_actions.py` (the `ran` fixture, the `use`/`with_links`/`category` tests, append)

**Interfaces:**
- Consumes: `answer()`, `wants_json()` (Task 1).
- Produces:
  - `idea_actions.SCOPES = ("vinculados", "todos", "nada")`, `MAX_SCOPED = 6`.
  - `candidates(note, entries, category, keep_linked: bool = False) -> list[tuple[Path, Note]]`.
  - `in_common(note: Note, link: Note) -> bool` — a word of 4+ letters (`_bag`) or a tag shared.
  - `may_serve(note, entries, keep_linked=False, limit=MAX_SCOPED) -> list[tuple[Path, Note]]` — `candidates()` ranking, only links `in_common`, at most `limit`. Task 4 uses it for PUEDEN SERVIR with `entries = [(e.path, e.note) for e in reversed(library.entries)]`.
  - `scoped_links(cfg, note, scope: str) -> list[Note]`.
  - `compose(cfg, note, action, category, day, scope: str = "vinculados")`; `run_idea_action(cfg, idea, action, category="", trace=None, scope="vinculados")`.
  - `POST /item/{id}/actions/{action}` reads `alcance` only (no `category`, `with_links`, `use`); the `links` action runs over the whole library.
  - `GET /item/{id}/actions/state` → `{"running": [sorted names], "failed": [sorted names], "title": str}`; a missing idea → 404 `{"ok": false, "running": [], "failed": [], "title": ""}`. `"complete"` is the name of the title-and-summary run (`complete_idea`) in `working`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_idea_actions.py`, replace `test_compose_uses_the_chosen_links_and_says_so` and `test_compose_without_use_is_as_before` (the `use` parameter is gone, spec §2.1) with:

```python
# --- the scope of improve and expand (spec 2.1) ------------------------------

def test_linked_reads_every_linked_link_in_the_ideas_order(vault_cfg, asked):
    a = stored(vault_cfg, full_link(1, "WireGuard", "Una vpn."))
    b = stored(vault_cfg, full_link(2, "Tailscale", "Otra vpn."))
    text, _, _ = acts.compose(vault_cfg, idea(related=[b, a]), "expand", "", "2026-10-14",
                              scope="vinculados")
    assert asked[0].index("Otra vpn.") < asked[0].index("Una vpn.")
    assert text == "*Con 2 links: Tailscale · WireGuard.*\n\n- Modo offline"


def test_linked_is_the_default(vault_cfg, asked):
    a = stored(vault_cfg, full_link(1, "WireGuard", "Una vpn."))
    acts.compose(vault_cfg, idea(related=[a]), "expand", "", "2026-10-14")
    assert "Una vpn." in asked[0]


@pytest.mark.parametrize("scope", ["", "cualquiera", "VINCULADOS", "todo"])
def test_an_unknown_scope_is_linked(vault_cfg, asked, scope):
    a = stored(vault_cfg, full_link(1, "WireGuard", "Una vpn."))
    stored(vault_cfg, full_link(2, "Rutina de gimnasio", "Rutina para el gimnasio."))
    acts.compose(vault_cfg, idea(related=[a]), "expand", "", "2026-10-14", scope=scope)
    assert "Una vpn." in asked[0]
    assert "Rutina para el gimnasio." not in asked[0]


def test_linked_with_none_left_in_the_library_reads_no_links(vault_cfg, asked):
    text, _, _ = acts.compose(vault_cfg, idea(related=["2026-01-01-borrado"]), "expand", "",
                              "2026-10-14", scope="vinculados")
    assert "### " not in asked[0]
    assert text == "- Modo offline"


def test_only_my_text_reads_no_links_even_when_there_are(vault_cfg, asked):
    a = stored(vault_cfg, full_link(1, "WireGuard", "Una vpn."))
    text, _, _ = acts.compose(vault_cfg, idea(related=[a]), "expand", "", "2026-10-14",
                              scope="nada")
    assert "Una vpn." not in asked[0]
    assert text == "- Modo offline"


def test_the_whole_library_reads_the_six_closest_with_something_in_common(vault_cfg, asked):
    for n in range(1, 9):
        stored(vault_cfg, full_link(n, f"Rutina de gimnasio {n}", "Rutina para el gimnasio."))
    stored(vault_cfg, Note(id="000000000099", url="https://e.com/99", title="Pan casero",
                           category="Cocina", tags=[], type="article", source="e.com",
                           saved="2026-09-01", summary="Masa madre."))
    text, _, _ = acts.compose(vault_cfg, idea(), "expand", "", "2026-10-14", scope="todos")
    assert asked[0].count("### ") == 6
    assert "Masa madre." not in asked[0]
    assert text.startswith("*Con 6 links:")


def test_the_whole_library_includes_the_linked_ones(vault_cfg, asked):
    a = stored(vault_cfg, full_link(1, "Rutina de gimnasio", "Rutina para el gimnasio."))
    acts.compose(vault_cfg, idea(related=[a]), "expand", "", "2026-10-14", scope="todos")
    assert "Rutina para el gimnasio." in asked[0]


def test_already_out_there_ignores_the_scope(cfg, engine):
    from oknowledge.vault import write_note as put_link
    put_link(cfg, link(1, "Rutina de gimnasio", summary="Rutina para el gimnasio.")[1], "es")
    engine.reply = json.dumps({"verdict": "new", "matches": []})
    acts.compose(cfg, idea(), "exists", "", "2026-10-12", scope="todos")
    assert "Rutina para el gimnasio." not in engine.calls[0][1]


# --- what may help, without a model ------------------------------------------

def test_a_tag_in_common_is_something_in_common():
    note = idea(tags=["vpn"])
    path, other = link(1, "Algo", summary="nada que ver", tags=["vpn"])
    assert acts.in_common(note, other)
    assert not acts.in_common(idea(tags=["otra"]), other)


def test_may_serve_keeps_six_with_something_in_common_and_drops_the_linked():
    entries = [link(n, f"Rutina {n}", summary="gimnasio") for n in range(1, 9)]
    entries.append(link(9, "Recetas", summary="pan"))
    note = idea(related=[entries[0][0].stem])
    served = acts.may_serve(note, entries)
    assert len(served) == 6
    assert entries[0] not in served
    assert all(n.title != "Recetas" for _, n in served)


def test_may_serve_with_nothing_in_common_is_empty():
    assert acts.may_serve(idea(), [link(1, "Recetas", summary="pan casero")]) == []
```

In `tests/test_web_idea_actions.py`, replace the `ran` fixture with:

```python
@pytest.fixture
def ran(monkeypatch):
    calls = []
    outcome = {"problem": None}

    def run(cfg, idea, action, category="", trace=None, scope="vinculados"):
        calls.append((idea, action, category))
        outcome["scope"] = scope
        return outcome["problem"]

    monkeypatch.setattr("oknowledge.web.app.run_idea_action", run)
    return calls, outcome
```

replace `test_links_carries_the_category` with:

```python
def test_the_category_does_nothing_any_more(cfg, ran):
    a_link(cfg)
    note = put(cfg)
    TestClient(create_app(cfg)).post(f"/item/{note.id}/actions/links",
                                     data={"category": "Redes"})
    assert ran[0] == [(note.id, "links", "")]
```

delete the three tests that post `with_links`/`use` (≈360–377) and append:

```python
# --- the scope (spec 2.1) ------------------------------------------------------

@pytest.mark.parametrize("sent,used", [({}, "vinculados"), ({"alcance": "todos"}, "todos"),
                                        ({"alcance": "nada"}, "nada"),
                                        ({"alcance": "x"}, "vinculados")])
def test_the_scope_goes_to_the_action(cfg, ran, sent, used):
    note = put(cfg)
    TestClient(create_app(cfg)).post(f"/item/{note.id}/actions/improve", data=sent)
    assert ran[1]["scope"] == used


def test_the_old_link_boxes_do_nothing(cfg, ran):
    note = put(cfg)
    TestClient(create_app(cfg)).post(f"/item/{note.id}/actions/expand",
                                     data={"with_links": "1", "use": ["a"]})
    assert ran[1]["scope"] == "vinculados"


def test_a_script_is_told_in_json(cfg, ran):
    note = put(cfg)
    answer = TestClient(create_app(cfg)).post(f"/item/{note.id}/actions/improve",
                                              headers={"Accept": "application/json"})
    assert answer.json()["ok"] is True


def test_exists_without_a_searcher_is_a_409_for_a_script(tmp_path, ran):
    cfg = make(tmp_path, chain=("ollama",))
    note = put(cfg)
    answer = TestClient(create_app(cfg)).post(f"/item/{note.id}/actions/exists",
                                              headers={"Accept": "application/json"})
    assert answer.status_code == 409


# --- what is running (spec 2.2) --------------------------------------------------

def test_the_state_with_nothing_running(cfg):
    note = put(cfg)
    answer = TestClient(create_app(cfg)).get(f"/item/{note.id}/actions/state")
    assert answer.json() == {"running": [], "failed": [], "title": "VPN propia"}


def test_the_state_while_an_action_runs_and_after_one_failed(cfg):
    note = put(cfg)
    app = create_app(cfg)
    app.state.working.start(note.id, "improve")
    app.state.working.start(note.id, "expand")
    app.state.working.finish(note.id, "expand", "the model did not answer")
    assert TestClient(app).get(f"/item/{note.id}/actions/state").json() == {
        "running": ["improve"], "failed": ["expand"], "title": "VPN propia"}


def test_the_state_of_an_idea_that_is_gone_is_a_404(cfg):
    answer = TestClient(create_app(cfg)).get("/item/nope/actions/state")
    assert answer.status_code == 404
    assert answer.json()["ok"] is False and answer.json()["running"] == []


def test_naming_an_idea_is_watched_like_an_action(cfg, monkeypatch):
    seen = []
    monkeypatch.setattr("oknowledge.web.app.complete_idea",
                        lambda cfg, idea, trace=None: seen.append(idea) or True)
    app = create_app(cfg)
    client = TestClient(app)
    client.post("/ideas/guardar", data={"text": "Una idea."})
    assert len(seen) == 1
    assert app.state.working.of(seen[0]) == (set(), {})       # finished, and well


def test_a_naming_that_fails_is_remembered(cfg, monkeypatch):
    monkeypatch.setattr("oknowledge.web.app.complete_idea",
                        lambda cfg, idea, trace=None: False)
    note = put(cfg)
    app = create_app(cfg)
    TestClient(app).post(f"/item/{note.id}/describe")
    assert set(app.state.working.of(note.id)[1]) == {"complete"}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_idea_actions.py tests/test_web_idea_actions.py`
Expected: FAIL — `compose()` has no `scope`, no `in_common`/`may_serve`, the route still reads `category`, `/actions/state` is a 405.

- [ ] **Step 3: The scope in `idea_actions.py`**

After `MAX_LINK_POINT` add:

```python
SCOPES = ("vinculados", "todos", "nada")
"""Which links improve and expand read (spec 2.1): the idea's own, the
library's closest, or none. The first is the default and what any other
value means."""

MAX_SCOPED = 6
"""Links read from the whole library, and links offered beside an idea."""
```

Change `candidates()`:

```python
def candidates(note: Note, entries: list[tuple[Path, Note]],
               category: str, keep_linked: bool = False) -> list[tuple[Path, Note]]:
    """The links offered to the model: in the category (any, if none), not
    already linked to the idea unless `keep_linked`, most words in common
    with it first, newest first among equals."""
    mine = _bag(" ".join([note.title, note.my_note, " ".join(note.tags)]))
    pool = [(path, link) for path, link in reversed(entries)
            if (not category or link.category == category)
            and (keep_linked or path.stem not in note.related)]
```

(the rest of the body unchanged), and after it add:

```python
def in_common(note: Note, link: Note) -> bool:
    """A word of four letters or more, or a tag, that the two share."""
    mine = _bag(" ".join([note.title, note.my_note, " ".join(note.tags)]))
    theirs = _bag(" ".join([link.title, link.summary, " ".join(link.tags)]))
    return bool(mine & theirs) or bool(set(note.tags) & set(link.tags))


def may_serve(note: Note, entries: list[tuple[Path, Note]], keep_linked: bool = False,
              limit: int = MAX_SCOPED) -> list[tuple[Path, Note]]:
    """The links closest to the idea that have something in common with it,
    ranked by candidates(), without asking anybody (spec §2, PUEDEN SERVIR)."""
    return [pair for pair in candidates(note, entries, "", keep_linked)
            if in_common(note, pair[1])][:limit]


def scoped_links(cfg: Config, note: Note, scope: str) -> list[Note]:
    """The links improve and expand read under this scope. An unknown scope
    is the linked links; linked links that are all gone are no links."""
    if scope == "nada":
        return []
    if scope == "todos":
        return [link for _, link in may_serve(note, all_entries(cfg, cfg.links),
                                              keep_linked=True)]
    return chosen_links(cfg, note, note.related)
```

In `compose()`: signature `def compose(cfg: Config, note: Note, action: str, category: str, day: str, scope: str = "vinculados") -> tuple[str, str, str]:`, the docstring's last sentence becomes "`scope` says which links improve and expand read (SCOPES).", and `picked = chosen_links(cfg, note, use)` becomes `picked = scoped_links(cfg, note, scope)`. Drop the now-unused `Iterable` import only if nothing else uses it (`chosen_links` still does).

In `pipeline.run_idea_action`: parameter `scope: str = "vinculados"` instead of `use: Sequence[str] = ()`, and the call `compose_action(cfg, found[1], action, category, today(), scope=scope)`. Remove `Sequence` from the `collections.abc` import if nothing else uses it.

- [ ] **Step 4: The route, the naming and the state**

In `app.py`, import `SCOPES` (`from ..idea_actions import SCOPES`). Replace `act()` and `ask_about_idea()` with:

```python
    def act(live: Config, idea: str, action: str, scope: str) -> None:
        """The background half of an action: run it, then say how it ended."""
        problem: str | None = "it stopped before it could say why"
        try:
            problem = run_idea_action(live, idea, action, "", trace=progress.note,
                                      scope=scope)
        except Exception as error:        # a background task has nowhere to raise to
            problem = str(error) or type(error).__name__
        finally:
            working.finish(idea, action, problem)

    def complete(live: Config, idea: str) -> None:
        """The background half of naming an idea: its title, tags, summary and
        points. Watched under "complete" like an action, so the screen can
        wait for the title (spec 2.2)."""
        problem: str | None = "it stopped before it could say why"
        try:
            problem = (None if complete_idea(live, idea, trace=progress.note)
                       else "the model did not answer")
        except Exception as error:        # a background task has nowhere to raise to
            problem = str(error) or type(error).__name__
        finally:
            working.finish(idea, "complete", problem)

    @app.post("/item/{link_id}/actions/{action}")
    def ask_about_idea(request: Request, background: BackgroundTasks, link_id: str,
                       action: str, alcance: str = Form("")):
        """One of the actions on an idea, behind the page.

        `alcance` says which links improve and expand read (spec 2.1); the
        old `category`, `with_links` and `use` are not read any more. Already
        out there? needs an engine that searches, and ignores the scope.
        """
        if action not in ACTIONS:
            raise HTTPException(status_code=404, detail="no such action")
        ideas.refresh()
        if ideas.by_id(link_id) is None:
            return answer(request, "/ideas", "no-such-idea")
        live = current["cfg"]
        if action == "exists" and not can_search(live):
            return answer(request, item_url(link_id), "cannot-search")
        scope = alcance if alcance in SCOPES else "vinculados"
        if working.start(link_id, action):
            background.add_task(act, live, link_id, action, scope)
        return answer(request, item_url(link_id), "thinking")

    @app.get("/item/{link_id}/actions/state")
    def idea_state(link_id: str):
        """What is running on an idea and what last failed, for its screen to
        wait on (spec 2.2). In memory: a restart forgets it, as before."""
        ideas.refresh()
        note = ideas.by_id(link_id)
        if note is None:
            return JSONResponse({"ok": False, "running": [], "failed": [], "title": ""},
                                status_code=404)
        running, failed = working.of(link_id)
        return JSONResponse({"running": sorted(running), "failed": sorted(failed),
                             "title": note.title})
```

In `rewrite_card()`, the idea branch becomes (and the route takes `request: Request` first):

```python
        if ideas.by_id(link_id) is not None:
            if working.start(link_id, "complete"):
                background.add_task(complete, current["cfg"], link_id)
            return answer(request, item_url(link_id), "completing")
```

and the card branch's last line `return answer(request, item_url(link_id), "rewriting")`. In `save_the_idea()` replace `background.add_task(complete_idea, live, note.id, trace=progress.note)` with:

```python
        if working.start(note.id, "complete"):
            background.add_task(complete, live, note.id)
```

- [ ] **Step 5: Run the tests**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_idea_actions.py tests/test_web_idea_actions.py tests/test_pipeline_idea_actions.py tests/test_web_ideas_page.py`
Expected: PASS. (`test_pipeline_idea_actions.py` keeps passing: its ideas link nothing that exists, so the default scope reads no links.)

- [ ] **Step 6: Whole suite, commit**

Run the suite. A test that still posts `use`/`with_links` and asserts what the model read (`grep -rn "with_links\|\"use\"" tests/`) is about removed behaviour (spec 2.1): delete it and ledger. The old idea page still draws its boxes until Task 7; they are ignored.

```bash
git add src/oknowledge/idea_actions.py src/oknowledge/pipeline.py src/oknowledge/web/app.py \
        tests/test_idea_actions.py tests/test_web_idea_actions.py
git commit -m "Let the AI's scope pick the links an idea's action reads, and say what is running on it"
```

---
### Task 3: An idea's screen

**Files:**
- Create: `src/oknowledge/web/shelf_view.py`
- Create: `src/oknowledge/web/templates/idea.html`, `idea-results.html`
- Modify: `src/oknowledge/web/markup.py` (append `Section`, `section_cards`)
- Modify: `src/oknowledge/web/app.py` — `ideas_back()` after `local_path()` (≈497); `idea_context()` and `GET /ideas/{idea_id}` after the `/ideas` route (≈1910); the redirects of `ask_about_idea`, `rewrite_card` (idea branch) and `save_the_idea` go to the screen
- Modify: `src/oknowledge/web/static/app.css` (append)
- Modify: `src/oknowledge/i18n.py`
- Test: `tests/test_web_idea_screen.py` (new), `tests/test_markup_cards.py` (new); update the location asserts in `tests/test_web_idea_actions.py` (`test_a_button_queues_its_action_and_says_it_is_thinking`, `test_exists_without_a_searcher_is_refused_up_front`), `tests/test_web_ideas_page.py::test_saving_writes_the_idea_and_queues_the_model` and `tests/test_web_ideas_mine.py::test_asking_again_queues_the_model`

**Interfaces:**
- Consumes: `answer()` (Task 1); `SCOPES`, `/item/{id}/title`, `"complete"` in `working` (Tasks 1–2).
- Produces:
  - `shelf_view`: `IDEA_WORDS`, `IDEA_DOTS`, `TABS` (`(key, label, action)`), `TAB_OF` (action → tab key, `"complete"` → `"resumen"`), `AI_BUTTONS`, `WORKING`, `SECTION_NAMES`, `tab_of(raw) -> str`, `scope_of(raw) -> str`, `excerpt(text, size=60) -> str`, `idea_url(idea_id, **params) -> str` (drops empty values and the defaults `pestana=resumen`, `alcance=vinculados`, `back=/ideas`).
  - `markup.Section` (`used: Markup | None`, `lead`, `cards: list[tuple[Markup, Markup]]`, `tail`) and `section_cards(text) -> Section`.
  - `ideas_back(raw: str) -> str` (module level in `app.py`): a `local_path` that is `/ideas` or `/ideas?…`, else `/ideas`.
  - `idea_context(note, pestana, alcance, back, q) -> dict` (closure) with keys `note, tab, scope, back, q, url, running, failed, searchable, linked_now, placeholder, sections` plus the constants. Task 4 adds the column's keys to it.
  - DOM hooks for Task 6: `#idea[data-id]`, `#save-state[data-saving][data-saved]`, `#idea-title[data-autosave][data-skip-empty]`, `#idea-text[data-autosave]`, `#idea-controls`, `#idea-tags`, `#idea-ai[data-running][data-done-as][data-failed-as][data-name-*]`, `#idea-working`, `a[data-tab]`, `[data-pane]`, `a[data-scope]`, `form[data-json]` (with `data-runs="<action>"` on the AI forms and the regenerate form), `#idea-results`, `[data-nojs]`.

- [ ] **Step 1: Write the failing tests**

`tests/test_markup_cards.py`:

```python
"""An action's section as the idea's screen draws it: cards, not a list."""

from oknowledge.web.markup import section_cards


def test_improvements_are_title_and_detail_under_the_links_line():
    part = section_cards("*Con 2 links: A · B.*\n\n- **Débil** — el arreglo.\n- **Otra** — otro.")
    assert str(part.used) == "Con 2 links: A · B."
    assert [(str(a), str(b)) for a, b in part.cards] == [("Débil", "el arreglo."), ("Otra", "otro.")]
    assert part.lead == [] and part.tail == []


def test_a_finding_keeps_its_link_and_the_lines_around_it():
    part = section_cards("**Ya existe.** Buscado el 2026-10-13 con fake.\n\n"
                         "- [Tailscale](https://tailscale.com) — VPN sobre WireGuard.\n\n"
                         "**Lo tuyo:** para la familia.")
    assert [str(x) for x in part.lead] == ["<strong>Ya existe.</strong> Buscado el 2026-10-13 con fake."]
    title, detail = part.cards[0]
    assert str(title) == '<a href="https://tailscale.com" target="_blank" rel="noreferrer">Tailscale</a>'
    assert str(detail) == "VPN sobre WireGuard."
    assert [str(x) for x in part.tail] == ["<strong>Lo tuyo:</strong> para la familia."]


def test_an_expansion_point_is_a_card_with_no_detail():
    part = section_cards("- Compartir fotos.\n- Bloquear publicidad.")
    assert [(str(a), str(b)) for a, b in part.cards] == [("Compartir fotos.", ""),
                                                         ("Bloquear publicidad.", "")]


def test_nothing_is_an_empty_section():
    part = section_cards("")
    assert (part.used, part.lead, part.cards, part.tail) == (None, [], [], [])


def test_model_text_is_still_escaped():
    title, _ = section_cards("- <img src=x> — y").cards[0]
    assert "<img" not in str(title)
```

`tests/test_web_idea_screen.py`:

```python
"""An idea's own screen (spec §2): header, the AI bar, the text beside the
results. The column of links is tests/test_web_idea_screen_links.py."""

import re

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.model import Note
from oknowledge.vault import note_path, rebuild_indexes, write_note
from oknowledge.web.app import create_app

IMPROVE = ("*Con 1 link: WireGuard.*\n\n"
           "- **Acceso desde la tele** — usar un router con WireGuard.\n"
           "- **Quién la mantiene** — automatizar las actualizaciones.")


def make(tmp_path, chain=("opencode",)):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True, exist_ok=True)
    cfg = Config(vault=vault, chain=chain)
    rebuild_indexes(cfg, "es")
    return cfg


@pytest.fixture
def cfg(tmp_path):
    return make(tmp_path)


def put(cfg, **fields):
    note = new_idea("Una vpn para la familia, que ande en la tele.", "VPN familiar",
                    "2026-10-13", "2026-10-13T00:00:00.000001+00:00")
    note.summary, note.points = "Una VPN propia para la casa.", ["Para quién es.", "Qué resuelve."]
    note.tags, note.score, note.state = ["vpn", "casa"], 3, "doing"
    note.actions = {"improve": IMPROVE}
    for key, value in fields.items():
        setattr(note, key, value)
    write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ideas))
    return note


def screen(cfg, note, query="", app=None):
    return TestClient(app or create_app(cfg)).get(f"/ideas/{note.id}{query}").text


def part(body, start, end):
    head = body.index(start)
    return body[head:body.index(end, head)]


def bar(body):
    return part(body, 'id="idea-ai"', 'class="idea-body"')


def test_a_missing_idea_is_the_apps_404(cfg):
    answer = TestClient(create_app(cfg)).get("/ideas/000000000000")
    assert answer.status_code == 404
    assert "Not found" in answer.text


def test_three_columns_and_no_page_scroll(cfg):
    body = screen(cfg, put(cfg))
    assert '<div class="app idea-screen">' in body
    assert 'id="idea"' in body and 'class="links-column"' in body


# --- the header ---------------------------------------------------------------

def test_back_to_the_ideas_and_when_it_was_written(cfg):
    body = screen(cfg, put(cfg))
    assert '<a class="back" href="/ideas">← Ideas</a>' in body
    assert "created 13 Oct" in body


def test_back_keeps_the_filter_it_came_from(cfg):
    body = screen(cfg, put(cfg), "?back=/ideas?estado%3Ddoing")
    assert '<a class="back" href="/ideas?estado=doing">' in body


@pytest.mark.parametrize("back", ["//evil.com", "https://evil.com", "/settings", "/ideasx"])
def test_back_never_leaves_the_ideas(cfg, back):
    assert '<a class="back" href="/ideas">' in screen(cfg, put(cfg), "?back=" + back)


def test_the_title_is_a_box_that_saves_itself(cfg):
    note = put(cfg)
    box = re.search(r'<input[^>]*id="idea-title"[^>]*>', screen(cfg, note)).group(0)
    assert 'value="VPN familiar"' in box
    assert f'data-autosave="/item/{note.id}/title"' in box and "data-skip-empty" in box


def test_while_the_model_names_it_the_box_shows_the_start_of_the_text(cfg):
    note = put(cfg, title="")
    app = create_app(cfg)
    app.state.working.start(note.id, "complete")
    box = re.search(r'<input[^>]*id="idea-title"[^>]*>', screen(cfg, note, app=app)).group(0)
    assert 'value=""' in box and "waiting" in box
    assert 'placeholder="Una vpn para la familia, que ande en la tele."' in box


def test_the_state_is_a_segmented_control(cfg):
    note = put(cfg)
    seg = part(screen(cfg, note), f'action="/item/{note.id}/mine/state"', "</form>")
    assert re.findall(r'value="(\w+)"', seg) == ["pending", "doing", "done", "dropped"]
    assert re.search(r'value="doing" class="on"', seg)
    for word in ("seed", "under way", "done", "dropped"):
        assert f">{word}<" in seg


def test_the_current_star_takes_the_stars_off(cfg):
    note = put(cfg)
    stars = part(screen(cfg, note), f'action="/item/{note.id}/mine/score"', "</form>")
    assert re.findall(r'name="score" value="(\d)"', stars) == ["1", "2", "0", "4", "5"]


def test_the_more_menu_regenerates_and_deletes(cfg):
    note = put(cfg)
    body = screen(cfg, note)
    assert f'action="/item/{note.id}/describe"' in body
    assert "Regenerate everything with the AI" in body
    assert f'action="/item/{note.id}/delete"' in body and "Delete idea" in body


def test_the_tags_are_chips_and_a_box(cfg):
    tags = part(screen(cfg, put(cfg)), 'id="idea-tags"', "</div>")
    assert "#vpn" in tags and "#casa" in tags
    assert 'name="add"' in tags and 'placeholder="+ tag"' in tags


def test_no_save_buttons_but_for_a_browser_without_javascript(cfg):
    body = screen(cfg, put(cfg))
    assert "💾" not in body and "Edit tags" not in body
    saves = re.findall(r"<button[^>]*>Save</button>", body)
    assert saves and all("data-nojs" in button for button in saves)


# --- the AI bar ------------------------------------------------------------------

def test_the_ai_bar_has_three_actions_and_the_scope(cfg):
    note = put(cfg)
    ai = bar(screen(cfg, note))
    for action in ("exists", "improve", "expand"):
        assert f'action="/item/{note.id}/actions/{action}"' in ai
    assert ai.count('name="alcance" value="vinculados"') == 3
    for text in ("ASK THE AI", "using", "Linked links (0)", "The whole library", "Only my text"):
        assert text in ai
    assert "links that may help" not in ai.lower()


def test_the_scope_comes_from_the_url(cfg):
    ai = bar(screen(cfg, put(cfg), "?alcance=todos"))
    assert ai.count('name="alcance" value="todos"') == 3
    assert re.search(r'data-scope="todos" class="on"', ai)


def test_an_unknown_scope_is_the_linked_links(cfg):
    assert bar(screen(cfg, put(cfg), "?alcance=x")).count('name="alcance" value="vinculados"') == 3


def test_the_scope_counts_the_linked_links_still_there(cfg):
    stem = write_note(cfg, Note(id="aaaaaaaaaaaa", url="https://wireguard.com",
                                title="WireGuard", category="Redes", tags=[], type="article",
                                source="wireguard.com", saved="2026-10-10",
                                summary="Una vpn."), "es").stem
    rebuild_indexes(cfg, "es")
    assert "Linked links (1)" in screen(cfg, put(cfg, related=[stem, "2026-01-01-borrado"]))


def test_without_a_searcher_already_out_there_is_off_with_the_reason(tmp_path):
    cfg = make(tmp_path, chain=("ollama",))
    ai = bar(screen(cfg, put(cfg)))
    button = re.search(r'actions/exists".*?(<button[^>]*>)', ai, re.S).group(1)
    assert "disabled" in button
    assert 'title="No engine in your chain searches the web' in button


def test_a_running_action_is_off_and_said(cfg):
    note = put(cfg)
    app = create_app(cfg)
    app.state.working.start(note.id, "improve")
    ai = bar(screen(cfg, note, app=app))
    assert 'data-running="improve"' in ai
    assert "disabled" in re.search(r'actions/improve".*?(<button[^>]*>)', ai, re.S).group(1)
    assert "Improvements…" in ai


# --- the body -------------------------------------------------------------------------

def test_your_idea_fills_the_left_and_saves_itself(cfg):
    note = put(cfg)
    body = screen(cfg, note)
    area = re.search(r'<textarea[^>]*id="idea-text"[^>]*>(.*?)</textarea>', body, re.S)
    assert area.group(1) == "Una vpn para la familia, que ande en la tele."
    assert f'data-autosave="/item/{note.id}/mine/note"' in area.group(0)
    assert 'placeholder="Write it however it comes out: the AI puts it in order."' in area.group(0)
    assert "YOUR IDEA" in body and "saves itself" in body


def test_four_tabs_summary_first(cfg):
    body = screen(cfg, put(cfg))
    assert re.findall(r'data-tab="(\w+)"', body) == ["resumen", "existe", "mejoras", "ampliacion"]
    assert re.search(r'data-tab="resumen" class="on"', body)
    assert re.search(r'data-pane="resumen">', body)
    assert 'data-pane="mejoras" hidden>' in body


def test_the_tab_comes_from_the_url(cfg):
    body = screen(cfg, put(cfg), "?pestana=mejoras")
    assert re.search(r'data-pane="mejoras">', body)
    assert 'data-pane="resumen" hidden>' in body


def test_an_unknown_tab_is_the_summary(cfg):
    assert re.search(r'data-pane="resumen">', screen(cfg, put(cfg), "?pestana=zzz"))


def test_the_summary_is_a_paragraph_and_numbered_points(cfg):
    pane = part(screen(cfg, put(cfg)), 'data-pane="resumen"', 'data-pane="existe"')
    assert "Una VPN propia para la casa." in pane
    assert re.search(r'>01</span>\s*<span[^>]*>Para quién es\.', pane)
    assert ">02</span>" in pane


def test_improvements_are_cards_of_title_and_detail_under_the_links_line(cfg):
    pane = part(screen(cfg, put(cfg)), 'data-pane="mejoras"', 'data-pane="ampliacion"')
    assert pane.index("Con 1 link: WireGuard.") < pane.index("Acceso desde la tele")
    assert re.search(r'<div class="result-card">\s*<p class="title">Acceso desde la tele</p>\s*'
                     r'<p class="detail">usar un router con WireGuard\.</p>', pane)
    assert pane.count('class="result-card"') == 2


def test_already_out_there_draws_each_finding_as_a_card(cfg):
    found = ("**Hay parecidas.** Buscado el 2026-10-13 con fake.\n\n"
             "- [Tailscale](https://tailscale.com) — VPN sobre WireGuard.\n\n"
             "**Lo tuyo:** es para la familia.")
    pane = part(screen(cfg, put(cfg, actions={"exists": found})), 'data-pane="existe"',
                'data-pane="mejoras"')
    assert "Hay parecidas." in pane and "es para la familia." in pane
    assert '<a href="https://tailscale.com" target="_blank" rel="noreferrer">Tailscale</a>' in pane


def test_an_empty_tab_offers_to_ask(cfg):
    note = put(cfg)
    pane = part(screen(cfg, note), 'data-pane="ampliacion"', "</section>")
    assert "You have not asked yet." in pane
    assert f'action="/item/{note.id}/actions/expand"' in pane
    assert 'class="btn primary"' in pane


def test_a_summary_not_written_yet_offers_to_regenerate(cfg):
    note = put(cfg, summary="", points=[])
    pane = part(screen(cfg, note), 'data-pane="resumen"', 'data-pane="existe"')
    assert "You have not asked yet." in pane
    assert f'action="/item/{note.id}/describe"' in pane


def test_the_last_failure_is_said_in_its_tab(cfg):
    note = put(cfg)
    app = create_app(cfg)
    app.state.working.start(note.id, "expand")
    app.state.working.finish(note.id, "expand", "the model did not answer")
    pane = part(screen(cfg, note, app=app), 'data-pane="ampliacion"', "</section>")
    assert "Last time it failed: the model did not answer" in pane


# --- back to the screen without JavaScript ---------------------------------------------

def test_an_action_comes_back_to_its_tab(cfg, monkeypatch):
    monkeypatch.setattr("oknowledge.web.app.run_idea_action", lambda *a, **k: None)
    note = put(cfg)
    answer = TestClient(create_app(cfg)).post(f"/item/{note.id}/actions/improve",
                                              data={"alcance": "todos"}, follow_redirects=False)
    assert answer.headers["location"] == (
        f"/ideas/{note.id}?pestana=mejoras&alcance=todos&notice=thinking")


def test_regenerating_comes_back_to_the_screen(cfg, monkeypatch):
    monkeypatch.setattr("oknowledge.web.app.complete_idea", lambda cfg, idea, trace=None: True)
    note = put(cfg)
    answer = TestClient(create_app(cfg)).post(f"/item/{note.id}/describe",
                                              follow_redirects=False)
    assert answer.headers["location"] == f"/ideas/{note.id}?notice=completing"


def test_the_notice_is_a_toast(cfg):
    assert 'class="notice toast"' in screen(cfg, put(cfg), "?notice=thinking")
```

Update the four location asserts listed under **Files** to `/ideas/{note.id}?pestana=mejoras&notice=thinking` (improve), `/ideas/{note.id}?pestana=existe&notice=cannot-search`, `/ideas/{idea.id}?notice=completing` (`test_web_ideas_page`) and `/ideas/{note.id}?notice=completing` (`test_web_ideas_mine`).

- [ ] **Step 2: Run them to verify they fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_markup_cards.py tests/test_web_idea_screen.py`
Expected: FAIL — `ImportError: section_cards`, and `/ideas/{id}` is a 404.

- [ ] **Step 3: The pure parts**

`src/oknowledge/web/shelf_view.py`:

```python
"""Ocio and the ideas as one URL describes them, and the words and colours
they are drawn with (docs/2026-10-14-rediseno-ocio-ideas-design.md). Pure:
no request, no disk -- what the routes and templates in app.py need,
testable on its own, like library_view."""

from __future__ import annotations

from urllib.parse import quote, urlencode

from ..idea_actions import SCOPES
from ..vault import IDEA_STATES

IDEA_WORDS = {"pending": "seed", "doing": "under way", "done": "done", "dropped": "dropped"}
"""An idea's four states, in its own words: an idea is had, worked on, made,
or let go."""
IDEA_DOTS = {"pending": "#6d6f78", "doing": "#a9b4de", "done": "#8fc29a",
             "dropped": "#55575f"}
"""The handoff's three state colours (spec §1); a dropped idea is the
dimmest grey there is."""

TABS = (("resumen", "Summary", ""), ("existe", "Already out there?", "exists"),
        ("mejoras", "Improvements", "improve"), ("ampliacion", "Expansion", "expand"))
"""An idea's results: the key in the URL (`pestana=`), the label, and the
action that fills it -- "" for the summary, which naming the idea fills."""
TAB_OF = {action: key for key, _, action in TABS if action}
TAB_OF["complete"] = "resumen"

AI_BUTTONS = (("exists", "Already out there?"), ("improve", "Improve"), ("expand", "Expand"))
WORKING = {"exists": "Searching…", "improve": "Improvements…", "expand": "Expansion…",
           "complete": "Regenerating…"}
SECTION_NAMES = {"exists": "Already out there?", "improve": "Improvements",
                 "expand": "Expansion", "complete": "Summary"}
"""What "Listo: {sección}" names when each run ends (spec 2.2)."""

_DEFAULTS = {"pestana": "resumen", "alcance": "vinculados", "back": "/ideas"}


def tab_of(raw: str) -> str:
    return raw if raw in {key for key, _, _ in TABS} else "resumen"


def scope_of(raw: str) -> str:
    return raw if raw in SCOPES else "vinculados"


def excerpt(text: str, size: int = 60) -> str:
    """The start of an idea's text, for its title box while the model names it."""
    flat = " ".join((text or "").split())
    return flat if len(flat) <= size else flat[:size].rstrip() + "…"


def idea_url(idea_id: str, **params) -> str:
    """An idea's screen, with the parameters that are not their default."""
    pairs = [(k, str(v)) for k, v in params.items() if v and v != _DEFAULTS.get(k)]
    query = urlencode(pairs)
    return "/ideas/" + quote(idea_id, safe="") + ("?" + query if query else "")
```

Append to `src/oknowledge/web/markup.py` (add `from dataclasses import dataclass, field` to the imports):

```python
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
```

- [ ] **Step 4: The route**

In `app.py` import `from .shelf_view import (AI_BUTTONS, IDEA_WORDS, SECTION_NAMES, TAB_OF, TABS, WORKING, excerpt, idea_url, scope_of, tab_of)` (`IDEA_STATES` keeps coming from `..vault`, as today) and `from .markup import blocks, section_cards, split_suggestions`. After `local_path()` add:

```python
def ideas_back(raw: str) -> str:
    """Where "← Ideas" goes: the list as it was when the idea was opened
    (spec §2), and never anywhere but the list."""
    path = local_path(raw)
    return path if path and (path == "/ideas" or path.startswith("/ideas?")) else "/ideas"
```

After the `/ideas` route add:

```python
    def idea_context(note, pestana: str, alcance: str, back: str, q: str) -> dict:
        """What an idea's screen shows (spec §2)."""
        tab, scope, home = tab_of(pestana), scope_of(alcance), ideas_back(back)
        running, failed = working.of(note.id)
        library.refresh()
        present = {entry.path.stem for entry in library.entries}
        params = {"pestana": tab, "alcance": scope, "back": home, "q": q}
        return {
            "note": note, "tab": tab, "scope": scope, "back": home, "q": q,
            "url": lambda **changes: idea_url(note.id, **{**params, **changes}),
            "running": running, "failed": failed,
            "searchable": can_search(current["cfg"]),
            "linked_now": sum(1 for stem in note.related if stem in present),
            # While the model names a new idea, the box shows the start of
            # its text, dimmed, and the screen's poll fills the name in.
            "placeholder": (excerpt(note.my_note)
                            if "complete" in running and not note.title.strip() else ""),
            "sections": {action: section_cards(note.actions.get(action, ""))
                         for action in ("exists", "improve", "expand")},
            "IDEA_STATES": IDEA_STATES, "IDEA_WORDS": IDEA_WORDS, "TABS": TABS,
            "AI_BUTTONS": AI_BUTTONS, "WORKING": WORKING, "SECTION_NAMES": SECTION_NAMES,
        }

    @app.get("/ideas/{idea_id}", response_class=HTMLResponse)
    def idea_screen(request: Request, idea_id: str, pestana: str = "", alcance: str = "",
                    back: str = "", q: str = ""):
        """One idea on a screen of its own. One that is not there is the app's 404."""
        ideas.refresh()
        entry = ideas.entry(idea_id)
        if entry is None:
            raise HTTPException(status_code=404, detail="no such idea")
        return page(request, "idea.html", section="ideas", toast=True,
                    **idea_context(read_full(entry), pestana, alcance, back, q))
```

In `ask_about_idea` the two answers that name the idea become:

```python
        if action == "exists" and not can_search(live):
            return answer(request, idea_url(link_id, pestana="existe"), "cannot-search")
        scope = alcance if alcance in SCOPES else "vinculados"
        if working.start(link_id, action):
            background.add_task(act, live, link_id, action, scope)
        return answer(request, idea_url(link_id, pestana=TAB_OF.get(action, ""), alcance=scope),
                      "thinking")
```

In `rewrite_card`'s idea branch: `return answer(request, idea_url(link_id), "completing")`. In `save_the_idea` the last line: `return see_other(idea_url(note.id), notice=notice)`.

- [ ] **Step 5: The templates**

`src/oknowledge/web/templates/idea.html`:

```jinja
{% extends "base.html" %}
{% block title %}{{ note.title or t('Untitled idea') }} - oknowledge{% endblock %}
{% block app_class %}idea-screen{% endblock %}
{% block layout %}
<section class="idea-main" id="idea" data-id="{{ note.id }}" aria-label="{{ t('Ideas') }}">
  <header class="idea-head">
    <div class="idea-meta-row">
      <a class="back" href="{{ back }}">← {{ t('Ideas') }}</a><span>·</span>
      <span>{{ t('created %1', note.saved|short_date(t)) }}</span>
      <span class="save-state" id="save-state" aria-live="polite"
            data-saving="{{ t('Saving…') }}" data-saved="{{ t('Saved') }}"></span>
    </div>
    <div class="idea-title-row">
      <form method="post" action="/item/{{ note.id|slug }}/title" class="idea-title">
        <input name="title" id="idea-title" value="{{ note.title }}" autocomplete="off"
               class="{% if placeholder %}waiting{% endif %}"
               aria-label="{{ t('Title') }}" placeholder="{{ placeholder or t('Untitled idea') }}"
               data-autosave="/item/{{ note.id|slug }}/title" data-skip-empty data-indicator="#save-state">
        <button class="btn" data-nojs>{{ t('Save') }}</button>
      </form>
      <div class="idea-controls" id="idea-controls">
        <form method="post" action="/item/{{ note.id|slug }}/mine/state" class="seg" data-json>
          {% for state in IDEA_STATES %}<button name="state" value="{{ state }}" class="{% if note.state == state %}on{% endif %}">{{ t(IDEA_WORDS[state]) }}</button>{% endfor %}
        </form>
        <form method="post" action="/item/{{ note.id|slug }}/mine/score" class="stars" data-json>
          {% for n in range(1, 6) %}<button name="score" value="{{ 0 if n == note.score else n }}" class="{% if n <= note.score %}on{% endif %}" title="{{ n }}/5" aria-label="{{ n }}/5">{% include "icon-star.html" %}</button>{% endfor %}
        </form>
        <details class="menu more">
          <summary class="btn icon framed" aria-label="{{ t('More') }}" title="{{ t('More') }}">⋯</summary>
          <div class="menu-list">
            <form method="post" action="/item/{{ note.id|slug }}/describe" data-json data-runs="complete">
              <button>{{ t('Regenerate everything with the AI') }}</button>
            </form>
            <form method="post" action="/item/{{ note.id|slug }}/delete" data-ask="{{ t('Move this idea to the trash folder?') }}">
              <button class="danger" onclick="return confirm(this.form.dataset.ask)">{{ t('Delete idea') }}</button>
            </form>
          </div>
        </details>
      </div>
    </div>
    <div class="chips tags" id="idea-tags">
      {% for tag in note.tags %}
        <form method="post" action="/item/{{ note.id|slug }}/tags" class="chip" data-json>
          <span>#{{ tag }}</span>
          <input type="hidden" name="tags" value="{{ note.tags|reject('equalto', tag)|join(' ') }}">
          <button aria-label="{{ t('Remove the tag %1', tag) }}" title="{{ t('Remove the tag %1', tag) }}">✕</button>
        </form>
      {% endfor %}
      <form method="post" action="/item/{{ note.id|slug }}/tags" class="tag-new" data-json>
        <input type="hidden" name="tags" value="{{ note.tags|join(' ') }}">
        <input name="add" required autocomplete="off" aria-label="{{ t('+ tag') }}" placeholder="{{ t('+ tag') }}">
      </form>
    </div>
  </header>
  <div class="idea-ai" id="idea-ai" data-running="{{ running|sort|join(' ') }}"
       data-done-as="{{ t('Done: %1') }}" data-failed-as="{{ t('Failed: %1') }}"
       {% for action, name in SECTION_NAMES.items() %}data-name-{{ action }}="{{ t(name) }}" {% endfor %}>
    <span class="label">{{ t('ASK THE AI') }}</span>
    {% for action, label in AI_BUTTONS %}
      {% set blocked = action == 'exists' and not searchable %}
      <form method="post" action="/item/{{ note.id|slug }}/actions/{{ action }}" data-json data-runs="{{ action }}">
        <input type="hidden" name="alcance" value="{{ scope }}">
        <button class="ai-btn"{% if action in running or blocked %} disabled{% endif %}{% if blocked %} title="{{ t('No engine in your chain searches the web: opencode or the Anthropic API do.') }}"{% endif %}>{{ t(label) }}</button>
      </form>
    {% endfor %}
    <span class="using">{{ t('using') }}</span>
    <details class="menu scope">
      <summary class="btn">{% if scope == 'todos' %}{{ t('The whole library') }}{% elif scope == 'nada' %}{{ t('Only my text') }}{% else %}{{ t('Linked links (%1)', linked_now) }}{% endif %} ▾</summary>
      <div class="menu-list">
        {% for key in ('vinculados', 'todos', 'nada') %}
          <a href="{{ url(alcance=key) }}" data-scope="{{ key }}" class="{% if key == scope %}on{% endif %}">
            <span>{% if key == 'todos' %}{{ t('The whole library') }}{% elif key == 'nada' %}{{ t('Only my text') }}{% else %}{{ t('Linked links (%1)', linked_now) }}{% endif %}</span>
            <span>{% if key == scope %}✓{% endif %}</span></a>
        {% endfor %}
      </div>
    </details>
    <span class="working" id="idea-working">{% for action in running|sort %}{{ t(WORKING.get(action, '')) }} {% endfor %}</span>
  </div>
  <div class="idea-body">
    <section class="idea-text">
      <p class="label"><span>{{ t('YOUR IDEA') }}</span><span>{{ t('saves itself') }}</span></p>
      <form method="post" action="/item/{{ note.id|slug }}/mine/note">
        <textarea name="my_note" id="idea-text" aria-label="{{ t('Your idea') }}"
                  placeholder="{{ t('Write it however it comes out: the AI puts it in order.') }}"
                  data-autosave="/item/{{ note.id|slug }}/mine/note" data-indicator="#save-state">{{ note.my_note }}</textarea>
        <button class="btn" data-nojs>{{ t('Save') }}</button>
      </form>
    </section>
    <section class="idea-results" id="idea-results" aria-label="{{ t('Results') }}">
      {% include "idea-results.html" %}
    </section>
  </div>
</section>
<aside class="links-column" aria-label="{{ t('Links of this idea') }}">
  <div class="links-head">
    <p class="links-title"><span>{{ t('Links of this idea') }}</span><b class="mono" id="idea-links-count">{{ note.related|length }}</b></p>
  </div>
</aside>
{% endblock %}
```

`src/oknowledge/web/templates/idea-results.html`:

```jinja
<nav class="tabs" aria-label="{{ t('Results') }}">
  {% for key, label, action in TABS %}<a href="{{ url(pestana=key) }}" data-tab="{{ key }}" class="{% if key == tab %}on{% endif %}">{{ t(label) }}</a>{% endfor %}
</nav>
{% for key, label, action in TABS %}
<div class="tab-pane" data-pane="{{ key }}"{% if key != tab %} hidden{% endif %}>
  {% if not action %}
    {% if note.summary or note.points %}
      {% for para in note.summary|paragraphs %}<p class="lead" dir="auto">{{ para }}</p>{% endfor %}
      {% if note.points %}
        <ol class="numbered">
          {% for point in note.points %}<li><span class="n mono">{{ '%02d'|format(loop.index) }}</span> <span dir="auto">{{ point }}</span></li>{% endfor %}
        </ol>
      {% endif %}
    {% else %}
      <div class="tab-empty">
        <p>{{ t('You have not asked yet.') }}</p>
        <form method="post" action="/item/{{ note.id|slug }}/describe" data-json data-runs="complete">
          <button class="btn primary"{% if 'complete' in running %} disabled{% endif %}>{{ t('Regenerate everything with the AI') }}</button>
        </form>
      </div>
    {% endif %}
  {% else %}
    {% set part = sections[action] %}
    {% if part.used or part.lead or part.cards or part.tail %}
      {% if part.used %}<p class="used">{{ part.used }}</p>{% endif %}
      {% for line in part.lead %}<p class="lead">{{ line }}</p>{% endfor %}
      {% for title, detail in part.cards %}
        <div class="result-card">
          <p class="title">{{ title }}</p>
          {% if detail %}<p class="detail">{{ detail }}</p>{% endif %}
        </div>
      {% endfor %}
      {% for line in part.tail %}<p class="tail">{{ line }}</p>{% endfor %}
    {% else %}
      <div class="tab-empty">
        <p>{{ t('You have not asked yet.') }}</p>
        <form method="post" action="/item/{{ note.id|slug }}/actions/{{ action }}" data-json data-runs="{{ action }}">
          <input type="hidden" name="alcance" value="{{ scope }}">
          {% for one, label in AI_BUTTONS if one == action %}
            <button class="btn primary"{% if action in running or (action == 'exists' and not searchable) %} disabled{% endif %}>{{ t(label) }}</button>
          {% endfor %}
        </form>
      </div>
    {% endif %}
    {% if failed.get(action) %}<p class="failed">{{ t('Last time it failed: %1', failed[action]) }}</p>{% endif %}
  {% endif %}
</div>
{% endfor %}
```

- [ ] **Step 6: Style the screen**

Append to `app.css` (values from the handoff's "Ideas" section and `Idea detalle.dc.html`; class names chosen so no rule of `style.css` matches them — `.idea-links`, `.tabs` and `.mine` there belong to the old page until Task 7):

```css
/* --- an idea's screen (spec §2, Idea detalle.dc.html) -------------------- */
.app.idea-screen { grid-template-columns: 216px minmax(0, 1fr) 400px; overflow: hidden;
  line-height: normal; }
.idea-main { display: flex; flex-direction: column; min-width: 0; min-height: 0; }
.idea-head { padding: 20px 40px 16px; border-bottom: 1px solid var(--b-div);
  display: flex; flex-direction: column; gap: 12px; }
.idea-meta-row { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--t5); }
.idea-meta-row .back { color: var(--acc); text-decoration: none; }
.save-state { margin-left: auto; color: var(--t6); }
.idea-title-row { display: flex; align-items: flex-start; gap: 20px; }
.idea-title { flex: 1; min-width: 0; display: flex; gap: 8px; margin: 0; }
.idea-title input { flex: 1; min-width: 0; background: transparent; border: 0; outline: 0;
  padding: 0; color: var(--t1); font: inherit; font-size: 28px; font-weight: 600;
  letter-spacing: -.02em; }
.idea-title input.waiting::placeholder { color: var(--t6); }
.idea-controls { display: flex; align-items: center; gap: 12px; padding-top: 4px; }
.seg button { background: none; border: 0; padding: 5px 10px; border-radius: 6px; font: inherit;
  font-size: 12.5px; color: var(--t5); cursor: pointer; white-space: nowrap; }
.seg button.on { background: var(--s7); color: var(--t1); }
.stars { display: flex; margin: 0; }
.stars button { background: none; border: 0; padding: 0 1px; cursor: pointer; color: #33353e;
  font-size: 17px; line-height: 1; }
.stars button.on { color: var(--fav); }
.btn.framed { background: none; border-color: var(--b-input); color: var(--t5); font-size: 16px; }
.idea-head .chip { background: var(--s4); color: var(--t4); }
.idea-head .tag-new input { width: 100px; }
.idea-ai { display: flex; align-items: center; gap: 8px; padding: 12px 40px; background: #17181d;
  border-bottom: 1px solid var(--b-div); }
.idea-ai form { display: contents; }
.idea-ai .label { font-size: 12px; color: var(--t6); letter-spacing: .06em; margin: 0 4px 0 0; }
.ai-btn { padding: 7px 14px; border-radius: 9px; border: 1px solid #2e3038; background: #1f2026;
  color: var(--t1); font: inherit; font-size: 13.5px; font-weight: 500; cursor: pointer; }
.ai-btn[disabled] { opacity: .45; cursor: default; }
.idea-ai .using { font-size: 13px; color: var(--t5); margin-left: 8px; }
.idea-ai .scope > summary { border-radius: 9px; height: auto; padding: 7px 12px; background: none;
  color: var(--t2); }
.idea-ai .menu-list { min-width: 230px; }
.menu-list a { display: flex; justify-content: space-between; gap: 12px; padding: 8px 10px;
  border-radius: 6px; color: var(--t2); text-decoration: none; font-size: 13px; }
.menu-list a.on, .menu-list a:hover { background: var(--s5); color: var(--t1); }
.idea-ai .working { margin-left: auto; font-size: 13px; color: var(--acc); }
.idea-body { flex: 1; min-height: 0; display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.15fr); }
.idea-text { padding: 24px 28px 24px 40px; border-right: 1px solid var(--b-div);
  display: flex; flex-direction: column; gap: 10px; min-height: 0; }
.idea-text .label { display: flex; justify-content: space-between; margin: 0; font-size: 11px;
  color: var(--t6); letter-spacing: .08em; }
.idea-text .label span + span { letter-spacing: 0; }
.idea-text form { flex: 1; display: flex; flex-direction: column; gap: 8px; min-height: 0; margin: 0; }
.idea-text textarea { flex: 1; resize: none; background: var(--s2); border: 1px solid var(--b-input);
  border-radius: 12px; padding: 16px 18px; color: var(--t1); font: inherit; font-size: 15px;
  line-height: 1.6; outline: 0; }
.idea-results { padding: 24px 40px 24px 28px; display: flex; flex-direction: column; gap: 14px;
  min-height: 0; overflow-y: auto; }
.idea-results .tabs { display: flex; gap: 18px; border-bottom: 1px solid var(--b-div); font-size: 13px; }
.idea-results .tabs a { padding: 0 0 9px; margin-bottom: -1px; color: var(--t5);
  border-bottom: 2px solid transparent; text-decoration: none; }
.idea-results .tabs a.on { color: var(--t1); border-bottom-color: var(--t1); }
.tab-pane { display: flex; flex-direction: column; gap: 10px; flex: 1; }
.tab-pane[hidden] { display: none; }
.tab-pane p { margin: 0; }
.tab-pane .lead { font-size: 15px; line-height: 1.6; color: var(--t1); }
.tab-pane .used, .tab-pane .tail { font-size: 13px; color: var(--t5); line-height: 1.5; }
.tab-pane .failed { font-size: 13px; color: var(--danger); }
.numbered { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 10px; }
.numbered li { display: grid; grid-template-columns: 22px minmax(0, 1fr); gap: 8px; font-size: 14px;
  line-height: 1.5; color: var(--t2); }
.numbered .n { font-size: 12px; color: var(--t6); padding-top: 2px; }
.result-card { background: var(--s2); border-radius: 10px; padding: 12px 14px; display: flex;
  flex-direction: column; gap: 4px; }
.result-card .title { font-size: 14px; font-weight: 500; color: var(--t1); }
.result-card .detail { font-size: 13px; color: var(--t5); line-height: 1.5; }
.tab-empty { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 10px; text-align: center; color: var(--t5); font-size: 14px; line-height: 1.5; }
.links-column { border-left: 1px solid var(--b-div); display: flex; flex-direction: column; min-height: 0; }
.links-head { padding: 20px 20px 0; display: flex; flex-direction: column; gap: 12px; }
.links-title { display: flex; justify-content: space-between; align-items: baseline; margin: 0;
  font-size: 15px; font-weight: 600; color: var(--t1); }
.links-title b { font-size: 12px; font-weight: 400; color: var(--t6); }
```

- [ ] **Step 7: The Spanish**

| key | es |
|---|---|
| created %1 | creada %1 |
| Saving… | Guardando… |
| ASK THE AI | PEDILE A LA IA |
| using | usando |
| Linked links (%1) | Links vinculados (%1) |
| The whole library | Toda la biblioteca |
| Only my text | Sólo mi texto |
| YOUR IDEA | TU IDEA |
| Write it however it comes out: the AI puts it in order. | Escribila como te salga: la IA la ordena. |
| saves itself | se guarda sola |
| You have not asked yet. | Todavía no se lo pediste. |
| Regenerate everything with the AI | Regenerar todo con la IA |
| Delete idea | Borrar idea |
| Move this idea to the trash folder? | ¿Mover esta idea a la papelera? |
| Searching… | Buscando… |
| Improvements… | Mejoras… |
| Expansion… | Ampliación… |
| Regenerating… | Regenerando… |
| Done: %1 | Listo: %1 |
| Failed: %1 | Falló: %1 |
| Links of this idea | Links de esta idea |

("Saved", "Title", "Your idea", "Summary", "Already out there?", "Improvements", "Expansion", "Improve", "Expand", "Results", "More", "+ tag", "Remove the tag %1", "Last time it failed: %1", "Untitled idea", "Ideas", "seed", "under way", "done", "dropped" already have theirs.)

- [ ] **Step 8: Run the tests**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_markup_cards.py tests/test_web_idea_screen.py tests/test_web_idea_actions.py tests/test_web_ideas_page.py tests/test_web_ideas_mine.py tests/test_i18n.py`
Expected: PASS.

- [ ] **Step 9: Whole suite, commit**

Run the suite; expected green. Until Task 7 the old idea page at `/item/{id}` is still there and the writes that name an idea by `item_url` (state, stars, tags, text, links) still land on it without JavaScript; that is expected and Task 7 redirects it.

```bash
git add src/oknowledge/web/shelf_view.py src/oknowledge/web/markup.py src/oknowledge/web/app.py \
        src/oknowledge/web/templates/idea.html src/oknowledge/web/templates/idea-results.html \
        src/oknowledge/web/static/app.css src/oknowledge/i18n.py \
        tests/test_markup_cards.py tests/test_web_idea_screen.py tests/test_web_idea_actions.py \
        tests/test_web_ideas_page.py tests/test_web_ideas_mine.py
git commit -m "Give an idea a screen of its own: header, AI bar with its scope, text beside tabbed results"
```

---
### Task 4: The column of links beside an idea

**Files:**
- Create: `src/oknowledge/web/templates/idea-links.html`
- Modify: `src/oknowledge/web/app.py` — `links_context()` beside `idea_context()` (Task 3), which merges it in; `idea_link_search` (≈885) renders `idea-links.html`; `join_idea` (≈1343) and `leave_idea` (≈1372) come back to `idea_url()`
- Modify: `src/oknowledge/web/templates/idea.html` (the `<aside>`), `src/oknowledge/web/static/app.css`, `src/oknowledge/i18n.py`
- Test: `tests/test_web_idea_screen_links.py` (new); rewrite `tests/test_web_idea_link_search.py` (the fragment changed shape); in `tests/test_web_idea_actions.py::test_add_from_the_idea_goes_back_to_the_idea` the assert becomes `startswith(f"/ideas/{note.id}")`

**Interfaces:**
- Consumes: `may_serve(note, entries, keep_linked=False, limit=MAX_SCOPED)` (Task 2), `idea_url()`, `idea_context()` (Task 3), `links_for(note, q) -> (searched, found)` (existing).
- Produces:
  - `links_context(note, q) -> dict` with `related: list[tuple[str, Note | None]]`, `serve: list[Note]`, `searched: bool`, `found: list[Note]`, `library_total: int`, `idea_id: str`, `q: str`.
  - `idea-links.html`: `<div id="idea-links-body" data-linked="N">` holding the VINCULADOS list and either PUEDEN SERVIR or RESULTADOS; every ✕ and "+ Sumar" is a `form[data-json][data-links]`. The search box is `#links-q[data-results="/item/{id}/buscar-links"]`, count `#idea-links-count`. Task 6 binds them.

- [ ] **Step 1: Write the failing tests**

`tests/test_web_idea_screen_links.py`:

```python
"""The column of links beside an idea (spec §2): the linked ones, the ones
that may help, and a search over the whole library."""

import re

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.model import Note
from oknowledge.vault import note_path, rebuild_indexes, write_note
from oknowledge.web.app import create_app


@pytest.fixture
def cfg(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    config = Config(vault=vault)
    rebuild_indexes(config, "es")
    return config


def a_link(cfg, n, title, summary="Una vpn.", tags=("vpn",), category="Redes"):
    stem = write_note(cfg, Note(id=f"l{n:011d}", url=f"https://e{n}.com/x", title=title,
                                category=category, tags=list(tags), type="article",
                                source=f"e{n}.com", saved=f"2026-10-{n:02d}",
                                summary=summary), "es").stem
    rebuild_indexes(cfg, "es")
    return stem


def an_idea(cfg, related=(), text="Una vpn para la familia.", tags=("vpn",)):
    note = new_idea(text, "VPN familiar", "2026-10-12", "2026-10-12T00:00:00.000001+00:00")
    note.related, note.tags = list(related), list(tags)
    write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ideas))
    return note


def column(cfg, idea, query=""):
    body = TestClient(create_app(cfg)).get(f"/ideas/{idea.id}{query}").text
    head = body.index('<aside class="links-column"')
    return body[head:body.index("</aside>", head)]


def test_the_head_counts_the_linked_links(cfg):
    stem = a_link(cfg, 1, "WireGuard")
    aside = column(cfg, an_idea(cfg, related=[stem]))
    assert "Links of this idea" in aside
    assert '<b class="mono" id="idea-links-count">1</b>' in aside


def test_the_search_box_counts_the_library(cfg):
    a_link(cfg, 1, "WireGuard")
    a_link(cfg, 2, "Tailscale")
    box = re.search(r'<input[^>]*id="links-q"[^>]*>', column(cfg, an_idea(cfg))).group(0)
    assert 'placeholder="Search your 2 links to add"' in box
    assert 'data-results="/item/' in box and 'name="q"' in box


def test_a_linked_link_is_a_row_that_opens_in_the_library(cfg):
    stem = a_link(cfg, 1, "WireGuard", category="Redes")
    idea = an_idea(cfg, related=[stem])
    aside = column(cfg, idea)
    linked = aside[aside.index("LINKED"):]
    assert '<a href="/?sel=l00000000001"' in linked and ">WireGuard</a>" in linked
    assert "e1.com" in linked
    assert 'style="background: oklch(' in linked
    drop = re.search(rf'<form[^>]*action="/item/{idea.id}/related/drop"[^>]*>', linked).group(0)
    assert "data-json" in drop and "data-links" in drop
    assert f'name="stem" value="{stem}"' in linked


def test_a_gone_link_is_dimmed_and_can_still_go(cfg):
    idea = an_idea(cfg, related=["2026-01-01-borrada"])
    aside = column(cfg, idea)
    assert 'class="row gone"' in aside and "2026-01-01-borrada" in aside
    assert 'name="stem" value="2026-01-01-borrada"' in aside


def test_no_linked_links_yet(cfg):
    assert "No linked links yet" in column(cfg, an_idea(cfg))


def test_links_in_common_may_help_with_an_add_button(cfg):
    a_link(cfg, 1, "Montar una vpn casera", tags=("vpn",))
    a_link(cfg, 2, "Recetas de pan", summary="Harina.", tags=("cocina",), category="Cocina")
    idea = an_idea(cfg)
    aside = column(cfg, idea)
    serve = aside[aside.index("MAY HELP"):]
    assert "Montar una vpn casera" in serve and "Recetas de pan" not in serve
    add = re.search(r'<form[^>]*action="/item/l00000000001/ideas"[^>]*>', serve).group(0)
    assert "data-json" in add and "data-links" in add
    assert f'name="idea" value="{idea.id}"' in serve and 'name="back" value="idea"' in serve
    assert "+ Add" in serve


def test_a_linked_link_is_not_offered_again(cfg):
    stem = a_link(cfg, 1, "Montar una vpn casera")
    aside = column(cfg, an_idea(cfg, related=[stem]))
    assert aside.count("Montar una vpn casera") == 1


def test_nothing_in_common(cfg):
    a_link(cfg, 1, "Recetas de pan", summary="Harina.", tags=("cocina",))
    assert "Nothing in common yet" in column(cfg, an_idea(cfg))


def test_a_search_replaces_may_help_with_results(cfg):
    a_link(cfg, 1, "Recetas de pan", summary="Harina.", tags=("cocina",))
    aside = column(cfg, an_idea(cfg), "?q=pan")
    assert "RESULTS" in aside and "MAY HELP" not in aside
    assert "Recetas de pan" in aside
    assert 'name="q" value="pan"' in aside


def test_a_search_that_finds_nothing_says_so(cfg):
    a_link(cfg, 1, "VPN")
    assert "Nothing matches" in column(cfg, an_idea(cfg), "?q=zzzz")


def test_adding_and_removing_come_back_to_the_screen(cfg):
    stem = a_link(cfg, 1, "WireGuard")
    idea = an_idea(cfg)
    client = TestClient(create_app(cfg))
    joined = client.post("/item/l00000000001/ideas",
                         data={"idea": idea.id, "back": "idea", "q": "wire"},
                         follow_redirects=False)
    assert joined.headers["location"] == f"/ideas/{idea.id}?q=wire&notice=saved"
    left = client.post(f"/item/{idea.id}/related/drop", data={"stem": stem},
                       follow_redirects=False)
    assert left.headers["location"] == f"/ideas/{idea.id}?notice=saved"


def test_adding_by_script_answers_json(cfg):
    a_link(cfg, 1, "WireGuard")
    idea = an_idea(cfg)
    reply = TestClient(create_app(cfg)).post(
        "/item/l00000000001/ideas", data={"idea": idea.id, "back": "idea"},
        headers={"Accept": "application/json"})
    assert reply.json()["ok"] is True
```

Replace `tests/test_web_idea_link_search.py`'s body below `search()` (keep its imports, `state_tree`, `cfg`, `a_link`, `an_idea`, `search`) with:

```python
def rows(text):
    return re.findall(r'<li class="row add">', text)


def test_it_finds_by_title_without_accents(cfg):
    a_link(cfg, 1, "Túnel WireGuard")
    reply = search(cfg, an_idea(cfg), "tunel")
    assert reply.status_code == 200
    assert '<div id="idea-links-body"' in reply.text
    assert "Túnel WireGuard" in reply.text and len(rows(reply.text)) == 1


def test_linked_links_are_left_out_of_the_results(cfg):
    stem = a_link(cfg, 1, "WireGuard")
    a_link(cfg, 2, "WireGuard rápido")
    reply = search(cfg, an_idea(cfg, related=[stem]), "wireguard")
    results = reply.text[reply.text.index("RESULTS"):]
    assert "WireGuard rápido" in results and ">WireGuard<" not in results


def test_at_most_twelve(cfg):
    for n in range(1, 16):
        a_link(cfg, n, f"VPN {n}")
    assert len(rows(search(cfg, an_idea(cfg), "vpn").text)) == 12


@pytest.mark.parametrize("q", ["", "v", "   ", "#", "#a", "a b"])
def test_too_little_to_search_shows_what_may_help(cfg, q):
    a_link(cfg, 1, "VPN")
    reply = search(cfg, an_idea(cfg), q)
    assert reply.status_code == 200 and "RESULTS" not in reply.text


def test_nothing_found_says_so(cfg):
    a_link(cfg, 1, "VPN")
    assert "Nothing matches" in search(cfg, an_idea(cfg), "zzzz").text


def test_a_missing_idea_is_404(cfg):
    assert TestClient(create_app(cfg)).get("/item/nope/buscar-links?q=vpn").status_code == 404


def test_each_result_adds_to_the_idea_and_keeps_the_query(cfg):
    a_link(cfg, 1, "WireGuard")
    idea = an_idea(cfg)
    text = search(cfg, idea, "wire").text
    assert 'action="/item/l00000000001/ideas"' in text
    assert f'name="idea" value="{idea.id}"' in text
    assert 'name="back" value="idea"' in text and 'name="q" value="wire"' in text


def test_adding_goes_back_to_the_search(cfg):
    a_link(cfg, 1, "WireGuard")
    idea = an_idea(cfg)
    reply = TestClient(create_app(cfg)).post(
        "/item/l00000000001/ideas", data={"idea": idea.id, "back": "idea", "q": "wire"},
        follow_redirects=False)
    assert reply.headers["location"] == f"/ideas/{idea.id}?q=wire&notice=saved"


def test_the_screen_shows_results_without_javascript(cfg):
    a_link(cfg, 1, "WireGuard")
    idea = an_idea(cfg)
    page = TestClient(create_app(cfg)).get(f"/ideas/{idea.id}", params={"q": "wire"}).text
    assert 'action="/item/l00000000001/ideas"' in page
```

(add `import re` to its imports.)

In `tests/test_web_idea_actions.py::test_add_from_the_idea_goes_back_to_the_idea` change `startswith(f"/item/{note.id}")` to `startswith(f"/ideas/{note.id}")`.

- [ ] **Step 2: Run them to verify they fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_idea_screen_links.py tests/test_web_idea_link_search.py`
Expected: FAIL — the aside has only its head, the fragment is still `idea-link-results.html`.

- [ ] **Step 3: The context and the routes**

Import `may_serve` from `..idea_actions`. Beside `idea_context()`:

```python
    def links_context(note, q: str) -> dict:
        """The column beside an idea (spec §2). The rows that may help are
        ranked without asking anybody: words and tags in common."""
        library.refresh()
        by_stem = {entry.path.stem: entry.note for entry in library.entries}
        searched, found = links_for(note, q)
        # library.entries is newest first; may_serve() wants the vault's
        # order, oldest first, like all_entries() gives it.
        pool = [(entry.path, entry.note) for entry in reversed(library.entries)]
        return {"idea_id": note.id, "q": q, "searched": searched, "found": found,
                "related": [(stem, by_stem.get(stem)) for stem in note.related],
                "serve": [] if searched else [link for _, link in may_serve(note, pool)],
                "library_total": len(library.entries)}
```

In `idea_context()` return `{**links_context(note, q), …the keys of Task 3…}` (the `q` and `note` keys agree). Replace the body of `idea_link_search` after the 404 with:

```python
        return page(request, "idea-links.html", note=idea, **links_context(idea, q))
```

In `join_idea`: `home = idea_url(idea, q=q) if back == "idea" else item_url(link_id)`, and the `again` parameter goes away (`answer(request, home, "idea-full")`, `answer(request, home, result.notice)`). In `leave_idea`: `return answer(request, idea_url(link_id), result.notice)`.

- [ ] **Step 4: The column**

`src/oknowledge/web/templates/idea-links.html`:

```jinja
{# The body of the column beside an idea: rendered in the screen, and
   fetched alone by idea.js as you type and after each add or remove. #}
<div id="idea-links-body" data-linked="{{ related|length }}">
  <p class="links-label">{{ t('LINKED') }}</p>
  {% if related %}
    <ul class="rows">
      {% for stem, link in related %}
        <li class="row{% if not link %} gone{% endif %}">
          <span class="dot" style="background: {{ (link.category if link else '')|dot }}"></span>
          <span class="row-text">
            {% if link %}<a href="/?sel={{ link.id|slug }}" dir="auto">{{ link.title or link.url }}</a>
            <span class="domain mono">{{ link.source }}</span>
            {% else %}<span class="mono">{{ stem }}</span>{% endif %}
          </span>
          <form method="post" action="/item/{{ idea_id|slug }}/related/drop" data-json data-links>
            <input type="hidden" name="stem" value="{{ stem }}">
            <button class="x" aria-label="{{ t('Remove') }}" title="{{ t('Remove') }}">✕</button>
          </form>
        </li>
      {% endfor %}
    </ul>
  {% else %}
    <p class="links-empty">{{ t('No linked links yet') }}</p>
  {% endif %}
  {% if searched %}
    <p class="links-label">{{ t('RESULTS') }}</p>
    {% set offered = found %}
  {% else %}
    <p class="links-label">{{ t('MAY HELP') }}</p>
    {% set offered = serve %}
  {% endif %}
  {% if offered %}
    <ul class="rows">
      {% for link in offered %}
        <li class="row add">
          <span class="row-text">
            <span class="row-title" dir="auto">{{ link.title or link.url }}</span>
            <span class="domain mono">{{ link.source }}</span>
          </span>
          <form method="post" action="/item/{{ link.id|slug }}/ideas" data-json data-links>
            <input type="hidden" name="idea" value="{{ idea_id }}">
            <input type="hidden" name="back" value="idea">
            <input type="hidden" name="q" value="{{ q }}">
            <button class="add">{{ t('+ Add') }}</button>
          </form>
        </li>
      {% endfor %}
    </ul>
  {% else %}
    <p class="links-empty">{{ t('Nothing matches') if searched else t('Nothing in common yet') }}</p>
  {% endif %}
</div>
```

The `<aside>` of `idea.html` becomes:

```jinja
<aside class="links-column" aria-label="{{ t('Links of this idea') }}">
  <div class="links-head">
    <p class="links-title"><span>{{ t('Links of this idea') }}</span><b class="mono" id="idea-links-count">{{ related|length }}</b></p>
    <form method="get" action="/ideas/{{ note.id|slug }}" class="links-search" role="search">
      {% if tab != 'resumen' %}<input type="hidden" name="pestana" value="{{ tab }}">{% endif %}
      {% if scope != 'vinculados' %}<input type="hidden" name="alcance" value="{{ scope }}">{% endif %}
      <input type="search" name="q" id="links-q" value="{{ q }}" autocomplete="off"
             aria-label="{{ t('Search your %1 links to add', library_total) }}"
             placeholder="{{ t('Search your %1 links to add', library_total) }}"
             data-results="/item/{{ note.id|slug }}/buscar-links">
    </form>
  </div>
  <div class="links-scroll">{% include "idea-links.html" %}</div>
</aside>
```

- [ ] **Step 5: Style it**

Append to `app.css` (`Idea detalle.dc.html`: rows padding 10px 12px radius 10, the dashed border `#2a2b32`, "+ Sumar" in `#a9b4de`):

```css
.links-search input { width: 100%; height: 36px; padding: 0 12px; border-radius: 9px;
  border: 1px solid var(--b-input); background: var(--s2); color: var(--t1); font: inherit;
  font-size: 13px; outline: 0; }
.links-scroll { flex: 1; min-height: 0; overflow-y: auto; padding: 8px 20px 20px; }
.links-label { margin: 14px 0 8px; font-size: 11px; letter-spacing: .08em; color: var(--t6); }
.links-empty { margin: 0; font-size: 13px; color: var(--t6); }
.rows { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.row { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 10px;
  background: var(--s2); }
.row .dot { width: 7px; height: 7px; border-radius: 50%; flex: none; }
.row-text { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.row-text a, .row-title { color: var(--t1); text-decoration: none; font-size: 13.5px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.row .domain { font-size: 11px; color: var(--t6); }
.row form { margin: 0; }
.row .x { background: none; border: 0; color: var(--t6); cursor: pointer; font-size: 12px; }
.row.gone { opacity: .5; }
.row.add { background: none; border: 1px dashed #2a2b32; }
.row .add { background: none; border: 0; color: var(--acc); font: inherit; font-size: 12.5px;
  cursor: pointer; white-space: nowrap; }
```

- [ ] **Step 6: The Spanish**

| key | es |
|---|---|
| LINKED | VINCULADOS |
| MAY HELP | PUEDEN SERVIR |
| RESULTS | RESULTADOS |
| + Add | + Sumar |
| No linked links yet | Todavía no vinculaste links |
| Nothing in common yet | Nada en común todavía |
| Search your %1 links to add | Buscá en tus %1 links para sumar |

("Remove" and "Nothing matches" already have theirs; check with `grep -n '"Remove"' src/oknowledge/i18n.py` and add `"Remove": "Quitar"` if it is missing.)

- [ ] **Step 7: Run the tests**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_idea_screen_links.py tests/test_web_idea_link_search.py tests/test_web_idea_screen.py tests/test_web_ideas_related.py tests/test_web_idea_actions.py tests/test_i18n.py`
Expected: PASS. (`tests/test_web_ideas_related.py` still reads the old page at `/item/{idea}`, which keeps `idea-link-results.html` until Task 7.)

- [ ] **Step 8: Whole suite, commit**

Run the suite; expected green.

```bash
git add src/oknowledge/web/app.py src/oknowledge/web/templates/idea-links.html \
        src/oknowledge/web/templates/idea.html src/oknowledge/web/static/app.css \
        src/oknowledge/i18n.py tests/test_web_idea_screen_links.py tests/test_web_idea_link_search.py \
        tests/test_web_idea_actions.py
git commit -m "Put the idea's links in a column: linked, may help, and a search to add more"
```

---
### Task 5: The ideas list at full width

**Files:**
- Modify: `src/oknowledge/web/shelf_view.py` (append `IdeaView`, `choose_ideas`, `idea_filters`)
- Create: `src/oknowledge/web/templates/idea-shelf.html`, `idea-list.html`, `idea-list-more.html`, `idea-items.html`
- Delete: `src/oknowledge/web/templates/ideas.html`
- Modify: `src/oknowledge/web/templates/sidebar.html` (a generic `filters` block), `src/oknowledge/web/app.py` (`idea_shelf` ≈1911 rewritten, new `GET /ideas/lista` registered **before** `GET /ideas/{idea_id}`, `save_the_idea` ≈1950 also takes `q`; `IDEA_STATE_ORDER` ≈378 goes when nothing reads it), `src/oknowledge/web/static/shell.js`, `src/oknowledge/web/static/app.css`, `src/oknowledge/i18n.py`
- Test: `tests/test_shelf_view_ideas.py` (new), `tests/test_web_ideas_list.py` (new), `tests/test_web_shell_js.py` (append); replace `tests/test_web_ideas_page.py`'s page tests (ledger below); edit `tests/test_web_layout.py:69` and `tests/test_web_marks.py:138,146` (drop `"/ideas"` from their parameters)

**Interfaces:**
- Consumes: `idea_url()`, `IDEA_WORDS`, `IDEA_DOTS` (Task 3); `library_view.CHUNK`, `LAYOUTS`, `_count`.
- Produces:
  - `IdeaView(estado: str = "", q: str = "", vista: str = "tarjetas", hasta: int = CHUNK)` — frozen dataclass; `from_query(params)`, `url(path="/ideas", **changes) -> str`, `label(t) -> str`, `open(idea_id) -> str` (the screen with `back=` this view).
  - `choose_ideas(notes, view) -> list[Note]` (newest first by `(saved, title)`; `estado` filter, else the dropped ones out; `q` matches every folded word in title, text or tags).
  - `idea_filters(notes, view) -> list[dict]`: `[{"title": "STATE", "rows": [{"href", "label", "dot", "count", "on"}]}]`, labels are keys the template translates.
  - `sidebar.html` draws any `filters` list a page passes (Task 8 passes Ocio's).
  - `shell.js`: the list column is fetched from `list.dataset.source` (default `/lista`); `#panel` is optional; `form.dataset.mode` is `library` (default), `ideas` or `ocio`; the live search keeps `vista`, `estado`, `tipo` and `orden` from the URL; the remembered layout is per mode (`oknowledge.vista`, `oknowledge.vista.ideas`) and only where an `a[data-view]` exists.

- [ ] **Step 1: Write the failing tests**

`tests/test_shelf_view_ideas.py`:

```python
"""The ideas list as one URL describes it (spec §2): pure, no app."""

import pytest

from oknowledge.ideas import new_idea
from oknowledge.web.library_view import CHUNK
from oknowledge.web.shelf_view import IdeaView, choose_ideas, idea_filters


def idea(n, state="pending", text="", title=None, tags=(), saved=None):
    note = new_idea(text or f"Texto {n}.", f"Idea {n}" if title is None else title,
                    saved or f"2026-10-{n:02d}", f"2026-10-{n:02d}T00:00:00.000001+00:00")
    note.state, note.tags = state, list(tags)
    return note


def test_an_unknown_state_and_layout_are_the_usual_view():
    view = IdeaView.from_query({"estado": "archived", "vista": "x", "hasta": "7"})
    assert (view.estado, view.vista, view.hasta) == ("", "tarjetas", CHUNK)


def test_the_url_leaves_out_the_defaults():
    assert IdeaView().url() == "/ideas"
    assert IdeaView(estado="doing", vista="lista").url(q="vpn") == "/ideas?estado=doing&q=vpn&vista=lista"
    assert IdeaView(q="vpn").url("/ideas/lista", desde=60) == "/ideas/lista?q=vpn&desde=60"


def test_opening_an_idea_carries_the_way_back():
    assert IdeaView(estado="doing").open("abc") == "/ideas/abc?back=%2Fideas%3Festado%3Ddoing"
    assert IdeaView().open("abc") == "/ideas/abc"


def test_the_label():
    t = lambda text, *a: text
    assert IdeaView().label(t) == "Ideas"
    assert IdeaView(estado="doing").label(t) == "under way"
    assert IdeaView(q="vpn").label(t) == "Results"


def test_newest_first_and_the_dropped_out_of_all():
    notes = [idea(1), idea(3, "dropped"), idea(2, "done")]
    assert [n.title for n in choose_ideas(notes, IdeaView())] == ["Idea 2", "Idea 1"]


def test_a_state_shows_only_its_ideas_dropped_too():
    notes = [idea(1), idea(3, "dropped")]
    assert [n.title for n in choose_ideas(notes, IdeaView(estado="dropped"))] == ["Idea 3"]


def test_the_search_reads_title_text_and_tags_without_accents():
    notes = [idea(1, title="Túnel"), idea(2, text="una VPN casera"), idea(3, tags=("hogar",)),
             idea(4)]
    found = lambda q: [n.title for n in choose_ideas(notes, IdeaView(q=q))]
    assert found("tunel") == ["Túnel"]
    assert found("vpn casera") == ["Idea 2"]
    assert found("#hogar") == ["Idea 3"]


def test_the_search_keeps_out_the_dropped_unless_asked():
    notes = [idea(1, "dropped", title="VPN")]
    assert choose_ideas(notes, IdeaView(q="vpn")) == []
    assert len(choose_ideas(notes, IdeaView(q="vpn", estado="dropped"))) == 1


def test_the_state_group_counts_each_state_and_all_without_the_dropped():
    notes = [idea(1), idea(2, "doing"), idea(3, "dropped"), idea(4, "typo")]
    group, = idea_filters(notes, IdeaView(estado="doing"))
    assert group["title"] == "STATE"
    rows = [(r["label"], r["count"], r["on"]) for r in group["rows"]]
    assert rows == [("All", 3, False), ("seed", 1, False), ("under way", 1, True),
                    ("done", 0, False), ("dropped", 1, False)]
    assert group["rows"][2]["href"] == "/ideas?estado=doing"
    assert group["rows"][2]["dot"] == "#a9b4de"


def test_a_filter_keeps_the_layout_and_drops_the_search():
    group, = idea_filters([idea(1)], IdeaView(q="x", vista="lista"))
    assert group["rows"][1]["href"] == "/ideas?estado=pending&vista=lista"
```

`tests/test_web_ideas_list.py`:

```python
"""/ideas (spec §2): the sidebar, a field, and the ideas at full width."""

import re

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.vault import note_path, rebuild_indexes, write_note
from oknowledge.web.app import create_app


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


def put(cfg, n, state="pending", title=None, text=None, related=(), day=None):
    day = day or n
    note = new_idea(text or f"Texto de la idea {n}.", f"Idea {n}" if title is None else title,
                    f"2026-10-{day:02d}", f"2026-10-{day:02d}T00:00:00.{n:06d}+00:00")
    note.state, note.related = state, list(related)
    write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ideas))
    return note


def test_two_columns_and_no_panel(cfg, client):
    put(cfg, 1)
    body = client.get("/ideas").text
    assert '<div class="app idea-shelf">' in body
    assert 'id="list"' in body and 'data-source="/ideas/lista"' in body
    assert 'id="panel"' not in body
    assert '<script src="/static/shell.js" defer></script>' in body


def test_the_field_searches_and_offers_a_new_idea(cfg, client):
    body = client.get("/ideas").text
    form = re.search(r'<form[^>]*id="unified"[^>]*>', body).group(0)
    assert 'action="/ideas"' in form and 'data-mode="ideas"' in form
    assert 'placeholder="Search your ideas"' in body
    button = re.search(r'<button[^>]*id="save-link"[^>]*>(.*?)</button>', body, re.S)
    assert 'formaction="/ideas/guardar"' in button.group(0) and "New idea ↵" in button.group(1)


def test_with_text_in_the_field_the_new_idea_button_shows(cfg, client):
    assert re.search(r'class="unified saving"', client.get("/ideas?q=vpn").text)


def test_the_head_counts_and_switches_layout(cfg, client):
    put(cfg, 1), put(cfg, 2)
    body = client.get("/ideas").text
    assert re.search(r"Ideas · <b class=\"mono\">2</b>", body)
    assert 'data-view="lista"' in body and 'data-view="tarjetas"' in body


def test_a_card_is_title_text_state_and_links(cfg, client):
    note = put(cfg, 1, state="doing", related=["a", "b"])
    body = client.get("/ideas").text
    card = re.search(rf'<li class="item idea" id="idea-{note.id}">.*?</li>', body, re.S).group(0)
    assert f'href="/ideas/{note.id}"' in card
    assert ">Idea 1<" in card and "Texto de la idea 1." in card
    assert "under way · 2 links" in card
    assert 'style="background: #a9b4de"' in card


def test_one_link_is_said_in_the_singular(cfg, client):
    put(cfg, 1, related=["a"])
    assert "seed · 1 link<" in client.get("/ideas").text


def test_the_card_opens_the_screen_with_the_way_back(cfg, client):
    note = put(cfg, 1, state="doing")
    assert f'href="/ideas/{note.id}?back=%2Fideas%3Festado%3Ddoing"' in client.get("/ideas?estado=doing").text


def test_an_untitled_idea_is_never_an_empty_link(cfg, client):
    put(cfg, 1, title="")
    assert ">Untitled idea<" in client.get("/ideas").text


def test_the_list_layout_is_rows(cfg, client):
    put(cfg, 1)
    assert 'class="items rows"' in client.get("/ideas?vista=lista").text


def test_the_sidebar_has_the_state_group(cfg, client):
    put(cfg, 1), put(cfg, 2, "dropped")
    body = client.get("/ideas").text
    side = body[body.index('<aside class="sidebar"'):body.index("</aside>")]
    assert "STATE" in side
    assert re.search(r'href="/ideas"[^>]*class="filter on"[^>]*>.*?All.*?<b class="count mono">1</b>',
                     side, re.S)
    assert 'href="/ideas?estado=dropped"' in side


def test_dropped_ideas_are_out_of_all_and_in_their_state(cfg, client):
    put(cfg, 1, "dropped", title="Descartada")
    assert ">Descartada<" not in client.get("/ideas").text
    assert ">Descartada<" in client.get("/ideas?estado=dropped").text


def test_an_unknown_state_is_all(cfg, client):
    put(cfg, 1)
    assert ">Idea 1<" in client.get("/ideas?estado=archived").text


def test_a_state_typed_by_hand_does_not_break_it(cfg, client):
    put(cfg, 1, state="whatever")
    assert client.get("/ideas").status_code == 200


def test_the_column_alone_for_the_live_search(cfg, client):
    put(cfg, 1, title="VPN casera"), put(cfg, 2, title="Pan")
    column = client.get("/ideas/lista?q=vpn").text
    assert "<html" not in column and ">VPN casera<" in column and ">Pan<" not in column


def test_more_comes_in_chunks(cfg, client):
    for n in range(1, 63):
        put(cfg, n, day=n % 28 + 1)
    body = client.get("/ideas").text
    assert body.count('class="item idea"') == 60
    assert 'data-more="/ideas/lista?desde=60"' in body
    rest = client.get("/ideas/lista?desde=60").text
    assert rest.count('class="item idea"') == 2


def test_nothing_yet_says_where_to_start(client):
    assert "No ideas yet" in client.get("/ideas").text


def test_a_search_that_finds_nothing_says_so(cfg, client):
    put(cfg, 1)
    assert "No idea matches “zzz”" in client.get("/ideas?q=zzz").text


def test_new_idea_takes_the_field_and_opens_the_screen(cfg, client, monkeypatch):
    monkeypatch.setattr("oknowledge.web.app.complete_idea", lambda cfg, idea, trace=None: True)
    answer = client.post("/ideas/guardar", data={"q": "una vpn para la familia"},
                         follow_redirects=False)
    assert re.fullmatch(r"/ideas/[0-9a-f]{12}\?notice=completing", answer.headers["location"])


def test_the_screen_route_is_not_shadowed(cfg, client):
    assert client.get("/ideas/lista").status_code == 200
```

Append to `tests/test_web_shell_js.py`:

```python
def test_the_script_serves_any_list_column():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "list.dataset.source" in text
    assert 'form.dataset.mode' in text
    assert '"estado", "tipo", "orden"' in text


def test_in_ideas_enter_never_saves():
    body = between(SCRIPT.read_text(encoding="utf-8"), "function saves", "// --- the list column")
    assert 'mode !== "library"' in body
```

Replace `tests/test_web_ideas_page.py` from `test_the_form_is_open_only_while_there_is_nothing` through the end of the file with the tests that still describe a route (the page ones moved to `tests/test_web_ideas_list.py` above):

```python
def test_saving_writes_the_idea_and_queues_the_model(cfg, client, queued):
    answer = client.post("/ideas/guardar", data={"text": "Una vpn para la familia."},
                         follow_redirects=False)
    idea = next(iter(ideas_of(cfg)))
    assert answer.headers["location"] == f"/ideas/{idea.id}?notice=completing"
    assert queued == [idea.id]
```

and keep `test_a_title_you_type_is_kept`, `test_no_text_no_idea`, `test_two_saves_are_two_ideas`, `test_a_stale_index_still_saves_and_says_so`, `test_a_failed_write_saves_nothing_and_queues_nothing` as they are (read the file first: `ideas_of` and `queued` are its own helpers; if the first test is already in the form Task 3 left, leave it).

**Ledger — tests deleted here** (each one's behaviour is in the new file or left the spec): `test_the_form_is_open_only_while_there_is_nothing` (the form is the field now), `test_the_section_shows_ideas_and_not_links`, `test_dropped_ideas_are_out_of_sight_until_asked_for`, `test_an_unknown_state_shows_the_usual_view`, `test_a_state_typed_by_hand_does_not_break_the_section`, `test_an_untitled_idea_is_never_an_empty_link` (all four → `test_web_ideas_list.py`), `test_ideas_filter_by_tag` (the list's parameters are `estado`, `q`, `vista`, `hasta`: a tag is found with the search, `#tag`), `test_an_idea_not_yet_completed_says_so` and `test_stars_never_run_past_five` (the card of the spec has neither); `tests/test_web_layout.py::test_the_filters_fold_into_one_line[/ideas]`, `tests/test_web_marks.py::test_every_card_and_note_page_has_the_picker[/ideas-…]` and `::test_each_card_has_an_anchor_to_come_back_to[/ideas]` (no marks on the ideas list, spec §1).

- [ ] **Step 2: Run them to verify they fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_shelf_view_ideas.py tests/test_web_ideas_list.py tests/test_web_shell_js.py`
Expected: FAIL — `ImportError: IdeaView`; `/ideas` still the old page.

- [ ] **Step 3: The view**

Append to `shelf_view.py` (imports: `import dataclasses`, `from collections.abc import Mapping`, `from dataclasses import dataclass`, `from .index import fold, terms`, `from .library_view import CHUNK, LAYOUTS, _count`):

```python
@dataclass(frozen=True)
class IdeaView:
    """/ideas as its URL says it: `estado`, `q`, `vista`, `hasta` (spec §2)."""

    estado: str = ""
    q: str = ""
    vista: str = "tarjetas"
    hasta: int = CHUNK

    @classmethod
    def from_query(cls, params: Mapping[str, str]) -> IdeaView:
        estado, vista = params.get("estado", ""), params.get("vista", "")
        return cls(estado=estado if estado in IDEA_STATES else "",
                   q=" ".join(params.get("q", "").split()),
                   vista=vista if vista in LAYOUTS else "tarjetas",
                   hasta=_count(params.get("hasta", "")))

    def url(self, path: str = "/ideas", **changes) -> str:
        own = {k: v for k, v in changes.items() if k in _IDEA_FIELDS}
        extra = [(k, str(v)) for k, v in changes.items() if k not in _IDEA_FIELDS]
        view = dataclasses.replace(self, **own)
        pairs = [("estado", view.estado), ("q", view.q),
                 ("vista", view.vista if view.vista != "tarjetas" else ""),
                 ("hasta", str(view.hasta) if view.hasta != CHUNK else "")] + extra
        query = urlencode([(k, v) for k, v in pairs if v])
        return path + ("?" + query if query else "")

    def label(self, t) -> str:
        if self.q:
            return t("Results")
        return t(IDEA_WORDS[self.estado]) if self.estado else t("Ideas")

    def open(self, idea_id: str) -> str:
        """The idea's screen, with "← Ideas" coming back to this list."""
        return idea_url(idea_id, back=self.url())


_IDEA_FIELDS = {f.name for f in dataclasses.fields(IdeaView)}


def _words(note) -> str:
    return fold(" ".join([note.title, note.my_note, " ".join(note.tags)]))


def choose_ideas(notes, view: IdeaView) -> list:
    """Newest first; a state, or all of them but the dropped; every word of
    the search somewhere in the title, the text or the tags."""
    found = sorted(notes, key=lambda n: (n.saved, n.title), reverse=True)
    if view.estado:
        found = [n for n in found if n.state == view.estado]
    else:
        found = [n for n in found if n.state != "dropped"]
    words = terms(view.q)
    if words:
        found = [n for n in found if all(word in _words(n) for word in words)]
    return found


def idea_filters(notes, view: IdeaView) -> list[dict]:
    """The sidebar's ESTADO group for the ideas (spec §1). "All" counts what
    "All" shows: every idea but the dropped ones."""
    counts = {state: 0 for state in IDEA_STATES}
    for note in notes:
        if note.state in counts:
            counts[note.state] += 1
    rows = [{"href": view.url(estado="", q="", hasta=CHUNK), "label": "All", "dot": "#6d6f78",
             "count": sum(1 for n in notes if n.state != "dropped"),
             "on": not view.estado and not view.q}]
    rows += [{"href": view.url(estado=state, q="", hasta=CHUNK), "label": IDEA_WORDS[state],
              "dot": IDEA_DOTS[state], "count": counts[state], "on": view.estado == state}
             for state in IDEA_STATES]
    return [{"title": "STATE", "rows": rows}]
```

- [ ] **Step 4: The routes**

Replace `idea_shelf` in `app.py` (import `IdeaView, choose_ideas, idea_filters, IDEA_DOTS` from `.shelf_view`):

```python
    def idea_listing(view: IdeaView) -> dict:
        ideas.refresh()
        notes = choose_ideas(ideas.notes, view)
        return {"view": view, "notes": notes[:view.hasta], "chosen": notes,
                "total": len(notes), "more": len(notes) > view.hasta, "chunk": CHUNK,
                "IDEA_WORDS": IDEA_WORDS, "IDEA_DOTS": IDEA_DOTS}

    @app.get("/ideas", response_class=HTMLResponse)
    def idea_shelf(request: Request):
        """The ideas at full width (spec §2). An unknown filter is the usual
        view: these arrive from a URL somebody can type."""
        view = IdeaView.from_query(request.query_params)
        shown = idea_listing(view)
        return page(request, "idea-shelf.html", section="ideas", toast=True,
                    filters=idea_filters(ideas.notes, view),
                    unreadable_ideas=ideas.unreadable, **shown)

    @app.get("/ideas/lista", response_class=HTMLResponse)
    def idea_column(request: Request, desde: str = ""):
        """The list column alone, for the live search and "more". Registered
        before /ideas/{idea_id}, which would take "lista" for an id."""
        shown = idea_listing(IdeaView.from_query(request.query_params))
        if not desde:
            return page(request, "idea-list.html", **shown)
        try:
            start = max(0, int(desde))
        except ValueError:
            start = 0
        end = start + CHUNK
        notes = shown["chosen"]
        return page(request, "idea-list-more.html", **{**shown, "notes": notes[start:end],
                    "more": len(notes) > end, "next_desde": end, "next_hasta": end + CHUNK})
```

`save_the_idea` gains `q: str = Form("")` and starts with `text = text or q` (the field on `/ideas` is named `q`). Delete `IDEA_STATE_ORDER` (≈378) — `grep -n IDEA_STATE_ORDER src/` must print nothing afterwards.

- [ ] **Step 5: The templates**

`idea-items.html`:

```jinja
{# One idea in the list: a card (title, three lines of your text, state and
   links) or a row (dot, title, state and links, date) -- the class on the
   <ul> decides. The whole item opens the idea's screen. #}
{% macro item(note, view) -%}
{% set word = IDEA_WORDS.get(note.state, '') %}
<li class="item idea" id="idea-{{ note.id }}">
  <a class="hit" href="{{ view.open(note.id) }}">
    <span class="title" dir="auto">{{ note.title or t('Untitled idea') }}</span>
    <span class="excerpt" dir="auto">{{ (note.my_note or note.summary)|plain }}</span>
    <span class="sub"><i class="dot" style="background: {{ IDEA_DOTS.get(note.state, '#6d6f78') }}"></i>
      {%- if word %}{{ t(word) }} · {% endif %}{% if note.related|length == 1 %}{{ t('1 link') }}{% else %}{{ t('%1 links', note.related|length) }}{% endif %}</span>
    <span class="date mono">{{ note.saved|short_date(t) }}</span>
  </a>
</li>
{%- endmacro %}
```

`idea-list.html`:

```jinja
{% import "idea-items.html" as shelf with context %}
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
  {% if notes %}
    <ul class="items {{ 'rows' if view.vista == 'lista' else 'tiles' }} ideas" id="items">
      {% for note in notes %}{{ shelf.item(note, view) }}{% endfor %}
    </ul>
    {% if more %}<a class="more" href="{{ view.url(hasta=view.hasta + chunk) }}" data-more="{{ view.url('/ideas/lista', desde=view.hasta) }}">{{ t('Show more') }}</a>{% endif %}
  {% elif view.q %}
    <div class="empty-state"><p class="empty-title">{{ t('No idea matches “%1”', view.q) }}</p>
      <p>{{ t('Press “New idea” to write it down.') }}</p></div>
  {% elif view.estado %}
    <div class="empty-state"><p class="empty-title">{{ t('There is nothing in %1', view.label(t)) }}</p>
      <a class="btn" href="/ideas">{{ t('See everything') }}</a></div>
  {% else %}
    <div class="empty-state"><p class="empty-title">{{ t('No ideas yet') }}</p>
      <p>{{ t('Write one in the box above and press “New idea”.') }}</p></div>
  {% endif %}
</div>
```

`idea-list-more.html`:

```jinja
{% import "idea-items.html" as shelf with context %}
<ul>{% for note in notes %}{{ shelf.item(note, view) }}{% endfor %}</ul>
{% if more %}<a class="more" href="{{ view.url(hasta=next_hasta) }}" data-more="{{ view.url('/ideas/lista', desde=next_desde) }}">{{ t('Show more') }}</a>{% endif %}
```

`idea-shelf.html`:

```jinja
{% extends "base.html" %}
{% block title %}{% if view.q %}{{ view.q }} - {% endif %}{{ t('Ideas') }} - oknowledge{% endblock %}
{% block app_class %}idea-shelf{% endblock %}
{% block scripts %}<script src="/static/shell.js" defer></script>{% endblock %}
{% block layout %}
<section class="center" aria-label="{{ t('Ideas') }}">
  {# GET, so Enter searches; "New idea" posts the same field (spec §2). #}
  <form class="unified{% if view.q %} saving{% endif %}" id="unified" action="/ideas" method="get"
        role="search" data-mode="ideas">
    <button type="submit" class="default-submit" tabindex="-1" aria-hidden="true"></button>
    <input type="text" name="q" id="field-q" value="{{ view.q }}" autocomplete="off"
           aria-label="{{ t('Search your ideas') }}" placeholder="{{ t('Search your ideas') }}">
    {% if view.estado %}<input type="hidden" name="estado" value="{{ view.estado }}">{% endif %}
    {% if view.vista == 'lista' %}<input type="hidden" name="vista" value="lista">{% endif %}
    <span class="save">
      <button type="submit" class="btn primary" formmethod="post" formaction="/ideas/guardar" id="save-link">{{ t('New idea') }} ↵</button>
    </span>
    <kbd class="hint mono">/</kbd>
  </form>
  {% if unreadable_ideas %}
    <p class="quiet">{{ t('%1 ideas could not be read and are not shown', unreadable_ideas) }}</p>
  {% endif %}
  <div class="list" id="list" data-source="/ideas/lista">{% include "idea-list.html" %}</div>
</section>
{% endblock %}
```

In `sidebar.html`, after the `{% if groups is defined and groups %}…{% endif %}` block:

```jinja
  {% for group in filters|default([]) %}
    <nav class="group" aria-label="{{ t(group.title) }}">
      <p class="group-title">{{ t(group.title) }}</p>
      {% for row in group.rows %}
        <a href="{{ row.href }}" data-nav class="filter{% if row.on %} on{% endif %}"><i class="dot" style="background: {{ row.dot }}"></i><span>{{ t(row.label) }}</span><b class="count mono">{{ row.count }}</b></a>
      {% endfor %}
    </nav>
  {% endfor %}
```

Delete `templates/ideas.html`.

- [ ] **Step 6: shell.js serves every list**

In `shell.js`:

1. The guard and the new settings at the top:

```js
  var list = document.getElementById("list");
  var panel = document.getElementById("panel");          // not on /ideas
  var form = document.getElementById("unified");
  var field = document.getElementById("field-q");
  if (!list || !form || !field) return;
  var texts = document.body.dataset;
  var mode = form.dataset.mode || "library";
  var source = list.dataset.source || "/lista";
  var STORE = "oknowledge.vista" + (mode === "library" ? "" : "." + mode);
  // What a new search keeps from the URL: the shape and the sidebar's filter.
  var KEEP = ["vista", "estado", "tipo", "orden"];
```

2. `saves()` starts with `if (mode !== "library") return false;` — on /ideas Enter searches and only the button saves; Ocio decides in Task 12.

3. In `loadList`: `return fetch(source + target.search)`; the block after `history.replaceState` guards the panel: `if (panel && moved) {…} else if (panel) {…}` (the same two branches as today).

4. `loadPanel`, `emptyPanel` and `stillPicked` start with `if (!panel) return;` (`stillPicked` returns `true`); the `data-inline` handler and `watch()` read `panel && panel.querySelector(...)`.

5. In the `input` handler: `form.classList.toggle("saving", mode === "ideas" ? text.trim() !== "" : saving);` then `if (saving) return;`, and the URL is built from the form and the kept parameters:

```js
    timer = setTimeout(function () {
      var url = new URL(form.getAttribute("action") || "/", location.href);
      var q = text.trim().split(/\s+/).join(" ");
      if (q) url.searchParams.set("q", q);
      KEEP.forEach(function (name) {
        var value = here().searchParams.get(name);
        if (value) url.searchParams.set(name, value);
      });
      loadList(url.href);
    }, 250);
```

6. The sidebar click keeps `vista` as today (`KEEP` is for the field: a filter link already carries its own `estado`/`tipo`).

7. The remembered layout runs only `if (document.querySelector("a[data-view]"))`.

- [ ] **Step 7: Style it**

Append to `app.css`:

```css
/* --- the ideas list (spec §2) -------------------------------------------- */
.app.idea-shelf { grid-template-columns: 216px minmax(0, 1fr); overflow: hidden; line-height: normal; }
.ideas.tiles { grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); }
.ideas .hit { display: flex; flex-direction: column; gap: 8px; padding: 14px 16px; color: inherit;
  text-decoration: none; height: 100%; box-sizing: border-box; }
.ideas .title { font-size: 14.5px; font-weight: 600; color: var(--t1); }
.ideas .excerpt { font-size: 13px; line-height: 1.5; color: var(--t4); display: -webkit-box;
  -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.ideas .sub { margin-top: auto; font-size: 12px; color: var(--t5); display: flex;
  align-items: center; gap: 6px; }
.ideas.tiles .date { display: none; }
.ideas.rows .hit { flex-direction: row; align-items: center; gap: 14px; padding: 10px 16px; }
.ideas.rows .excerpt { display: none; }
.ideas.rows .title { flex: 1; min-width: 0; font-size: 13.5px; font-weight: 500;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ideas.rows .sub { margin: 0; order: -1; }
.ideas.rows .sub i { margin-right: 4px; }
.ideas.rows .date { font-size: 12px; color: var(--t6); }
```

(The `.rows` list keeps the dot first by `order: -1` on `.sub`; the label after the dot stays visible in the row, as the spec's row lists it.)

- [ ] **Step 8: The Spanish**

| key | es |
|---|---|
| Search your ideas | Buscá en tus ideas |
| STATE | ESTADO |
| 1 link | 1 link |
| %1 links | %1 links |
| No ideas yet | Todavía no hay ideas |
| Write one in the box above and press “New idea”. | Escribila en el campo de arriba y tocá “Nueva idea”. |
| No idea matches “%1” | Ninguna idea coincide con “%1” |
| Press “New idea” to write it down. | Tocá “Nueva idea” para anotarla. |

("New idea" → "Nueva idea" is already there.) Delete the entries only `ideas.html` asked for and nothing else does: run `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_i18n.py` and remove each key `test_every_translated_string_is_one_the_code_asks_for` names (expected: "What is the idea?", "Title (optional: the model names it if you leave it empty)", "Filters", "Nothing matches that filter", "not completed", among others — remove exactly the ones it lists).

- [ ] **Step 9: Run the tests**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_shelf_view_ideas.py tests/test_web_ideas_list.py tests/test_web_shell_js.py tests/test_web_ideas_page.py tests/test_web_sidebar.py tests/test_web_layout.py tests/test_web_marks.py tests/test_i18n.py tests/test_packaging.py`
Expected: PASS.

- [ ] **Step 10: Check it in a browser**

```bash
SP=/tmp/claude-1000/-home-fer-Projects-gym/d89ecc8a-2029-44cb-b47f-742ed00daeae/scratchpad
~/.local/share/oknowledge/venv/bin/python "$SP/shots/serve.py" > "$SP/serve.log" 2>&1 &
echo $! > "$SP/serve.pid"
cd "$SP/pw" && [ -d node_modules/playwright ] || npm install --no-save --silent playwright
cat > "$SP/pw/ideas-list.js" <<'EOF'
const { chromium } = require("playwright");
(async () => {
  const browser = await chromium.launch({ executablePath: "/usr/bin/chromium" });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto("http://127.0.0.1:8812/ideas");
  await page.fill("#field-q", "vpn");
  await page.waitForTimeout(600);
  console.log("url", new URL(page.url()).search, "items", await page.locator("li.item.idea").count(),
              "new-idea visible", await page.locator("#save-link").isVisible());
  await page.keyboard.press("Enter");
  await page.waitForTimeout(400);
  console.log("after enter", new URL(page.url()).pathname);
  console.log("scroll", await page.evaluate(() => document.scrollingElement.scrollHeight <= innerHeight));
  await browser.close();
})();
EOF
node "$SP/pw/ideas-list.js"
ps -p "$(cat "$SP/serve.pid")" -o args= | grep -q serve.py && kill "$(cat "$SP/serve.pid")"
```

Expected: `url ?q=vpn items <n ≥ 0> new-idea visible true`, `after enter /ideas`, `scroll true`.

- [ ] **Step 11: Whole suite, commit**

Run the suite; expected green, with the deleted tests of the ledger gone.

```bash
git add -A src/oknowledge/web tests/test_shelf_view_ideas.py tests/test_web_ideas_list.py \
        tests/test_web_shell_js.py tests/test_web_ideas_page.py tests/test_web_layout.py \
        tests/test_web_marks.py src/oknowledge/i18n.py
git commit -m "Show the ideas at full width with a state filter, a live search and a New idea button"
```

---
### Task 6: Autosave, and an idea's screen without reloads

**Files:**
- Create: `src/oknowledge/web/static/autosave.js`, `src/oknowledge/web/static/idea.js`
- Modify: `src/oknowledge/web/templates/idea.html` (a `scripts` block)
- Modify: `src/oknowledge/web/static/app.css` (`[data-nojs]` and `.toast` already exist from delivery 1 — only the line below)
- Test: `tests/test_web_idea_scripts.py` (new); `tests/test_packaging.py:95` (add `"autosave.js"`, `"idea.js"` to the parameters)

**Interfaces:**
- Consumes: the DOM hooks of Tasks 3 and 4; `answer()` JSON (Task 1); `GET /item/{id}/actions/state` (Task 2); `"no-such-idea"` in `NOTICES` (exists, ≈148).
- Produces:
  - `window.oknowledge = {toast(text), post(form, submitter) -> Promise<body>, bind(root)}` from `autosave.js`. `post` sends `Accept: application/json` and rejects with an `Error` whose `message` is the server's `error` (or the body's `data-save-failed`) and whose `status` is the HTTP status. `bind(root)` hides every `[data-nojs]` and watches every `[data-autosave]` under `root` once.
  - On each watched field, `field.oknowledgeSettle(value) -> bool`: replaces the value only when the field is not focused, not dirty and not saving (the poll uses it for a title the model just wrote).
  - Task 12 loads `autosave.js` on `/ocio` and calls `window.oknowledge.bind(panel)` after each panel swap.

- [ ] **Step 1: Write the failing tests**

`tests/test_web_idea_scripts.py`:

```python
"""What autosave.js and idea.js promise (spec §1 autosave, §2.2 polling).
node --check runs them in tests/test_packaging.py; the behaviour is checked
in a browser in this task's last step. These pin the parts a reviewer would
otherwise have to trust."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.vault import note_path, rebuild_indexes, write_note
from oknowledge.web.app import create_app

STATIC = Path(__file__).resolve().parent.parent / "src" / "oknowledge" / "web" / "static"
AUTOSAVE = (STATIC / "autosave.js").read_text(encoding="utf-8") if (STATIC / "autosave.js").exists() else ""
IDEA = (STATIC / "idea.js").read_text(encoding="utf-8") if (STATIC / "idea.js").exists() else ""


def between(text, start, end):
    head = text.index(start)
    return text[head:text.index(end, head)]


@pytest.fixture
def client(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    rebuild_indexes(cfg, "es")
    note = new_idea("Una vpn.", "VPN", "2026-10-13", "2026-10-13T00:00:00.000001+00:00")
    write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ideas))
    client = TestClient(create_app(cfg))
    client.idea = note.id
    return client


def test_the_screen_loads_autosave_before_idea(client):
    body = client.get(f"/ideas/{client.idea}").text
    first = body.index('<script src="/static/autosave.js" defer></script>')
    assert first < body.index('<script src="/static/idea.js" defer></script>')


@pytest.mark.parametrize("name", ["autosave.js", "idea.js"])
def test_the_scripts_are_served(client, name):
    assert client.get(f"/static/{name}").status_code == 200


def test_autosave_waits_a_second_and_saves_on_blur():
    assert "DELAY = 1000" in AUTOSAVE
    assert '"blur"' in AUTOSAVE and '"input"' in AUTOSAVE


def test_autosave_asks_for_json():
    assert 'Accept: "application/json"' in AUTOSAVE


def test_one_save_in_flight_per_field_and_the_newest_text_after_it():
    """Review Focus 1: a save that is in flight makes the next one wait; when
    it returns, what is in the field now is sent -- never the older value."""
    flush = between(AUTOSAVE, "function flush", "function schedule")
    assert "if (inflight) { again = true; return; }" in flush
    assert "var sending = field.value;" in flush
    assert "if (again) { again = false; flush(); }" in flush


def test_a_reply_never_writes_the_field():
    """The older reply must not put the older text back: only settle(),
    which refuses while the field is focused, dirty or saving, writes it."""
    assert AUTOSAVE.count("field.value = ") == 1
    settle = between(AUTOSAVE, "field.oknowledgeSettle", "};")
    assert "field.value = value" in settle
    assert "document.activeElement === field" in settle and "inflight" in settle


def test_an_empty_title_is_not_sent():
    assert 'hasAttribute("data-skip-empty")' in AUTOSAVE


def test_a_failure_keeps_the_text_and_says_so():
    flush = between(AUTOSAVE, "function flush", "function schedule")
    assert "toast(" in flush and "saveFailed" in AUTOSAVE


def test_without_javascript_buttons_are_hidden_by_it():
    assert "[data-nojs]" in AUTOSAVE and ".hidden = true" in AUTOSAVE


def test_idea_polls_every_three_seconds_and_stops():
    assert "POLL = 3000" in IDEA and "/actions/state" in IDEA
    assert "clearInterval(polling)" in IDEA


def test_a_deleted_idea_stops_the_poll_and_goes_back():
    """Review Focus 3."""
    tick = between(IDEA, "function tick", "function gone")
    assert "status === 404" in tick and "stop()" in tick
    assert '"/ideas?notice=no-such-idea"' in IDEA


def test_the_tab_and_the_scope_live_in_the_url():
    assert '"pestana"' in IDEA and '"alcance"' in IDEA and "history.replaceState" in IDEA


def test_the_links_search_is_live_and_keeps_only_the_newest_answer():
    assert "250" in IDEA
    body = between(IDEA, "function search", "function started")
    assert "searchAsked" in body and "!== searchAsked" in body


def test_the_parts_come_from_the_server():
    assert "new DOMParser()" in IDEA and "fetch(location.href" in IDEA
```

In `tests/test_packaging.py` the parameter list becomes `["autosave.js", "idea.js", "popup.js", "redo.js", "shell.js"]`.

- [ ] **Step 2: Run them to verify they fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_idea_scripts.py tests/test_packaging.py`
Expected: FAIL — the scripts do not exist (`ValueError: substring not found`, 404 on `/static/autosave.js`, node cannot open the files).

- [ ] **Step 3: autosave.js**

`src/oknowledge/web/static/autosave.js`:

```js
// Saving as you go (docs/2026-10-14-rediseno-ocio-ideas-design.md §1).
// Every form under it works without this file: each keeps a Save button
// marked data-nojs, which this hides. A text field with data-autosave posts
// itself 1 s after the last key or when it loses focus; every post asks for
// JSON, so the routes answer {"ok": ...} instead of redirecting.
(function () {
  "use strict";
  var DELAY = 1000;
  var texts = document.body.dataset;

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

  // The answer of a write, as JSON. Anything that is not {"ok": true} is an
  // error with the server's words, or the page's "could not be saved".
  function answer(r) {
    return r.json().catch(function () { return { ok: false }; }).then(function (body) {
      if (r.ok && body.ok) return body;
      var error = new Error(body.error || texts.saveFailed || "");
      error.status = r.status;
      throw error;
    });
  }

  function send(url, data) {
    return fetch(url, { method: "POST", body: data,
                        headers: { Accept: "application/json" } }).then(answer);
  }

  function post(form, submitter) {
    return send(form.action, new FormData(form, submitter || undefined));
  }

  function watchField(field) {
    if (field.dataset.bound) return;
    field.dataset.bound = "1";
    var saved = field.value;        // what the server has, as far as we know
    var timer = null;
    var inflight = false;
    var again = false;
    var indicator = field.dataset.indicator ? document.querySelector(field.dataset.indicator) : null;

    function say(state) {
      if (indicator) indicator.textContent = state ? (indicator.dataset[state] || "") : "";
    }

    // One request in flight per field. A flush asked for while one is out
    // waits for it, and then sends what the field holds by then: the newest
    // text always lands last, and a reply never writes the field.
    function flush() {
      clearTimeout(timer);
      timer = null;
      if (field.value === saved) return;
      if (field.hasAttribute("data-skip-empty") && !field.value.trim()) return;
      if (inflight) { again = true; return; }
      inflight = true;
      var sending = field.value;
      var data = new FormData();
      data.set(field.name, sending);
      say("saving");
      send(field.dataset.autosave, data)
        .then(function () {
          saved = sending;
          say(field.value === saved ? "saved" : "saving");
          field.dispatchEvent(new CustomEvent("saved", { bubbles: true }));
        })
        .catch(function (error) {
          say("");
          toast(error.message || texts.saveFailed);    // the text stays in the field
        })
        .then(function () {
          inflight = false;
          if (again) { again = false; flush(); }
        });
    }

    function schedule() {
      clearTimeout(timer);
      timer = setTimeout(flush, DELAY);
    }

    field.addEventListener("input", schedule);
    field.addEventListener("blur", flush);
    if (field.form) {
      field.form.addEventListener("submit", function (event) {
        event.preventDefault();          // Enter in the title: save now, stay here
        flush();
      });
    }
    // A value from elsewhere (the model named the idea): taken only when
    // nobody is typing in the field and nothing of theirs is unsaved.
    field.oknowledgeSettle = function (value) {
      if (document.activeElement === field || field.value !== saved || inflight) return false;
      field.value = value;
      saved = value;
      return true;
    };
  }

  function bind(root) {
    var scope = root || document;
    scope.querySelectorAll("[data-nojs]").forEach(function (el) { el.hidden = true; });
    scope.querySelectorAll("[data-autosave]").forEach(watchField);
  }

  window.oknowledge = { toast: toast, post: post, bind: bind };
  bind(document);
})();
```

- [ ] **Step 4: idea.js**

`src/oknowledge/web/static/idea.js`:

```js
// An idea's screen without reloads (spec §2, §2.2). The server draws every
// part; this asks for the screen again and swaps the parts that changed.
// Without it every link and form here still works, a page at a time.
(function () {
  "use strict";
  var root = document.getElementById("idea");
  var ok = window.oknowledge;
  if (!root || !ok) return;
  var id = root.dataset.id;
  var POLL = 3000;
  var TAB_OF = { exists: "existe", improve: "mejoras", expand: "ampliacion", complete: "resumen" };

  function here() { return new URL(location.href); }

  function setParam(name, value, fallback) {
    var url = here();
    if (!value || value === fallback) url.searchParams.delete(name);
    else url.searchParams.set(name, value);
    history.replaceState(null, "", url.pathname + url.search);
  }

  function parse(html) { return new DOMParser().parseFromString(html, "text/html"); }

  // The screen again, as the URL says it now, and the named parts swapped in.
  function refresh(ids) {
    return fetch(location.href, { headers: { Accept: "text/html" } })
      .then(function (r) {
        if (r.status === 404) { gone(); throw new Error("gone"); }
        if (!r.ok) throw new Error(r.status);
        return r.text();
      })
      .then(function (html) {
        var page = parse(html);
        ids.forEach(function (name) {
          var fresh = page.getElementById(name);
          var old = document.getElementById(name);
          if (fresh && old) old.replaceWith(document.adoptNode(fresh));
        });
        ok.bind(document);
      })
      .catch(function () { /* the next poll or click tries again */ });
  }

  // --- tabs and scope ---------------------------------------------------------
  function openTab(key) {
    document.querySelectorAll("a[data-tab]").forEach(function (a) {
      a.classList.toggle("on", a.dataset.tab === key);
    });
    document.querySelectorAll("[data-pane]").forEach(function (pane) {
      pane.hidden = pane.dataset.pane !== key;
    });
    setParam("pestana", key, "resumen");
  }

  document.addEventListener("click", function (event) {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey) return;
    var tab = event.target.closest("a[data-tab]");
    if (tab) { event.preventDefault(); openTab(tab.dataset.tab); return; }
    var scope = event.target.closest("a[data-scope]");
    if (scope) {
      event.preventDefault();
      var menu = scope.closest("details");
      if (menu) menu.open = false;
      setParam("alcance", scope.dataset.scope, "vinculados");
      refresh(["idea-ai", "idea-results"]);
    }
  });

  // --- writes -------------------------------------------------------------------
  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (!form.matches("form[data-json]")) return;
    event.preventDefault();
    var menu = form.closest("details");
    if (menu) menu.open = false;
    ok.post(form, event.submitter)
      .then(function () {
        if (form.dataset.runs) started(form.dataset.runs);
        else if (form.hasAttribute("data-links")) { search(); refresh(["idea-ai"]); }
        else refresh(["idea-controls", "idea-tags"]);
      })
      .catch(function (error) {
        if (error.status === 404) { gone(); return; }
        ok.toast(error.message);
      });
  });

  // --- the column of links --------------------------------------------------
  var box = document.getElementById("links-q");
  var searchAsked = 0;
  var searchTimer = null;

  function search() {
    if (!box) return;
    var mine = ++searchAsked;
    var q = box.value.trim().split(/\s+/).join(" ");
    fetch(box.dataset.results + "?q=" + encodeURIComponent(q))
      .then(function (r) {
        if (r.status === 404) { gone(); throw new Error("gone"); }
        if (!r.ok) throw new Error(r.status);
        return r.text();
      })
      .then(function (html) {
        if (mine !== searchAsked) return;        // a newer search is on its way
        var fresh = parse(html).getElementById("idea-links-body");
        var old = document.getElementById("idea-links-body");
        if (!fresh || !old) return;
        old.replaceWith(document.adoptNode(fresh));
        var count = document.getElementById("idea-links-count");
        if (count) count.textContent = fresh.dataset.linked;
        setParam("q", q, "");
      })
      .catch(function () { /* the next key tries again */ });
  }

  if (box) {
    box.addEventListener("input", function () {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(search, 250);
    });
    box.form.addEventListener("submit", function (event) {
      event.preventDefault();
      clearTimeout(searchTimer);
      search();
    });
  }

  // --- while the AI works ---------------------------------------------------------
  var bar = document.getElementById("idea-ai");
  var running = (bar && bar.dataset.running || "").split(" ").filter(Boolean);
  var polling = null;

  function started(action) {
    if (running.indexOf(action) < 0) running.push(action);
    openTab(TAB_OF[action] || "resumen");
    refresh(["idea-ai", "idea-results"]);
    poll();
  }

  function poll() {
    if (polling || !running.length) return;
    polling = setInterval(tick, POLL);
  }

  function stop() {
    clearInterval(polling);
    polling = null;
  }

  function nameOf(action) {
    var now = document.getElementById("idea-ai") || bar;
    return now.dataset["name" + action.charAt(0).toUpperCase() + action.slice(1)] || action;
  }

  function settleTitle(title) {
    var field = document.getElementById("idea-title");
    if (field && title && field.oknowledgeSettle && field.oknowledgeSettle(title)) {
      field.classList.remove("waiting");
      document.title = title + " - oknowledge";
    }
  }

  function tick() {
    fetch("/item/" + encodeURIComponent(id) + "/actions/state",
          { headers: { Accept: "application/json" } })
      .then(function (r) {
        if (r.status === 404) { stop(); gone(); return null; }
        if (!r.ok) throw new Error(r.status);
        return r.json();
      })
      .then(function (state) {
        if (!state) return;
        var ended = running.filter(function (a) { return state.running.indexOf(a) < 0; });
        var now = document.getElementById("idea-ai") || bar;
        ended.forEach(function (action) {
          var failed = state.failed.indexOf(action) >= 0;
          ok.toast((failed ? now.dataset.failedAs : now.dataset.doneAs).replace("%1", nameOf(action)));
          if (action === "complete") settleTitle(state.title);
        });
        running = state.running.slice();
        if (ended.length) {
          openTab(TAB_OF[ended[ended.length - 1]] || "resumen");
          refresh(["idea-ai", "idea-results", "idea-tags"]);
        }
        if (!running.length) stop();
      })
      .catch(function () { /* try again in three seconds */ });
  }

  // Hoisted: refresh() and search() call it too.
  function gone() { location.href = "/ideas?notice=no-such-idea"; }

  poll();
})();
```

In `idea.html` add, after the `app_class` block:

```jinja
{% block scripts %}<script src="/static/autosave.js" defer></script><script src="/static/idea.js" defer></script>{% endblock %}
```

Append to `app.css`:

```css
[data-nojs][hidden] { display: none !important; }
```

- [ ] **Step 5: Run the tests**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_idea_scripts.py tests/test_packaging.py tests/test_web_idea_screen.py`
Expected: PASS.

- [ ] **Step 6: Check it in a browser**

The race (Review Focus 1), the poll and the deleted idea (Review Focus 3), with the server's answers held back or faked by Playwright, on the scratch vault:

```bash
SP=/tmp/claude-1000/-home-fer-Projects-gym/d89ecc8a-2029-44cb-b47f-742ed00daeae/scratchpad
~/.local/share/oknowledge/venv/bin/python "$SP/shots/serve.py" > "$SP/serve.log" 2>&1 &
echo $! > "$SP/serve.pid"
cd "$SP/pw" && [ -d node_modules/playwright ] || npm install --no-save --silent playwright
cat > "$SP/pw/idea-screen.js" <<'EOF'
const { chromium } = require("playwright");
const fs = require("fs");
const ID = fs.readFileSync(process.argv[2], "utf8").trim();
const BASE = "http://127.0.0.1:8812";
(async () => {
  const browser = await chromium.launch({ executablePath: "/usr/bin/chromium" });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  // 1. The race: the first save is held 1.5 s; typing goes on meanwhile.
  const sent = [];
  let first = true;
  await page.route("**/mine/note", async (route) => {
    sent.push(route.request().postDataBuffer().toString());
    if (first) { first = false; await new Promise((r) => setTimeout(r, 1500)); }
    await route.continue();
  });
  await page.goto(`${BASE}/ideas/${ID}`);
  console.log("save buttons visible", await page.locator("button:has-text('Guardar'):visible").count());
  await page.fill("#idea-text", "uno");
  await page.waitForTimeout(1100);                         // the first save is out
  await page.type("#idea-text", " dos");
  await page.waitForTimeout(1100);                         // a second flush while it is out
  await page.waitForTimeout(2500);
  console.log("posts", sent.length, "last carries 'uno dos'", /uno\+dos/.test(sent[sent.length - 1]));
  await page.reload();
  console.log("on disk", JSON.stringify(await page.inputValue("#idea-text")));
  console.log("indicator", await page.textContent("#save-state"));
  // 2. An action that ends: the tab opens and the toast says so.
  await page.route("**/actions/improve", (r) => r.fulfill({ json: { ok: true, notice: "" } }));
  let calls = 0;
  await page.route("**/actions/state", (r) => {
    calls += 1;
    r.fulfill({ json: calls < 2 ? { running: ["improve"], failed: [], title: "" }
                                : { running: [], failed: [], title: "" } });
  });
  await page.click("#idea-ai button:has-text('Mejorar')");
  await page.waitForTimeout(7000);
  console.log("tab", new URL(page.url()).searchParams.get("pestana"),
              "toast", await page.locator(".toast").textContent().catch(() => ""));
  // 3. The idea is deleted while the screen polls.
  await page.unroute("**/actions/state");
  await page.route("**/actions/state", (r) => r.fulfill({ status: 404, json: { ok: false, running: [], failed: [], title: "" } }));
  await page.click("#idea-ai button:has-text('Ampliar')");
  await page.waitForURL("**/ideas?notice=no-such-idea", { timeout: 8000 });
  console.log("went to", new URL(page.url()).pathname + new URL(page.url()).search);
  console.log("scroll", await page.evaluate(() => document.scrollingElement.scrollHeight <= innerHeight));
  await browser.close();
})();
EOF
node "$SP/pw/idea-screen.js" "$SP/shots/idea"
ps -p "$(cat "$SP/serve.pid")" -o args= | grep -q serve.py && kill "$(cat "$SP/serve.pid")"
```

Expected:

```
save buttons visible 0
posts 2 last carries 'uno dos' true
on disk "uno dos"
indicator Guardado
tab mejoras toast Listo: Mejoras
went to /ideas?notice=no-such-idea
scroll true
```

(`posts 2`: the second flush waited for the first instead of racing it. If the scratch vault is from delivery 1 and the idea's text was already changed by a previous run, the result is the same: the check writes it.)

- [ ] **Step 7: Whole suite, commit**

Run the suite; expected green.

```bash
git add src/oknowledge/web/static/autosave.js src/oknowledge/web/static/idea.js \
        src/oknowledge/web/templates/idea.html src/oknowledge/web/static/app.css \
        tests/test_web_idea_scripts.py tests/test_packaging.py
git commit -m "Save an idea as you type and refresh its screen in place while the AI works"
```

---
### Task 7: The old idea page goes

**Files:**
- Modify: `src/oknowledge/web/app.py` — `item()` (≈897): an idea redirects to `/ideas/{id}`; its `ideas` branch, `ACTION_TITLES` (≈404), `ACTION_BUTTONS` (≈408) and the `blocks, split_suggestions` import go
- Modify: `src/oknowledge/web/templates/item.html` — the `{% if idea %}…{% endif %}` block (≈103–270), the idea halves of `body_class`, `scripts` and `has-aside`, and the `link-card.html` import
- Modify: `src/oknowledge/web/markup.py` (delete `blocks`, `split_suggestions` and the regexes only they use)
- Modify: `src/oknowledge/web/static/style.css` (the rules of the old idea page), `src/oknowledge/i18n.py` (the keys nothing asks for any more)
- Delete: `src/oknowledge/web/static/idea-links.js`, `src/oknowledge/web/templates/idea-link-results.html`, `src/oknowledge/web/templates/link-card.html`, `tests/test_web_idea_links_column.py`
- Test: `tests/test_web_idea_redirect.py` (new); edits listed in the ledger

**Interfaces:**
- Consumes: `idea_url()` (Task 3).
- Produces: `GET /item/{id}` of an idea → 303 to `/ideas/{id}` carrying `notice`, `n`, `m`. The no-JS writes on an idea (state, stars, tags, text) still answer with `item_url(id)`, which now lands on the screen through this redirect.

- [ ] **Step 1: Write the failing tests**

`tests/test_web_idea_redirect.py`:

```python
"""An idea has one page, its screen (spec §1, "Lo que se va")."""

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.vault import note_path, rebuild_indexes, write_note
from oknowledge.web.app import create_app


@pytest.fixture
def cfg(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    config = Config(vault=vault)
    rebuild_indexes(config, "es")
    return config


def put(cfg):
    note = new_idea("Una vpn.", "VPN", "2026-10-12", "2026-10-12T00:00:00.000001+00:00")
    write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ideas))
    return note


def test_an_idea_s_old_address_opens_its_screen(cfg):
    note = put(cfg)
    answer = TestClient(create_app(cfg)).get(f"/item/{note.id}", follow_redirects=False)
    assert answer.status_code == 303
    assert answer.headers["location"] == f"/ideas/{note.id}"


def test_the_redirect_carries_the_notice(cfg):
    note = put(cfg)
    answer = TestClient(create_app(cfg)).get(f"/item/{note.id}?notice=moved&n=2&m=1",
                                              follow_redirects=False)
    assert answer.headers["location"] == f"/ideas/{note.id}?notice=moved&n=2&m=1"


def test_a_write_without_javascript_ends_on_the_screen(cfg):
    note = put(cfg)
    answer = TestClient(create_app(cfg)).post(f"/item/{note.id}/mine/state",
                                              data={"state": "doing"})
    assert answer.status_code == 200
    assert str(answer.url).endswith(f"/ideas/{note.id}?notice=saved")


@pytest.mark.parametrize("name", ["idea-links.js"])
def test_the_old_script_is_not_served(cfg, name):
    assert TestClient(create_app(cfg)).get(f"/static/{name}").status_code == 404


def test_the_old_templates_are_gone():
    from importlib.resources import files
    templates = files("oknowledge.web").joinpath("templates")
    for name in ("idea-link-results.html", "link-card.html", "ideas.html"):
        assert not templates.joinpath(name).is_file()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_idea_redirect.py`
Expected: FAIL — `/item/{idea}` answers 200 with the old page; `idea-links.js` is served.

- [ ] **Step 3: Redirect, and cut the idea out of `item()`**

In `item()`, right after the `links` redirect:

```python
        if where.name == "ideas":
            params = request.query_params
            return see_other(idea_url(link_id), notice=params.get("notice"),
                             n=params.get("n"), m=params.get("m"))
```

Delete the `if where.name == "ideas":` branch that built `extra` (the `elif where.name == "ocio":` becomes `if where.name == "ocio":`), the `q` parameter of `item()`, `idea=where.name == "ideas"` from its `page()` call, `ACTION_TITLES`, `ACTION_BUTTONS`, and `blocks, split_suggestions` from the `.markup` import (keep `section_cards`). `grep -n "ACTION_TITLES\|ACTION_BUTTONS\|split_suggestions\|blocks(" src/` must print nothing.

In `markup.py` delete `blocks()`, `split_suggestions()` and any regex only they read (`grep -n` each name first; `_ITEM` and `inline` stay — `section_cards` uses them).

In `item.html`: delete line 2 (`{% from "link-card.html" … %}`), make `body_class` and `scripts` empty for every note (`{% block body_class %}{% endblock %}` and no `scripts` block), `<article class="item">` without `has-aside`, and delete the whole `{% if idea %}` … its matching `{% endif %}` block (≈103–270). What stays is the card half (until Task 10) and the parts both used.

Delete `static/idea-links.js`, `templates/idea-link-results.html`, `templates/link-card.html`.

In `style.css` delete the rules whose selectors name only the old idea page: `grep -n "idea-links\|\.idea-\|has-aside\|tab-switch\|tab-pane\|idea-cards\|idea-go\|idea-search\|\.suggested\|\.why" src/oknowledge/web/static/style.css` and remove each rule it finds (a rule that also names a selector still in use keeps that selector). `app.css`'s `.tab-pane` rules (Task 3) are the new screen's and stay.

- [ ] **Step 4: The ledger**

Edit these tests, then delete the ones listed — each reads the old page, and what it checked is now in `tests/test_web_idea_screen.py`, `tests/test_web_idea_screen_links.py` or left the spec:

- `tests/test_web_idea_links_column.py`: the whole file (the aside is `links-column`, tested in `tests/test_web_idea_screen_links.py`).
- `tests/test_web_idea_actions.py`: `page()` reads `f"/ideas/{note.id}"`; `test_the_last_failure_is_shown_and_cleared_by_a_success` reads `f"/ideas/{note.id}"` both times and is kept, as is `test_a_section_cannot_inject_markup_or_script_links` and `test_exists_is_disabled_with_its_reason_when_nobody_searches`. Delete `test_the_four_buttons_are_there` (three buttons now, `test_the_ai_bar_has_three_actions_and_the_scope`), `test_a_running_action_says_thinking_and_is_disabled` (`test_a_running_action_is_off_and_said`), `test_exists_is_offered_when_the_chain_searches`, `test_a_section_with_text_is_drawn_under_its_heading` (`test_improvements_are_cards_of_title_and_detail_under_the_links_line`), `test_a_suggestion_offers_add_to_the_idea`, `test_a_suggestion_already_linked_offers_nothing`, `test_a_gone_suggestion_is_dimmed_and_cannot_be_added`, `test_the_category_picker_lists_the_library` (the "links" action left the interface, spec decisions), `test_blocks_group_bullets_into_one_list`, `test_suggestions_are_split_from_the_rest` (the functions are gone; `test_inline_escapes_first_and_links_only_the_web` stays) and every test from `test_the_actions_sit_between_your_text_and_save` to `test_the_links_search_is_labelled_and_its_button_says_search` (the old page's layout). Remove `blocks` and `split_suggestions` from its imports.
- `tests/test_web_ideas_mine.py`: `page_of()` reads `f"/ideas/{note.id}"`. Delete `test_the_page_offers_your_title_and_text_to_edit` (`test_the_title_is_a_box_that_saves_itself`, `test_your_idea_fills_the_left_and_saves_itself`), `test_an_untitled_idea_has_a_heading` (the title is an input with a placeholder) and `test_an_idea_s_tags_lead_to_the_ideas` (no tag filter in the list, Task 5). In `test_a_page_opened_before_the_model_named_it_keeps_the_name` delete the two lines `page = page_of(client, note)` and `assert 'name="title_was" value=""' in page` (the route's guard stays and is what the test checks).
- `tests/test_web_ideas_related.py`: delete `test_the_idea_shows_its_links_by_their_real_titles` and `test_a_link_that_is_not_there_any_more_is_dimmed_not_dropped` (`test_a_linked_link_is_a_row_that_opens_in_the_library`, `test_a_gone_link_is_dimmed_and_can_still_go`).

Then `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_i18n.py` and delete each key `test_every_translated_string_is_one_the_code_asks_for` names (the old page's: "Add to the idea", "Ask again", "already linked", "Search", "Use", and the rest it lists — exactly those).

- [ ] **Step 5: Run the tests**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_idea_redirect.py tests/test_web_idea_actions.py tests/test_web_ideas_mine.py tests/test_web_ideas_related.py tests/test_web_idea_screen.py tests/test_i18n.py tests/test_web_read.py`
Expected: PASS (`test_web_read.py` holds `test_no_template_marks_note_content_safe`, which walks every template).

- [ ] **Step 6: Whole suite, commit**

Run the suite; expected green, minus the ledger.

```bash
git add -A src/oknowledge tests
git commit -m "Send an idea's old page to its screen and delete what only that page used"
```

---
### Task 8: Ocio's centre: filters, order and the poster grid

**Files:**
- Modify: `src/oknowledge/web/shelf_view.py` (append the Ocio half)
- Create: `src/oknowledge/web/templates/ocio-shelf.html`, `ocio-list.html`, `ocio-list-more.html`, `posters.html`
- Delete: `src/oknowledge/web/templates/ocio.html`, `src/oknowledge/web/templates/embed.html`, `src/oknowledge/web/static/popup.js`
- Modify: `src/oknowledge/web/app.py` — `leisure` (≈1787) rewritten, new `GET /ocio/lista`, `rewrite_every_card` (≈1806) answers through `answer()`, the `/embed/{id}` route (≈946) and `"/embed/"` in `not_found` go, `KIND_WORDS`/`STATE_ORDER`/`_count_by` go when nothing reads them
- Modify: `src/oknowledge/web/static/app.css`, `src/oknowledge/i18n.py`
- Test: `tests/test_shelf_view_ocio.py` (new), `tests/test_web_ocio_shelf.py` (new); delete `tests/test_web_ocio_page.py`'s page tests and the others in the ledger; `tests/test_packaging.py:95` drops `"popup.js"`

**Interfaces:**
- Consumes: `library_view.CHUNK`, `LAYOUTS`, `_count`; `sidebar.html`'s `filters` (Task 5); `rewriting.all_of("describe") -> (set[str], dict[str, str])`.
- Produces:
  - `shelf_view`: `KIND_HUES = {"movie": 300, "series": 200, "anime": 20, "book": 60}`, `KIND_NAMES` (plural, sidebar), `KIND_ONE` (singular, chips), `CARD_WORDS[kind][state]`, `CARD_DOTS`, `SORTS`, `words_for(kind) -> dict`, `poster_fill(kind) -> str`, `kind_dot(kind) -> str`, `catalog_name(source) -> str`, `year_of(note) -> int | None`.
  - `CardView(tipo="", estado="", q="", sel="", orden="recientes", hasta=CHUNK)` — frozen; `from_query(params)`, `url(path="/ocio", **changes)`, `label(t)`.
  - `choose_cards(notes, view) -> list[Note]` (filtered and sorted), `sort_cards(notes, orden) -> list[Note]`, `card_filters(notes, view) -> list[dict]` (TYPE then STATE; same row shape as Task 5).
  - `card_listing(view) -> dict` in `app.py` (keys `view, notes, chosen, total, more, chunk, current, unrewritten, rewriting_all, busy`), used by `/ocio` and `/ocio/lista`.
  - `posters.html`: `{% macro poster(note, view, current, busy) %}` → `<li class="item poster…" id="card-{id}">` with `<a class="hit" href="{{ view.url(sel=id) }}" data-sel="{id}">`.
  - `/ocio` draws `<section class="detail" id="panel">` with the empty text; Task 9 fills it. No script on `/ocio` until Task 11.

- [ ] **Step 1: Write the failing tests**

`tests/test_shelf_view_ocio.py`:

```python
"""Ocio as one URL describes it (spec §3): pure, no app."""

import pytest

from oknowledge.model import Note
from oknowledge.web.library_view import CHUNK
from oknowledge.web.shelf_view import (CardView, card_filters, catalog_name, choose_cards,
                                       poster_fill, sort_cards, year_of)


def card(title, kind="movie", saved="2026-10-01", published=None, score=0, state="",
         tags=(), author=None):
    return Note(id=title.lower().replace(" ", "")[:12].ljust(12, "x"), url="https://imdb.com/x",
                title=title, category="Películas", tags=list(tags), type=kind,
                source="imdb.com", saved=saved, summary="s", published=published,
                score=score, state=state, author=author)


def titles(notes):
    return [n.title for n in notes]


def test_unknown_values_are_all_and_recent():
    view = CardView.from_query({"tipo": "podcast", "estado": "dropped", "orden": "x",
                                "hasta": "3"})
    assert (view.tipo, view.estado, view.orden, view.hasta) == ("", "", "recientes", CHUNK)


def test_the_url_leaves_out_the_defaults_and_keeps_the_rest():
    assert CardView().url() == "/ocio"
    view = CardView(tipo="book", estado="done", orden="anio")
    assert view.url(sel="abc") == "/ocio?tipo=book&estado=done&sel=abc&orden=anio"
    assert CardView(q="dune").url("/ocio/lista", desde=60) == "/ocio/lista?q=dune&desde=60"


def test_the_label():
    t = lambda text, *a: text
    assert CardView().label(t) == "Leisure"
    assert CardView(tipo="book").label(t) == "Books"
    assert CardView(tipo="book", estado="doing").label(t) == "Books · Reading"
    assert CardView(estado="done").label(t) == "Watched"
    assert CardView(q="x").label(t) == "Results"


def test_recent_is_newest_saved_first():
    notes = [card("A", saved="2026-10-01"), card("B", saved="2026-10-03"), card("C", saved="2026-10-02")]
    assert titles(sort_cards(notes, "recientes")) == ["B", "C", "A"]


def test_title_ignores_case_and_accents():
    notes = [card("Ébano"), card("alien"), card("Dune")]
    assert titles(sort_cards(notes, "titulo")) == ["alien", "Dune", "Ébano"]


def test_year_newest_first_and_missing_or_odd_years_last():
    """Review Focus 4: no year, or a published nobody can read, goes last,
    newest saved first among them; nothing raises."""
    notes = [card("Old", published="1984-10-26"), card("None", saved="2026-10-05"),
             card("New", published="2021"), card("Odd", published="s/f", saved="2026-10-09")]
    assert titles(sort_cards(notes, "anio")) == ["New", "Old", "Odd", "None"]
    assert year_of(card("x", published="s/f")) is None
    assert year_of(card("x", published="1999-01-01")) == 1999


def test_stars_most_first_and_none_last():
    """Review Focus 4: 0 stars last, newest first among them."""
    notes = [card("Two", score=2), card("Zero", saved="2026-10-02"), card("Five", score=5),
             card("Zero too", saved="2026-10-04")]
    assert titles(sort_cards(notes, "estrellas")) == ["Five", "Two", "Zero too", "Zero"]


def test_choose_filters_kind_state_and_words():
    notes = [card("Dune", kind="book", state="done", author="Frank Herbert"),
             card("Alien", state="done", tags=("terror",)), card("Bebop", kind="anime")]
    assert titles(choose_cards(notes, CardView(tipo="book"))) == ["Dune"]
    assert titles(choose_cards(notes, CardView(estado="done", orden="titulo"))) == ["Alien", "Dune"]
    assert titles(choose_cards(notes, CardView(q="herbert"))) == ["Dune"]
    assert titles(choose_cards(notes, CardView(q="#terror"))) == ["Alien"]


def test_the_type_group_hides_a_kind_with_no_cards():
    notes = [card("Dune", kind="book"), card("Alien")]
    kinds, states = card_filters(notes, CardView())
    assert kinds["title"] == "TYPE"
    assert [(r["label"], r["count"]) for r in kinds["rows"]] == [("All", 2), ("Movies", 1), ("Books", 1)]
    assert kinds["rows"][2]["href"] == "/ocio?tipo=book"


def test_the_state_group_speaks_the_kind_and_counts_within_it():
    notes = [card("Dune", kind="book", state="doing"), card("Alien", state="doing"),
             card("Solaris", kind="book")]
    _, states = card_filters(notes, CardView(tipo="book", estado="doing"))
    assert states["title"] == "STATE"
    assert [(r["label"], r["count"], r["on"]) for r in states["rows"]] == [
        ("All", 2, False), ("To read", 0, False), ("Reading", 1, True), ("Read", 0, False)]
    assert states["rows"][2]["dot"] == "#a9b4de"
    assert states["rows"][2]["href"] == "/ocio?tipo=book&estado=doing"


def test_a_filter_keeps_the_order_and_drops_the_search_and_the_pick():
    kinds, _ = card_filters([card("Alien")], CardView(q="x", sel="abc", orden="anio"))
    assert kinds["rows"][1]["href"] == "/ocio?tipo=movie&orden=anio"


def test_a_poster_without_a_cover_is_its_kind_s_gradient():
    """Review Focus 5."""
    assert poster_fill("movie") == ("linear-gradient(160deg, oklch(0.42 0.06 300), "
                                    "oklch(0.18 0.03 300))")
    assert poster_fill("book").endswith("oklch(0.18 0.03 60))")
    assert poster_fill("podcast") == "linear-gradient(160deg, #2a2c34, #17181d)"


def test_the_catalog_is_named_like_people_say_it():
    assert catalog_name("imdb.com") == "IMDb"
    assert catalog_name("openlibrary.org") == "Open Library"
    assert catalog_name("example.com") == "example.com"
```

`tests/test_web_ocio_shelf.py`:

```python
"""/ocio (spec §3): sidebar TIPO/ESTADO, the poster grid, the panel column."""

import re

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.vault import note_path, rebuild_indexes, write_note
from oknowledge.web.app import create_app


@pytest.fixture(autouse=True)
def state_tree(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr("oknowledge.web.app.CONFIG_PATH", tmp_path / "config" / "config.toml")


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


def put(cfg, n, title, kind="movie", **over):
    fields = dict(id=f"c{n:011d}", url=f"https://www.imdb.com/title/tt{n}", title=title,
                  category="Películas", tags=["drama"], type=kind, source="imdb.com",
                  saved=f"2026-10-{n:02d}", summary="Algo pasa.", engine="fake")
    fields.update(over)
    note = Note(**fields)
    write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ocio))
    return note


def grid(body):
    head = body.index('<ul class="posters"')
    return body[head:body.index("</ul>", head)]


def test_three_columns_with_the_panel(cfg, client):
    put(cfg, 1, "Alien")
    body = client.get("/ocio").text
    assert '<div class="app ocio">' in body
    assert 'id="list"' in body and 'data-source="/ocio/lista"' in body
    assert 'id="panel"' in body


def test_the_field_says_what_it_takes(client):
    body = client.get("/ocio").text
    form = re.search(r'<form[^>]*id="unified"[^>]*>', body).group(0)
    assert 'action="/ocio"' in form and 'data-mode="ocio"' in form
    assert ('placeholder="Search Leisure or paste a link from IMDb or Open Library"'
            in body)


def test_the_head_counts_and_offers_the_four_orders(cfg, client):
    put(cfg, 1, "Alien"), put(cfg, 2, "Brazil")
    body = client.get("/ocio").text
    assert re.search(r"Leisure · <b class=\"mono\">2</b>", body)
    for key, label in (("recientes", "Recent"), ("titulo", "Title"), ("anio", "Year"),
                       ("estrellas", "Your stars")):
        assert f">{label}<" in body
    assert 'href="/ocio?orden=titulo"' in body
    assert "Recent ▾" in body


def test_the_order_comes_from_the_url(cfg, client):
    put(cfg, 1, "Brazil"), put(cfg, 2, "Alien")
    body = client.get("/ocio?orden=titulo").text
    assert body.index(">Alien<") < body.index(">Brazil<")
    assert "Title ▾" in body


def test_a_poster_with_a_cover_and_its_chips(cfg, client):
    note = put(cfg, 1, "Alien", cover="../attachments/a.jpg", state="done", score=4,
               published="1979-05-25", rating="8.5")
    item = grid(client.get("/ocio").text)
    assert f'<img src="/cover/{note.id}"' in item
    assert '<span class="chip kind">Movie</span>' in item
    assert '<span class="chip state">' in item and "Watched" in item
    assert "1979" in item and "IMDb 8.5" in item
    assert item.count('class="star on"') == 4


def test_a_poster_without_a_cover_is_the_gradient_with_the_title(cfg, client):
    """Review Focus 5: no <img>, no /cover request."""
    note = put(cfg, 1, "Alien")
    item = grid(client.get("/ocio").text)
    assert "<img" not in item and "/cover/" not in item
    assert "linear-gradient(160deg, oklch(0.42 0.06 300), oklch(0.18 0.03 300))" in item
    assert '<span class="fill-title" dir="auto">Alien</span>' in item


def test_a_kind_nobody_knows_gets_the_neutral_fill(cfg, client):
    """Review Focus 5: a hand-edited type."""
    put(cfg, 1, "Raro", kind="podcast")
    item = grid(client.get("/ocio").text)
    assert "linear-gradient(160deg, #2a2c34, #17181d)" in item
    assert '<span class="chip kind">' not in item


def test_no_state_no_state_chip(cfg, client):
    put(cfg, 1, "Alien")
    assert '<span class="chip state">' not in grid(client.get("/ocio").text)


def test_the_first_card_is_selected_and_an_unknown_sel_too(cfg, client):
    put(cfg, 1, "Alien"), put(cfg, 2, "Brazil")
    for query in ("", "?sel=nope"):
        body = client.get("/ocio" + query).text
        assert re.search(r'<li class="item poster on" id="card-c00000000002"', body)


def test_the_sidebar_has_type_and_state(cfg, client):
    put(cfg, 1, "Alien"), put(cfg, 2, "Dune", kind="book", category="Libros", state="doing")
    body = client.get("/ocio?tipo=book").text
    side = body[body.index('<aside class="sidebar"'):body.index("</aside>")]
    assert "TYPE" in side and "STATE" in side
    assert ">Movies<" in side and ">Books<" in side and ">Series<" not in side
    assert ">To read<" in side and ">Reading<" in side and ">To watch<" not in side


def test_kind_and_state_filter_the_grid(cfg, client):
    put(cfg, 1, "Alien", state="done"), put(cfg, 2, "Dune", kind="book", category="Libros")
    assert ">Dune<" not in client.get("/ocio?tipo=movie").text
    assert ">Dune<" not in client.get("/ocio?estado=done").text


def test_unknown_filters_show_everything(cfg, client):
    put(cfg, 1, "Alien")
    for query in ("?tipo=podcast", "?estado=dropped", "?orden=x"):
        assert ">Alien<" in client.get("/ocio" + query).text


def test_the_search_reads_title_author_and_tags(cfg, client):
    put(cfg, 1, "Dune", kind="book", category="Libros", author="Frank Herbert")
    put(cfg, 2, "Alien")
    column = client.get("/ocio/lista?q=herbert").text
    assert "<html" not in column and ">Dune<" in column and ">Alien<" not in column


def test_the_column_alone_comes_in_chunks(cfg, client):
    for n in range(1, 63):
        put(cfg, n, f"Película {n}", saved=f"2026-{1 + n // 28:02d}-{n % 28 + 1:02d}")
    body = client.get("/ocio").text
    assert grid(body).count('class="item poster') == 60
    assert 'data-more="/ocio/lista?desde=60"' in body
    assert client.get("/ocio/lista?desde=60").text.count('class="item poster') == 2


def test_the_unrewritten_notice_only_when_there_are_some(cfg, client):
    put(cfg, 1, "Alien")
    assert "not rewritten" not in client.get("/ocio").text
    put(cfg, 2, "Brazil", engine="")
    put(cfg, 3, "Cube", engine="")
    body = client.get("/ocio").text
    assert "2 cards not rewritten" in body
    assert 'action="/ocio/reescribir"' in body and ">Rewrite<" in body


def test_one_unrewritten_card_is_said_in_the_singular(cfg, client):
    put(cfg, 1, "Alien", engine="")
    assert "1 card not rewritten" in client.get("/ocio").text


def test_while_they_are_rewritten_the_notice_says_so(cfg, client):
    put(cfg, 1, "Alien", engine="")
    app = create_app(cfg)
    app.state.rewriting.start("c00000000001", "describe")
    body = TestClient(app).get("/ocio").text
    assert "Rewriting…" in body and 'action="/ocio/reescribir"' not in body


def test_an_empty_shelf_says_how_to_start(client):
    assert "Nothing in Leisure yet" in client.get("/ocio").text


def test_the_old_fragment_and_popup_are_gone(cfg, client):
    put(cfg, 1, "Alien")
    assert client.get("/embed/c00000000001").status_code == 404
    assert client.get("/static/popup.js").status_code == 404
```

(`app.state.rewriting` is the `Working` that tracks rewrites, set in `create_app` ≈689.)

**Ledger — tests deleted here:** all of `tests/test_web_ocio_page.py` except `test_the_nav_has_the_section`, `test_the_library_does_not_show_the_cards` and `test_a_link_never_offers_it` (move those three into `tests/test_web_ocio_shelf.py` unchanged with their fixtures, then delete the file) — the rest read `ocio.html` and are replaced test-for-test above (`test_the_four_kinds_filter` → `test_kind_and_state_filter_the_grid`, `test_an_unknown_*` → `test_unknown_filters_show_everything`, `test_a_card_nobody_rewrote_is_marked` → `test_the_unrewritten_notice_only_when_there_are_some`, `test_a_card_opens_from_the_section` → `test_the_first_card_is_selected_and_an_unknown_sel_too`); `tests/test_web_ocio_rewrite.py::test_a_failed_rewrite_is_told_on_the_shelf` (the failure is said in the card's panel, Task 9), `::test_the_shelf_offers_to_rewrite_what_is_left` and `::test_no_button_when_every_card_is_rewritten` (both → `test_the_unrewritten_notice_only_when_there_are_some`); `tests/test_web_cards.py` from `test_the_fragment_is_the_note_without_the_page_around_it` through `test_the_popup_script_is_served` and `test_the_popup_shows_it_too` (`/embed` and `popup.js` are gone, spec §1); `tests/test_web_ocio_mine.py::test_the_popup_of_a_card_opens`; `tests/test_web_layout.py::test_the_filters_fold_into_one_line` (the last path it had); `tests/test_web_marks.py::test_every_card_and_note_page_has_the_picker[/ocio-…]`, `::test_each_card_has_an_anchor_to_come_back_to` and `::test_the_picker_sends_you_back_where_you_were` (no marks in Ocio, spec decisions).

- [ ] **Step 2: Run them to verify they fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_shelf_view_ocio.py tests/test_web_ocio_shelf.py`
Expected: FAIL — `ImportError: CardView`; `/ocio` is still the old page.

- [ ] **Step 3: The view**

Append to `shelf_view.py` (add `import re`, `from .. import cards` and `from ..vault import STATES as CARD_STATES` to the imports):

```python
KIND_HUES = {"movie": 300, "series": 200, "anime": 20, "book": 60}
"""Each kind's hue for the poster with no cover (Ocio.dc.html)."""
KIND_NAMES = {"movie": "Movies", "series": "Series", "anime": "Anime", "book": "Books"}
KIND_ONE = {"movie": "Movie", "series": "Series", "anime": "Anime", "book": "Book"}
_WATCH = {"pending": "To watch", "doing": "Watching", "done": "Watched"}
_READ = {"pending": "To read", "doing": "Reading", "done": "Read"}
CARD_WORDS = {"movie": _WATCH, "series": _WATCH, "anime": _WATCH, "book": _READ}
CARD_DOTS = {"pending": "#6d6f78", "doing": "#a9b4de", "done": "#8fc29a"}
SORTS = (("recientes", "Recent"), ("titulo", "Title"), ("anio", "Year"),
         ("estrellas", "Your stars"))
_SORT_KEYS = {key for key, _ in SORTS}
CATALOGS = {"imdb.com": "IMDb", "openlibrary.org": "Open Library"}


def words_for(kind: str) -> dict[str, str]:
    """A book is read; everything else is watched -- and so is "All"."""
    return CARD_WORDS.get(kind, _WATCH)


def poster_fill(kind: str) -> str:
    hue = KIND_HUES.get(kind)
    if hue is None:
        return "linear-gradient(160deg, #2a2c34, #17181d)"
    return f"linear-gradient(160deg, oklch(0.42 0.06 {hue}), oklch(0.18 0.03 {hue}))"


def kind_dot(kind: str) -> str:
    hue = KIND_HUES.get(kind)
    return "#6d6f78" if hue is None else f"oklch(0.74 0.09 {hue})"


def catalog_name(source: str) -> str:
    return CATALOGS.get(source, source)


def year_of(note) -> int | None:
    """The year a card came out, or None for no date or one nobody can read."""
    found = re.match(r"(\d{4})", note.published or "")
    return int(found.group(1)) if found else None


@dataclass(frozen=True)
class CardView:
    """/ocio as its URL says it: `tipo`, `estado`, `q`, `sel`, `orden`,
    `hasta` (spec §3). Unknown values are All and Recent."""

    tipo: str = ""
    estado: str = ""
    q: str = ""
    sel: str = ""
    orden: str = "recientes"
    hasta: int = CHUNK

    @classmethod
    def from_query(cls, params: Mapping[str, str]) -> CardView:
        tipo, estado, orden = (params.get(k, "") for k in ("tipo", "estado", "orden"))
        return cls(tipo=tipo if tipo in cards.KINDS else "",
                   estado=estado if estado in CARD_STATES else "",
                   q=" ".join(params.get("q", "").split()), sel=params.get("sel", ""),
                   orden=orden if orden in _SORT_KEYS else "recientes",
                   hasta=_count(params.get("hasta", "")))

    def url(self, path: str = "/ocio", **changes) -> str:
        own = {k: v for k, v in changes.items() if k in _CARD_FIELDS}
        extra = [(k, str(v)) for k, v in changes.items() if k not in _CARD_FIELDS]
        view = dataclasses.replace(self, **own)
        pairs = [("tipo", view.tipo), ("estado", view.estado), ("q", view.q),
                 ("sel", view.sel), ("orden", view.orden if view.orden != "recientes" else ""),
                 ("hasta", str(view.hasta) if view.hasta != CHUNK else "")] + extra
        query = urlencode([(k, v) for k, v in pairs if v])
        return path + ("?" + query if query else "")

    def label(self, t) -> str:
        if self.q:
            return t("Results")
        state = t(words_for(self.tipo)[self.estado]) if self.estado else ""
        if self.tipo:
            name = t(KIND_NAMES[self.tipo])
            return f"{name} · {state}" if state else name
        return state or t("Leisure")


_CARD_FIELDS = {f.name for f in dataclasses.fields(CardView)}


def sort_cards(notes, orden: str) -> list:
    """Newest saved first, then the order asked for; Python's sort is stable,
    so the cards a key cannot tell apart stay newest first (spec §3)."""
    found = sorted(notes, key=lambda n: (n.saved, n.id), reverse=True)
    if orden == "titulo":
        return sorted(found, key=lambda n: fold(n.title))
    if orden == "anio":
        return sorted(found, key=lambda n: (year_of(n) is None, -(year_of(n) or 0)))
    if orden == "estrellas":
        return sorted(found, key=lambda n: -max(0, min(int(n.score or 0), 5)))
    return found


def choose_cards(notes, view: CardView) -> list:
    found = [n for n in notes if (not view.tipo or n.type == view.tipo)
             and (not view.estado or n.state == view.estado)]
    words = terms(view.q)
    if words:
        def text(n):
            return fold(" ".join([n.title, n.author or "", " ".join(n.tags)]))
        found = [n for n in found if all(word in text(n) for word in words)]
    return sort_cards(found, view.orden)


def card_filters(notes, view: CardView) -> list[dict]:
    """TIPO (a kind with no cards is not drawn) and ESTADO, in the words of
    the kind chosen, counted within it (spec §1)."""
    fresh = {"q": "", "sel": "", "hasta": CHUNK}
    kinds = [{"href": view.url(tipo="", **fresh), "label": "All", "dot": "#6d6f78",
              "count": len(notes), "on": not view.tipo}]
    for kind in cards.KINDS:
        count = sum(1 for n in notes if n.type == kind)
        if count:
            kinds.append({"href": view.url(tipo=kind, **fresh), "label": KIND_NAMES[kind],
                          "dot": kind_dot(kind), "count": count, "on": view.tipo == kind})
    within = [n for n in notes if not view.tipo or n.type == view.tipo]
    words = words_for(view.tipo)
    states = [{"href": view.url(estado="", **fresh), "label": "All", "dot": "#6d6f78",
               "count": len(within), "on": not view.estado}]
    states += [{"href": view.url(estado=state, **fresh), "label": words[state],
                "dot": CARD_DOTS[state], "count": sum(1 for n in within if n.state == state),
                "on": view.estado == state} for state in CARD_STATES]
    return [{"title": "TYPE", "rows": kinds}, {"title": "STATE", "rows": states}]
```

- [ ] **Step 4: The routes**

In `app.py` import from `.shelf_view` `CardView, KIND_ONE, CARD_DOTS, SORTS, card_filters, catalog_name, choose_cards, poster_fill, words_for`, and register `catalog_name`, `poster_fill` as Jinja filters next to `dot` (≈693). Replace `leisure`:

```python
    def card_listing(view: CardView) -> dict:
        shelf.refresh()
        notes = choose_cards(shelf.notes, view)
        ids = [n.id for n in notes]
        running, _ = rewriting.all_of("describe")
        left = [n.id for n in shelf.notes if not n.engine]
        return {"view": view, "notes": notes[:view.hasta], "chosen": notes,
                "total": len(notes), "more": len(notes) > view.hasta, "chunk": CHUNK,
                # A pick that is not in the list opens the first card (spec §3).
                "current": view.sel if view.sel in ids else (ids[0] if ids else ""),
                "unrewritten": len(left),
                "rewriting_all": bool(left) and all(i in running for i in left),
                "busy": running, "KIND_ONE": KIND_ONE, "CARD_DOTS": CARD_DOTS,
                "SORTS": SORTS, "words_for": words_for}

    @app.get("/ocio", response_class=HTMLResponse)
    def leisure(request: Request):
        """The cards (spec §3). An unknown filter shows everything rather
        than nothing: these arrive from a URL somebody can type."""
        view = CardView.from_query(request.query_params)
        shown = card_listing(view)
        return page(request, "ocio-shelf.html", section="ocio", toast=True,
                    filters=card_filters(shelf.notes, view),
                    save_prefixes=" ".join(sorted(cards.PREFIXES)),
                    unreadable_cards=shelf.unreadable, **shown)

    @app.get("/ocio/lista", response_class=HTMLResponse)
    def card_column(request: Request, desde: str = ""):
        shown = card_listing(CardView.from_query(request.query_params))
        if not desde:
            return page(request, "ocio-list.html", **shown)
        try:
            start = max(0, int(desde))
        except ValueError:
            start = 0
        end = start + CHUNK
        notes = shown["chosen"]
        return page(request, "ocio-list-more.html", **{**shown, "notes": notes[start:end],
                    "more": len(notes) > end, "next_desde": end, "next_hasta": end + CHUNK})
```

`rewrite_every_card` takes `request: Request` and returns `answer(request, "/ocio", "nothing-to-rewrite")` / `answer(request, "/ocio", "rewriting-all")`. Delete the `/embed/{link_id}` route and `"/embed/"` from the tuple in `not_found`. Delete `KIND_WORDS`, `STATE_ORDER` and `_count_by` if `grep -n "KIND_WORDS\|STATE_ORDER\|_count_by" src/` shows no other reader (the old card page reads `STATE_WORDS`, which stays until Task 9).

- [ ] **Step 5: The templates**

`posters.html`:

```jinja
{# One card in Ocio's grid (spec §3, Ocio.dc.html): the cover, or the kind's
   colour with the title on it; the kind's chip on the left, the state's on
   the right; under it the title and "year · stars · catalog rating". #}
{% macro poster(note, view, current, busy) -%}
{% set words = words_for(note.type) %}
<li class="item poster{% if note.id == current %} on{% endif %}" id="card-{{ note.id }}"
    {%- if note.id in busy %} data-working="{{ note.id }}"{% endif %}>
  <a class="hit" href="{{ view.url(sel=note.id) }}" data-sel="{{ note.id }}">
    <span class="art" style="background: {{ note.type|poster_fill }}">
      {% if note.cover %}<img src="/cover/{{ note.id|slug }}" alt="" loading="lazy">
      {% else %}<span class="fill-title" dir="auto">{{ note.title }}</span>{% endif %}
      {% if note.type in KIND_ONE %}<span class="chip kind">{{ t(KIND_ONE[note.type]) }}</span>{% endif %}
      {% if note.state in words %}<span class="chip state"><i class="dot" style="background: {{ CARD_DOTS[note.state] }}"></i>{{ t(words[note.state]) }}</span>{% endif %}
    </span>
    <span class="title" dir="auto">{{ note.title }}</span>
    <span class="meta">
      {%- set year = (note.published or '')[:4] -%}
      {%- if year|length == 4 and year.isdigit() %}<span class="mono">{{ year }}</span>{% endif -%}
      {%- if note.score %}<span class="stars-shown" aria-label="{{ [note.score, 5]|min }}/5">{% for n in range(1, 6) %}<i class="star{% if n <= note.score %} on{% endif %}">{% include "icon-star.html" %}</i>{% endfor %}</span>{% endif -%}
      {%- if note.rating %}<span class="mono">{{ note.source|catalog_name }} {{ note.rating }}</span>{% endif -%}
    </span>
  </a>
</li>
{%- endmacro %}
```

`ocio-list.html`:

```jinja
{% import "posters.html" as shelf with context %}
<div class="list-head">
  <span>{{ view.label(t) }} · <b class="mono">{{ total }}</b>
  {% if unrewritten %}
    <span class="unrewritten"><i class="dot" style="background: var(--acc)"></i>
      {% if unrewritten == 1 %}{{ t('1 card not rewritten') }}{% else %}{{ t('%1 cards not rewritten', unrewritten) }}{% endif %}
      {% if rewriting_all %}<em>{{ t('Rewriting…') }}</em>
      {% else %}<form method="post" action="/ocio/reescribir" data-inline><button class="btn small">{{ t('Rewrite') }}</button></form>{% endif %}
    </span>
  {% endif %}
  </span>
  <details class="menu sort">
    {% for key, label in SORTS if key == view.orden %}<summary class="btn">{{ t(label) }} ▾</summary>{% endfor %}
    <div class="menu-list">
      {% for key, label in SORTS %}<a href="{{ view.url(orden=key, sel='', hasta=chunk) }}" data-nav class="{% if key == view.orden %}on{% endif %}"><span>{{ t(label) }}</span><span>{% if key == view.orden %}✓{% endif %}</span></a>{% endfor %}
    </div>
  </details>
</div>
<div class="list-body" id="list-body">
  {% if notes %}
    <ul class="posters" id="items" data-current="{{ current }}">
      {% for note in notes %}{{ shelf.poster(note, view, current, busy) }}{% endfor %}
    </ul>
    {% if more %}<a class="more" href="{{ view.url(hasta=view.hasta + chunk) }}" data-more="{{ view.url('/ocio/lista', desde=view.hasta) }}">{{ t('Show more') }}</a>{% endif %}
  {% elif view.q %}
    <div class="empty-state"><p class="empty-title">{{ t('Nothing matches “%1”', view.q) }}</p>
      <p>{{ t('Search the catalogs to add it.') }}</p></div>
  {% elif view.tipo or view.estado %}
    <div class="empty-state"><p class="empty-title">{{ t('There is nothing in %1', view.label(t)) }}</p>
      <a class="btn" href="/ocio">{{ t('See everything') }}</a></div>
  {% else %}
    <div class="empty-state"><p class="empty-title">{{ t('Nothing in Leisure yet') }}</p>
      <p>{{ t('Type a title in the box above and search the catalogs.') }}</p></div>
  {% endif %}
</div>
```

`ocio-list-more.html`:

```jinja
{% import "posters.html" as shelf with context %}
<ul>{% for note in notes %}{{ shelf.poster(note, view, current, busy) }}{% endfor %}</ul>
{% if more %}<a class="more" href="{{ view.url(hasta=next_hasta) }}" data-more="{{ view.url('/ocio/lista', desde=next_desde) }}">{{ t('Show more') }}</a>{% endif %}
```

`ocio-shelf.html`:

```jinja
{% extends "base.html" %}
{% block title %}{% if view.q %}{{ view.q }} - {% endif %}{{ t('Leisure') }} - oknowledge{% endblock %}
{% block app_class %}ocio{% endblock %}
{% block layout %}
<section class="center" aria-label="{{ t('Leisure') }}">
  <form class="unified" id="unified" action="/ocio" method="get" role="search"
        data-mode="ocio" data-save-prefixes="{{ save_prefixes }}">
    <button type="submit" class="default-submit" tabindex="-1" aria-hidden="true"></button>
    <input type="text" name="q" id="field-q" value="{{ view.q }}" autocomplete="off"
           aria-label="{{ t('Search Leisure or paste a link from IMDb or Open Library') }}"
           placeholder="{{ t('Search Leisure or paste a link from IMDb or Open Library') }}">
    {% for name in ('tipo', 'estado') %}{% if view[name] %}<input type="hidden" name="{{ name }}" value="{{ view[name] }}">{% endif %}{% endfor %}
    {% if view.orden != 'recientes' %}<input type="hidden" name="orden" value="{{ view.orden }}">{% endif %}
    <span class="save">
      <button type="submit" class="btn primary" formmethod="post" formaction="/add" id="save-link">{{ t('Save') }} ↵</button>
    </span>
    <kbd class="hint mono">/</kbd>
  </form>
  {% if unreadable_cards %}
    <p class="quiet">{{ t('%1 cards could not be read and are not shown', unreadable_cards) }}</p>
  {% endif %}
  <div class="list" id="list" data-source="/ocio/lista">{% include "ocio-list.html" %}</div>
</section>
<section class="detail" id="panel" aria-label="{{ t('Detail') }}"
         data-empty="{{ t('Choose a card to see it here.') }}">
  <p class="detail-empty">{{ t('Choose a card to see it here.') }}</p>
</section>
{% endblock %}
```

(`view[name]` works on a dataclass in Jinja through attribute fallback. The `"%1 cards could not be read…"` key: `grep -n "cards could not be read" src/oknowledge/i18n.py` — reuse the existing wording if `ocio.html` had one, else add it below.)

Delete `templates/ocio.html`, `templates/embed.html` and `static/popup.js`; in `tests/test_packaging.py` the list becomes `["autosave.js", "idea.js", "redo.js", "shell.js"]`.

- [ ] **Step 6: Style it**

Append to `app.css` (`Ocio.dc.html`: grid `repeat(auto-fill, minmax(168px, 1fr))`, gap 16, `aspect-ratio: 2/3`, radius 10, chip bg `#141519cc`, selected border 2px `#e7e7ea`):

```css
/* --- Ocio (spec §3, Ocio.dc.html) ----------------------------------------- */
.app.ocio { grid-template-columns: 216px minmax(0, 1fr) 460px; overflow: hidden; line-height: normal; }
.posters { list-style: none; margin: 0; padding: 4px 20px 20px; display: grid; gap: 16px;
  grid-template-columns: repeat(auto-fill, minmax(168px, 1fr)); }
.poster .hit { display: flex; flex-direction: column; gap: 8px; color: inherit; text-decoration: none; }
.poster .art { position: relative; display: block; aspect-ratio: 2 / 3; border-radius: 10px;
  overflow: hidden; border: 2px solid transparent; }
.poster.on .art { border-color: #e7e7ea; }
.poster .art img { width: 100%; height: 100%; object-fit: cover; display: block; }
.poster .fill-title { position: absolute; left: 12px; right: 12px; bottom: 14px; font-size: 15px;
  font-weight: 600; line-height: 1.25; color: #f1f1f3; }
.poster .chip { position: absolute; top: 8px; display: inline-flex; align-items: center; gap: 5px;
  padding: 3px 8px; border-radius: 6px; background: #141519cc; color: #e7e7ea; font-size: 11px; }
.poster .chip.kind { left: 8px; }
.poster .chip.state { right: 8px; }
.poster .chip .dot { width: 6px; height: 6px; border-radius: 50%; }
.poster .title { font-size: 13.5px; font-weight: 500; color: var(--t1); white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis; }
.poster .meta { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--t5); }
.poster .meta > * + *::before { content: "·"; margin-right: 6px; color: var(--t6); }
.stars-shown { display: inline-flex; gap: 1px; }
.stars-shown .star { color: #33353e; display: inline-flex; }
.stars-shown .star.on { color: var(--fav); }
.stars-shown svg { width: 11px; height: 11px; }
.list-head .unrewritten { display: inline-flex; align-items: center; gap: 8px; margin-left: 14px;
  font-size: 12.5px; color: var(--t4); }
.list-head .unrewritten form { margin: 0; }
.list-head .unrewritten em { font-style: normal; color: var(--acc); }
.list-head .sort > summary { height: auto; padding: 4px 10px; font-size: 12.5px; }
.list-head .sort .menu-list { right: 0; left: auto; min-width: 170px; }
```

- [ ] **Step 7: The Spanish**

| key | es |
|---|---|
| TYPE | TIPO |
| Movie | Película |
| Book | Libro |
| To watch | Por ver |
| Watching | Viendo |
| Watched | Vista |
| To read | Por leer |
| Reading | Leyendo |
| Read | Leído |
| Recent | Recientes |
| Year | Año |
| Your stars | Tus estrellas |
| 1 card not rewritten | 1 ficha sin reescribir |
| %1 cards not rewritten | %1 fichas sin reescribir |
| Rewrite | Reescribir |
| Rewriting… | Reescribiendo… |
| Search Leisure or paste a link from IMDb or Open Library | Buscá en Ocio o pegá un link de IMDb u Open Library |
| Choose a card to see it here. | Elegí una ficha para verla acá. |
| Nothing in Leisure yet | Todavía no hay nada en Ocio |
| Type a title in the box above and search the catalogs. | Escribí un título en el campo de arriba y buscalo en los catálogos. |
| Search the catalogs to add it. | Buscalo en los catálogos para sumarlo. |

(Check each with `grep -n` first: "Series", "Anime", "Movies", "Books", "Title", "All", "Leisure", "Results", "Detail", "Show more", "See everything", "There is nothing in %1", "Nothing matches “%1”" exist; "Rewrite" or "Rewriting…" may exist from the old page — keep one entry.) Then run `tests/test_i18n.py` and delete each key it names that only `ocio.html`, `embed.html` or `popup.js` asked for (e.g. "Pending", "In progress", "Finished", "Close" if nothing else reads them — exactly the ones it lists).

- [ ] **Step 8: Run the tests**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_shelf_view_ocio.py tests/test_web_ocio_shelf.py tests/test_web_ocio_rewrite.py tests/test_web_cards.py tests/test_web_ocio_mine.py tests/test_web_layout.py tests/test_web_marks.py tests/test_web_sidebar.py tests/test_packaging.py tests/test_i18n.py tests/test_web_read.py`
Expected: PASS.

- [ ] **Step 9: Whole suite, commit**

Run the suite; expected green, minus the ledger.

```bash
git add -A src/oknowledge tests
git commit -m "Draw Ocio as a poster grid with type and state filters, four orders and the rewrite notice"
```

---
### Task 9: A card's panel, and the old card page goes

**Files:**
- Create: `src/oknowledge/web/templates/card-panel.html`, `tests/test_web_ocio_panel.py`
- Modify: `src/oknowledge/web/app.py` — `card_context()` beside `panel_context()` (≈786); `detail` (`/panel/{id}`, ≈818) serves cards; `leisure` draws the current card's panel; new `POST /item/{link_id}/kind`; `item()` (≈897) sends a card to `/ocio?sel=`; `remove` (≈1210) goes back to `/ocio` for a card and answers through `answer()`; `rewrite_card` (≈1121) card branch answers through `answer()` (already, Task 2); `link_state` (`/item/{id}/state`, ≈1639) speaks for a card being rewritten; `STATE_WORDS` (≈382) goes
- Modify: `src/oknowledge/vault.py` (`update_note` gains `kind`), `src/oknowledge/web/templates/ocio-shelf.html` (the panel), `src/oknowledge/web/static/app.css`, `src/oknowledge/i18n.py`
- Delete: `src/oknowledge/web/templates/item.html`, `mine-buttons.html`, `mark-picker.html`, `icon-save.html`, `src/oknowledge/web/static/redo.js`
- Test: ledger below; `tests/test_packaging.py:95` becomes `["autosave.js", "idea.js", "shell.js"]`

**Interfaces:**
- Consumes: `CardView`, `words_for`, `KIND_ONE`, `KIND_NAMES`, `CARD_DOTS`, `poster_fill`, `catalog_name` (Task 8); `answer()` (Task 1).
- Produces:
  - `card_context(card_id, view) -> dict | None` (keys `note, panel_id, card: True, words, rewriting: bool, rewrite_failed: str, back`).
  - `card-panel.html`: root `<div class="detail-scroll card" data-panel="{id}"{% if rewriting %} data-working="{id}"{% endif %}>`; every write is a `form[data-inline]`; the note box is `textarea#card-note[data-autosave="/item/{id}/mine/note"][data-indicator="#card-save-state"]`.
  - `POST /item/{id}/kind` (form `kind`): a card only (404 otherwise); one of `cards.KINDS` sets `type` and `category` (`cards.CATEGORIES[content language][kind]`); anything else answers `bad-kind` (400 for JSON) and writes nothing.
  - `update_note(..., kind: str | None = None)` sets `note.type`.
  - `GET /item/{id}/state` of a card: `{"working": true, "status": "rewriting"}` while it is rewritten, then `{"working": false, "status": "failed" | "ok"}`.
  - `GET /item/{card}` → 303 `/ocio?sel={id}` with `notice`, `n`, `m`.

- [ ] **Step 1: Write the failing tests**

`tests/test_web_ocio_panel.py`:

```python
"""A card in Ocio's right column (spec §3, "Panel derecho")."""

import re

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.vault import find_note, note_path, rebuild_indexes, write_note
from oknowledge.web.app import create_app


@pytest.fixture(autouse=True)
def state_tree(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr("oknowledge.web.app.CONFIG_PATH", tmp_path / "config" / "config.toml")


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


CARD = "c00000000001"


def put(cfg, **over):
    fields = dict(id=CARD, url="https://www.imdb.com/title/tt0088247", title="The Terminator",
                  category="Películas", tags=["acción"], type="movie", source="imdb.com",
                  saved="2026-10-11", summary="Un cyborg viaja al pasado.\n\nY no para.",
                  published="1984-10-26", length="108 min", rating="8.1", engine="fake",
                  state="doing", score=4, my_note="La vi dos veces.")
    fields.update(over)
    note = Note(**fields)
    write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ocio))
    return note


def panel(client, query=""):
    return client.get(f"/panel/{CARD}{query}").text


def test_the_panel_is_a_fragment_for_a_card(cfg, client):
    put(cfg)
    body = panel(client)
    assert "<html" not in body and f'data-panel="{CARD}"' in body


def test_ocio_draws_the_selected_card_s_panel(cfg, client):
    put(cfg)
    body = client.get("/ocio").text
    assert f'data-panel="{CARD}"' in body and "Choose a card to see it here." not in body


def test_the_top_bar_has_the_state_in_the_kind_s_words(cfg, client):
    put(cfg)
    seg = re.search(rf'<form[^>]*action="/item/{CARD}/mine/state"[^>]*>.*?</form>',
                    panel(client), re.S).group(0)
    assert "data-inline" in seg
    assert re.findall(r">(To watch|Watching|Watched)<", seg) == ["To watch", "Watching", "Watched"]
    assert re.search(r'value="doing" class="on"', seg)


def test_a_book_is_read(cfg, client):
    put(cfg, type="book", category="Libros", url="https://openlibrary.org/works/OL1W",
        source="openlibrary.org")
    body = panel(client)
    assert ">To read<" in body and ">Reading<" in body and ">To watch<" not in body


def test_the_current_star_takes_the_stars_off(cfg, client):
    put(cfg)
    stars = re.search(rf'<form[^>]*action="/item/{CARD}/mine/score"[^>]*>.*?</form>',
                      panel(client), re.S).group(0)
    assert re.findall(r'name="score" value="(\d)"', stars) == ["1", "2", "3", "0", "5"]


def test_the_more_menu(cfg, client):
    put(cfg)
    body = panel(client)
    assert f'action="/item/{CARD}/describe"' in body and "Rewrite the card" in body
    assert "Change type ▸" in body
    assert re.findall(rf'action="/item/{CARD}/kind".*?value="(\w+)"', body, re.S)[:1] == ["movie"]
    for kind in ("movie", "series", "anime", "book"):
        assert f'name="kind" value="{kind}"' in body
    assert f'action="/item/{CARD}/delete"' in body


def test_the_head_poster_kind_title_and_chips(cfg, client):
    put(cfg, cover="../attachments/t.jpg")
    body = panel(client)
    assert f'<img src="/cover/{CARD}"' in body
    assert "Movie · imdb.com" in body
    assert '<h1 dir="auto">The Terminator</h1>' in body
    for chip in ("1984", "108 min", "IMDb ★ 8.1"):
        assert f">{chip}<" in body


def test_a_card_without_a_cover_has_the_gradient(cfg, client):
    put(cfg)
    head = panel(client).split("<h1", 1)[0]
    assert "<img" not in head and "oklch(0.42 0.06 300)" in head


def test_open_in_its_site(cfg, client):
    put(cfg)
    assert re.search(r'<a class="btn primary" href="https://www.imdb.com/title/tt0088247" '
                     r'target="_blank" rel="noreferrer">Open in imdb.com ↗</a>', panel(client))


def test_a_url_that_is_not_the_web_is_never_a_link(cfg, client):
    put(cfg, url="javascript:alert(1)")
    assert "javascript:" not in panel(client)


def test_a_rewritten_card_has_no_notice(cfg, client):
    put(cfg)
    assert "as the source gave it" not in panel(client)


def test_an_unrewritten_card_offers_the_rewrite(cfg, client):
    put(cfg, engine="")
    body = panel(client)
    assert "The card is as the source gave it (in English)." in body
    assert re.search(rf'<form[^>]*action="/item/{CARD}/describe"[^>]*data-inline[^>]*>\s*'
                     r'<button class="btn primary">Rewrite in Spanish</button>', body)


def test_while_it_is_rewritten_it_says_so_and_is_watched(cfg):
    put(cfg, engine="")
    app = create_app(cfg)
    app.state.rewriting.start(CARD, "describe")
    body = TestClient(app).get(f"/panel/{CARD}").text
    assert f'data-working="{CARD}"' in body and "Rewriting…" in body
    assert "Rewrite in Spanish" not in body


def test_a_failed_rewrite_says_why(cfg):
    put(cfg, engine="")
    app = create_app(cfg)
    app.state.rewriting.start(CARD, "describe")
    app.state.rewriting.finish(CARD, "describe", "opencode: 429")
    assert "Last time it failed: opencode: 429" in TestClient(app).get(f"/panel/{CARD}").text


def test_what_it_is_about_your_note_and_tags(cfg, client):
    put(cfg)
    body = panel(client)
    assert "WHAT IT IS ABOUT" in body and "Un cyborg viaja al pasado." in body
    area = re.search(r'<textarea[^>]*id="card-note"[^>]*>(.*?)</textarea>', body, re.S)
    assert area.group(1) == "La vi dos veces."
    assert f'data-autosave="/item/{CARD}/mine/note"' in area.group(0)
    assert 'placeholder="What you thought of it"' in area.group(0)
    assert "YOUR NOTE" in body and "saves itself" in body
    assert "#acción" in body and 'placeholder="+ tag"' in body


def test_no_save_buttons_marks_or_disks(cfg, client):
    put(cfg)
    body = panel(client)
    assert "💾" not in body and "Edit tags" not in body and "/mark" not in body
    saves = re.findall(r"<button[^>]*>Save</button>", body)
    assert all("data-nojs" in button for button in saves)


def test_the_state_route_speaks_for_a_rewrite(cfg):
    put(cfg, engine="")
    app = create_app(cfg)
    client = TestClient(app)
    app.state.rewriting.start(CARD, "describe")
    assert client.get(f"/item/{CARD}/state").json() == {"working": True, "status": "rewriting"}
    app.state.rewriting.finish(CARD, "describe", "boom")
    assert client.get(f"/item/{CARD}/state").json() == {"working": False, "status": "failed"}
    app.state.rewriting.start(CARD, "describe")
    app.state.rewriting.finish(CARD, "describe", None)
    assert client.get(f"/item/{CARD}/state").json() == {"working": False, "status": "ok"}


# --- the type -------------------------------------------------------------------------

def test_changing_the_type_changes_type_and_category(cfg, client):
    put(cfg)
    answer = client.post(f"/item/{CARD}/kind", data={"kind": "anime"}, follow_redirects=False)
    assert answer.headers["location"] == f"/ocio?sel={CARD}&notice=saved"
    after = find_note(cfg, CARD, shelf=cfg.ocio)[1]
    assert (after.type, after.category) == ("anime", "Anime")


def test_a_book_is_filed_under_books(cfg, client):
    put(cfg)
    client.post(f"/item/{CARD}/kind", data={"kind": "book"})
    assert find_note(cfg, CARD, shelf=cfg.ocio)[1].category == "Libros"


@pytest.mark.parametrize("kind", ["podcast", "", "idea"])
def test_an_unknown_type_changes_nothing(cfg, client, kind):
    put(cfg)
    answer = client.post(f"/item/{CARD}/kind", data={"kind": kind},
                         headers={"Accept": "application/json"})
    assert answer.status_code == 400 and answer.json()["ok"] is False
    assert find_note(cfg, CARD, shelf=cfg.ocio)[1].type == "movie"


def test_only_a_card_has_a_type_to_change(cfg, client):
    write_note(cfg, Note(id="l00000000001", url="https://e.com", title="E", category="Redes",
                         tags=[], type="article", source="e.com", saved="2026-10-10",
                         summary="s"), "es")
    rebuild_indexes(cfg, "es")
    assert client.post("/item/l00000000001/kind", data={"kind": "movie"}).status_code == 404


def test_the_type_by_script_answers_json(cfg, client):
    put(cfg)
    answer = client.post(f"/item/{CARD}/kind", data={"kind": "series"},
                         headers={"Accept": "application/json"})
    assert answer.json()["ok"] is True


# --- where a card lives now ----------------------------------------------------------

def test_a_card_s_old_address_opens_it_in_ocio(cfg, client):
    put(cfg)
    answer = client.get(f"/item/{CARD}?notice=saved", follow_redirects=False)
    assert answer.headers["location"] == f"/ocio?sel={CARD}&notice=saved"


def test_a_deleted_card_goes_back_to_ocio(cfg, client):
    put(cfg)
    answer = client.post(f"/item/{CARD}/delete", follow_redirects=False)
    assert answer.headers["location"] == "/ocio?notice=trashed"


def test_the_old_pages_and_scripts_are_gone(client):
    from importlib.resources import files
    templates = files("oknowledge.web").joinpath("templates")
    for name in ("item.html", "mine-buttons.html", "mark-picker.html", "icon-save.html"):
        assert not templates.joinpath(name).is_file()
    assert client.get("/static/redo.js").status_code == 404
```

**Ledger — tests deleted or changed here.** Everything that read `item.html` for a card now reads the panel:

- `tests/test_web_ocio_mine.py`: `test_the_words_depend_on_what_it_is`, `test_a_film_is_watched_and_not_read` (→ `test_the_top_bar_has_the_state_in_the_kind_s_words`, `test_a_book_is_read`), `test_a_link_has_no_stars` and `test_a_link_still_offers_all_of_it` (they read `/item/{link}`, which is the library's panel since delivery 1: change `client.get(f"/item/{…}")` to `client.get(f"/panel/{…}")` and keep them), `test_the_card_page_offers_nothing_that_answers_404` (→ `test_no_save_buttons_marks_or_disks`; delete). Write-route tests that assert a location `"/item/{card}?notice=…"` now see `/item/{card}` answered by the redirect — they assert the 303 of the write itself and stay as they are.
- `tests/test_web_ocio_rewrite.py::test_a_failed_rewrite_shows_its_reason_on_the_card_page` → reads `/panel/{card}` instead of `/item/{card}`; `::test_a_running_rewrite_says_so_and_is_not_asked_twice` likewise if it reads the page.
- `tests/test_web_ocio_save.py::test_the_card_opens_at_its_own_page` → follows to `/ocio?sel=…` (change the expected text to `f'data-panel="{card_id}"'`); `::test_the_button_asks_again` and `::test_the_button_is_only_for_cards` read the page for the describe button: read `/panel/{id}`.
- `tests/test_web_cards.py`: `test_everything_that_is_read_rather_than_scanned_keeps_its_measure[/item/a1]` (the item page is a redirect now: drop that parameter), `test_the_note_page_shows_the_cover_the_card_showed`, `test_the_cover_is_above_the_text_and_below_the_title`, `test_a_note_with_no_cover_draws_no_frame` (they read `/item/{link}` → the library panel: keep them only if they pass against `/panel/{id}`, else delete — the panel's cover is delivery 1's), `test_every_field_says_what_it_is_above_itself`, `test_saving_is_a_drawn_disk_with_a_name_for_what_cannot_see_it`, `test_joining_a_collection_is_not_drawn_as_saving` (the 💾 forms of `item.html`, spec §1: delete), `test_the_note_page_names_the_engine_too` (→ the panel draws `engine-badge.html`; read `/panel/{id}`).
- `tests/test_web_marks.py::test_every_card_and_note_page_has_the_picker` (its last parameter, `/item/{LINK}`, is the library panel: keep it reading `/panel/{LINK}`), any other test there that reads `mark-picker.html` on a card.
- `tests/test_web_ideas_related.py::test_neither_a_card_nor_an_idea_offers_the_picker`: the card half reads `/panel/{CARD}`.

Any other failure after Step 3 is a fault in this task, not a ledger entry.

- [ ] **Step 2: Run them to verify they fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_ocio_panel.py`
Expected: FAIL — `/panel/{card}` is a 404, `/item/{id}/kind` a 405.

- [ ] **Step 3: The routes**

In `vault.update_note` add the parameter `kind: str | None = None` after `mark`, and beside the `category` branch:

```python
    if kind is not None:
        note.type = kind
```

In `app.py` add `KIND_NAMES` to the `.shelf_view` import, and next to `panel_context()`:

```python
    def card_context(card_id: str, view) -> dict | None:
        """What a card's panel shows (spec §3), or None for no such card."""
        shelf.refresh()
        entry = shelf.entry(card_id)
        if entry is None:
            return None
        note = read_full(entry)
        running, failed = rewriting.of(card_id)
        return {"note": note, "panel_id": card_id, "card": True,
                "words": words_for(note.type), "rewriting": "describe" in running,
                "rewrite_failed": failed.get("describe", ""), "back": view.url(sel=card_id),
                "KIND_ONE": KIND_ONE, "KIND_NAMES": KIND_NAMES, "CARD_DOTS": CARD_DOTS}
```

`detail` (`/panel/{link_id}`) tries the library first, then a card:

```python
        found = panel_context(link_id, view, analyzing())
        if found is None:
            card = card_context(link_id, CardView.from_query(request.query_params))
            if card is None:
                raise HTTPException(status_code=404, detail="no such link")
            return page(request, "card-panel.html", **card)
        return page(request, "panel.html", **found)
```

In `leisure`, before `return`:

```python
        card = card_context(shown["current"], view) if shown["current"] else None
```

and pass `panel=card is not None, **(card or {})` to `page()` (after `**shown`).

The new route, after `set_mark`:

```python
    @app.post("/item/{link_id}/kind")
    def change_kind(request: Request, link_id: str, kind: str = Form("")):
        """A card's type, and the category that goes with it, as when it was
        made (spec §3, "Cambiar tipo"). A type nobody knows changes nothing."""
        shelf.refresh()
        if shelf.by_id(link_id) is None:
            raise HTTPException(status_code=404, detail="no such card")
        home = f"/ocio?sel={quote(link_id, safe='')}"
        if kind not in cards.KINDS:
            return answer(request, home, "bad-kind")

        def retype(cfg, language):
            names = cards.CATEGORIES.get(language, cards.CATEGORIES["en"])
            return update_note(cfg, link_id, language, shelf=cfg.ocio, kind=kind,
                               category=names[kind])
        result = edit(link_id, retype, "saved", "indexes-stale", shelves=shelf)
        if result.notice == MISSING:
            raise HTTPException(status_code=404, detail="no such card")
        return answer(request, home, result.notice)
```

Add `"bad-kind": "That is not a type a card can have."` to `NOTICES` and `"bad-kind": 400` to `FAILURES`.

In `item()`, after the ideas redirect (Task 7):

```python
        if where.name == "ocio":
            params = request.query_params
            return see_other("/ocio", sel=link_id, notice=params.get("notice"),
                             n=params.get("n"), m=params.get("m"))
```

and the rest of `item()` after it goes (the `extra` for cards, the final `page(request, "item.html", …)`); the `library.error` branch at its top calls `page(request, "notfound.html")` instead of `"item.html"` — `page()` draws `error.html` with a 503 whenever the library cannot be read, whatever name it is given.

In `remove`: `def remove(request: Request, link_id: str)`, `home = {"ideas": "/ideas", "ocio": "/ocio"}.get(which.name, "/")`, and `return answer(request, where, result.notice)`.

In `link_state`, first thing:

```python
        shelf.refresh()
        if shelf.by_id(link_id) is not None:
            running, failed = rewriting.of(link_id)
            if "describe" in running:
                return JSONResponse({"working": True, "status": "rewriting"})
            return JSONResponse({"working": False,
                                 "status": "failed" if failed.get("describe") else "ok"})
```

Delete `STATE_WORDS` (`grep -n STATE_WORDS src/` must print only `IDEA_STATE_WORDS` lines, or nothing if Task 5 left none) and the templates and script listed under **Delete**.

- [ ] **Step 4: The panel**

`card-panel.html`:

```jinja
{# A card in Ocio's right column (spec §3): the bar on top stays, the rest
   scrolls. Every write is a form that works alone; shell.js posts it in
   place and autosave.js saves the note as you type. #}
{% set kind_one = KIND_ONE.get(note.type, '') %}
<div class="card-top">
  <form method="post" action="/item/{{ note.id|slug }}/mine/state" class="seg" data-inline>
    {% for state, word in words.items() %}<button name="state" value="{{ state }}" class="{% if note.state == state %}on{% endif %}">{{ t(word) }}</button>{% endfor %}
  </form>
  <form method="post" action="/item/{{ note.id|slug }}/mine/score" class="stars big" data-inline>
    {% for n in range(1, 6) %}<button name="score" value="{{ 0 if n == note.score else n }}" class="{% if n <= note.score %}on{% endif %}" title="{{ n }}/5" aria-label="{{ n }}/5">{% include "icon-star.html" %}</button>{% endfor %}
  </form>
  <details class="menu more">
    <summary class="btn icon framed" aria-label="{{ t('More') }}" title="{{ t('More') }}">⋯</summary>
    <div class="menu-list">
      <form method="post" action="/item/{{ note.id|slug }}/describe" data-inline>
        <button>{{ t('Rewrite the card') }}</button>
      </form>
      <details class="submenu">
        <summary>{{ t('Change type') }} ▸</summary>
        <form method="post" action="/item/{{ note.id|slug }}/kind" data-inline>
          {% for kind, name in KIND_NAMES.items() %}<button name="kind" value="{{ kind }}" class="{% if note.type == kind %}on{% endif %}">{{ t(KIND_ONE[kind]) }}</button>{% endfor %}
        </form>
      </details>
      <form method="post" action="/item/{{ note.id|slug }}/delete" data-inline
            data-ask="{{ t('Move this card to the trash folder?') }}">
        <button class="danger" onclick="return confirm(this.form.dataset.ask)">{{ t('Delete') }}</button>
      </form>
    </div>
  </details>
</div>
<div class="detail-scroll card" data-panel="{{ panel_id }}"{% if rewriting %} data-working="{{ panel_id }}"{% endif %}>
  <div class="card-head">
    <span class="art" style="background: {{ note.type|poster_fill }}">
      {% if note.cover %}<img src="/cover/{{ note.id|slug }}" alt="">{% endif %}
    </span>
    <div class="card-facts">
      <p class="kind-line">{% if kind_one %}{{ t(kind_one) }} · {% endif %}{{ note.source }}</p>
      <h1 dir="auto">{{ note.title }}</h1>
      <p class="chips facts">
        {%- set year = (note.published or '')[:4] -%}
        {%- if year|length == 4 and year.isdigit() %}<span class="chip mono">{{ year }}</span>{% endif -%}
        {%- if note.length %}<span class="chip">{{ note.length }}</span>{% endif -%}
        {%- if note.rating %}<span class="chip mono">{{ note.source|catalog_name }} ★ {{ note.rating }}</span>{% endif -%}
      </p>
      {% if note.url is web_url %}<a class="btn primary" href="{{ note.url }}" target="_blank" rel="noreferrer">{{ t('Open in %1', note.source) }} ↗</a>{% endif %}
    </div>
  </div>
  {% if not note.engine %}
    <div class="unrewritten-box">
      <p>{{ t('The card is as the source gave it (in English).') }}</p>
      {% if rewriting %}<p class="working">{{ t('Rewriting…') }}</p>
      {% else %}
        <form method="post" action="/item/{{ note.id|slug }}/describe" data-inline>
          <button class="btn primary">{{ t('Rewrite in Spanish') }}</button>
        </form>
      {% endif %}
      {% if rewrite_failed %}<p class="failed">{{ t('Last time it failed: %1', rewrite_failed) }}</p>{% endif %}
    </div>
  {% elif rewriting %}
    <p class="working">{{ t('Rewriting…') }}</p>
  {% endif %}
  {% if note.summary %}
    <section class="about">
      <p class="label">{{ t('WHAT IT IS ABOUT') }}</p>
      {% for para in note.summary|paragraphs %}<p class="body" dir="auto">{{ para }}</p>{% endfor %}
    </section>
  {% endif %}
  <section class="your-note">
    <p class="label"><span>{{ t('YOUR NOTE') }}</span>
      <span class="save-state" id="card-save-state" data-saving="{{ t('saving…') }}" data-saved="{{ t('saved') }}">{{ t('saves itself') }}</span></p>
    <form method="post" action="/item/{{ note.id|slug }}/mine/note">
      <textarea name="my_note" id="card-note" rows="4" aria-label="{{ t('YOUR NOTE') }}"
                placeholder="{{ t('What you thought of it') }}"
                data-autosave="/item/{{ note.id|slug }}/mine/note" data-indicator="#card-save-state">{{ note.my_note }}</textarea>
      <button class="btn" data-nojs>{{ t('Save') }}</button>
    </form>
  </section>
  <div class="chips tags">
    {% for tag in note.tags %}
      <form method="post" action="/item/{{ note.id|slug }}/tags" data-inline class="chip">
        <span>#{{ tag }}</span>
        <input type="hidden" name="tags" value="{{ note.tags|reject('equalto', tag)|join(' ') }}">
        <button aria-label="{{ t('Remove the tag %1', tag) }}" title="{{ t('Remove the tag %1', tag) }}">✕</button>
      </form>
    {% endfor %}
    <form method="post" action="/item/{{ note.id|slug }}/tags" data-inline class="tag-new">
      <input type="hidden" name="tags" value="{{ note.tags|join(' ') }}">
      <input name="add" required autocomplete="off" aria-label="{{ t('+ tag') }}" placeholder="{{ t('+ tag') }}">
    </form>
  </div>
</div>
```

In `ocio-shelf.html` the panel section becomes:

```jinja
<section class="detail" id="panel" aria-label="{{ t('Detail') }}"
         data-empty="{{ t('Choose a card to see it here.') }}">
  {% if panel %}{% include "card-panel.html" %}{% else %}<p class="detail-empty">{{ t('Choose a card to see it here.') }}</p>{% endif %}
</section>
```

Append to `app.css` (`Ocio.dc.html`: top bar padding `16px 24px`, grid `112px 1fr`, title 24/600, stars 19px, body 15px/1.6):

```css
.card-top { display: flex; align-items: center; gap: 12px; padding: 16px 24px;
  border-bottom: 1px solid var(--b-div); }
.card-top .more { margin-left: auto; }
.stars.big button { font-size: 19px; }
.stars.big svg { width: 19px; height: 19px; }
.submenu > summary { list-style: none; padding: 8px 10px; border-radius: 6px; cursor: pointer;
  font-size: 13px; color: var(--t2); }
.submenu > summary:hover { background: var(--s5); }
.submenu form { display: flex; flex-direction: column; padding-left: 10px; }
.detail-scroll.card { padding: 22px 24px; gap: 18px; }
.card-head { display: grid; grid-template-columns: 112px minmax(0, 1fr); gap: 16px; }
.card-head .art { display: block; aspect-ratio: 2 / 3; border-radius: 8px; overflow: hidden; }
.card-head .art img { width: 100%; height: 100%; object-fit: cover; display: block; }
.card-facts { display: flex; flex-direction: column; gap: 8px; align-items: flex-start; }
.card-facts .kind-line { margin: 0; font-size: 12px; color: var(--t5); }
.card-facts h1 { font-size: 24px; font-weight: 600; letter-spacing: -0.02em; line-height: 1.2; }
.card-facts .facts { margin: 0; }
.unrewritten-box { background: var(--s2); border: 1px solid var(--b-card); border-radius: 10px;
  padding: 12px 14px; display: flex; flex-direction: column; gap: 10px; font-size: 13px; color: var(--t4); }
.unrewritten-box p, .detail .working { margin: 0; }
.detail .working { color: var(--acc); font-size: 13px; }
.detail .failed { margin: 0; color: var(--danger); font-size: 13px; }
.about .body { font-size: 15px; line-height: 1.6; }
.your-note .label { display: flex; justify-content: space-between; }
.your-note form { display: flex; flex-direction: column; gap: 8px; margin: 0; }
.your-note textarea { resize: vertical; min-height: 96px; background: var(--s2);
  border: 1px solid var(--b-input); border-radius: 10px; padding: 12px 14px; color: var(--t1);
  font: inherit; font-size: 14px; line-height: 1.55; outline: 0; }
```

- [ ] **Step 5: The Spanish**

| key | es |
|---|---|
| Rewrite the card | Reescribir la ficha |
| Change type | Cambiar tipo |
| Move this card to the trash folder? | ¿Mover esta ficha a la papelera? |
| Open in %1 | Abrir en %1 |
| The card is as the source gave it (in English). | La ficha está como vino de la fuente (en inglés). |
| Rewrite in Spanish | Reescribir en español |
| WHAT IT IS ABOUT | DE QUÉ TRATA |
| YOUR NOTE | TU NOTA |
| What you thought of it | Qué te pareció |
| saving… | guardando… |
| saved | guardado |
| That is not a type a card can have. | Ese no es un tipo de ficha. |

("Delete" → "Borrar" is already there.) Then run `tests/test_i18n.py` and delete each key it names that only `item.html`, `mine-buttons.html`, `mark-picker.html` or `redo.js` asked for — exactly those (e.g. "to watch", "watching", "watched", "to read", "reading", "read" in lowercase, "Your note", "Rewrite in your language").

- [ ] **Step 6: Run the tests**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_ocio_panel.py tests/test_web_ocio_shelf.py tests/test_web_ocio_mine.py tests/test_web_ocio_rewrite.py tests/test_web_ocio_save.py tests/test_web_cards.py tests/test_web_marks.py tests/test_web_ideas_related.py tests/test_vault_cards.py tests/test_packaging.py tests/test_i18n.py tests/test_web_read.py`
Expected: PASS.

- [ ] **Step 7: Whole suite, commit**

Run the suite; expected green, minus the ledger.

```bash
git add -A src/oknowledge tests
git commit -m "Show a card in Ocio's panel with its state, stars, type and note, and retire the old card page"
```

---
### Task 10: The catalogs in the panel

**Files:**
- Modify: `src/oknowledge/catalog/__init__.py` (`Candidate.people`), `src/oknowledge/catalog/openlibrary.py` (`_candidate`), `src/oknowledge/catalog/cinemeta.py` (`search`)
- Modify: `src/oknowledge/cards.py` (new `from_link`)
- Create: `src/oknowledge/web/templates/catalog-panel.html`
- Delete: `src/oknowledge/web/templates/candidates.html`
- Modify: `src/oknowledge/web/app.py` — `candidates_context()` beside `ask_catalogs()` (≈1820); new `GET /ocio/candidatos`; `card_candidates` (`GET /ocio/buscar`, ≈1859) becomes a 303; `leisure` reads `buscar`, `year`; `save_the_card` (`/ocio/guardar`, ≈1892) and `add_pasted` (`/add`, ≈1972) go to `/ocio?sel=` / `/ocio?buscar=`; `add_pasted` reads `en` and `tipo`
- Modify: `src/oknowledge/web/templates/ocio-shelf.html` (the catalog button, `en=ocio`), `src/oknowledge/web/static/app.css`, `src/oknowledge/i18n.py`
- Test: `tests/test_web_ocio_catalogs.py` (new), `tests/test_cards.py` (append), `tests/test_catalog_people.py` (new); edits in `tests/test_web_ocio_search.py` and `tests/test_web_ocio_save.py` (below)

**Interfaces:**
- Consumes: `ask_catalogs(tipo, query, year) -> (list[Candidate], str)`, `save_card(tipo, candidate, background) -> (id | None, notice)`, `card_context()` (Task 9), the `fake_catalog` stub pattern of `tests/test_web_ocio_search.py`.
- Produces:
  - `Candidate.people: str = ""` — a book's first author (Open Library `author_name`); Cinemeta's search answers carry a director only sometimes (`_first(meta.get("director"))`).
  - `cards.from_link(text: str, kind: str = "") -> Wanted | None` — an IMDb title URL (`tt…`, kind from `kind` unless it is `book`, else `movie`) or an Open Library work URL (`book`); anything else `None`.
  - `candidates_context(q, tipo, year="") -> dict | None` with `query_text, kind, candidates, failed, KIND_ONE` (None for an empty query).
  - `GET /ocio/candidatos?q=&tipo=&year=` → the `catalog-panel.html` fragment; 404 with no words. `tipo` unknown → `movie`.
  - `GET /ocio?buscar=…&tipo=…&year=…` draws the candidates in the panel. `GET /ocio/buscar?q=…&tipo=…&year=…` → 303 to that.
  - `catalog-panel.html` root `<div class="detail-scroll candidates" data-panel="" data-search="{q}">`, kind switch `a[data-kind]`.
  - `POST /add` with `en=ocio`: a prefix or a catalog link saves (→ `/ocio?sel=`) or lists (→ `/ocio?buscar=`); any other link → `/ocio?notice=not-a-catalog-link`; plain text → `/ocio?buscar=…&tipo=…`.

- [ ] **Step 1: Write the failing tests**

`tests/test_catalog_people.py`:

```python
"""Who made it, on a candidate (spec §3, "autor o director")."""

from oknowledge.catalog import openlibrary, cinemeta


def test_a_book_names_its_first_author():
    found = openlibrary._candidate({"key": "/works/OL1W", "title": "Dune",
                                    "author_name": ["Frank Herbert", "Otro"]}, "book")
    assert found.people == "Frank Herbert"


def test_a_book_without_authors_names_nobody():
    assert openlibrary._candidate({"key": "/works/OL1W", "title": "Dune"}, "book").people == ""


def test_a_film_names_its_director_when_the_search_says(monkeypatch):
    answer = '{"metas": [{"id": "tt1", "name": "Alien", "director": ["Ridley Scott"]}, ' \
             '{"id": "tt2", "name": "Brazil"}]}'
    monkeypatch.setattr(cinemeta.net, "fetch",
                        lambda url, **kw: type("R", (), {"text": answer})())
    found, _ = cinemeta.search("movie", "x")
    assert [c.people for c in found] == ["Ridley Scott", ""]
```

Append to `tests/test_cards.py`:

```python
from oknowledge.cards import from_link


def test_an_imdb_link_is_a_film_by_its_id():
    asked = from_link("https://www.imdb.com/title/tt0088247/?ref_=x")
    assert (asked.kind, asked.query) == ("movie", "tt0088247")


def test_an_imdb_link_takes_the_kind_it_was_pasted_under():
    assert from_link("https://m.imdb.com/title/tt0213338/", "anime").kind == "anime"
    assert from_link("https://imdb.com/title/tt0213338/", "book").kind == "movie"


def test_an_open_library_work_is_a_book():
    asked = from_link("https://openlibrary.org/works/OL893414W/Dune")
    assert (asked.kind, asked.query) == ("book", "OL893414W")


def test_any_other_link_or_text_is_not_a_catalog_link():
    for text in ("https://myanimelist.net/anime/1", "https://www.goodreads.com/book/show/1",
                 "https://imdb.com/name/nm0000116", "Terminator", ""):
        assert from_link(text) is None
```

`tests/test_web_ocio_catalogs.py`:

```python
"""Searching the catalogs from Ocio's field (spec §3, "Candidatos de catálogos").
No test reaches the network: both catalogs are the fake below."""

import re

import pytest
from fastapi.testclient import TestClient

from oknowledge.catalog import Candidate, Card
from oknowledge.config import Config
from oknowledge.vault import rebuild_indexes
from oknowledge.web.app import create_app


@pytest.fixture(autouse=True)
def state_tree(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr("oknowledge.web.app.CONFIG_PATH", tmp_path / "config" / "config.toml")


@pytest.fixture
def client(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    rebuild_indexes(cfg, "es")
    return TestClient(create_app(cfg))


@pytest.fixture
def asked(monkeypatch):
    calls = []

    def films(kind, query, via=""):
        calls.append((via or "movie", query))
        return [Candidate(ref="tt0088247", kind=kind, via=via or "movie", title="The Terminator",
                          year="1984", rating="8.1", poster="https://img/t.jpg",
                          people="James Cameron")], ""

    def books(kind, query, via=""):
        calls.append(("book", query))
        return [Candidate(ref="/works/OL1W", kind="book", via="book", title="Dune",
                          year="1965", people="Frank Herbert")], ""

    monkeypatch.setattr("oknowledge.catalog.cinemeta.search", films)
    monkeypatch.setattr("oknowledge.catalog.openlibrary.search", books)
    return calls


def stub_the_card(monkeypatch):
    """What Cinemeta's card() would answer for The Terminator, and no poster
    download and no model: saving must stay on this machine."""
    card = Card(url="https://www.imdb.com/title/tt0088247/", source="imdb.com",
                title="The Terminator", year="1984", people="James Cameron",
                released="1984-10-26", genres=["Action"], length="108 min", rating="8.1",
                synopsis="A cyborg assassin from the future.", poster="")
    monkeypatch.setattr("oknowledge.catalog.cinemeta.card", lambda candidate: card)
    monkeypatch.setattr("oknowledge.web.app.describe", lambda cfg, link_id, **rest: True)


def test_the_field_offers_the_catalogs(client):
    body = client.get("/ocio").text
    button = re.search(r'<button[^>]*id="catalog-search"[^>]*>(.*?)</button>', body, re.S)
    assert 'formaction="/ocio/buscar"' in button.group(0)
    assert "Search the catalogs ↵" in button.group(1)
    assert '<input type="hidden" name="en" value="ocio">' in body


def test_the_candidates_are_a_fragment(client, asked):
    body = client.get("/ocio/candidatos?q=terminator&tipo=movie").text
    assert "<html" not in body and 'data-search="terminator"' in body
    assert ">The Terminator<" in body and "1984" in body and "James Cameron" in body
    assert '<img src="https://img/t.jpg" alt="" loading="lazy" referrerpolicy="no-referrer">' in body


def test_each_candidate_saves_itself(client, asked):
    body = client.get("/ocio/candidatos?q=terminator&tipo=movie").text
    form = re.search(r'<form[^>]*action="/ocio/guardar".*?</form>', body, re.S).group(0)
    assert 'name="tipo" value="movie"' in form and 'name="ref" value="tt0088247"' in form
    assert 'name="via" value="movie"' in form and ">Save<" in form


def test_all_kinds_is_films(client, asked):
    client.get("/ocio/candidatos?q=x")
    client.get("/ocio/candidatos?q=x&tipo=ovni")
    assert asked == [("movie", "x"), ("movie", "x")]


def test_a_book_names_its_author(client, asked):
    body = client.get("/ocio/candidatos?q=dune&tipo=book").text
    assert asked == [("book", "dune")] and "Frank Herbert" in body


def test_a_switch_of_kind_on_top(client, asked):
    body = client.get("/ocio/candidatos?q=dune&tipo=book").text
    kinds = re.findall(r'data-kind="(\w+)"', body)
    assert kinds == ["movie", "series", "anime", "book"]
    assert re.search(r'href="/ocio\?buscar=dune&amp;tipo=book" data-kind="book" class="on"', body)


def test_nothing_found_says_so(client, monkeypatch):
    monkeypatch.setattr("oknowledge.catalog.cinemeta.search", lambda *a, **k: ([], ""))
    assert "I found nothing in the catalogs" in client.get("/ocio/candidatos?q=zzz").text


def test_a_catalog_that_is_down_says_so(client, monkeypatch):
    monkeypatch.setattr("oknowledge.catalog.cinemeta.search",
                        lambda *a, **k: ([], "connection refused"))
    body = client.get("/ocio/candidatos?q=zzz").text
    assert "could not be reached" in body and "connection refused" in body


def test_no_words_no_search(client, asked):
    assert client.get("/ocio/candidatos?q=%20").status_code == 404
    assert asked == []


def test_without_javascript_ocio_draws_them_in_the_panel(client, asked):
    body = client.get("/ocio?buscar=terminator&tipo=series").text
    panel = body[body.index('id="panel"'):]
    assert ">The Terminator<" in panel
    assert asked == [("series", "terminator")]


def test_the_old_search_page_sends_you_to_the_panel(client):
    answer = client.get("/ocio/buscar?tipo=movie&q=Terminator&year=1984",
                        follow_redirects=False)
    assert answer.status_code == 303
    assert answer.headers["location"] == "/ocio?buscar=Terminator&tipo=movie&year=1984"


def test_the_button_without_words_is_just_ocio(client):
    answer = client.get("/ocio/buscar?q=&tipo=book", follow_redirects=False)
    assert answer.headers["location"] == "/ocio?tipo=book"


def test_a_saved_card_opens_in_ocio(client, monkeypatch):
    stub_the_card(monkeypatch)
    answer = client.post("/ocio/guardar", data={"tipo": "movie", "ref": "tt0088247",
                                                "via": "movie"}, follow_redirects=False)
    assert re.fullmatch(r"/ocio\?sel=[0-9a-f]{12}&notice=\w[\w-]*", answer.headers["location"])


# --- the field on /ocio ------------------------------------------------------------

def test_plain_text_from_ocio_lists_candidates(client):
    answer = client.post("/add", data={"q": "terminator", "en": "ocio", "tipo": "series"},
                         follow_redirects=False)
    assert answer.headers["location"] == "/ocio?buscar=terminator&tipo=series"


def test_a_prefix_lists_candidates_in_ocio(client):
    answer = client.post("/add", data={"q": "película:Terminator"}, follow_redirects=False)
    assert answer.headers["location"] == "/ocio?buscar=Terminator&tipo=movie"


def test_an_imdb_link_from_ocio_is_saved_as_a_card(client, monkeypatch):
    stub_the_card(monkeypatch)
    answer = client.post("/add", data={"q": "https://www.imdb.com/title/tt0088247/",
                                       "en": "ocio"}, follow_redirects=False)
    assert answer.headers["location"].startswith("/ocio?sel=")


def test_an_imdb_link_the_catalog_does_not_know_lists_it(client, monkeypatch):
    monkeypatch.setattr("oknowledge.catalog.cinemeta.card", lambda candidate: None)
    monkeypatch.setattr("oknowledge.catalog.cinemeta.search", lambda *a, **k: ([], ""))
    answer = client.post("/add", data={"q": "https://www.imdb.com/title/tt0088247/",
                                       "en": "ocio"}, follow_redirects=False)
    assert answer.headers["location"] == "/ocio?buscar=tt0088247&tipo=movie"


def test_another_link_from_ocio_is_not_a_card(client):
    answer = client.post("/add", data={"q": "https://myanimelist.net/anime/1", "en": "ocio"},
                         follow_redirects=False)
    assert answer.headers["location"] == "/ocio?notice=not-a-catalog-link"


def test_a_link_from_the_library_is_still_a_link(client, monkeypatch):
    taken = []
    monkeypatch.setattr("oknowledge.web.app.fetch",
                        lambda cfg, url, content, **rest: taken.append(url))
    client.post("/add", data={"q": "https://www.imdb.com/title/tt0088247/"})
    assert taken == ["https://www.imdb.com/title/tt0088247/"]
```

Edits to existing tests:
- `tests/test_web_ocio_search.py`: the two prefix tests expect `"/ocio?buscar=Terminator&tipo=movie"`; every `client.get("/ocio/buscar?…")` from `test_the_candidates_are_drawn_with_what_matters` to the end reads `/ocio/candidatos?…` with `q=` and `tipo=` as they are; `test_an_unknown_kind_is_not_a_search` becomes `test_an_unknown_kind_searches_films` (`client.get("/ocio/candidatos?tipo=ovni&q=x")` then `assert fake_catalog.asked == [("movie", "x")]`); `test_a_search_with_no_words_is_not_a_search` reads `/ocio/candidatos?tipo=movie&q=` (still 404).
- `tests/test_web_ocio_save.py`: `"/item/" in answer.headers["location"]` → `"sel=" in answer.headers["location"]` (≈118, 220, 244, 331); `"/ocio/buscar?tipo=movie&q=tt…"` → `"/ocio/candidatos?tipo=movie&q=tt…"` (≈249–272).

- [ ] **Step 2: Run them to verify they fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_catalog_people.py tests/test_cards.py tests/test_web_ocio_catalogs.py`
Expected: FAIL — `Candidate` has no `people`, `from_link` does not exist, `/ocio/candidatos` is a 404.

- [ ] **Step 3: Who made it, and catalog links**

In `catalog/__init__.py` add to `Candidate`, after `poster`: `people: str = ""      # a book's author, a film's director, or ""`. In `openlibrary._candidate` add `people=_first(doc.get("author_name"))`; in `cinemeta.search` add `people=_first(meta.get("director"))` to the `Candidate(...)`.

In `cards.py`:

```python
_IMDB_LINK = re.compile(r"https?://(?:www\.|m\.)?imdb\.com/title/(tt\d{7,})(?:[/?#].*)?",
                        re.IGNORECASE)
_OPENLIBRARY_LINK = re.compile(r"https?://(?:www\.)?openlibrary\.org/works/(OL\d+W)(?:[/?#].*)?",
                               re.IGNORECASE)


def from_link(text: str, kind: str = "") -> Wanted | None:
    """A catalog's own page, pasted in Ocio: the card it names. Only the two
    catalogs a card is made from; any other page is a link, not a card."""
    text = text.strip()
    found = _IMDB_LINK.fullmatch(text)
    if found:
        return Wanted(kind=kind if kind in KINDS and kind != "book" else "movie",
                      query=found.group(1))
    found = _OPENLIBRARY_LINK.fullmatch(text)
    if found:
        return Wanted(kind="book", query=found.group(1).upper())
    return None
```

(`reference()` turns either id back into the catalog's form, which is what `only_one_meant()` asks it.)

- [ ] **Step 4: The routes**

Beside `ask_catalogs()`:

```python
    def candidates_context(q: str, tipo: str, year: str = "") -> dict | None:
        """What the catalogs answer, for the panel (spec §3). All kinds is
        films; no words is no search."""
        query = " ".join(q.split())[:cards.LONGEST]
        if not query:
            return None
        kind = tipo if tipo in cards.KINDS else "movie"
        ref = cards.reference(query)
        if ref:
            one = Candidate(ref=ref, kind=kind, via=catalog_type_for(kind), title=query)
            full = catalog_of(one.via).card(one)
            named = [] if full is None else [
                dataclasses.replace(one, title=full.title, year=full.year,
                                    rating=full.rating, poster=full.poster)]
            return {"query_text": query, "kind": kind, "candidates": named, "failed": "",
                    "KIND_ONE": KIND_ONE}
        found, failed = ask_catalogs(kind, query, year)
        return {"query_text": query, "kind": kind, "candidates": found[:cards.MOST],
                "failed": failed, "KIND_ONE": KIND_ONE}

    @app.get("/ocio/candidatos", response_class=HTMLResponse)
    def catalog_candidates(request: Request, q: str = "", tipo: str = "", year: str = ""):
        """The catalogs' answers as the panel draws them. Writes nothing:
        saving is the POST of each row (a GET that wrote a card could be
        made by any <img>)."""
        found = candidates_context(q, tipo, year)
        if found is None:
            raise HTTPException(status_code=404, detail="no such search")
        return page(request, "catalog-panel.html", **found)
```

Replace the body of `card_candidates` (`GET /ocio/buscar`) with:

```python
    @app.get("/ocio/buscar")
    def card_candidates(q: str = "", tipo: str = "", year: str = ""):
        """The old search page, and the field's button without JavaScript:
        the candidates live in Ocio's panel now."""
        query = " ".join(q.split())
        if not query:
            return see_other("/ocio", tipo=tipo if tipo in cards.KINDS else "")
        return see_other("/ocio", buscar=query, tipo=tipo if tipo in cards.KINDS else "movie",
                         year=year)
```

In `leisure`, read `buscar = request.query_params.get("buscar", "")` and `year = request.query_params.get("year", "")`; when `buscar` is not blank, `found = candidates_context(buscar, view.tipo or request.query_params.get("tipo", ""), year)` and pass `catalog=found` instead of the card panel (`panel=False`); `ocio-shelf.html`'s panel section draws `{% if catalog %}{% include "catalog-panel.html" with context %}{% elif panel %}…`. For `catalog-panel.html` to read its keys at the top level, pass `**found` and `catalog=True` instead of `catalog=found`.

`save_the_card`: `return see_other("/ocio", sel=saved, notice=notice)`.

`add_pasted` gains `en: str = Form("")` and `tipo: str = Form("")`. Replace its card half (from `asked = cards.wanted(url)` to the `see_other("/ocio/buscar", …)`) with:

```python
        asked = cards.wanted(url)
        if asked is None and en == "ocio":
            asked = cards.from_link(url, tipo)
        if asked is not None:
            only = only_one_meant(asked.kind, asked.query, asked.year)
            if only is not None:
                saved, notice = save_card(asked.kind, only, background)
                if saved:
                    return see_other("/ocio", sel=saved, notice=notice)
            return see_other("/ocio", buscar=asked.query, tipo=asked.kind, year=asked.year)
        if en == "ocio":
            # Ocio's field: a page that is no catalog's is not a card, and
            # plain words are a search of the catalogs (spec §3).
            if pasted_link(url):
                return see_other("/ocio", notice="not-a-catalog-link")
            words = " ".join(url.split())
            if not words:
                return see_other("/ocio")
            return see_other("/ocio", buscar=words, tipo=tipo if tipo in cards.KINDS else "movie")
```

Add to `NOTICES`: `"not-a-catalog-link": "Only an IMDb or Open Library page makes a card. Paste it in the Library to save it as a link."`. In the `already-saved` branch nothing changes here (Task 12).

- [ ] **Step 5: The templates**

`catalog-panel.html`:

```jinja
{# The catalogs' answers in Ocio's panel (spec §3). Nothing here writes but
   each row's Save, a POST. The posters are the catalog's, on its server:
   nothing is saved yet, so there is no local file to show. #}
<div class="card-top">
  <nav class="seg" aria-label="{{ t('Type') }}">
    {% for one in ('movie', 'series', 'anime', 'book') %}<a href="/ocio?buscar={{ query_text|urlencode }}&amp;tipo={{ one }}" data-kind="{{ one }}" class="{% if one == kind %}on{% endif %}">{{ t(KIND_ONE[one]) }}</a>{% endfor %}
  </nav>
</div>
<div class="detail-scroll candidates" data-panel="" data-search="{{ query_text }}">
  <p class="label">{{ t('Looking for “%1”', query_text) }}</p>
  {% if candidates %}
    <ul class="candidate-rows">
      {% for c in candidates %}
        <li class="candidate">
          {% if c.poster %}<img src="{{ c.poster }}" alt="" loading="lazy" referrerpolicy="no-referrer">
          {% else %}<span class="noposter" style="background: {{ kind|poster_fill }}" aria-hidden="true"></span>{% endif %}
          <span class="who">
            <b dir="auto">{{ c.title }}</b>
            <span class="meta">{% if c.year %}<span class="mono">{{ c.year }}</span>{% endif %}{% if c.people %}<span>{{ c.people }}</span>{% endif %}</span>
          </span>
          <form action="/ocio/guardar" method="post">
            <input type="hidden" name="tipo" value="{{ kind }}">
            <input type="hidden" name="ref" value="{{ c.ref }}">
            <input type="hidden" name="via" value="{{ c.via }}">
            <button class="btn">{{ t('Save') }}</button>
          </form>
        </li>
      {% endfor %}
    </ul>
  {% elif failed %}
    <div class="empty-state"><p class="empty-title">{{ t('The catalogue could not be reached. Try again in a moment.') }}</p>
      <p class="mono">{{ failed }}</p></div>
  {% else %}
    <div class="empty-state"><p class="empty-title">{{ t('I found nothing in the catalogs') }}</p></div>
  {% endif %}
</div>
```

(The Save of a candidate is a plain POST, not `data-inline`: it ends on `/ocio?sel=` with the new card selected, which is a new page anyway.)

In `ocio-shelf.html`'s form add, after the hidden inputs, `<input type="hidden" name="en" value="ocio">` and, after the `<span class="save">…</span>`:

```jinja
    <span class="find">
      <button type="submit" class="btn primary" formmethod="get" formaction="/ocio/buscar" id="catalog-search">{{ t('Search the catalogs') }} ↵</button>
    </span>
```

and give the form `class="unified{% if field_saves %} saving{% elif view.q %} finding{% endif %}"`, with `field_saves=saves(view.q)` passed from `leisure` (`library_view.saves`, the library's own test of "a link or a prefix"). Delete `templates/candidates.html`.

Append to `app.css`:

```css
.unified .find { display: none; }
.unified.finding .find { display: flex; }
.unified.finding .hint { display: none; }
.detail-scroll.candidates { padding: 18px 24px; gap: 12px; }
.candidate-rows { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.candidate { display: grid; grid-template-columns: 44px minmax(0, 1fr) auto; gap: 12px;
  align-items: center; padding: 8px; border-radius: 10px; background: var(--s2); }
.candidate img, .candidate .noposter { width: 44px; aspect-ratio: 2 / 3; border-radius: 6px;
  object-fit: cover; display: block; }
.candidate .who { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.candidate .who b { font-size: 13.5px; font-weight: 500; color: var(--t1); overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap; }
.candidate .meta { display: flex; gap: 6px; font-size: 12px; color: var(--t5); }
.candidate .meta > * + *::before { content: "·"; margin-right: 6px; }
.candidate form { margin: 0; }
```

- [ ] **Step 6: The Spanish**

| key | es |
|---|---|
| Search the catalogs | Buscar en catálogos |
| I found nothing in the catalogs | No encontré nada en los catálogos |
| Type | Tipo |
| Only an IMDb or Open Library page makes a card. Paste it in the Library to save it as a link. | Sólo una página de IMDb u Open Library arma una ficha. Pegala en la Biblioteca para guardarla como link. |

("Looking for “%1”", "Save" and "The catalogue could not be reached. Try again in a moment." exist.) Then `tests/test_i18n.py`, and delete what only `candidates.html` asked for ("Which one?", "Nothing found for “%1”.", exactly the ones it lists).

- [ ] **Step 7: Run the tests**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_catalog_people.py tests/test_cards.py tests/test_web_ocio_catalogs.py tests/test_web_ocio_search.py tests/test_web_ocio_save.py tests/test_web_ocio_shelf.py tests/test_i18n.py tests/test_web_read.py`
Expected: PASS.

- [ ] **Step 8: Whole suite, commit**

Run the suite; expected green.

```bash
git add -A src/oknowledge tests
git commit -m "Search the catalogs from Ocio's field and pick the card in its panel"
```

---
### Task 11: Ocio without reloads

**Files:**
- Modify: `src/oknowledge/web/static/shell.js`
- Modify: `src/oknowledge/web/templates/ocio-shelf.html` (scripts), `card-panel.html` and `ocio-list.html` (the toast words for a rewrite), `src/oknowledge/i18n.py`
- Test: `tests/test_web_shell_js.py` (append), `tests/test_web_ocio_scripts.py` (new)

**Interfaces:**
- Consumes: `window.oknowledge.{toast, post, bind}` (Task 6); `/ocio/lista`, `/panel/{card}`, `/ocio/candidatos`, `/item/{id}/state` for cards (Tasks 8–10); `data-mode="ocio"`, `#catalog-search`, `a[data-kind]`, `[data-working]`, `data-done-as`/`data-failed-as`.
- Produces: `shell.js` posts every `form[data-inline]` with `Accept: application/json` and reads `{ok, notice, error}` (the library's panel too — its routes answer JSON since Task 1); after each panel swap it calls `window.oknowledge.bind(panel)` when `autosave.js` is on the page.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_web_shell_js.py`:

```python
def test_inline_writes_ask_for_json_and_say_what_came_back():
    body = between(SCRIPT.read_text(encoding="utf-8"), 'form[data-inline]', "// --- links being read")
    assert 'Accept: "application/json"' in body
    assert "answer.notice" in body and "answer.error" in body


def test_a_panel_that_lands_binds_its_autosave():
    body = between(SCRIPT.read_text(encoding="utf-8"), "function loadPanel", "function emptyPanel")
    assert "window.oknowledge" in body and ".bind(panel)" in body


def test_ocio_searches_the_catalogs_in_the_panel():
    text = SCRIPT.read_text(encoding="utf-8")
    body = between(text, "function loadCatalog", "function emptyPanel")
    assert '"/ocio/candidatos?"' in body and '"buscar"' in body
    assert "data-kind" in text and "catalog-search" in text


def test_a_rewrite_says_its_own_words_when_it_ends():
    body = between(SCRIPT.read_text(encoding="utf-8"), "function watch", "observe();\n  watch();\n})")
    assert "doneAs" in body and "failedAs" in body
    assert "panel.querySelectorAll" in body
```

`tests/test_web_ocio_scripts.py`:

```python
"""What Ocio's page gives its scripts (spec §1 autosave, §3)."""

import re

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.vault import note_path, rebuild_indexes, write_note
from oknowledge.web.app import create_app


@pytest.fixture(autouse=True)
def state_tree(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr("oknowledge.web.app.CONFIG_PATH", tmp_path / "config" / "config.toml")


@pytest.fixture
def client(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    note = Note(id="c00000000001", url="https://www.imdb.com/title/tt1", title="Alien",
                category="Películas", tags=[], type="movie", source="imdb.com",
                saved="2026-10-01", summary="s", engine="")
    write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ocio))
    rebuild_indexes(cfg, "es")
    return TestClient(create_app(cfg))


def test_ocio_loads_autosave_then_the_shell(client):
    body = client.get("/ocio").text
    first = body.index('<script src="/static/autosave.js" defer></script>')
    assert first < body.index('<script src="/static/shell.js" defer></script>')


def test_a_card_panel_being_rewritten_carries_its_own_words(client):
    app = client.app
    app.state.rewriting.start("c00000000001", "describe")
    body = client.get("/panel/c00000000001").text
    root = re.search(r'<div class="detail-scroll card"[^>]*>', body).group(0)
    assert 'data-working="c00000000001"' in root
    assert 'data-done-as="Done: card rewritten"' in root
    assert 'data-failed-as="The card could not be rewritten"' in root


def test_the_grid_says_the_same_for_a_rewrite_of_all(client):
    body = client.get("/ocio").text
    grid = re.search(r'<ul class="posters"[^>]*>', body).group(0)
    assert 'data-done-as="Done: card rewritten"' in grid
```

- [ ] **Step 2: Run them to verify they fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_shell_js.py tests/test_web_ocio_scripts.py`
Expected: FAIL — no `Accept` header in `shell.js`, no scripts on `/ocio`, no `data-done-as`.

- [ ] **Step 3: The pages**

`ocio-shelf.html`: `{% block scripts %}<script src="/static/autosave.js" defer></script><script src="/static/shell.js" defer></script>{% endblock %}`.

`card-panel.html`: the root becomes

```jinja
<div class="detail-scroll card" data-panel="{{ panel_id }}"{% if rewriting %} data-working="{{ panel_id }}"{% endif %}
     data-done-as="{{ t('Done: card rewritten') }}" data-failed-as="{{ t('The card could not be rewritten') }}">
```

`ocio-list.html`: `<ul class="posters" id="items" data-current="{{ current }}" data-done-as="{{ t('Done: card rewritten') }}" data-failed-as="{{ t('The card could not be rewritten') }}">`.

| key | es |
|---|---|
| Done: card rewritten | Listo: ficha reescrita |
| The card could not be rewritten | No se pudo reescribir la ficha |

- [ ] **Step 4: shell.js**

1. In `loadPanel`'s success branch, after `panel.innerHTML = html;`:

```js
        if (window.oknowledge) window.oknowledge.bind(panel);   // the note saves itself
        watch();
```

2. `saves()` keeps Task 5's `if (mode !== "library") …` but lets Ocio save what the library saves: change that line to `if (mode === "ideas") return false;` and update the test of Task 5 (`test_in_ideas_enter_never_saves`) to look for `mode === "ideas"`.

3. The field in Ocio: in the `input` handler, after computing `saving`, `form.classList.toggle("finding", mode === "ocio" && !saving && text.trim() !== "");`.

4. The catalogs in the panel, after `emptyPanel`'s neighbour `loadPanel`:

```js
  // Ocio: the catalogs' answers in the panel (spec §3). The URL says what
  // was searched, so a reload shows the same.
  function loadCatalog(q, kind) {
    if (!panel) return;
    var mine = ++shownAsked;
    var url = here();
    url.searchParams.set("buscar", q);
    url.searchParams.set("tipo", kind || url.searchParams.get("tipo") || "movie");
    url.searchParams.delete("sel");
    history.replaceState(null, "", url.pathname + url.search);
    var ask = new URLSearchParams({ q: q, tipo: url.searchParams.get("tipo") });
    fetch("/ocio/candidatos?" + ask.toString())
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.text(); })
      .then(function (html) { if (mine === shownAsked) panel.innerHTML = html; })
      .catch(function () { if (mine === shownAsked) location.href = url.href; });
  }
```

(It sits right before `function emptyPanel`, which the test reads as its end.) In the `submit` handler of the form, before `if (saves(field.value))`:

```js
    var catalog = event.submitter && event.submitter.id === "catalog-search";
    if (mode === "ocio" && !saves(field.value) && (catalog || field.value.trim())) {
      event.preventDefault();
      if (field.value.trim()) loadCatalog(field.value.trim().split(/\s+/).join(" "));
      return;
    }
```

(and the first line of the handler stays: the Save button is a real POST). In the click handler, before the `a[data-sel]…` lookup:

```js
    var kind = event.target.closest("a[data-kind]");
    if (kind && panel && panel.contains(kind)) {
      event.preventDefault();
      var search = panel.querySelector("[data-search]");
      loadCatalog(search ? search.dataset.search : "", kind.dataset.kind);
      return;
    }
```

5. The inline writes speak JSON. Replace the `fetch(...)` chain of the `form[data-inline]` handler with:

```js
    fetch(target.action, { method: "POST", body: data,
                           headers: { Accept: "application/json" } })
      .then(function (r) {
        return r.json().catch(function () { return { ok: false }; });
      })
      .then(function (answer) {
        if (!answer.ok) { toast(answer.error || texts.saveFailed); return; }
        toast(answer.notice || "");
        var shown = panel && panel.querySelector("[data-panel]");
        if (shown && shown.dataset.panel && stillPicked(shown.dataset.panel)) {
          loadPanel(shown.dataset.panel, true);    // deleted: gone
        }
        loadList(here().href, true);
      })
      .catch(function () { toast(texts.saveFailed); });
```

6. `watch()` also watches a panel being rewritten, and each one says its own words:

```js
  var watched = {};
  function watch() {
    var busy = Array.prototype.slice.call(list.querySelectorAll("[data-working]"));
    if (panel) busy = busy.concat(Array.prototype.slice.call(panel.querySelectorAll("[data-working]")));
    busy.forEach(function (el) {
      var id = el.dataset.working;
      if (watched[id]) return;
      var words = el.closest("[data-done-as]");
      var doneAs = words ? words.dataset.doneAs : texts.done;
      var failedAs = words ? words.dataset.failedAs : texts.failed;
      watched[id] = setInterval(function () {
        fetch("/item/" + encodeURIComponent(id) + "/state")
          .then(function (r) { return r.json(); })
          .then(function (state) {
            if (state.working) return;
            clearInterval(watched[id]);
            delete watched[id];
            toast(state.status === "failed" ? failedAs : doneAs);
            var shown = panel && panel.querySelector("[data-panel]");
            if (shown && shown.dataset.panel === id && stillPicked(id)) loadPanel(id, true);
            loadList(here().href, true);
          })
          .catch(function () { /* try again in three seconds */ });
      }, 3000);
    });
  }
```

- [ ] **Step 5: Run the tests**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_shell_js.py tests/test_web_ocio_scripts.py tests/test_packaging.py tests/test_i18n.py`
Expected: PASS.

- [ ] **Step 6: Check it in a browser**

The catalogs are answered by Playwright, not by the internet (the scratch server would otherwise call Cinemeta):

```bash
SP=/tmp/claude-1000/-home-fer-Projects-gym/d89ecc8a-2029-44cb-b47f-742ed00daeae/scratchpad
~/.local/share/oknowledge/venv/bin/python "$SP/shots/serve.py" > "$SP/serve.log" 2>&1 &
echo $! > "$SP/serve.pid"
cd "$SP/pw" && [ -d node_modules/playwright ] || npm install --no-save --silent playwright
cat > "$SP/pw/ocio.js" <<'EOF'
const { chromium } = require("playwright");
const BASE = "http://127.0.0.1:8812";
(async () => {
  const browser = await chromium.launch({ executablePath: "/usr/bin/chromium" });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.route("**/ocio/candidatos*", (r) => r.fulfill({ contentType: "text/html",
    body: '<div class="card-top"><nav class="seg"><a href="#" data-kind="book">Libro</a></nav></div>' +
          '<div class="detail-scroll candidates" data-panel="" data-search="dune"><p>STUB ' +
          new URL(r.request().url()).search + '</p></div>' }));
  await page.goto(`${BASE}/ocio`);
  console.log("posters", await page.locator("li.poster").count());
  await page.fill("#field-q", "dune");
  await page.waitForTimeout(600);
  console.log("filtered", await page.locator("li.poster").count(),
              "catalog button", await page.locator("#catalog-search").isVisible());
  await page.keyboard.press("Enter");
  await page.waitForTimeout(500);
  console.log("panel", (await page.textContent("#panel")).trim(), "url", new URL(page.url()).search);
  await page.click("#panel a[data-kind=book]");
  await page.waitForTimeout(500);
  console.log("kind", (await page.textContent("#panel")).trim());
  await page.fill("#field-q", "");
  await page.waitForTimeout(600);
  await page.click("li.poster >> nth=0");
  await page.waitForTimeout(500);
  await page.click("#panel .card-top .seg button >> nth=0");
  await page.waitForTimeout(800);
  console.log("state on", await page.locator("#panel .card-top .seg button.on").textContent(),
              "reloaded", page.url().includes("notice="));
  await page.fill("#card-note", "Muy buena.");
  await page.waitForTimeout(1600);
  console.log("note", await page.textContent("#card-save-state"));
  console.log("scroll", await page.evaluate(() => document.scrollingElement.scrollHeight <= innerHeight));
  await browser.close();
})();
EOF
node "$SP/pw/ocio.js"
ps -p "$(cat "$SP/serve.pid")" -o args= | grep -q serve.py && kill "$(cat "$SP/serve.pid")"
```

Expected:

```
posters 6
filtered 0 catalog button true
panel STUB ?q=dune&tipo=movie url ?buscar=dune&tipo=movie
kind STUB ?q=dune&tipo=book
state on Por ver reloaded false
note guardado
scroll true
```

(`filtered 0`: the scratch vault has no card named "dune". The numbers of posters follow `$SP/shots/serve.py`'s six cards.)

- [ ] **Step 7: Whole suite, commit**

Run the suite; expected green.

```bash
git add src/oknowledge/web/static/shell.js src/oknowledge/web/templates/ocio-shelf.html \
        src/oknowledge/web/templates/card-panel.html src/oknowledge/web/templates/ocio-list.html \
        src/oknowledge/i18n.py tests/test_web_shell_js.py tests/test_web_ocio_scripts.py
git commit -m "Run Ocio in place: live filter, catalogs in the panel, JSON writes and the card's note saving itself"
```

---
### Task 12: Delivery 1's leftovers that touch the same screens

**Files:**
- Modify: `src/oknowledge/web/static/app.css` (`.chip`, `.chips`, `.warn` ≈159–178 scoped)
- Modify: `src/oknowledge/web/app.py` — `add_pasted`'s `already-saved` (≈2011) carries `sel`; `page()` (≈704) stops ranking marks; the `rank_marks` import goes if nothing else reads it
- Modify: `src/oknowledge/web/static/layout.js` (the notice leaves the URL), `src/oknowledge/web/static/shell.js` (the pick is written to the URL)
- Modify: `src/oknowledge/web/templates/shelf-items.html` (the ★ is said)
- Modify: `src/oknowledge/web/index.py` (delete `tally`, `years`, `months`, `tag_home`, `filter(when=)` and what only they use)
- Modify: `src/oknowledge/web/static/style.css` (rules only the deleted pages used)
- Test: `tests/test_web_leftovers.py` (new); delete the tests of the deleted helpers (ledger)

**Interfaces:**
- Consumes: everything above; nothing later depends on this task but Task 13's screenshots.
- Produces: no new names. `Library.filter(category=None, tag=None, collection=None)` loses `when`.

- [ ] **Step 1: Write the failing tests**

`tests/test_web_leftovers.py`:

```python
"""docs/2026-10-14-rediseno-biblioteca-pendientes.md, the part spec §4 takes."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.urls import link_id
from oknowledge.vault import rebuild_indexes, write_note
from oknowledge.web import index
from oknowledge.web.app import create_app

STATIC = Path(__file__).resolve().parent.parent / "src" / "oknowledge" / "web" / "static"


@pytest.fixture
def cfg(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    config = Config(vault=vault)
    write_note(config, Note(id=link_id("https://e.com/x"), url="https://e.com/x", title="Uno",
                            category="Redes", tags=["x"], type="article", source="e.com",
                            saved="2026-10-10", summary="s", mark="⭐"), "es")
    rebuild_indexes(config, "es")
    return config


def test_the_chip_rules_stay_in_the_redesigned_screens():
    css = (STATIC / "app.css").read_text(encoding="utf-8")
    for name in (".chip", ".chips", ".warn"):
        bare = re.findall(rf"^{re.escape(name)}[ ,:{{]", css, re.M)
        assert bare == [], f"{name} is still global in app.css"
    assert ":where(.app:not(.legacy)) .chip {" in css


def test_pasting_a_link_you_have_opens_it(cfg):
    answer = TestClient(create_app(cfg)).post("/add", data={"q": "https://e.com/x"},
                                              follow_redirects=False)
    assert answer.headers["location"] == f"/?sel={link_id('https://e.com/x')}&notice=already-saved"


def test_the_notice_leaves_the_url_once_said():
    script = (STATIC / "layout.js").read_text(encoding="utf-8")
    assert "history.replaceState" in script
    for name in ('"notice"', '"n"', '"m"'):
        assert name in script


def test_the_pick_is_written_when_the_url_has_none():
    script = (STATIC / "shell.js").read_text(encoding="utf-8")
    assert "dataset.current" in script and 'searchParams.get("sel")' in script
    assert "// --- the pick in the URL" in script


def test_the_favorite_star_on_a_card_is_said(cfg):
    body = TestClient(create_app(cfg)).get("/").text
    flag = re.search(r'<span class="flag fav"[^>]*>', body).group(0)
    assert 'role="img"' in flag and 'aria-label="Favorite"' in flag


def test_the_dead_helpers_are_gone():
    for name in ("tally", "tag_home", "years", "months"):
        assert not hasattr(index.Library, name) and not hasattr(index, name)


def test_no_page_ranks_marks_any_more():
    source = (Path(__file__).resolve().parent.parent / "src" / "oknowledge" / "web"
              / "app.py").read_text(encoding="utf-8")
    assert "used_marks" not in source and "rank_marks" not in source
```

**Ledger — tests deleted here:** `tests/test_web_read.py::test_a_tag_belongs_to_the_category_it_is_used_in_most`, `::test_a_tag_used_evenly_lands_in_the_same_group_every_time` (`tag_home`), and from `::test_the_library_counts_the_notes_of_each_year` through `::test_a_period_and_a_collection_are_asked_together` (`years`, `months`, `filter(when=)`), plus their `dated` fixture if nothing else uses it; in `tests/test_web_findability.py::test_a_vanished_vault_leaves_nothing_behind_to_offer` drop `and library.years() == {"2021": 1}` and the `library.years(), library.months()` pair from the tuple (the rest of the test stands).

- [ ] **Step 2: Run them to verify they fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_leftovers.py`
Expected: FAIL — `.chip {` is global, the `already-saved` redirect has no `sel`, etc.

- [ ] **Step 3: The changes**

1. `app.css`: prefix the three rules and their children (`.chip`, `.chip::-webkit-details-marker`, `.chip button`, `.chip a`, `.chips`, `.warn`) with `:where(.app:not(.legacy)) ` — every redesigned screen has an `app_class` other than `legacy`, and the pages still on the old layout (settings, categories, import, activity) get their chips from `style.css` again. `:where()` keeps the specificity the rules have today, so `.poster .chip` and `.idea-head .chip` still override them.

2. `add_pasted`: `return see_other("/", sel=link_id(clean), notice="already-saved")`.

3. `layout.js`, at the end of the IIFE:

```js
  // A notice is said once. Left in the URL, a reload would say it again.
  var said = new URL(location.href);
  if (said.searchParams.has("notice")) {
    ["notice", "n", "m"].forEach(function (name) { said.searchParams.delete(name); });
    history.replaceState(null, "", said.pathname + said.search + said.hash);
  }
```

4. `shell.js`, before the final `observe(); watch();`:

```js
  // --- the pick in the URL -------------------------------------------------
  // With no sel, a reload of the list would open whatever is first by then
  // (a batch adds links on top): the pick shown is written down.
  (function () {
    var items = document.getElementById("items");
    var url = here();
    if (panel && items && items.dataset.current && !url.searchParams.get("sel")) {
      url.searchParams.set("sel", items.dataset.current);
      history.replaceState(null, "", url.pathname + url.search);
    }
  })();
```

5. `shelf-items.html`: the flag span becomes `<span class="flag{% if note.mark == '⭐' %} fav{% endif %}"{% if note.mark == '⭐' %} role="img" aria-label="{{ t('Favorite') }}"{% endif %}>`.

6. `page()`: delete the `used = rank_marks(...)` lines and `"used_marks"` from both dicts; keep `"marks"` (the library panel's ⋯ uses it). Remove `rank_marks` from the `..marks` import.

7. `index.py`: delete `tally()`, `Library.years()`, `Library.months()`, `Library.tag_home()`, the `when` parameter and its branch in `Library.filter()`, and then every name `grep -n` shows only these used (`periods()`, `period_of`, `UNDATED`, the year/month counters in `refresh()`): check each with `grep -rn "<name>" src/ tests/` before deleting it.

8. `style.css`: for each selector below, `grep -rn` it in `src/oknowledge/web/templates` and `static/*.js`; delete the rule when nothing matches: `.new-idea`, `.filters`, `.candidates`, `.noposter` (the new one is in `app.css` under `.candidate`), `.who`, `.mine`, `.mine-buttons`, `.picker`, `.mark-picker`, `.save-icon`, `.cards .stars`, `.card .pad`, `.card .sum`, `.card .site`, `.unwritten`, `.state`, `.embed`, `.popup`, `dialog`, `.timeline`, `.years`, `.months`. (A rule with several selectors keeps the ones still used.)

- [ ] **Step 4: Run the tests**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_leftovers.py tests/test_web_read.py tests/test_web_findability.py tests/test_web_add.py tests/test_web_shell_js.py tests/test_web_layout.py tests/test_packaging.py`
Expected: PASS.

- [ ] **Step 5: Check the old pages still look like themselves**

```bash
SP=/tmp/claude-1000/-home-fer-Projects-gym/d89ecc8a-2029-44cb-b47f-742ed00daeae/scratchpad
~/.local/share/oknowledge/venv/bin/python "$SP/shots/serve.py" > "$SP/serve.log" 2>&1 &
echo $! > "$SP/serve.pid"
cd "$SP/pw" && [ -d node_modules/playwright ] || npm install --no-save --silent playwright
cat > "$SP/pw/legacy.js" <<'EOF'
const { chromium } = require("playwright");
(async () => {
  const browser = await chromium.launch({ executablePath: "/usr/bin/chromium" });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  for (const path of ["/settings", "/categories", "/retry", "/import"]) {
    await page.goto("http://127.0.0.1:8812" + path);
    await page.screenshot({ path: `${process.argv[2]}/legacy${path.replace("/", "-")}.png` });
  }
  await page.goto("http://127.0.0.1:8812/?notice=saved");
  console.log("notice gone", !page.url().includes("notice="), "sel written", page.url().includes("sel="));
  await browser.close();
})();
EOF
mkdir -p "$SP/shots/leftovers" && node "$SP/pw/legacy.js" "$SP/shots/leftovers"
ps -p "$(cat "$SP/serve.pid")" -o args= | grep -q serve.py && kill "$(cat "$SP/serve.pid")"
```

Expected: `notice gone true sel written true`. Look at the four PNGs with the Read tool: the chips and warnings there must look as they did before delivery 1's `app.css` (no `--s4` background leaking onto them).

- [ ] **Step 6: Whole suite, commit**

Run the suite; expected green, minus the ledger.

```bash
git add -A src/oknowledge tests
git commit -m "Fold in delivery 1's leftovers: scoped chips, the pick and the notice in the URL, a spoken star, dead code out"
```

---
### Task 13: The screens in Spanish, side by side with the handoff

**Files:**
- Test: `tests/test_web_redesign_spanish.py` (new)
- Modify: `src/oknowledge/i18n.py` (only if a string of spec §5 comes out different), `src/oknowledge/web/static/app.css` (only the differences the screenshots show)
- Create (scratch, not committed): `$SP/pw/shots2.js`, `$SP/shots/d2/*.png`

**Interfaces:**
- Consumes: every screen of Tasks 3–12.
- Produces: nothing new; a check that spec §5's words are on screen as the handoff writes them, and screenshots at 1440×900 compared with `design_handoff_oknowledge_redesign/screenshots/12-ocio.png` and `13-idea.png`.

- [ ] **Step 1: Write the failing test**

`tests/test_web_redesign_spanish.py`:

```python
"""Spec §5: the handoff's words, verbatim, on the three screens of this
delivery. One request per screen, every string looked for in it."""

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.model import Note
from oknowledge.vault import note_path, rebuild_indexes, write_note
from oknowledge.web.app import create_app


@pytest.fixture
def client(tmp_path, isolated_ui_language, monkeypatch):
    isolated_ui_language.write_text('{"language": "es"}', encoding="utf-8")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    write_note(cfg, Note(id="l00000000001", url="https://wireguard.com", title="WireGuard",
                         category="Redes", tags=["vpn"], type="article", source="wireguard.com",
                         saved="2026-10-10", summary="Una vpn."), "es")
    idea = new_idea("Una vpn para la familia.", "VPN familiar", "2026-10-13",
                    "2026-10-13T00:00:00.000001+00:00")
    idea.tags = ["vpn"]
    write_note(cfg, idea, "es", path=note_path(cfg, idea, shelf=cfg.ideas))
    for n, (kind, category) in enumerate((("movie", "Películas"), ("book", "Libros")), 1):
        card = Note(id=f"c{n:011d}", url=f"https://www.imdb.com/title/tt{n}", title=f"Ficha {n}",
                    category=category, tags=[], type=kind, source="imdb.com",
                    saved=f"2026-10-0{n}", summary="De qué va.", engine="")
        write_note(cfg, card, "es", path=note_path(cfg, card, shelf=cfg.ocio))
    for shelf in (cfg.links, cfg.ocio, cfg.ideas):
        rebuild_indexes(cfg, "es", shelf=shelf)
    client = TestClient(create_app(cfg))
    client.idea = idea.id
    return client


IDEA_SCREEN = ["← Ideas", "creada 13 oct", "Guardando…", "Guardado", "PEDILE A LA IA", "usando",
               "Links vinculados (0)", "Toda la biblioteca", "Sólo mi texto", "TU IDEA",
               "Escribila como te salga: la IA la ordena.", "se guarda sola", "Resumen",
               "¿Ya existe?", "Mejoras", "Ampliación", "Todavía no se lo pediste.",
               "Regenerar todo con la IA", "Borrar idea", "Links de esta idea",
               "Buscá en tus 1 links para sumar", "VINCULADOS", "PUEDEN SERVIR", "+ Sumar",
               "semilla", "en marcha"]

IDEAS_LIST = ["Nueva idea", "Buscá en tus ideas", "ESTADO", "descartada"]

OCIO = ["Buscá en Ocio o pegá un link de IMDb u Open Library",
        "2 fichas sin reescribir", "Reescribir", "Recientes", "Por ver", "Viendo", "Vista",
        "Reescribir la ficha", "Cambiar tipo", "Abrir en imdb.com",
        "La ficha está como vino de la fuente (en inglés).", "Reescribir en español",
        "DE QUÉ TRATA", "TU NOTA", "Qué te pareció", "Buscar en catálogos", "TIPO",
        "Películas", "Libros"]


@pytest.mark.parametrize("text", IDEA_SCREEN)
def test_the_idea_screen_says_it_as_the_handoff_does(client, text):
    assert text in client.get(f"/ideas/{client.idea}").text


@pytest.mark.parametrize("text", IDEAS_LIST)
def test_the_ideas_list_says_it_as_the_handoff_does(client, text):
    assert text in client.get("/ideas").text


@pytest.mark.parametrize("text", OCIO)
def test_ocio_says_it_as_the_handoff_does(client, text):
    assert text in client.get("/ocio?sel=c00000000001").text


def test_a_book_s_states_are_read(client):
    body = client.get("/ocio?tipo=book").text
    for text in ("Por leer", "Leyendo", "Leído"):
        assert text in body


def test_the_idea_screen_has_no_english_left(client):
    body = client.get(f"/ideas/{client.idea}").text
    for english in ("Saving…", "ASK THE AI", "YOUR IDEA", "Linked links", "Delete idea",
                    "+ Add", "LINKED", "MAY HELP"):
        assert english not in body
```

- [ ] **Step 2: Run it**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_redesign_spanish.py`
Expected: PASS if every task added its Spanish as its table said. For each failing parameter, fix the entry in `STRINGS["es"]` to the spec's words (the spec is binding: §5 lists them verbatim) and run again until it passes. ("Buscá en tus 1 links para sumar" is the handoff's sentence with this fixture's count; the template does not pluralise it, as the handoff does not.)

- [ ] **Step 3: Screenshots of the scratch vault**

```bash
SP=/tmp/claude-1000/-home-fer-Projects-gym/d89ecc8a-2029-44cb-b47f-742ed00daeae/scratchpad
~/.local/share/oknowledge/venv/bin/python "$SP/shots/serve.py" > "$SP/serve.log" 2>&1 &
echo $! > "$SP/serve.pid"
cd "$SP/pw" && [ -d node_modules/playwright ] || npm install --no-save --silent playwright
cat > "$SP/pw/shots2.js" <<'EOF'
const { chromium } = require("playwright");
const fs = require("fs");
const OUT = process.argv[2];
const ID = fs.readFileSync(process.argv[3], "utf8").trim();
(async () => {
  const browser = await chromium.launch({ executablePath: "/usr/bin/chromium" });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const shots = [["12-ocio", "/ocio"], ["13-idea", `/ideas/${ID}?pestana=mejoras`],
                 ["ideas-list", "/ideas"], ["ocio-libros", "/ocio?tipo=book"]];
  for (const [name, path] of shots) {
    await page.goto("http://127.0.0.1:8812" + path);
    await page.waitForTimeout(400);
    const scroll = await page.evaluate(() => document.scrollingElement.scrollHeight <= innerHeight);
    await page.screenshot({ path: `${OUT}/${name}.png` });
    console.log(name, "no page scroll", scroll);
  }
  await browser.close();
})();
EOF
mkdir -p "$SP/shots/d2" && node "$SP/pw/shots2.js" "$SP/shots/d2" "$SP/shots/idea"
ps -p "$(cat "$SP/serve.pid")" -o args= | grep -q serve.py && kill "$(cat "$SP/serve.pid")"
```

Expected: four lines, each ending `no page scroll true`.

- [ ] **Step 4: Compare with the handoff**

Read `$SP/shots/d2/12-ocio.png` beside `design_handoff_oknowledge_redesign/screenshots/12-ocio.png`, and `$SP/shots/d2/13-idea.png` beside `13-idea.png`, with the Read tool. Check, in this order: the three columns' widths (216 | grid | 460 and 216 | 1fr | 400), the header and AI bar paddings and backgrounds, the poster grid's columns and chips, the selected poster's 2px border, the AI buttons' look, the tabs, the numbered points / result cards, the links column's rows and dashed suggestions, fonts and sizes. For every difference, read the element's inline style in `Ocio.dc.html` or `Idea detalle.dc.html` and change the matching rule in the `app.css` blocks of Tasks 3, 4, 8, 9 or 10 to that value. Re-run Step 3 after each round; stop when nothing differs but the data (titles, covers, counts).

- [ ] **Step 5: Whole suite, commit**

Run the suite; expected green.

```bash
git add tests/test_web_redesign_spanish.py src/oknowledge/i18n.py src/oknowledge/web/static/app.css
git commit -m "Check the handoff's Spanish on the new screens and match their spacing to the screenshots"
```

(The screenshots stay in the scratchpad: the repository is public and they show a test vault, not the product.)

---

## Self-review

- **Spec coverage.** §1 sidebar groups (Tasks 5, 8), autosave (6, 9, 11), JSON writes (1), no Save/💾/"Editar etiquetas" (3, 9; `data-nojs`), removals (7, 8, 9, 10), redirects of `/item/{id}` (7, 9). §2 list (5), screen header/AI bar/body/tabs (3), links column (4), 2.1 scope (2), 2.2 state and polling (2, 6). §3 grid, filters, order, notice (8), panel and `/item/{id}/kind` (9), catalogs (10), in-place behaviour (11). §4 (12, and the removals in 7–10). §5 (each task's table; 13). §6 every bullet has its test file named in its task.
- **Review Focus.** 1 → Task 6 `test_one_save_in_flight_per_field_and_the_newest_text_after_it`, `test_a_reply_never_writes_the_field` and the browser check; 2 → Task 2 scope tests; 3 → Task 2 `/actions/state` 404 and Task 6 `test_a_deleted_idea_stops_the_poll_and_goes_back` plus the browser check; 4 → Task 8 `test_year_newest_first_and_missing_or_odd_years_last`, `test_stars_most_first_and_none_last`; 5 → Task 8 `test_a_poster_without_a_cover_is_the_gradient_with_the_title`, `test_a_kind_nobody_knows_gets_the_neutral_fill`, `test_a_poster_without_a_cover_is_its_kind_s_gradient`.
- **Names across tasks.** `answer()`/`FAILURES`/`wants_json()` (1) → 2–4, 8–10; `SCOPES`, `may_serve` (2) → 3, 4; `idea_url`, `idea_context` (3) → 4, 5, 7; `IdeaView`, `filters` in `sidebar.html` (5) → 8; `window.oknowledge` (6) → 11; `CardView`, `words_for`, `KIND_ONE`, `poster_fill`, `catalog_name` (8) → 9–11; `card_context` (9) → 10; `candidates_context` (10) → 11.
