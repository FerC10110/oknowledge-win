# Rediseño, entrega 3 (modales, teclado, selección múltiple y Deshacer) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Settings becomes a tabbed modal that saves as you go. A shortcuts dialog and the keyboard of the handoff work on every screen. Library, Ocio and Ideas items can be ticked and moved, starred or deleted together from a floating bar. Every delete — one or many — offers **Deshacer** for 5 s and puts the files back exactly where they were.

**Architecture:** Server-rendered as in deliveries 1 and 2.
- **Vault and undo.** The vault gains `restore_note()` and a `rebuild=` switch. A new module `undo.py` keeps one small JSON per delete under `$XDG_STATE_HOME/oknowledge/undo/`; the notes themselves stay in `<vault>/oknowledge/trash/` as today.
- **Routes.** The routes get `POST /undo/{token}`, `POST /bulk/{action}`, `GET /settings/panel` (a fragment) and a partial `POST /settings`. Every settings write answers through `answer()`.
- **Scripts.** A new `static/app.js` loads first on every page: one toast, the menu rule, the two `<dialog>` modals and the global keys. `settings.js` binds the Settings fragment, on the page or in the modal. `shell.js` adds the list keys and exposes `oknowledge.list`. A new `select.js` drives the checkboxes and the bulk bar.

**Tech Stack:** Python 3.12, FastAPI + Jinja2, plain JS (no build), pytest + TestClient, `node --check` and small node harnesses for JS, Playwright for node driving `/usr/bin/chromium` for behaviour checks and screenshots.

**Spec:** `docs/2026-10-14-rediseno-modales-teclado-design.md` (binding). Earlier deliveries: `docs/2026-10-14-rediseno-biblioteca-plan.md`, `docs/2026-10-14-rediseno-ocio-ideas-plan.md` (conventions this builds on).
**Visual reference:** `design_handoff_oknowledge_redesign/README.md`:
- §4 Ajustes, §5 Ayuda de atajos and §6 Toast;
- "Barra de selección múltiple" and the checkbox under "Tarjeta";
- "Interactions & Behavior", plus the tokens and radii;
- screenshots `03-pantalla.png` (multi-select), `07` (Ajustes → Motores), `08` (Ajustes → Idioma y guardado) and `09` (Atajos).

## Rulings in this plan

The spec left these open. Each is decided here, for review:

1. **`undo.remember(cfg, items)`**, not `remember(items)`. Paths are stored relative to `cfg.root`, which the function cannot know otherwise.
2. **A lot is claimed before it is restored.** `restore()` unlinks the JSON *first*, then moves the notes. A second Deshacer (a double click, or the form and the script at once) finds nothing and answers `undo-gone`, never a half-restore twice. Consequence: a lot whose notes were all skipped (`undo-blocked`) cannot be retried; the files are still in `trash/`.
3. **`restore_note()` placement.**
   - `source` must sit *directly* in `shelf.dir`, and `target` directly in `trash_dir(cfg)`. Anything else is refused.
   - The move is `os.link` + `unlink`. On a filesystem without hard links (`os.link` raises something other than `FileExistsError`), it reserves the name with `O_CREAT|O_EXCL` and then `os.replace`s onto its own placeholder. Either way an existing file is never overwritten.
4. **New notices.**
   - `deleted` ("Deleted", JSON only).
   - `undo-gone` (404) and `undo-blocked` (409).
   - `restored-one` / `restored` / `restored-partial` / `restored-one-partial`, with `n` = restored and `m` = skipped.
   - `restored-indexes-stale`.
   - `analysing` / `analysing-one` (the JSON of `POST /retry`).
   - `bad-state` (400, bulk only).
   - In `FAILURES`: `nothing-picked` 400, `settings-failed` 500, `env-failed` 500, `env-there` 409, `batch-running` 409.
5. **Rebuilds in bulk.**
   - Only `category`, `kind` and `delete` rebuild, once per shelf touched. A state or a mark never names an index, so it rebuilt nothing before either.
6. **Bulk `mark`.**
   - It takes only `⭐`. Any other value is `bad-mark` (400).
   - Whether the batch stars or un-stars is decided over the ids that exist.
7. **Bulk `state`.**
   - A value outside `IDEA_STATES` is `bad-state` (400), refused before the first id.
   - A value that is valid for some notes but not for this one (`dropped` on a card) leaves that id in `failed`.
   - The single route `/item/{id}/mine/state` keeps today's rule (an unknown state silently changes nothing).
8. **Singular forms added:**
   - "1 marked as favorite";
   - "1 could not be changed";
   - "Analysing 1 link";
   - "Restored · %2 not: …" (one restored, some skipped).
9. **No-JS bulk delete** (unreachable from the UI) redirects with `notice=trashed&undo=<token>`, not `notice=saved`, so the server toast offers Deshacer. The other actions redirect with `saved` as the spec says.
10. **`reload` never goes into a URL.** `answer()` copies `undo` and `reload` into the JSON. On a redirect it keeps `undo` and drops `reload`.
11. **`local_path()` drops `notice`, `n`, `m` and `undo`**, not just `notice`. That one change gives the toast's `back` field and every other "go back here" form a clean URL. No listing uses `n`, `m` or `undo` as a parameter.
12. **Checkboxes and radios are not "typing".** With the focus on a ticked checkbox, `j`/`x`/`⌫` still work. Text inputs, textareas, selects and contenteditable block every key but Esc.
13. **Esc** blurs only a *field* (a typing element). With the focus on a link or button, Esc goes on to clear the selection, so "click an item, `x`, Esc" clears it in one press.
14. **The keys-help `kbd`** follows spec §3.2 (Geist Mono 10px, border `1px #2a2b32`, radius 4), not the filled keys of screenshot 09. One `kbd` per key, so "1 2 3" is three.
15. **New key "Open the original link"** → "Abrir original" for the help row. The panel's button keeps its "Open original" → "Abrir el original".
16. **Mentions segment labels.**
    - New keys "Tools" → "Herramientas".
    - "All" is reused (already "Todo").
    - "Only what it discusses" changes its Spanish to "Sólo lo discutido".
    - "Tools and companies" and "Everything named" leave the table, since nothing asks for them any more.
17. **One toast, delegated.**
    - `autosave.js` and `shell.js` keep a one-line local `toast(text)` that calls `window.oknowledge.toast`. Their callers (and the delivery-2 source tests that pin `toast(body.notice)`) stay as they are; the element is created by nobody but `app.js`.
    - `autosave.js` extends `window.oknowledge` instead of replacing it, and its node harness keeps passing.
18. **Rename in the modal reloads on close.** Any rename that answered `ok` reloads the page when the modal closes. It does not try to tell whether something moved.
19. **The Settings ✕** is `<a href="/" data-close>`. In the modal, `app.js` turns the click into `dialog.close()`. On the `/settings` page it goes to the library. One markup for both.
20. **Toast animation.**
    - The server's toast hides itself by CSS (`.toast:not(.live)`, 2.2 s; 5 s with `.undo`).
    - `app.js` adds `live` to any toast it owns and times it itself.
21. **Checkbox geometry.**
    - On a card or poster the checkbox is positioned absolutely, top-left.
    - In a row it sits in a left gutter (`padding-left` on the row's `.hit` under `.js`), which looks like the handoff's `18px 8px 1fr auto` grid without moving the checkbox inside the link.
22. **`POST /settings` with no or an unknown `tab`** redirects to `/settings`.
23. **The readable-key warning** (`chmod 600`) moves out of the `api-only` block, so it shows whatever engine is ticked ("sigue siempre visible").
24. **`delete_one(link_id, rebuild)` returns `(Edited, shelf name)`.** The bulk route needs the shelf of each deleted note, both for its rebuilds and for the undo lot.
25. **The delete in the panel picks the next item client-side.**
    - `shell.js` computes "the one after, else the one before, else none" from the list on screen *before* reloading, and puts it in `sel`.
    - With none left, the panel is emptied. The server's `current` is not consulted for this.

## Global Constraints

- **Language.**
  - Code, Python names, commits and docstrings in English.
  - Every UI string goes through `t()`. Its Spanish goes into `src/oknowledge/i18n.py` `STRINGS["es"]` **in the same task that adds the string** (voseo, the handoff's and spec §10's words verbatim).
  - `tests/test_i18n.py::test_every_string_a_template_asks_for_has_a_spanish_translation` and `::test_every_translated_string_is_one_the_code_asks_for` run in every suite. A task that removes a string also deletes the entry nothing asks for any more.
  - JS files are not scanned by those tests, so every string a script shows travels in a `data-*` attribute drawn by a template.
- No `|safe` and no `autoescape` in templates (`tests/test_web_read.py::test_no_template_marks_note_content_safe`).
- Never `datetime.datetime.utcnow()` / `utcfromtimestamp()`; use `datetime.datetime.now(datetime.timezone.utc)` (`app.py` and `undo.py` import it as `dt`).
- Commit messages in English, with no `Co-Authored-By`, `Claude-Session` or "Generated with" lines.
- **Suite.**
  - Run `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider` from `/home/fer/Projects/oknowledge` (≈2 min 40 s, **2759 passing** before this branch).
  - Redirect the output to a file and read its tail.
  - Every task ends with the whole suite green.
- **Tests never reach the network or run a program.** `conftest.py` refuses both and isolates:
  - `XDG_STATE_HOME` → `tmp_path/"xdg-state"`;
  - the config path;
  - `i18n.SHARED_FILE` (`isolated_ui_language`).

  A test that posts to `/add` stubs `oknowledge.web.app.fetch`; one that lists models stubs `oknowledge.web.app.build_engine`.
- **Tokens** (verbatim from the handoff, already on `:root` in `style.css`):
  - surfaces `--s1 #17181d` … `--s7 #2a2c34`;
  - borders `--b-div #22232a`, `--b-card #24252b`, `--b-input #2a2b32`, `--b-menu #33353e`, `--b-sel #565a6a`;
  - text `--t1 #e7e7ea` … `--t7 #55575f`;
  - `--acc #a9b4de`, `--fav #d9b54a`, `--danger #e59a8f`, `--shadow` (`0 12px 32px #0008`).

  New in this delivery:
  - modal backdrop `#0009`; modal bg `#1b1c21`, border `#2e3038`, radius 14; Settings 640×520; keys help 420px;
  - toast bg `#e7e7ea` / text `#141519`, radius 10, padding `9px 14px`, "Deshacer" weight 600;
  - bulk bar bg `#24252c`, border `#33353e`, radius 12, `bottom: 20px`, items padding `6px 10px` radius 7;
  - checkbox 18px, radius 5, border `1.5px #55575f`, checked bg and border `#e7e7ea`;
  - inputs in Settings bg `#141519` radius 8;
  - drop zone `1.5px dashed #33353e`, radius 12, padding 30;
  - `kbd` Geist Mono 10px, border `1px #2a2b32`, radius 4.
- **Timings:**
  - toast 2200 ms, or 5000 ms with Deshacer;
  - undo lots live 24 h;
  - the list poll stays 3000 ms and the search debounce 250 ms.
- **Live checks only on the scratch vault.**
  - `SP=/tmp/claude-1000/-home-fer-Projects-gym/d89ecc8a-2029-44cb-b47f-742ed00daeae/scratchpad`.
  - Task 7 creates `$SP/shots/serve3.py`. It runs delivery 2's `$SP/shots/serve.py` on 127.0.0.1:8812 in Spanish, with `i18n.SHARED_FILE` inside the scratchpad.
  - Reset the vault with `rm -rf "$SP/shots/vault" "$SP/shots/state" "$SP/shots/config"` (it is re-seeded on start).
  - Wait for the server with `until curl -sf http://127.0.0.1:8812/ >/dev/null; do sleep 0.2; done`.
  - Never the user's vault, `~/.config/oknowledge`, `.env` or `~/.config/omarchy/plugin-language.json`.
  - Kill servers by the PID in `$SP/serve.pid` after checking the command line.
- **Browser checks** use Playwright for node in `$SP/pw` (`cd "$SP/pw" && [ -d node_modules/playwright ] || npm install --no-save --silent playwright`), launched with `executablePath: "/usr/bin/chromium"`.

## Review Focus

Five ways this can bite a user that no single task's happy-path test exercises. Each is pinned by a test in its owning task:

1. **Undo after the file was touched in Obsidian.**
   - The note was edited in `trash/`: it is restored, with the edit.
   - Its `id:` was changed, or its marker removed, or it was dragged back by hand: it is skipped, not duplicated.
   - The link was pasted again meanwhile: skipped. Nothing is overwritten and the file stays in `trash/`.

   Pinned in Task 1 (`restore_note` refusals) and Task 3 (`test_undo_after_the_note_was_*`).
2. **Undo twice.**
   - The second `POST /undo/{token}` answers 404 `undo-gone` and moves nothing.
   - That holds also when the first one was the no-JS form and the second the script.

   Pinned in Task 2 (`test_a_lot_is_used_once`) and Task 3 (`test_a_second_undo_is_gone`).
3. **Keys firing inside the Settings modal's inputs**, or anywhere a modal is open: typing `j`, `1` or `x` into a model box must type it, never move the list or navigate. Pinned in Task 7 (node harness over `app.js`) and Task 8 (browser check typing into the modal).
4. **Bulk actions on items deleted meanwhile** (in Obsidian, or in another tab):
   - the gone ids land in `failed` and no file is created for them;
   - the others still land;
   - all gone is a 404 with the "not there any more" words.

   Pinned in Task 4 (`test_bulk_*_with_an_id_deleted_meanwhile`) and the Task 10 browser check.
5. **Opening Settings when the server is down.** The modal opens and says it could not load, with a close button. No blank dialog, no navigation. Pinned in Task 8 (`test_the_modal_says_when_the_settings_cannot_be_loaded` plus a browser check that aborts `/settings/panel`).

---
### Task 1: The vault can put a deleted note back

**Files:**
- Modify: `src/oknowledge/vault.py`:
  - new `Trashed` after `IndexesStale` (≈87);
  - `update_note` (≈744; new `rebuild` flag, last lines ≈828–831);
  - `delete_note` (≈871);
  - new `restore_note` after `delete_note`.
- Test: `tests/test_vault_restore.py` (new), `tests/test_vault_edit.py:161-165,171-178,313-316` (`delete_note` now returns `Trashed`)

**Interfaces:**
- Produces:
  - `Trashed(source: Path, target: Path)` — frozen dataclass; `source` is where the note was, `target` its file in `trash/`.
  - `delete_note(cfg, link_id, language, shelf=None, rebuild=True) -> Trashed | None` — `IndexesStale.done` is the same `Trashed`.
  - `update_note(..., rebuild: bool = True)` — with `rebuild=False` no index is rebuilt even when `category` or `tags` change.
  - `restore_note(cfg, link_id, source, target, language, shelf=None, rebuild=True) -> bool` — `True` once the file is back at `source` (and, with `rebuild`, the shelf's indexes rebuilt: a failed rebuild raises `IndexesStale(True, error)`). `False`, with nothing touched, for every refusal of spec §6.2.

- [ ] **Step 1: Write the failing tests**

`tests/test_vault_restore.py`:

```python
"""Putting a deleted note back (spec §6.2). The vault's rule is that nothing
is destroyed and nothing is overwritten: every refusal below leaves both the
file in trash/ and whatever is at the old address exactly as they were."""

import errno
import os

import pytest

from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.vault import (
    IndexesStale, Trashed, delete_note, find_note, index_path, note_path,
    rebuild_indexes, restore_note, trash_dir, update_note, write_note,
)


def make(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    return Config(vault=vault)


def note(id, title="WireGuard", category="Redes", type="article"):
    return Note(id=id, url=f"https://e.com/{id}", title=title, category=category,
                tags=["vpn"], type=type, source="e.com", saved="2026-10-03",
                summary=f"Resumen de {title}.", points=[])


def trashed(cfg, id="a1", **kw):
    path = write_note(cfg, note(id, **kw), "es")
    rebuild_indexes(cfg, "es")
    return path, delete_note(cfg, id, "es")


def test_delete_says_where_the_note_was_and_where_it_went(tmp_path):
    cfg = make(tmp_path)
    path, moved = trashed(cfg)
    assert moved == Trashed(source=path, target=trash_dir(cfg) / path.name)


def test_restore_puts_the_same_file_back_and_rebuilds(tmp_path):
    cfg = make(tmp_path)
    path, moved = trashed(cfg)
    before = moved.target.read_bytes()
    assert not index_path(cfg, "Redes").exists()

    assert restore_note(cfg, "a1", moved.source, moved.target, "es") is True

    assert path.read_bytes() == before
    assert not moved.target.exists()
    assert "WireGuard" in index_path(cfg, "Redes").read_text(encoding="utf-8")


def test_restore_works_on_the_other_shelves(tmp_path):
    cfg = make(tmp_path)
    card = note("c1", title="Alien", category="Películas", type="movie")
    path = write_note(cfg, card, "es", path=note_path(cfg, card, shelf=cfg.ocio))
    moved = delete_note(cfg, "c1", "es", shelf=cfg.ocio)
    assert restore_note(cfg, "c1", moved.source, moved.target, "es", shelf=cfg.ocio)
    assert path.exists() and find_note(cfg, "c1", cfg.ocio) is not None


def test_a_note_edited_in_the_trash_comes_back_with_the_edit(tmp_path):
    cfg = make(tmp_path)
    path, moved = trashed(cfg)
    edited = moved.target.read_text(encoding="utf-8") + "\nUna línea mía.\n"
    moved.target.write_text(edited, encoding="utf-8")
    assert restore_note(cfg, "a1", moved.source, moved.target, "es")
    assert path.read_text(encoding="utf-8") == edited


@pytest.mark.parametrize("damage", ["id", "marker", "gone"])
def test_a_trash_file_that_is_no_longer_that_note_stays(tmp_path, damage):
    cfg = make(tmp_path)
    path, moved = trashed(cfg)
    text = moved.target.read_text(encoding="utf-8")
    if damage == "id":
        moved.target.write_text(text.replace("id: a1", "id: zz"), encoding="utf-8")
    elif damage == "marker":
        moved.target.write_text(text.replace("oknowledge: 1", "oknowledge: 0"), encoding="utf-8")
    else:
        os.replace(moved.target, path)              # dragged back by hand in Obsidian
    after = sorted(p.name for p in cfg.root.rglob("*.md"))

    assert restore_note(cfg, "a1", moved.source, moved.target, "es") is False
    assert sorted(p.name for p in cfg.root.rglob("*.md")) == after


def test_a_file_at_the_old_address_is_never_overwritten(tmp_path):
    cfg = make(tmp_path)
    path, moved = trashed(cfg)
    path.write_text("mine, written after the delete\n", encoding="utf-8")

    assert restore_note(cfg, "a1", moved.source, moved.target, "es") is False
    assert path.read_text(encoding="utf-8") == "mine, written after the delete\n"
    assert moved.target.exists()


def test_a_link_pasted_again_meanwhile_is_not_doubled(tmp_path):
    cfg = make(tmp_path)
    _, moved = trashed(cfg)
    write_note(cfg, note("a1", title="WireGuard otra vez"), "es")   # another name, same id

    assert restore_note(cfg, "a1", moved.source, moved.target, "es") is False
    assert moved.target.exists()


@pytest.mark.parametrize("where", ["source", "target"])
def test_paths_outside_the_shelf_or_the_trash_are_refused(tmp_path, where):
    cfg = make(tmp_path)
    path, moved = trashed(cfg)
    source, target = moved.source, moved.target
    if where == "source":
        source = cfg.ocio.dir / path.name                 # another shelf
    else:
        stray = cfg.root / "elsewhere" / path.name        # not in trash/
        stray.parent.mkdir()
        stray.write_bytes(moved.target.read_bytes())
        target = stray
    assert restore_note(cfg, "a1", source, target, "es") is False
    assert restore_note(cfg, "a1", cfg.root / ".." / ".." / "x.md", moved.target, "es") is False
    assert moved.target.exists() and not path.exists()


def test_a_name_that_appears_during_the_move_wins(tmp_path, monkeypatch):
    cfg = make(tmp_path)
    path, moved = trashed(cfg)

    def raced(src, dst):
        open(dst, "w", encoding="utf-8").write("theirs\n")
        raise FileExistsError(errno.EEXIST, "exists", str(dst))
    monkeypatch.setattr(os, "link", raced)

    assert restore_note(cfg, "a1", moved.source, moved.target, "es") is False
    assert path.read_text(encoding="utf-8") == "theirs\n"
    assert moved.target.exists()


def test_without_hard_links_it_still_moves_without_overwriting(tmp_path, monkeypatch):
    cfg = make(tmp_path)
    path, moved = trashed(cfg)
    before = moved.target.read_bytes()

    def unsupported(src, dst):
        raise OSError(errno.EPERM, "Operation not permitted")
    monkeypatch.setattr(os, "link", unsupported)

    assert restore_note(cfg, "a1", moved.source, moved.target, "es") is True
    assert path.read_bytes() == before and not moved.target.exists()


def count_rebuilds(monkeypatch):
    calls = []
    monkeypatch.setattr("oknowledge.vault.rebuild_indexes",
                        lambda cfg, language, shelf=None: calls.append(shelf))
    return calls


def test_rebuild_false_rebuilds_nothing(tmp_path, monkeypatch):
    cfg = make(tmp_path)
    write_note(cfg, note("a1"), "es")
    write_note(cfg, note("b2", title="SSH"), "es")
    calls = count_rebuilds(monkeypatch)

    update_note(cfg, "a1", "es", category="Seguridad", rebuild=False)
    moved = delete_note(cfg, "b2", "es", rebuild=False)
    restore_note(cfg, "b2", moved.source, moved.target, "es", rebuild=False)

    assert calls == []
    assert find_note(cfg, "a1")[1].category == "Seguridad"


def test_a_restore_whose_rebuild_fails_says_the_note_is_back(tmp_path, monkeypatch):
    cfg = make(tmp_path)
    path, moved = trashed(cfg)

    def boom(cfg, language, shelf=None):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr("oknowledge.vault.rebuild_indexes", boom)

    with pytest.raises(IndexesStale) as raised:
        restore_note(cfg, "a1", moved.source, moved.target, "es")
    assert raised.value.done is True and path.exists()
```

- [ ] **Step 2: Run them to see them fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_vault_restore.py`
Expected: FAIL at collection — `ImportError: cannot import name 'Trashed' from 'oknowledge.vault'`.

- [ ] **Step 3: Implement**

In `src/oknowledge/vault.py`, after the `IndexesStale` class:

```python
@dataclass(frozen=True)
class Trashed:
    """Where a deleted note was, and the file it is now in trash/. The pair
    is what a Deshacer needs to put it back (spec §6.2)."""

    source: Path
    target: Path
```

In `update_note`, add the parameter after `shelf`:

```python
                shelf: Shelf | None = None,
                rebuild: bool = True) -> Path | None:
```

add to its docstring:

```
    `rebuild=False` writes the note and leaves the indexes to the caller: a
    bulk move of thirty notes rebuilds once at the end, not thirty times.
```

and replace its last four lines:

```python
    # A change to mentions or collections skips the rebuild: no index names
    # either, and rebuilding the whole library on a delete click -- or once
    # per note while thirty of them join a project -- buys nothing.
    if (category is None and tags is None) or not rebuild:
        return written
    return _finish(cfg, language, written, shelf)
```

Replace `delete_note` with:

```python
def delete_note(cfg: Config, link_id: str, language: str,
                shelf: Shelf | None = None, rebuild: bool = True) -> Trashed | None:
    """Move one of our notes to trash/ and rebuild the indexes.

    Returns where it was and where it went, or None if no note of ours has
    that id. Deleting fires from a POST in a browser, so it has to be
    undoable: the file keeps its name and content, can be dragged back from
    Obsidian, and restore_note() puts it back from a Deshacer.
    """
    found = find_note(cfg, link_id, shelf)
    if found is None:
        return None
    path, _ = found
    # Location first, before anything is created: a trash/ symlinked out of
    # the vault has to be refused, not followed.
    folder = ensure_inside_root(cfg, trash_dir(cfg) / "note.md").parent
    folder.mkdir(parents=True, exist_ok=True)
    target = _free_name(folder, path.name)
    try:
        os.replace(path, target)                 # same filesystem: atomic
    except OSError:
        target.unlink(missing_ok=True)           # no empty placeholder left behind
        raise
    done = Trashed(source=path, target=target)
    if not rebuild:
        return done
    return _finish(cfg, language, done, shelf)


def restore_note(cfg: Config, link_id: str, source: Path, target: Path, language: str,
                 shelf: Shelf | None = None, rebuild: bool = True) -> bool:
    """Put a deleted note back at its old address, and rebuild its shelf.

    False, with nothing touched, unless all of this holds: `target` is a file
    directly in trash/, still ours and still this id (Obsidian can edit,
    unmark or move it in the meantime); `source` is a free name directly in
    the shelf's folder; and no note on the shelf has the id (the link was
    pasted again since). The move never overwrites: a file that appears at
    `source` between the check and the move wins, and the note stays in
    trash/.
    """
    shelf = shelf or cfg.links
    try:
        trashed = ensure_inside_root(cfg, Path(target))
        back = ensure_inside_root(cfg, Path(source))
    except ProtectedNote:
        return False
    if trashed.parent != trash_dir(cfg).resolve() or back.parent != shelf.dir.resolve():
        return False
    if not trashed.is_file() or not back.parent.is_dir():
        return False
    found = read_note(trashed)
    if found is None or found.id != link_id:
        return False
    if back.exists() or back.is_symlink() or find_note(cfg, link_id, shelf) is not None:
        return False
    try:
        os.link(trashed, back)                   # fails, not overwrites, if the name appeared
    except FileExistsError:
        return False
    except OSError:
        # A filesystem without hard links: reserve the name, then move onto
        # our own empty placeholder.
        try:
            os.close(os.open(back, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o666))
        except FileExistsError:
            return False
        try:
            os.replace(trashed, back)
        except OSError:
            back.unlink(missing_ok=True)
            raise
    else:
        trashed.unlink()
    if rebuild:
        _finish(cfg, language, True, shelf)
    return True
```

In `tests/test_vault_edit.py`:
- line 161: `moved = delete_note(cfg, "a1", "es").target`;
- lines 171 and 174: `one = delete_note(cfg, "a1", "es").target` and `two = delete_note(cfg, "b2", "es").target`;
- line 316: `assert raised.value.done.target == trash_dir(cfg) / path.name` and `assert not path.exists() and raised.value.done.target.exists()`.

- [ ] **Step 4: Run the new tests and the vault tests**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_vault_restore.py tests/test_vault_edit.py tests/test_vault.py`
Expected: PASS.

- [ ] **Step 5: Whole suite**

Run the suite. Expected: green.
- `app.py`'s delete route only checks the result for `None` and ignores the value, so it is unaffected.
- If `tests/test_web_write.py` or another test compares `delete_note(...)` to a `Path`, change it to `.target` the same way.

- [ ] **Step 6: Commit**

```bash
git add src/oknowledge/vault.py tests/test_vault_restore.py tests/test_vault_edit.py
git commit -m "Let the vault put a deleted note back, and let a caller skip the rebuild"
```

---

### Task 2: A Deshacer remembers what it can take back

**Files:**
- Create: `src/oknowledge/undo.py`
- Modify: `src/oknowledge/web/app.py` (`import`: `from .. import cards, env, undo`; `create_app` ≈683: purge on start)
- Test: `tests/test_undo.py` (new)

**Interfaces:**
- Consumes: `vault.Trashed`, `vault.restore_note(..., rebuild=False)`, `vault.rebuild_indexes`, `queue.state_dir()`, `queue.Locked`, `atomic.atomic_write`.
- Produces:
  - `undo.LIFETIME = timedelta(hours=24)` and `undo.TOKEN` (regex `[A-Za-z0-9_-]{22}`).
  - `undo.folder() -> Path` — `state_dir() / "undo"`.
  - `undo.remember(cfg, items, now=None) -> str`, where `items` is `[(link_id, shelf_name, Trashed), ...]`. It purges first, writes `<token>.json` with `atomic_write` and returns the token.
  - `undo.alive(token, now=None) -> bool` — a well-formed token whose lot exists and is under 24 h old.
  - `undo.restore(cfg, token, language, lock, now=None) -> UndoResult | None`:
    - `None` for a malformed, missing or expired token;
    - otherwise the lot is claimed (unlinked) first, then each item is restored under `lock(id)`, then one rebuild runs per shelf touched.
  - `UndoResult(restored: list[str], skipped: list[str], shelf: str, stale: bool)` — `shelf` is the first item's shelf (`links`, `ocio` or `ideas`); `stale` means notes came back but a rebuild failed.
  - `undo.purge(now=None) -> int` — deletes expired lot JSONs (and unreadable ones older than 24 h by mtime). Only files named `<token>.json` in `folder()`, never a note. It never creates the folder.

- [ ] **Step 1: Write the failing tests**

`tests/test_undo.py`:

```python
"""The lots a Deshacer restores (spec §6.2): a small JSON per delete in the
state dir, never a note. conftest points XDG_STATE_HOME into tmp_path."""

import contextlib
import datetime as dt
import json

import pytest

from oknowledge import undo
from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.queue import Locked, state_dir
from oknowledge.vault import delete_note, find_note, note_path, rebuild_indexes, write_note

NOW = dt.datetime(2026, 10, 14, 12, 0, tzinfo=dt.timezone.utc)


def make(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    return Config(vault=vault)


def put(cfg, id, shelf=None, type="article"):
    note = Note(id=id, url=f"https://e.com/{id}", title=f"Nota {id}", category="Redes",
                tags=[], type=type, source="e.com", saved="2026-10-03", summary="s")
    shelf = shelf or cfg.links
    write_note(cfg, note, "es", path=note_path(cfg, note, shelf=shelf))
    rebuild_indexes(cfg, "es", shelf=shelf)
    return delete_note(cfg, id, "es", shelf=shelf)


def no_lock(link_id):
    return contextlib.nullcontext()


def test_a_lot_is_a_json_in_the_state_dir(tmp_path):
    cfg = make(tmp_path)
    moved = put(cfg, "a1")
    token = undo.remember(cfg, [("a1", "links", moved)], now=NOW)

    assert undo.TOKEN.fullmatch(token)
    path = state_dir() / "undo" / f"{token}.json"
    assert path.is_relative_to(tmp_path)
    lot = json.loads(path.read_text(encoding="utf-8"))
    assert lot["at"] == NOW.isoformat()
    assert lot["items"] == [{"id": "a1", "shelf": "links",
                             "source": "links/" + moved.source.name,
                             "target": "trash/" + moved.target.name}]


def test_restore_puts_every_note_back_and_forgets_the_lot(tmp_path):
    cfg = make(tmp_path)
    one, two = put(cfg, "a1"), put(cfg, "a2")
    token = undo.remember(cfg, [("a1", "links", one), ("a2", "links", two)], now=NOW)

    result = undo.restore(cfg, token, "es", no_lock, now=NOW)

    assert result.restored == ["a1", "a2"] and result.skipped == []
    assert result.shelf == "links" and result.stale is False
    assert find_note(cfg, "a1") and find_note(cfg, "a2")
    assert not (undo.folder() / f"{token}.json").exists()


def test_a_lot_is_used_once(tmp_path):
    cfg = make(tmp_path)
    token = undo.remember(cfg, [("a1", "links", put(cfg, "a1"))], now=NOW)
    assert undo.restore(cfg, token, "es", no_lock, now=NOW) is not None
    assert undo.restore(cfg, token, "es", no_lock, now=NOW) is None
    assert not undo.alive(token, now=NOW)


def test_an_expired_lot_restores_nothing(tmp_path):
    cfg = make(tmp_path)
    moved = put(cfg, "a1")
    token = undo.remember(cfg, [("a1", "links", moved)], now=NOW)
    later = NOW + dt.timedelta(hours=24, seconds=1)

    assert undo.alive(token, now=NOW) and not undo.alive(token, now=later)
    assert undo.restore(cfg, token, "es", no_lock, now=later) is None
    assert moved.target.exists() and find_note(cfg, "a1") is None


@pytest.mark.parametrize("token", ["", "short", "a" * 23, "../decoy", "a/b" + "c" * 19,
                                   "..", "a" * 21 + "."])
def test_tokens_of_another_shape_touch_nothing(tmp_path, token):
    decoy = state_dir() / "decoy.json"
    decoy.parent.mkdir(parents=True, exist_ok=True)
    decoy.write_text(json.dumps({"at": NOW.isoformat(), "items": []}), encoding="utf-8")
    assert undo.restore(make(tmp_path), token, "es", no_lock, now=NOW) is None
    assert not undo.alive(token, now=NOW)
    assert decoy.exists()


def test_purge_drops_only_expired_lots_and_never_a_note(tmp_path):
    cfg = make(tmp_path)
    old = undo.remember(cfg, [("a1", "links", put(cfg, "a1"))], now=NOW)
    new = undo.remember(cfg, [("a2", "links", put(cfg, "a2"))],
                        now=NOW + dt.timedelta(hours=20))
    stray = undo.folder() / "notes.md"
    stray.write_text("not ours to delete\n", encoding="utf-8")

    assert undo.purge(now=NOW + dt.timedelta(hours=25)) == 1

    assert not (undo.folder() / f"{old}.json").exists()
    assert (undo.folder() / f"{new}.json").exists()
    assert stray.exists()
    assert len(list((cfg.root / "trash").glob("*.md"))) == 2     # both notes still in trash/


def test_remember_purges_the_old_ones_first(tmp_path):
    cfg = make(tmp_path)
    old = undo.remember(cfg, [("a1", "links", put(cfg, "a1"))], now=NOW)
    undo.remember(cfg, [("a2", "links", put(cfg, "a2"))], now=NOW + dt.timedelta(days=2))
    assert not (undo.folder() / f"{old}.json").exists()


def test_purge_without_a_folder_creates_none():
    assert undo.purge(now=NOW) == 0
    assert not undo.folder().exists()


def test_a_busy_link_is_skipped_and_the_others_come_back(tmp_path):
    cfg = make(tmp_path)
    token = undo.remember(cfg, [("a1", "links", put(cfg, "a1")),
                                ("a2", "links", put(cfg, "a2"))], now=NOW)

    @contextlib.contextmanager
    def lock(link_id):
        if link_id == "a1":
            raise Locked(link_id)
        yield

    result = undo.restore(cfg, token, "es", lock, now=NOW)
    assert result.restored == ["a2"] and result.skipped == ["a1"]


def test_one_rebuild_per_shelf_touched(tmp_path, monkeypatch):
    cfg = make(tmp_path)
    items = [("a1", "links", put(cfg, "a1")), ("a2", "links", put(cfg, "a2")),
             ("i1", "ideas", put(cfg, "i1", shelf=cfg.ideas, type="idea"))]
    token = undo.remember(cfg, items, now=NOW)
    calls = []
    monkeypatch.setattr("oknowledge.undo.rebuild_indexes",
                        lambda cfg, language, shelf=None: calls.append(shelf.name))
    monkeypatch.setattr("oknowledge.vault.rebuild_indexes",
                        lambda *a, **k: pytest.fail("restore_note rebuilt on its own"))

    undo.restore(cfg, token, "es", no_lock, now=NOW)

    assert sorted(calls) == ["ideas", "links"]


def test_a_failed_rebuild_is_said_and_the_notes_stay_back(tmp_path, monkeypatch):
    cfg = make(tmp_path)
    token = undo.remember(cfg, [("a1", "links", put(cfg, "a1"))], now=NOW)

    def boom(cfg, language, shelf=None):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr("oknowledge.undo.rebuild_indexes", boom)

    result = undo.restore(cfg, token, "es", no_lock, now=NOW)
    assert result.stale is True and result.restored == ["a1"]
    assert find_note(cfg, "a1") is not None


def test_a_lot_naming_an_unknown_shelf_skips_that_item(tmp_path):
    cfg = make(tmp_path)
    moved = put(cfg, "a1")
    token = undo.remember(cfg, [("a1", "trash", moved)], now=NOW)
    assert undo.restore(cfg, token, "es", no_lock, now=NOW).skipped == ["a1"]
    assert moved.target.exists()
```

- [ ] **Step 2: Run them to see them fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_undo.py`
Expected: FAIL at collection — `ImportError: cannot import name 'undo' from 'oknowledge'`.

- [ ] **Step 3: Implement**

`src/oknowledge/undo.py`:

```python
"""What a delete can still take back (spec §6.2).

The notes stay where delete_note() put them, in the vault's trash/: moving
them out of the vault would make the 24-hour expiry a real deletion, and
nothing in this project destroys a note. What lives here is one small JSON
per delete -- which file came from where -- so a Deshacer can put them back.
Forgetting a lot deletes that JSON and never a note.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import re
import secrets
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path

from .atomic import atomic_write
from .config import Config
from .queue import Locked, state_dir
from .vault import ProtectedNote, Trashed, rebuild_indexes, restore_note

log = logging.getLogger(__name__)

LIFETIME = dt.timedelta(hours=24)
"""How long a lot can be used. The toast offers it for 5 s; the rest is for
the no-JS form left open in a tab, and for nothing else."""

TOKEN = re.compile(r"[A-Za-z0-9_-]{22}")
"""secrets.token_urlsafe(16): the only thing that ever names a file here."""

SHELVES = ("links", "ocio", "ideas")


@dataclass(frozen=True)
class UndoResult:
    restored: list[str]
    skipped: list[str]
    shelf: str
    stale: bool = False


def _now(now: dt.datetime | None) -> dt.datetime:
    return now or dt.datetime.now(dt.timezone.utc)


def folder() -> Path:
    return state_dir() / "undo"


def _path(token) -> Path | None:
    if not isinstance(token, str) or not TOKEN.fullmatch(token):
        return None
    return folder() / f"{token}.json"


def _read(path: Path) -> dict | None:
    try:
        lot = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(lot, dict) or not isinstance(lot.get("items"), list):
        return None
    return lot


def _at(lot: dict) -> dt.datetime | None:
    try:
        at = dt.datetime.fromisoformat(str(lot.get("at", "")))
    except ValueError:
        return None
    return at if at.tzinfo is not None else None


def _fresh(lot: dict | None, now: dt.datetime) -> bool:
    at = _at(lot) if lot else None
    return at is not None and now - at <= LIFETIME


def remember(cfg: Config, items: list[tuple[str, str, Trashed]],
             now: dt.datetime | None = None) -> str:
    """Write the lot for one delete and return its token. Raises OSError
    when the state dir cannot be written; the delete itself has landed."""
    now = _now(now)
    purge(now)
    root = cfg.root.resolve()
    lot = {"at": now.isoformat(), "items": [
        {"id": link, "shelf": shelf,
         "source": trashed.source.resolve().relative_to(root).as_posix(),
         "target": trashed.target.resolve().relative_to(root).as_posix()}
        for link, shelf, trashed in items]}
    token = secrets.token_urlsafe(16)
    where = folder()
    where.mkdir(parents=True, exist_ok=True)
    atomic_write(where / f"{token}.json", json.dumps(lot, ensure_ascii=False))
    return token


def alive(token, now: dt.datetime | None = None) -> bool:
    """Whether a page may offer Deshacer for this token."""
    path = _path(token)
    return path is not None and _fresh(_read(path), _now(now))


def restore(cfg: Config, token, language: str,
            lock: Callable[[str], AbstractContextManager],
            now: dt.datetime | None = None) -> UndoResult | None:
    """Put a lot's notes back. None if the token names no lot that can be used.

    The JSON is claimed -- deleted -- before anything moves: a second
    Deshacer, from a double click or from the form and the script at once,
    finds nothing instead of racing the first.
    """
    path = _path(token)
    if path is None:
        return None
    lot = _read(path)
    if not _fresh(lot, _now(now)):
        return None
    try:
        path.unlink()
    except FileNotFoundError:
        return None
    restored: list[str] = []
    skipped: list[str] = []
    touched: dict[str, object] = {}
    items = [item for item in lot["items"] if isinstance(item, dict)]
    for item in items:
        link = str(item.get("id", ""))
        name = str(item.get("shelf", ""))
        back = False
        if name in SHELVES and link:
            shelf = cfg.shelf(name)
            try:
                with lock(link):
                    back = restore_note(cfg, link, cfg.root / str(item.get("source", "")),
                                        cfg.root / str(item.get("target", "")),
                                        language, shelf, rebuild=False)
            except (Locked, OSError, ProtectedNote, ValueError) as error:
                log.warning("could not restore %s: %s", link, error)
            if back:
                touched[name] = shelf
        (restored if back else skipped).append(link)
    stale = False
    for shelf in touched.values():
        try:
            rebuild_indexes(cfg, language, shelf)
        except OSError as error:
            log.warning("the indexes could not be rebuilt after a restore: %s", error)
            stale = True
    first = str(items[0].get("shelf", "")) if items else ""
    return UndoResult(restored, skipped, first if first in SHELVES else "links", stale)


def purge(now: dt.datetime | None = None) -> int:
    """Delete the lots older than LIFETIME. Only `<token>.json` files in
    folder(), never a note; a lot that cannot be read goes by its mtime."""
    now = _now(now)
    gone = 0
    try:
        paths = list(folder().glob("*.json"))
    except OSError:
        return 0
    for path in paths:
        if not TOKEN.fullmatch(path.stem):
            continue
        lot = _read(path)
        if lot is not None and _at(lot) is not None:
            if _fresh(lot, now):
                continue
        else:
            try:
                written = dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc)
            except OSError:
                continue
            if now - written <= LIFETIME:
                continue
        try:
            path.unlink()
            gone += 1
        except FileNotFoundError:
            pass
    return gone
```

In `src/oknowledge/web/app.py`:
- change `from .. import cards, env` to `from .. import cards, env, undo`;
- at the top of `create_app`, after `app.add_middleware(SameOriginOnly)`:

```python
    # The undo lots of earlier runs: the server can run for weeks
    # (idle_timeout 0), so a lot is also purged whenever a new one is made.
    try:
        undo.purge()
    except OSError as error:
        log.warning("old undo lots could not be cleared: %s", error)
```

- [ ] **Step 4: Run the new tests**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_undo.py`
Expected: PASS.

- [ ] **Step 5: Whole suite**

Run the suite. Expected: green (the purge at start finds no folder in any test and creates none, so `test_web_write.py`'s snapshots are unchanged).

- [ ] **Step 6: Commit**

```bash
git add src/oknowledge/undo.py src/oknowledge/web/app.py tests/test_undo.py
git commit -m "Remember what each delete can take back, for 24 hours, in the state dir"
```

---
### Task 3: A delete answers with Deshacer, and Deshacer works

**Files:**
- Modify `src/oknowledge/web/app.py`:
  - `NOTICES` (≈88);
  - `FAILURES` (≈434);
  - `answer()` (≈462);
  - `local_path()` (≈504, drops `n`, `m`, `undo` too);
  - `Edited` (≈232, gains `value`);
  - new module constant `SECTION_HOMES`;
  - in `create_app`: `page()` (≈723, `undo` and `undo_back` in the base context), `edit()` (≈1017, returns the value), `remove` (≈1241, now via `delete_one`), new `delete_one`, `keep_lot`, and `POST /undo/{token}`.
- Modify these templates and statics:
  - `src/oknowledge/web/templates/base.html` (the one `#toast`);
  - `panel.html:121-123`, `card-panel.html:24-27` and `idea.html:35-37` (no `confirm()` on Delete);
  - `src/oknowledge/web/static/layout.js` (also strips `undo`);
  - `src/oknowledge/web/static/app.css` (`.toast` block ≈50).
- Modify `src/oknowledge/i18n.py`.
- Test: `tests/test_web_undo.py` (new).
- Ledger:
  - `tests/test_web_write.py` (`WRITE_ROUTES`, `VAULT_WRITERS`);
  - `tests/test_web_ocio_panel.py:243`;
  - `tests/test_web_ideas_mine.py:141`;
  - `tests/test_web_idea_screen.py:298`;
  - `tests/test_web_panel.py:143`.

**Interfaces:**
- Consumes: `undo.remember/alive/restore` (Task 2), `Trashed` (Task 1).
- Produces:
  - `answer(request, where, notice="", extra: dict | None = None, **params)`. In the JSON it copies `undo` and `reload` from `params` when truthy, and merges `extra` into a success body. On a redirect, `reload` is dropped and `undo` goes in the URL.
  - `Edited(notice, landed, value=None)`, where `value` is what the change returned (`Trashed` for a delete, also when the indexes went stale).
  - `SECTION_HOMES = {"links": "/", "ocio": "/ocio", "ideas": "/ideas"}`.
  - `delete_one(link_id, rebuild=True) -> tuple[Edited, str]` (inside `create_app`; the str is the shelf name).
  - `keep_lot(items) -> str | None` (inside `create_app`; None when the state dir cannot be written).
  - `POST /item/{id}/delete` → JSON `{"ok": true, "notice": "Deleted", "undo": "<token>"}`, or 303 to its section with `notice=trashed&undo=<token>`.
  - `POST /undo/{token}` (field `back`) → JSON `{"ok": true, "notice", "restored": [...], "skipped": [...]}`, 404 `undo-gone` or 409 `undo-blocked`, or 303 to `back` / the first item's section.
  - Markup: `<div id="toast" class="toast[ undo]" role="status" aria-live="polite"[ hidden]>` holding `<span class="toast-text">` and, with a live token, `<form method="post" action="/undo/{token}" class="toast-undo">` with a hidden `back` and a `<button>`.
  - body data: none yet (Task 7 adds `data-undo`).

- [ ] **Step 1: Write the failing tests**

`tests/test_web_undo.py`:

```python
"""Deleting with Deshacer (spec §6.3, §6.4, §2): every delete answers with a
token, the page after it offers Deshacer as a form, and the token puts the
notes back exactly once."""

import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from oknowledge import undo
from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.model import Note
from oknowledge.vault import (
    all_notes, delete_note, find_note, note_path, rebuild_indexes, trash_dir, write_note,
)
from oknowledge.web.app import create_app

JSON = {"Accept": "application/json"}
CARD = "c00000000001"
STATIC = Path(__file__).resolve().parent.parent / "src" / "oknowledge" / "web" / "static"


def link(id, title, category):
    return Note(id=id, url=f"https://e.com/{id}", title=title, category=category, tags=["vpn"],
                type="article", source="e.com", saved="2026-10-03", summary="s",
                cover=f"../attachments/{id}.png")


@pytest.fixture
def s(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    first = write_note(cfg, link("a1", "WireGuard", "Redes"), "es")
    write_note(cfg, link("b2", "Masa madre", "Cocina"), "es")
    card = Note(id=CARD, url="https://www.imdb.com/title/tt1", title="Alien",
                category="Películas", tags=[], type="movie", source="imdb.com",
                saved="2026-10-01", summary="s", engine="")
    write_note(cfg, card, "es", path=note_path(cfg, card, shelf=cfg.ocio))
    idea = new_idea("Una vpn para la familia.", "VPN familiar", "2026-10-13",
                    "2026-10-13T00:00:00.000001+00:00")
    idea.related = [first.stem]
    write_note(cfg, idea, "es", path=note_path(cfg, idea, shelf=cfg.ideas))
    for shelf in (cfg.links, cfg.ocio, cfg.ideas):
        rebuild_indexes(cfg, "es", shelf=shelf)
    return SimpleNamespace(cfg=cfg, client=TestClient(create_app(cfg)), idea=idea.id)


def deleted(s, which="a1"):
    return s.client.post(f"/item/{which}/delete", headers=JSON).json()["undo"]


# --- the delete ------------------------------------------------------------------

def test_a_delete_asked_by_a_script_answers_deleted_and_a_token(s):
    answer = s.client.post("/item/a1/delete", headers=JSON)
    body = answer.json()
    assert answer.status_code == 200
    assert body["ok"] is True and body["notice"] == "Deleted"
    assert undo.TOKEN.fullmatch(body["undo"])
    assert find_note(s.cfg, "a1") is None


@pytest.mark.parametrize("which,home", [("a1", "/"), (CARD, "/ocio"), ("idea", "/ideas")])
def test_a_delete_from_a_form_goes_home_with_its_token(s, which, home):
    target = s.idea if which == "idea" else which
    location = s.client.post(f"/item/{target}/delete", follow_redirects=False).headers["location"]
    assert re.fullmatch(re.escape(home) + r"\?notice=trashed&undo=[A-Za-z0-9_-]{22}", location)


def test_a_delete_still_lands_when_the_lot_cannot_be_written(s, monkeypatch):
    def boom(*args, **kwargs):
        raise OSError(30, "Read-only file system")
    monkeypatch.setattr("oknowledge.undo.remember", boom)
    body = s.client.post("/item/a1/delete", headers=JSON).json()
    assert body["ok"] is True and "undo" not in body
    assert find_note(s.cfg, "a1") is None


def test_the_delete_buttons_ask_nothing_and_reprocess_still_asks(s):
    for page in ("/?sel=a1", f"/ocio?sel={CARD}", f"/ideas/{s.idea}"):
        body = s.client.get(page).text
        assert not re.search(r'/delete"[^>]*data-ask', body), page
        assert "confirm(this.form.dataset.ask)\">Delete" not in body, page
    assert "confirm(" in s.client.get("/?sel=a1").text          # Reprocess keeps its own


# --- the server's toast ------------------------------------------------------------

def test_the_page_after_a_delete_offers_undo_as_a_form(s):
    location = s.client.post("/item/a1/delete", follow_redirects=False).headers["location"]
    token = location.rsplit("=", 1)[1]
    toast = re.search(r'<div id="toast".*?</div>', s.client.get(location).text, re.S).group(0)
    assert 'class="toast undo"' in toast and " hidden" not in toast
    assert f'<form method="post" action="/undo/{token}" class="toast-undo">' in toast
    assert '<input type="hidden" name="back" value="/">' in toast
    assert ">Undo</button>" in toast


def test_the_undo_form_goes_back_to_the_page_without_the_notice(s):
    token = deleted(s)
    body = s.client.get(f"/?vista=lista&notice=trashed&undo={token}").text
    assert 'name="back" value="/?vista=lista"' in body


@pytest.mark.parametrize("token", ["A" * 22, "nope"])
def test_an_invented_token_draws_no_undo(s, token):
    body = s.client.get(f"/?notice=trashed&undo={token}").text
    assert "/undo/" not in body
    assert '<span class="toast-text">' in body               # the notice is still said


def test_with_no_notice_there_is_no_toast(s):
    token = deleted(s)
    body = s.client.get(f"/?undo={token}").text
    assert "/undo/" not in body
    assert re.search(r'<div id="toast" class="toast" role="status" aria-live="polite" hidden>', body)


def test_the_layout_script_takes_the_token_out_of_the_url():
    script = STATIC.joinpath("layout.js").read_text(encoding="utf-8")
    assert '"undo"' in script


# --- the undo --------------------------------------------------------------------

@pytest.mark.parametrize("which,column,title", [("a1", "/lista", "WireGuard"),
                                                (CARD, "/ocio/lista", "Alien"),
                                                ("idea", "/ideas/lista", "VPN familiar")])
def test_undo_puts_the_note_back_in_its_list(s, which, column, title):
    target = s.idea if which == "idea" else which
    token = deleted(s, target)
    assert title not in s.client.get(column).text

    answer = s.client.post(f"/undo/{token}", headers=JSON)

    assert answer.json() == {"ok": True, "notice": "Restored", "restored": [target], "skipped": []}
    assert title in s.client.get(column).text


def test_a_restored_link_keeps_its_cover_and_its_idea(s):
    s.client.post(f"/undo/{deleted(s)}", headers=JSON)
    assert find_note(s.cfg, "a1")[1].cover == "../attachments/a1.png"
    assert "WireGuard" in s.client.get(f"/ideas/{s.idea}").text


def test_a_second_undo_is_gone(s):
    token = deleted(s)
    assert s.client.post(f"/undo/{token}", headers=JSON).status_code == 200
    again = s.client.post(f"/undo/{token}", headers=JSON)
    assert again.status_code == 404
    assert again.json() == {"ok": False, "error": "It can no longer be undone"}
    assert len([n for n in all_notes(s.cfg) if n.id == "a1"]) == 1


def test_the_form_and_the_script_cannot_both_undo(s):
    token = deleted(s)
    first = s.client.post(f"/undo/{token}", data={"back": "/"}, follow_redirects=False)
    assert first.headers["location"] == "/?notice=restored-one&n=1"
    assert s.client.post(f"/undo/{token}", headers=JSON).status_code == 404
    assert len([n for n in all_notes(s.cfg) if n.id == "a1"]) == 1


def test_undo_without_a_script_goes_to_the_section_of_the_note(s):
    token = deleted(s, CARD)
    answer = s.client.post(f"/undo/{token}", follow_redirects=False)
    assert answer.headers["location"] == "/ocio?notice=restored-one&n=1"


def test_a_back_to_another_host_is_ignored(s):
    token = deleted(s)
    answer = s.client.post(f"/undo/{token}", data={"back": "//evil.example/x"},
                           follow_redirects=False)
    assert answer.headers["location"] == "/?notice=restored-one&n=1"


def test_an_invented_token_is_gone_without_a_script_too(s):
    answer = s.client.post("/undo/" + "A" * 22, follow_redirects=False)
    assert answer.headers["location"] == "/?notice=undo-gone"


def test_undo_after_the_note_was_pasted_again_is_blocked(s):
    token = deleted(s)
    write_note(s.cfg, link("a1", "WireGuard otra vez", "Redes"), "es")
    answer = s.client.post(f"/undo/{token}", headers=JSON)
    assert answer.status_code == 409
    assert answer.json() == {"ok": False, "error":
                             "It could not be restored: there is already another note with that link"}
    assert len(list(trash_dir(s.cfg).glob("*.md"))) == 1


def test_undo_after_the_note_was_edited_in_obsidian_keeps_the_edit(s):
    token = deleted(s)
    (moved,) = trash_dir(s.cfg).glob("*.md")
    moved.write_text(moved.read_text(encoding="utf-8") + "\nMía.\n", encoding="utf-8")
    assert s.client.post(f"/undo/{token}", headers=JSON).json()["restored"] == ["a1"]
    assert find_note(s.cfg, "a1")[0].read_text(encoding="utf-8").endswith("\nMía.\n")


def test_undo_after_the_id_was_changed_in_obsidian_is_blocked(s):
    token = deleted(s)
    (moved,) = trash_dir(s.cfg).glob("*.md")
    moved.write_text(moved.read_text(encoding="utf-8").replace("id: a1", "id: zz"),
                     encoding="utf-8")
    assert s.client.post(f"/undo/{token}", headers=JSON).status_code == 409
    assert moved.exists() and find_note(s.cfg, "a1") is None


def test_a_lot_with_one_blocked_says_both(s):
    one = delete_note(s.cfg, "a1", "es")
    two = delete_note(s.cfg, "b2", "es")
    token = undo.remember(s.cfg, [("a1", "links", one), ("b2", "links", two)])
    write_note(s.cfg, link("a1", "WireGuard otra vez", "Redes"), "es")

    body = s.client.post(f"/undo/{token}", headers=JSON).json()

    assert body == {"ok": True, "restored": ["b2"], "skipped": ["a1"],
                    "notice": "Restored · 1 not: there is already another note with that link"}
```

- [ ] **Step 2: Run them to see them fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_undo.py`
Expected: FAIL. The delete answers `"notice": "The note was moved…"` with no `undo`, `/undo/…` is a 404, and there is no `id="toast"`.

- [ ] **Step 3: Implement the server**

In `NOTICES`, after `"trashed-indexes-stale"`:

```python
    # A delete asked by a script: the toast is one word, and Deshacer is
    # beside it (spec §6.3). A redirect keeps the long "trashed" sentence,
    # which is also true after the 5 s are gone.
    "deleted": "Deleted",
    "undo-gone": "It can no longer be undone",
    "undo-blocked": "It could not be restored: there is already another note "
                    "with that link",
    "restored-one": "Restored",
    "restored": "%1 restored",
    "restored-one-partial": "Restored · %2 not: there is already another note "
                            "with that link",
    "restored-partial": "%1 restored · %2 not: there is already another note "
                        "with that link",
    "restored-indexes-stale": "Restored, but the indexes could not be rebuilt. "
                              "Run `oknowledge reindex` once the folder is "
                              "writable again.",
```

In `FAILURES`, add `"undo-gone": 404, "undo-blocked": 409`.

After `MISSING = "missing"`:

```python
SECTION_HOMES = {"links": "/", "ocio": "/ocio", "ideas": "/ideas"}
"""Where a shelf's notes are listed: where a delete and a Deshacer go."""
```

Replace `Edited`:

```python
class Edited(NamedTuple):
    """What edit() answers: the notice to show, whether the change really
    landed on disk -- which is what decides where a delete sends the user, and
    must never be guessed from the notice -- and what the change returned
    (a delete's Trashed, which a Deshacer needs)."""

    notice: str
    landed: bool
    value: object = None
```

Replace `answer()`:

```python
ONWARD = ("undo", "reload")
"""What a script needs besides the words: the token Deshacer posts back
(spec §6.3) and whether the page must reload (§3.1)."""


def answer(request: Request, where: str, notice: str = "", extra: dict | None = None,
           **params) -> Response:
    """The answer to a write: a 303 for a form, JSON for a script.

    The JSON carries the notice in words, so the toast says what the page
    would have said after the redirect, plus `undo`/`reload` when given and
    whatever `extra` a route adds (the ids a Deshacer restored).
    """
    if not wants_json(request):
        params.pop("reload", None)            # never in a URL: the page is new anyway
        return see_other(where, notice=notice, **params)
    t = translator(ui_language())
    text = None if notice in QUIET else NOTICES.get(notice)
    said = t(text, params.get("n") or 0, params.get("m") or 0) if text else ""
    status = FAILURES.get(notice)
    if status is not None:
        return JSONResponse({"ok": False, "error": said}, status_code=status)
    body = {"ok": True, "notice": said}
    if notice in RUNS:
        body["runs"] = True
    body.update({key: params[key] for key in ONWARD if params.get(key)})
    body.update(extra or {})
    return JSONResponse(body)
```

In `local_path()`, replace the query line, and say so in its docstring ("a notice it already carries is dropped, with its numbers and its Deshacer token"):

```python
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query)
                       if k not in ("notice", "n", "m", "undo")])
```

In `page()`, add to `base`, after `"toast": False`:

```python
                # A Deshacer the redirect after a delete carries. Only for a
                # lot that still exists and is fresh: an old URL reloaded, or
                # an invented token, offers nothing (spec §2).
                "undo": (request.query_params.get("undo")
                         if "notice" in request.query_params
                         and undo.alive(request.query_params.get("undo"))
                         else None),
                "undo_back": local_path(here) or "/",
```

In `edit()`, keep the value:

```python
        try:
            with link_lock(link_id):
                value = change(live, live.language)
                if value is None:
                    return Edited(MISSING, False)
        except Locked:
            return Edited("busy", False)
        except BadCategory:
            return Edited("bad-category", False)
        except IndexesStale as error:
            log.warning("the indexes could not be rebuilt: %s", error)
            shelves.refresh()
            return Edited(stale, True, error.done)
        except (OSError, ProtectedNote) as error:
            # (the comment that is there stays)
            log.warning("the vault could not be written: %s", error)
            return Edited("write-failed", False)
        shelves.refresh()
        return Edited(done, True, value)
```

Replace the `remove` route with:

```python
    def delete_one(link_id: str, rebuild: bool = True) -> tuple[Edited, str]:
        """One note to trash/, under its lock, on whichever shelf holds it:
        the delete route's body and each id of a bulk delete. Returns the
        shelf's name with the result, for the undo lot and the rebuilds."""
        shelves, which = held_by(link_id)
        result = edit(link_id, lambda cfg, language: delete_note(
            cfg, link_id, language, shelf=which, rebuild=rebuild),
            "trashed", "trashed-indexes-stale", shelves=shelves)
        return result, which.name

    def keep_lot(items) -> str | None:
        """The token a Deshacer posts back, or None when the state dir cannot
        be written: the notes are in trash/ either way and the delete stands."""
        try:
            return undo.remember(current["cfg"], items)
        except OSError as error:
            log.warning("the undo lot could not be written: %s", error)
            return None

    @app.post("/item/{link_id}/delete")
    def remove(request: Request, link_id: str):
        # Moves the file to <vault>/oknowledge/trash/, any shelf. A note that
        # really went to trash/ sends the user back to its section, whatever
        # the indexes did (the item page would 404 now), with a Deshacer; a
        # refused delete leaves them on the note they still have.
        result, name = delete_one(link_id)
        if result.notice == MISSING:
            raise HTTPException(status_code=404, detail="no such link")
        if not result.landed:
            return answer(request, item_url(link_id), result.notice)
        token = keep_lot([(link_id, name, result.value)])
        notice = ("deleted" if result.notice == "trashed" and wants_json(request)
                  else result.notice)
        return answer(request, SECTION_HOMES[name], notice, undo=token)

    @app.post("/undo/{token}")
    def take_back(request: Request, token: str, back: str = Form("")):
        """Deshacer (spec §6.3): a lot's notes back where they were, once."""
        live = current["cfg"]
        result = undo.restore(live, token, live.language, link_lock)
        where = local_path(back)
        if result is None:
            return answer(request, where or "/", "undo-gone")
        for each in (library, shelf, ideas):
            each.refresh()
        home = where or SECTION_HOMES.get(result.shelf, "/")
        if not result.restored:
            return answer(request, home, "undo-blocked")
        n, m = len(result.restored), len(result.skipped)
        if result.stale:
            code = "restored-indexes-stale"
        elif m:
            code = "restored-one-partial" if n == 1 else "restored-partial"
        else:
            code = "restored-one" if n == 1 else "restored"
        return answer(request, home, code, n=n, m=m or None,
                      extra={"restored": result.restored, "skipped": result.skipped})
```

- [ ] **Step 4: Implement the page side**

In `base.html`, replace `{% if notice and toast %}<p class="notice toast" role="status">{{ notice }}</p>{% endif %}` with:

```html
  {# The one toast (spec §2). The server fills it after a redirect, with a
     Deshacer form when the URL carries a live token; app.js takes it over
     and draws every other toast in it. #}
  <div id="toast" class="toast{% if undo %} undo{% endif %}" role="status" aria-live="polite"{% if not (notice and toast) %} hidden{% endif %}>
    {%- if notice and toast %}<span class="toast-text">{{ notice }}</span>
      {%- if undo %}<form method="post" action="/undo/{{ undo }}" class="toast-undo"><input type="hidden" name="back" value="{{ undo_back }}"><button>{{ t('Undo') }}</button></form>{% endif %}
    {%- endif %}</div>
```

In `panel.html`, the Delete form loses its question:

```html
      <form method="post" action="/item/{{ note.id|slug }}/delete">
        <button class="danger">{{ t('Delete') }}</button>
      </form>
```

In `card-panel.html`, the same, keeping `data-inline`:

```html
      <form method="post" action="/item/{{ note.id|slug }}/delete" data-inline>
        <button class="danger">{{ t('Delete') }}</button>
      </form>
```

In `idea.html`:

```html
            <form method="post" action="/item/{{ note.id|slug }}/delete">
              <button class="danger">{{ t('Delete idea') }}</button>
            </form>
```

In `layout.js`, replace the last block:

```js
  // A notice is said once, and its Deshacer is offered once. Left in the
  // URL, a reload would say it again.
  var said = new URL(location.href);
  if (said.searchParams.has("notice") || said.searchParams.has("undo")) {
    ["notice", "n", "m", "undo"].forEach(function (name) { said.searchParams.delete(name); });
    history.replaceState(null, "", said.pathname + said.search + said.hash);
  }
```

In `app.css`, replace the `.toast` rule and keep the keyframes:

```css
.toast { position: fixed; top: 16px; left: 50%; transform: translateX(-50%);
  z-index: 50; margin: 0; background: var(--t1); color: #141519; border-radius: 10px;
  padding: 9px 14px; font-size: 13.5px; box-shadow: var(--shadow);
  display: flex; align-items: center; gap: 14px; white-space: nowrap; }
.toast[hidden] { display: none; }
/* The server's toast hides itself; one app.js owns (.live) it times itself. */
.toast:not(.live) { animation: toast-out .3s ease 2.2s forwards; }
.toast.undo:not(.live) { animation-delay: 5s; }
.toast form { display: contents; }
.toast button { background: none; border: 0; padding: 0; font: inherit; font-weight: 600;
  color: #141519; cursor: pointer; }
.toast button:hover { text-decoration: underline; }
```

In `i18n.py` `STRINGS["es"]`:
- delete `"Move this note to the trash folder?"`, `"Move this card to the trash folder?"` and `"Move this idea to the trash folder?"`;
- add:

```python
        # Deleting with Deshacer (delivery 3, spec §6).
        "Deleted": "Borrado",
        "Undo": "Deshacer",
        "Restored": "Restaurado",
        "%1 restored": "%1 restaurados",
        "It can no longer be undone": "Ya no se puede deshacer",
        "It could not be restored: there is already another note with that link":
            "No se pudo restaurar: ya hay otra nota con ese link",
        "Restored · %2 not: there is already another note with that link":
            "Restaurado · %2 no: ya hay otra nota con ese link",
        "%1 restored · %2 not: there is already another note with that link":
            "%1 restaurados · %2 no: ya hay otra nota con ese link",
        "Restored, but the indexes could not be rebuilt. Run `oknowledge reindex` "
        "once the folder is writable again.":
            "Restaurado, pero no se pudieron rehacer los índices. Corré "
            "`oknowledge reindex` cuando la carpeta vuelva a ser escribible.",
```

- [ ] **Step 5: The ledger**

- `tests/test_web_write.py`:
  - add `("/undo/" + "A" * 22, {}),` and a comment ("Taking a delete back. A cross-site POST here would put notes back into this vault.") to `WRITE_ROUTES`;
  - add `"restore_note"` to `VAULT_WRITERS`.
- `tests/test_web_ocio_panel.py:243`: `assert answer.headers["location"].startswith("/ocio?notice=trashed&undo=")`.
- `tests/test_web_ideas_mine.py:141`: `assert answer.headers["location"].startswith("/ideas?notice=trashed&undo=")`.
- `tests/test_web_idea_screen.py:298`: `assert '<span class="toast-text">' in screen(cfg, put(cfg), "?notice=thinking")`.
- `tests/test_web_panel.py:143`: `assert '<div id="toast" class="toast" role="status" aria-live="polite"><span class="toast-text">Saved.</span>' in body`.

- [ ] **Step 6: Run the new tests and the ledger**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_undo.py tests/test_web_write.py tests/test_web_ocio_panel.py tests/test_web_ideas_mine.py tests/test_web_idea_screen.py tests/test_web_panel.py tests/test_i18n.py`
Expected: PASS.

- [ ] **Step 7: Whole suite, commit**

Run the suite; expected green.

```bash
git add src/oknowledge/web/app.py src/oknowledge/web/templates/base.html \
        src/oknowledge/web/templates/panel.html src/oknowledge/web/templates/card-panel.html \
        src/oknowledge/web/templates/idea.html src/oknowledge/web/static/layout.js \
        src/oknowledge/web/static/app.css src/oknowledge/i18n.py tests/test_web_undo.py \
        tests/test_web_write.py tests/test_web_ocio_panel.py tests/test_web_ideas_mine.py \
        tests/test_web_idea_screen.py tests/test_web_panel.py
git commit -m "Answer every delete with a Deshacer that puts the notes back once"
```

---
### Task 4: One action over many notes

**Files:**
- Modify: `src/oknowledge/web/app.py`:
  - module level: `NOTICES` and `FAILURES` (`bad-state`, `nothing-picked`), new `BULK_ACTIONS`, `BULK_HOMES` and `bulk_words()`;
  - `from ..vault import ACTIONS, IDEA_STATES, MAX_RELATED` gains `states_for`;
  - in `create_app`: `move` (≈1063), `set_state` (≈1129), `set_mark` (≈1183) and `change_kind` (≈1211) are split into `move_one`, `restate_one`, `mark_one` and `retype_one`;
  - new `POST /bulk/{action}`.
- Modify: `src/oknowledge/i18n.py`
- Test: `tests/test_web_bulk.py` (new); ledger `tests/test_web_write.py` (`WRITE_ROUTES`)

**Interfaces:**
- Consumes: `delete_one`, `keep_lot`, `SECTION_HOMES`, `answer()` (Task 3); `update_note(..., rebuild=False)` (Task 1).
- Produces:
  - `move_one(link_id, category, rebuild=True) -> Edited` — links only.
  - `retype_one(link_id, kind, rebuild=True) -> Edited` — cards only.
  - `restate_one(link_id, state) -> Edited` — cards and ideas; a link is `MISSING`.
  - `mark_one(link_id, mark, held=None) -> Edited`, where `held` is `(Library, Shelf)` or `held_by(link_id)`.
  - `bulk_words(t, action, done, failed, label="", unstar=False) -> str`.
  - `POST /bulk/{action}`:
    - fields: `ids` (repeated), `category`, `new_category`, `kind`, `state`, `mark`, `back`;
    - JSON `{"ok": true, "notice", "done": [...], "failed": [...]}`, plus `"undo"` for `delete`;
    - errors: 400 for a refused value or no ids, 404 when every id is gone, else the status of the first failure that is not "gone";
    - without JSON: 303 to `back` or the section, with `notice=saved`, or `notice=trashed&undo=…` for a delete.

- [ ] **Step 1: Write the failing tests**

`tests/test_web_bulk.py`:

```python
"""Bulk actions (spec §5.1): each id goes through its own route's rule and
lock, a refused value writes nothing, the indexes are rebuilt once per shelf,
and an id that is gone (or on another shelf, or busy) is counted, not fatal."""

import re
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.model import Note
from oknowledge.queue import Queue
from oknowledge.vault import find_note, index_path, note_path, rebuild_indexes, trash_dir, write_note
from oknowledge.web.app import create_app

JSON = {"Accept": "application/json"}
CARD1, CARD2 = "c00000000001", "c00000000002"


def link(id, title, category):
    return Note(id=id, url=f"https://e.com/{id}", title=title, category=category, tags=[],
                type="article", source="e.com", saved="2026-10-03", summary="s")


@pytest.fixture
def s(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    for id, title, category in (("a1", "WireGuard", "Redes"), ("b2", "Masa madre", "Cocina"),
                                ("c3", "SSH", "Redes")):
        write_note(cfg, link(id, title, category), "es")
    for id, kind, category in ((CARD1, "movie", "Películas"), (CARD2, "book", "Libros")):
        card = Note(id=id, url=f"https://www.imdb.com/title/{id}", title=f"Ficha {id}",
                    category=category, tags=[], type=kind, source="imdb.com",
                    saved="2026-10-01", summary="s", engine="")
        write_note(cfg, card, "es", path=note_path(cfg, card, shelf=cfg.ocio))
    ideas = []
    for n in (1, 2):
        idea = new_idea(f"Idea {n}.", f"Idea {n}", "2026-10-13",
                        f"2026-10-13T00:00:00.00000{n}+00:00")
        write_note(cfg, idea, "es", path=note_path(cfg, idea, shelf=cfg.ideas))
        ideas.append(idea.id)
    for shelf in (cfg.links, cfg.ocio, cfg.ideas):
        rebuild_indexes(cfg, "es", shelf=shelf)
    return SimpleNamespace(cfg=cfg, client=TestClient(create_app(cfg)), ideas=ideas,
                           vault=vault)


def post(s, action, **data):
    return s.client.post(f"/bulk/{action}", data=data, headers=JSON)


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


# --- move ------------------------------------------------------------------------

def test_a_bulk_move_moves_each_and_says_where(s):
    answer = post(s, "category", ids=["a1", "b2", "c3"], category="Seguridad")
    assert answer.json() == {"ok": True, "notice": "3 moved to Seguridad",
                             "done": ["a1", "b2", "c3"], "failed": []}
    assert {find_note(s.cfg, i)[1].category for i in ("a1", "b2", "c3")} == {"Seguridad"}
    assert index_path(s.cfg, "Seguridad").exists()
    assert not index_path(s.cfg, "Redes").exists() and not index_path(s.cfg, "Cocina").exists()


def test_one_moved_is_said_in_the_singular(s):
    assert post(s, "category", ids=["a1"], category="Seguridad").json()["notice"] == \
        "1 moved to Seguridad"


def test_a_new_category_typed_in_the_bar_is_used(s):
    post(s, "category", ids=["a1"], category="", new_category="Hogar")
    assert find_note(s.cfg, "a1")[1].category == "Hogar"


def test_ids_that_are_gone_or_on_another_shelf_are_counted_as_failed(s):
    body = post(s, "category", ids=["a1", "zzz", CARD1], category="Seguridad").json()
    assert body["done"] == ["a1"] and body["failed"] == ["zzz", CARD1]
    assert body["notice"] == "1 moved to Seguridad · 2 could not be changed"
    assert find_note(s.cfg, CARD1, s.cfg.ocio)[1].category == "Películas"


def test_bulk_move_with_an_id_deleted_meanwhile(s):
    path = find_note(s.cfg, "b2")[0]
    path.unlink()                                  # gone in Obsidian since the page was drawn
    body = post(s, "category", ids=["a1", "b2"], category="Seguridad").json()
    assert body["done"] == ["a1"] and body["failed"] == ["b2"]
    assert not path.exists() and find_note(s.cfg, "b2") is None


# --- refused values -----------------------------------------------------------------

@pytest.mark.parametrize("action,data,error", [
    ("category", {"category": "a/b"}, "cannot be used"),
    ("kind", {"kind": "opera"}, "type"),
    ("state", {"state": "abandonada"}, "state"),
    ("mark", {"mark": "🦄"}, "emoji"),
])
def test_a_refused_value_writes_nothing(s, action, data, error):
    before = snapshot(s.vault)
    answer = post(s, action, ids=["a1", CARD1, *s.ideas], **data)
    assert answer.status_code == 400 and error in answer.json()["error"]
    assert snapshot(s.vault) == before


def test_nothing_ticked_is_refused(s):
    answer = post(s, "delete")
    assert answer.status_code == 400
    assert answer.json()["error"] == "No cards were selected, so nothing changed."


def test_an_action_nobody_knows_is_a_404(s):
    assert s.client.post("/bulk/explode", data={"ids": ["a1"]}, headers=JSON).status_code == 404


# --- one rebuild per shelf ------------------------------------------------------------

def test_one_rebuild_per_shelf(s, monkeypatch):
    calls = []
    monkeypatch.setattr("oknowledge.web.app.rebuild_indexes",
                        lambda cfg, language, shelf=None: calls.append(shelf.name))
    monkeypatch.setattr("oknowledge.vault.rebuild_indexes",
                        lambda *a, **k: pytest.fail("rebuilt once per note"))

    post(s, "category", ids=["a1", "b2", "c3"], category="Seguridad")
    post(s, "kind", ids=[CARD1, CARD2], kind="series")
    post(s, "delete", ids=["a1", CARD1, s.ideas[0]])

    assert calls == ["links", "ocio", "ideas", "links", "ocio"]


def test_a_failed_rebuild_is_added_to_the_words(s, monkeypatch):
    def boom(cfg, language, shelf=None):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr("oknowledge.web.app.rebuild_indexes", boom)
    body = post(s, "category", ids=["a1"], category="Seguridad").json()
    assert body["ok"] is True
    assert body["notice"].startswith("1 moved to Seguridad · Saved, but the indexes")


# --- kind, state, mark ----------------------------------------------------------------

def test_kind_retypes_the_cards(s):
    body = post(s, "kind", ids=[CARD1, CARD2], kind="series").json()
    assert body["notice"] == "2 moved to Series"
    for card in (CARD1, CARD2):
        note = find_note(s.cfg, card, s.cfg.ocio)[1]
        assert (note.type, note.category) == ("series", "Series")


def test_state_changes_the_ideas_and_not_a_link(s):
    body = post(s, "state", ids=[*s.ideas, "a1"], state="doing").json()
    assert body["done"] == s.ideas and body["failed"] == ["a1"]
    assert body["notice"] == "2 moved to under way · 1 could not be changed"
    assert {find_note(s.cfg, i, s.cfg.ideas)[1].state for i in s.ideas} == {"doing"}


def test_dropped_is_not_a_state_a_card_can_have(s):
    answer = post(s, "state", ids=[CARD1], state="dropped")
    assert answer.status_code == 400
    assert find_note(s.cfg, CARD1, s.cfg.ocio)[1].state == ""


def marks(s, *ids):
    return [find_note(s.cfg, i)[1].mark for i in ids]


def test_the_star_goes_on_all_unless_all_have_it(s):
    s.client.post("/item/a1/mark", data={"mark": "⭐"})
    assert post(s, "mark", ids=["a1", "b2"], mark="⭐").json()["notice"] == \
        "2 marked as favorites"
    assert marks(s, "a1", "b2") == ["⭐", "⭐"]
    assert post(s, "mark", ids=["a1", "b2"], mark="⭐").json()["notice"] == \
        "Favorite removed from 2"
    assert marks(s, "a1", "b2") == ["", ""]


def test_one_star_is_said_in_the_singular(s):
    assert post(s, "mark", ids=["a1"], mark="⭐").json()["notice"] == "1 marked as favorite"


def test_the_star_is_for_links_only(s):
    answer = post(s, "mark", ids=[CARD1], mark="⭐")
    assert answer.status_code == 404


# --- delete ----------------------------------------------------------------------------

def test_a_bulk_delete_gives_one_token_for_all(s):
    body = post(s, "delete", ids=["a1", "b2", CARD1]).json()
    assert body["notice"] == "3 deleted" and body["done"] == ["a1", "b2", CARD1]
    back = s.client.post(f"/undo/{body['undo']}", headers=JSON).json()
    assert back["notice"] == "3 restored"
    assert sorted(back["restored"]) == sorted(["a1", "b2", CARD1])
    assert find_note(s.cfg, "a1") and find_note(s.cfg, CARD1, s.cfg.ocio)


def test_one_deleted_says_deleted(s):
    assert post(s, "delete", ids=["a1"]).json()["notice"] == "Deleted"


def test_bulk_delete_with_an_id_deleted_meanwhile(s):
    find_note(s.cfg, "b2")[0].unlink()
    body = post(s, "delete", ids=["a1", "b2"]).json()
    assert body["done"] == ["a1"] and body["failed"] == ["b2"]
    assert body["notice"] == "Deleted · 1 could not be changed"
    assert len(list(trash_dir(s.cfg).glob("*.md"))) == 1


def test_all_gone_is_a_404_with_the_words(s):
    answer = post(s, "delete", ids=["zzz", "yyy"])
    assert answer.status_code == 404
    assert answer.json() == {"ok": False, "error": "That is not there any more."}


def test_a_busy_link_is_skipped(s):
    with Queue().lock("a1"):
        body = post(s, "category", ids=["a1", "b2"], category="Seguridad").json()
    assert body["done"] == ["b2"] and body["failed"] == ["a1"]


def test_all_busy_is_a_409(s):
    with Queue().lock("a1"):
        answer = post(s, "delete", ids=["a1"])
    assert answer.status_code == 409
    assert find_note(s.cfg, "a1") is not None


# --- without a script --------------------------------------------------------------

def test_without_a_script_it_goes_back_with_saved(s):
    answer = s.client.post("/bulk/category", data={"ids": ["a1"], "category": "Seguridad",
                                                   "back": "/?vista=lista"},
                           follow_redirects=False)
    assert answer.headers["location"] == "/?vista=lista&notice=saved"


def test_a_bulk_delete_without_a_script_offers_undo(s):
    answer = s.client.post("/bulk/delete", data={"ids": [CARD1]}, follow_redirects=False)
    assert re.fullmatch(r"/ocio\?notice=trashed&undo=[A-Za-z0-9_-]{22}",
                        answer.headers["location"])
```

- [ ] **Step 2: Run them to see them fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_bulk.py`
Expected: FAIL — every `/bulk/...` is a 404 (or a 405 page), so `answer.json()` raises or has no `done`.

- [ ] **Step 3: Implement the module-level pieces**

In `NOTICES`, after `"bad-kind"`: `"bad-state": "That is not a state it can be in.",`. In `FAILURES` add `"bad-state": 400, "nothing-picked": 400`.

After `SECTION_HOMES`:

```python
BULK_ACTIONS = ("category", "kind", "state", "mark", "delete")
"""What the floating bar can do to the ticked items (spec §5.1)."""

BULK_HOMES = {"category": "/", "mark": "/", "kind": "/ocio", "state": "/ideas", "delete": "/"}
"""Where a bulk action's redirect goes when no `back` came with it."""


def bulk_words(t, action: str, done: int, failed: int, label: str = "",
               unstar: bool = False) -> str:
    """What a bulk action says (spec §5.1), in words: it names a category,
    a kind or a state, which a NOTICES key cannot carry in its numbers."""
    if action == "delete":
        said = t("Deleted") if done == 1 else t("%1 deleted", done)
    elif action == "mark":
        if unstar:
            said = t("Favorite removed from %1", done)
        else:
            said = t("1 marked as favorite") if done == 1 else t("%1 marked as favorites", done)
    else:
        said = t("1 moved to %2", done, label) if done == 1 else t("%1 moved to %2", done, label)
    if failed:
        said += " · " + (t("1 could not be changed") if failed == 1
                         else t("%1 could not be changed", failed))
    return said
```

Change the vault import line to `from ..vault import ACTIONS, IDEA_STATES, MAX_RELATED, states_for`.

- [ ] **Step 4: Split the single routes**

Replace `move`:

```python
    def move_one(link_id: str, category: str, rebuild: bool = True) -> Edited:
        """A link to another category: the route's body, and each id of a
        bulk move. The name is checked by the caller, once."""
        return edit(link_id, lambda cfg, language: update_note(
            cfg, link_id, language, category=category, rebuild=rebuild),
            "saved", "indexes-stale")

    @app.post("/item/{link_id}/category")
    def move(request: Request, link_id: str, category: str = Form("")):
        if clean_category(category) is None:
            # Before the lock, so a refused name creates nothing anywhere --
            # not even the lock file. update_note() checks it again anyway.
            return answer(request, item_url(link_id), notice="bad-category")
        result = move_one(link_id, category)
        if result.notice == MISSING:
            raise HTTPException(status_code=404, detail="no such link")
        return answer(request, item_url(link_id), notice=result.notice)
```

Replace `set_state`:

```python
    def restate_one(link_id: str, state: str) -> Edited:
        """A card's or an idea's state: the route's body, and each id of a
        bulk change. A link has no state: it is MISSING here, as its route
        has always said with a 404."""
        shelves, which = held_by(link_id)
        if which.name == "links":
            return Edited(MISSING, False)
        return edit(link_id, lambda cfg, language: update_note(
            cfg, link_id, language, shelf=cfg.shelf(which.name), state=state),
            "saved", "indexes-stale", shelves=shelves)

    @app.post("/item/{link_id}/mine/state")
    def set_state(request: Request, link_id: str, state: str = Form("")):
        result = restate_one(link_id, state)
        if result.notice == MISSING:
            raise HTTPException(status_code=404, detail="no such card")
        return answer(request, item_url(link_id), notice=result.notice)
```

In `set_mark`, add before it:

```python
    def mark_one(link_id: str, mark: str, held=None) -> Edited:
        """Your one emoji on a note: the route's body, and each id of a bulk ★.
        `held` is the (Library, Shelf) the caller already looked up."""
        shelves, which = held or held_by(link_id)
        return edit(link_id, lambda cfg, language: update_note(
            cfg, link_id, language, shelf=cfg.shelf(which.name), mark=mark),
            "", "indexes-stale", shelves=shelves)
```

and replace its `result = edit(...)` call with `result = mark_one(link_id, mark, (shelves, which))`.

In `change_kind`, add before it:

```python
    def retype_one(link_id: str, kind: str, rebuild: bool = True) -> Edited:
        """A card's type and the category that goes with it: the route's
        body, and each id of a bulk change. The kind is checked by the caller."""
        def retype(cfg, language):
            names = cards.CATEGORIES.get(language, cards.CATEGORIES["en"])
            return update_note(cfg, link_id, language, shelf=cfg.ocio, kind=kind,
                               category=names[kind], rebuild=rebuild)
        return edit(link_id, retype, "saved", "indexes-stale", shelves=shelf)
```

and in `change_kind` replace the inner `retype` and its `edit` call with `result = retype_one(link_id, kind)`.

- [ ] **Step 5: The bulk route**

After `take_back`:

```python
    @app.post("/bulk/{action}")
    def bulk(request: Request, action: str, ids: list[str] = Form([]),
             category: str = Form(""), new_category: str = Form(""),
             kind: str = Form(""), state: str = Form(""), mark: str = Form(""),
             back: str = Form("")):
        """One action over the ticked items (spec §5.1).

        Each id goes through the function its own route uses, under its own
        lock. The value is checked once, before the first id: a refused one
        writes nothing. The indexes are rebuilt once per shelf at the end,
        not once per note. An id that is gone, on another shelf or busy is
        counted in `failed` and the others still land.
        """
        if action not in BULK_ACTIONS:
            raise HTTPException(status_code=404, detail="no such action")
        live = current["cfg"]
        t = translator(ui_language())
        home = local_path(back) or BULK_HOMES[action]
        picked = list(dict.fromkeys(one for one in ids if one))
        if not picked:
            return answer(request, home, "nothing-picked")
        label, unstar = "", False

        def restate_checked(link: str) -> Edited:
            shelves, which = held_by(link)
            note = shelves.by_id(link)
            if note is None or which.name == "links":
                return Edited(MISSING, False)
            if state not in states_for(note.type):
                return Edited("bad-state", False)
            return restate_one(link, state)

        if action == "category":
            label = clean_category(category.strip() or new_category.strip())
            if label is None:
                return answer(request, home, "bad-category")
            one = lambda link: (move_one(link, label, rebuild=False), "links")
        elif action == "kind":
            if kind not in cards.KINDS:
                return answer(request, home, "bad-kind")
            label = t(KIND_NAMES[kind])
            one = lambda link: (retype_one(link, kind, rebuild=False), "ocio")
        elif action == "state":
            if state not in IDEA_STATES:
                return answer(request, home, "bad-state")
            label = t(IDEA_WORDS[state])
            one = lambda link: (restate_checked(link), "")
        elif action == "mark":
            if mark != "⭐":
                return answer(request, home, "bad-mark")
            library.refresh()
            present = [n for n in (library.by_id(link) for link in picked) if n is not None]
            unstar = bool(present) and all(n.mark == "⭐" for n in present)
            wanted = "" if unstar else "⭐"
            one = lambda link: (mark_one(link, wanted, (library, live.links)), "links")
        else:
            one = lambda link: delete_one(link, rebuild=False)

        done, failed, refused, touched, lot = [], [], [], set(), []
        for link in picked:
            result, name = one(link)
            if result.landed:
                done.append(link)
                touched.add(name)
                if action == "delete":
                    lot.append((link, name, result.value))
            else:
                failed.append(link)
                refused.append(result.notice)
        stale = False
        if action in ("category", "kind", "delete") and done:
            for name in sorted(touched):
                try:
                    rebuild_indexes(live, live.language, live.shelf(name))
                except OSError as error:
                    log.warning("the indexes could not be rebuilt: %s", error)
                    stale = True
            for each in (library, shelf, ideas):
                each.refresh()
        if not done:
            worst = next((code for code in refused if code != MISSING), None)
            if worst is None:
                raise HTTPException(status_code=404, detail="none of them is there")
            return answer(request, home, worst)
        token = keep_lot(lot) if lot else None
        if not wants_json(request):
            if action == "delete":
                where = local_path(back) or SECTION_HOMES.get(lot[0][1], "/")
                return see_other(where, notice="trashed", undo=token)
            return see_other(home, notice="saved")
        said = bulk_words(t, action, len(done), len(failed), label, unstar)
        if stale:
            said += " · " + t(NOTICES["indexes-stale"])
        body = {"ok": True, "notice": said, "done": done, "failed": failed}
        if token:
            body["undo"] = token
        return JSONResponse(body)
```

In `i18n.py` add:

```python
        # Bulk actions (delivery 3, spec §5.1).
        "That is not a state it can be in.": "Ese no es un estado que pueda tener.",
        "%1 deleted": "%1 borrados",
        "1 moved to %2": "1 movido a %2",
        "%1 moved to %2": "%1 movidos a %2",
        "1 marked as favorite": "1 marcado como favorito",
        "%1 marked as favorites": "%1 marcados como favoritos",
        "Favorite removed from %1": "Se quitó favorito a %1",
        "1 could not be changed": "1 no se pudo cambiar",
        "%1 could not be changed": "%1 no se pudieron cambiar",
```

In `tests/test_web_write.py` `WRITE_ROUTES`, add with a comment ("A bulk action. A cross-site POST here would move or delete many notes at once."):

```python
    ("/bulk/delete", {"ids": ["a1"]}),
```

- [ ] **Step 6: Run the new tests and the routes they share code with**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_bulk.py tests/test_web_write.py tests/test_web_marks.py tests/test_web_ocio_mine.py tests/test_web_ocio_panel.py tests/test_web_ideas_mine.py tests/test_web_inline_saves.py tests/test_i18n.py`
Expected: PASS.

- [ ] **Step 7: Whole suite, commit**

Run the suite; expected green.

```bash
git add src/oknowledge/web/app.py src/oknowledge/i18n.py tests/test_web_bulk.py tests/test_web_write.py
git commit -m "Move, star, restate or delete many notes at once, with one rebuild per shelf"
```

---
### Task 5: Every Settings write answers a script

**Files:**
- Modify: `src/oknowledge/web/app.py`:
  - module level: `NOTICES` (`analysing`, `analysing-one`), `FAILURES`, new `SETTINGS_TABS` and `settings_url()`;
  - in `create_app`: `save_settings` (≈1628), `find_models` (≈1717), `make_env_file` (≈1740), `start_batch` (≈2204), `rename` (≈1497).
- Modify: `src/oknowledge/i18n.py`
- Test: `tests/test_web_settings_saves.py` (new), `tests/test_web_retry.py` (append)

**Interfaces:**
- Consumes: `answer()` with `reload` (Task 3).
- Produces:
  - `SETTINGS_TABS = (("motores", "Engines"), ("idioma", "Language and saving"), ("importar", "Import"), ("categorias", "Categories"))` and `settings_url(tab) -> str` (`/settings?tab=<tab>`, or `/settings` for an unknown tab).
  - `POST /settings` with a hidden `tab`. A field that does not arrive keeps its saved value (the three `*_model` fields become `Form(None)`). JSON is `{"ok": true, "notice": ""}`, plus `"reload": true` when `ui_language` changed; `settings-failed` is 500.
  - `POST /settings/models/{engine}` and `POST /settings/env` answer through `answer(..., settings_url("motores"), …)`; `env-there` is 409 and `env-failed` 500.
  - `POST /retry` answers through `answer()`. For JSON, a started batch says `analysing` ("Analysing %1 links", `n` = size) or `analysing-one`; `batch-running` is 409.
  - `POST /categories/rename` answers through `answer(..., settings_url("categorias"), code, n=…, m=…)`.

- [ ] **Step 1: Write the failing tests**

`tests/test_web_settings_saves.py`:

```python
"""Settings saves itself, one pane at a time (spec §3.1): a field that does
not arrive keeps its value, every write answers JSON to a script, and the
interface language asks for a reload."""

import pytest
from fastapi.testclient import TestClient

from oknowledge.ai.fake import FakeEngine
from oknowledge.config import Config, load
from oknowledge.model import Note
from oknowledge.vault import rebuild_indexes, write_note
from oknowledge.web import app as module
from oknowledge.web.app import create_app

JSON = {"Accept": "application/json"}


@pytest.fixture(autouse=True)
def state_tree(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr("oknowledge.web.app.CONFIG_PATH", tmp_path / "config" / "config.toml")


@pytest.fixture
def client(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    for id in ("a1", "b2"):
        write_note(cfg, Note(id=id, url=f"https://e.com/{id}", title=id, category="Networking",
                             tags=[], type="article", source="e.com", saved="2026-10-03",
                             summary="s"), "es")
    rebuild_indexes(cfg, "es")
    return TestClient(create_app(cfg))


def saved(tmp_path):
    return load(tmp_path / "config" / "config.toml")


def listed(names):
    def build(name, cfg):
        found = FakeEngine([])
        found.models = lambda: list(names)
        return found
    return build


# --- one pane at a time ---------------------------------------------------------

def test_a_pane_saves_only_its_own_fields(client, tmp_path):
    client.post("/settings", data={"chain": ["opencode"], "opencode_model": "a/one",
                                   "tab": "motores"})
    client.post("/settings", data={"language": "en", "ui_language": "en",
                                   "default_content": "summary", "mentions": "all",
                                   "batch": "7", "tab": "idioma"})
    cfg = saved(tmp_path)
    assert cfg.engines["opencode"]["model"] == "a/one"
    assert cfg.chain == ("opencode",)
    assert (cfg.default_content, cfg.mentions, cfg.batch) == ("summary", "all", 7)


def test_an_empty_model_box_still_clears_it(client, tmp_path):
    client.post("/settings", data={"opencode_model": "a/one", "tab": "motores"})
    client.post("/settings", data={"opencode_model": "", "tab": "motores"})
    assert "model" not in saved(tmp_path).engines.get("opencode", {})


def test_a_pane_answers_a_script_with_nothing_to_say(client):
    answer = client.post("/settings", data={"default_content": "summary", "tab": "idioma"},
                         headers=JSON)
    assert answer.json() == {"ok": True, "notice": ""}


def test_changing_the_interface_language_asks_for_a_reload(client):
    first = client.post("/settings", data={"ui_language": "es", "tab": "idioma"}, headers=JSON)
    assert first.json() == {"ok": True, "notice": "", "reload": True}
    again = client.post("/settings", data={"ui_language": "es", "tab": "idioma"}, headers=JSON)
    assert "reload" not in again.json()


def test_a_form_goes_back_to_its_pane(client):
    answer = client.post("/settings", data={"ui_language": "es", "tab": "idioma"},
                         follow_redirects=False)
    assert answer.headers["location"] == "/settings?tab=idioma&notice=saved"


@pytest.mark.parametrize("tab", ["", "nope"])
def test_without_a_known_tab_it_goes_to_the_page(client, tab):
    answer = client.post("/settings", data={"batch": "3", "tab": tab}, follow_redirects=False)
    assert answer.headers["location"] == "/settings?notice=saved"


def test_a_config_that_cannot_be_written_is_a_500_to_a_script(client, monkeypatch):
    def boom(*args, **kwargs):
        raise OSError(13, "Permission denied")
    monkeypatch.setattr("oknowledge.web.app.save_config", boom)
    answer = client.post("/settings", data={"batch": "3", "tab": "idioma"}, headers=JSON)
    assert answer.status_code == 500
    assert "could not be saved" in answer.json()["error"]


def test_a_shared_language_that_cannot_be_written_is_said(client, monkeypatch):
    def boom(language):
        raise PermissionError(13, "read-only")
    monkeypatch.setattr("oknowledge.web.app.set_ui_language", boom)
    body = client.post("/settings", data={"ui_language": "es", "tab": "idioma"},
                       headers=JSON).json()
    assert body["ok"] is True and "interface language" in body["notice"]


# --- the action buttons -----------------------------------------------------------

def test_finding_models_answers_a_script_and_a_form_goes_to_engines(client, monkeypatch):
    monkeypatch.setattr(module, "build_engine", listed(["a/one", "b/two"]))
    body = client.post("/settings/models/opencode", headers=JSON).json()
    assert body == {"ok": True, "notice": "2 models found. They are in the list beside each box."}
    location = client.post("/settings/models/opencode", follow_redirects=False).headers["location"]
    assert location == "/settings?tab=motores&notice=models-found&n=2"


def test_making_the_env_answers_a_script(client):
    first = client.post("/settings/env", data={"provider": "groq"}, headers=JSON)
    assert first.status_code == 200 and first.json()["ok"] is True
    again = client.post("/settings/env", data={"provider": "groq"}, headers=JSON)
    assert again.status_code == 409


def test_an_env_that_cannot_be_made_is_a_500(client, monkeypatch):
    monkeypatch.setattr("oknowledge.web.app.env.create", lambda *a, **k: False)
    assert client.post("/settings/env", data={"provider": "groq"}, headers=JSON).status_code == 500


def test_renaming_answers_a_script_and_a_form_goes_to_categories(client):
    body = client.post("/categories/rename", data={"old": "Networking", "new": "Redes"},
                       headers=JSON).json()
    assert body == {"ok": True, "notice": "2 notes moved."}
    location = client.post("/categories/rename", data={"old": "Redes", "new": "Seguridad"},
                           follow_redirects=False).headers["location"]
    assert location == "/settings?tab=categorias&notice=renamed&n=2&m=0"


def test_a_refused_rename_is_a_400_to_a_script(client):
    answer = client.post("/categories/rename", data={"old": "Networking", "new": "a/b"},
                         headers=JSON)
    assert answer.status_code == 400 and "cannot be used" in answer.json()["error"]
```

Append to `tests/test_web_retry.py`:

```python
# --- a batch started from Settings (delivery 3, spec §3.1) ------------------------

JSON = {"Accept": "application/json"}


def test_a_script_starting_a_batch_is_told_how_many(setup, started):
    cfg, client = setup                       # batch=2
    owe(3)
    assert client.post("/retry", headers=JSON).json() == {"ok": True, "notice": "Analysing 2 links"}


def test_a_script_starting_one_is_told_in_the_singular(setup, started):
    cfg, client = setup
    owe(1)
    assert client.post("/retry", headers=JSON).json()["notice"] == "Analysing 1 link"


def test_a_second_batch_is_a_409_to_a_script(setup, started):
    cfg, client = setup
    owe(3)
    client.post("/retry", follow_redirects=False)
    assert client.post("/retry", headers=JSON).status_code == 409
    assert len(started) == 1
```

- [ ] **Step 2: Run them to see them fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_settings_saves.py tests/test_web_retry.py`
Expected: FAIL. A missing `opencode_model` clears the model, every route answers a 303 whatever the `Accept`, and the locations carry no `tab`.

- [ ] **Step 3: Implement**

Module level, after `BULK_HOMES`:

```python
SETTINGS_TABS = (("motores", "Engines"), ("idioma", "Language and saving"),
                 ("importar", "Import"), ("categorias", "Categories"))
"""Settings' four panes (spec §3.1), by the key their URL carries. The
labels are t() keys: the template asks for them through this table."""


def settings_url(tab: str) -> str:
    """Where a settings write goes back to: its own pane, or the page."""
    return f"/settings?tab={tab}" if tab in dict(SETTINGS_TABS) else "/settings"
```

In `NOTICES`, after `"batch-running"`:

```python
    # The same start, said to a script: the modal stays open and the toast
    # says what started (spec §3.1); "this page comes back" would be false.
    "analysing": "Analysing %1 links",
    "analysing-one": "Analysing 1 link",
```

In `FAILURES` add `"settings-failed": 500, "env-failed": 500, "env-there": 409, "batch-running": 409`.

`save_settings` becomes:

```python
    @app.post("/settings")
    def save_settings(request: Request, chain: list[str] = Form([]),
                      language: str = Form(""), default_content: str = Form(""),
                      mentions: str = Form(""), batch: str = Form(""),
                      interface: str = Form("", alias="ui_language"),
                      opencode_model: str | None = Form(None),
                      ollama_model: str | None = Form(None),
                      api_model: str | None = Form(None), api_provider: str = Form(""),
                      tab: str = Form("")):
        """One pane of Settings (spec §3.1). A field that does not arrive keeps
        what is saved: each pane is its own form and sends only its fields. An
        empty model box that does arrive still clears that model."""
        where = settings_url(tab)
        saved = current["cfg"]
        engines = {name: dict(options) for name, options in saved.engines.items()}
        for name, raw in (("opencode", opencode_model), ("ollama", ollama_model),
                          ("api", api_model)):
            if raw is None:                    # not in this pane: leave it
                continue
            model = model_name(raw)
            if model is None:                  # not a name: leave what is on disk
                continue
            if model:
                engines.setdefault(name, {})["model"] = model
            elif name in engines:
                engines[name].pop("model", None)
        # A provider the table does not have is not written: the file may name
        # a gateway of somebody's own, and this form must not be the thing
        # that replaces it with a guess.
        if find_provider(api_provider.strip()):
            engines.setdefault("api", {})["provider"] = api_provider.strip()
        # Every value is checked here, because config.load() would refuse the
        # file afterwards and the whole tool would stop reading its own config.
        # An empty one (a pane that does not send it) keeps the saved value.
        picked = tuple(name for name in chain if name in ENGINE_NAMES)
        updated = dataclasses.replace(
            saved,
            chain=picked or saved.chain,
            language=language if language in LANGUAGES else saved.language,
            default_content=(default_content if default_content in CONTENT_MODES
                             else saved.default_content),
            mentions=mentions if mentions in MENTION_MODES else saved.mentions,
            batch=batch_size(batch, saved.batch),
            engines=engines,
        )
        try:
            save_config(updated, config_file())
        except OSError as error:
            # The old file is still there, untouched: save() writes atomically
            # and backs up before it writes.
            log.warning("the config could not be saved: %s", error)
            return answer(request, where, "settings-failed")
        current["cfg"] = updated
        # Asked before it is written: afterwards both read the same.
        changed = interface in LANGUAGES and interface != ui_language()
        try:
            if interface in LANGUAGES:
                set_ui_language(interface)
        except OSError as error:
            # The config itself did land. Saying it did not would be a lie
            # about the half that worked.
            log.warning("the shared language file could not be written: %s", error)
            return answer(request, where, "language-not-saved")
        return answer(request, where, "saved", reload=changed or None)
```

`find_models` takes `request: Request` first, and its two returns become:

```python
        if not found:
            return answer(request, settings_url("motores"), "models-none")
        return answer(request, settings_url("motores"), "models-found", n=len(found))
```

`make_env_file` takes `request: Request` first, and its three returns become `answer(request, settings_url("motores"), "env-there")`, `… "env-failed")` and `… "env-made")`.

`start_batch` becomes:

```python
    @app.post("/retry")
    def start_batch(request: Request, background: BackgroundTasks, debug: str = Form("")):
        live = current["cfg"]
        if debug:
            # (the comment that is there stays)
            live = dataclasses.replace(live, trace_to=trace_run())
        # The same listing retry() walks, so the bar's total cannot promise
        # work the run will not find.
        waiting = len(owed(Queue())[0])
        if not waiting:
            return answer(request, "/retry", "nothing-owed")
        size = min(live.batch, waiting)
        if not progress.start(size):
            # Two runs would reach for the same links and pay twice for each.
            return answer(request, "/retry", "batch-running")
        # After the response, not before it: a batch of fifty is an hour.
        background.add_task(run_batch, live, progress, live.batch)
        if wants_json(request):
            return answer(request, "/retry", "analysing-one" if size == 1 else "analysing",
                          n=size)
        return see_other("/retry", notice="batch-started")
```

`rename` takes `request: Request` first. Each `see_other("/categories", notice=X)` becomes `answer(request, settings_url("categorias"), X)`, and the last return becomes:

```python
        return answer(request, settings_url("categorias"), code,
                      n=result.moved, m=len(result.failed))
```

In `i18n.py` add:

```python
        "Analysing %1 links": "Analizando %1 links",
        "Analysing 1 link": "Analizando 1 link",
```

and add the four tab labels now, since `SETTINGS_TABS` already asks for them. "Categories" is already there:

```python
        "Language and saving": "Idioma y guardado",
        "Import": "Importar",
```

- [ ] **Step 4: Run the tests of every route touched**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_settings_saves.py tests/test_web_retry.py tests/test_web_settings.py tests/test_web_write.py tests/test_web_batch.py tests/test_i18n.py`
Expected: PASS. The rename tests in `test_web_write.py` follow the redirect to `/settings?tab=categorias&notice=…`, whose page draws the notice.

- [ ] **Step 5: Whole suite, commit**

Run the suite; expected green.

```bash
git add src/oknowledge/web/app.py src/oknowledge/i18n.py tests/test_web_settings_saves.py tests/test_web_retry.py
git commit -m "Let each Settings pane save only its own fields, and answer every settings write as JSON"
```

---
### Task 6: Settings in four panes, and the sidebar's new foot

**Files:**
- Create: `src/oknowledge/web/templates/settings-body.html`
- Modify:
  - `src/oknowledge/web/app.py`: in `create_app`, `settings_page` (≈1592) splits into `settings_context()`, `GET /settings` and `GET /settings/panel`; `category_page` (≈1492) becomes a redirect.
  - `src/oknowledge/web/templates/settings.html` (it only includes the fragment) and `base.html` (loads `settings.js`).
  - `src/oknowledge/web/templates/sidebar.html`: section hints and foot.
  - `src/oknowledge/web/static/layout.js` (`js` class), `app.css` (settings, `.js-only`, `.key`, foot) and `style.css` (drop `.cat-grid`/`.cat-card`, ≈257–271).
  - `src/oknowledge/i18n.py`.
- Delete: `src/oknowledge/web/templates/categories.html`
- Test: `tests/test_web_settings_tabs.py` (new).
- Ledger:
  - `tests/test_web_sidebar.py:40`;
  - `tests/test_web_retry.py:268,433-439`;
  - `tests/test_web_activity.py:85-86`;
  - `tests/test_web_layout.py:62-74` (the two categories-page tests go);
  - `tests/test_web_settings.py:607-608`.

**Interfaces:**
- Consumes: `SETTINGS_TABS`, `settings_url` (Task 5).
- Produces:
  - `settings_context(tab) -> dict` (inside `create_app`). It holds `tab` (unknown → `motores`), `tabs`, `cfg`, `ui`, `engines`, `config_path`, `providers`, `picked`, `keys`, `stranger`, `by_hand`, `key`, `models`, `owed`, `size`, `languages`, `language_names` and `categories`.
  - `GET /settings?tab=` (page) and `GET /settings/panel?tab=` (fragment, no `<html>`, no sidebar).
  - `GET /categories` → 303 `/settings?tab=categorias`.
  - Markup hooks for Task 8:
    - root `.settings-body[data-settings-root]`;
    - tabs `a[data-settings-tab]` and panes `section[data-settings-pane]`;
    - pane forms `form[data-settings]` with a hidden `tab`;
    - action forms `form[data-settings-action]` (`find-{engine}`, `make-env-{provider}`, the `/retry` form);
    - rename forms `form[data-settings-rename]` inside a pane carrying `data-merge`;
    - the import form `form[data-settings-drop]`;
    - Save buttons `[data-nojs]`;
    - close link `a[data-close]` (href `/`).
  - Sidebar:
    - `<kbd class="key mono js-only">1</kbd>` (2, 3) in the sections;
    - foot `<button type="button" class="foot-link js-only" data-modal="keys">` and `<a href="/settings" class="foot-link" data-modal="settings">` with the batch counter.
  - `html.js` set by `layout.js`, and `html:not(.js) .js-only { display: none !important; }`.

- [ ] **Step 1: Write the failing tests**

`tests/test_web_settings_tabs.py`:

```python
"""Settings as four panes (spec §3.1, §7, §8): one fragment for the page and
the modal, each pane its own form, Categories folded in, and the sidebar's
new foot."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.vault import rebuild_indexes, write_note
from oknowledge.web import app as module
from oknowledge.web.app import create_app

WEB = Path(__file__).resolve().parent.parent / "src" / "oknowledge" / "web"
TABS = ["motores", "idioma", "importar", "categorias"]


@pytest.fixture
def client(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    for id, category in (("a1", "Redes"), ("b2", "Cocina")):
        write_note(cfg, Note(id=id, url=f"https://e.com/{id}", title=id, category=category,
                             tags=[], type="article", source="e.com", saved="2026-10-03",
                             summary="s"), "es")
    rebuild_indexes(cfg, "es")
    return TestClient(create_app(cfg))


def shown(body):
    """{pane: visible} for every pane in the page."""
    return {m.group(1): m.group(2) is None
            for m in re.finditer(r'data-settings-pane="([a-z]+)"( hidden)?', body)}


def sidebar(body):
    return re.search(r'<aside class="sidebar".*?</aside>', body, re.S).group(0)


# --- the fragment ------------------------------------------------------------------

def test_the_panel_is_a_fragment_with_four_tabs(client):
    body = client.get("/settings/panel").text
    assert "<html" not in body and '<aside class="sidebar"' not in body
    assert re.findall(r'data-settings-tab="([a-z]+)"', body) == TABS
    assert shown(body) == {"motores": True, "idioma": False, "importar": False,
                           "categorias": False}


@pytest.mark.parametrize("tab", TABS)
def test_the_tab_asked_for_is_the_one_shown(client, tab):
    for path in (f"/settings/panel?tab={tab}", f"/settings?tab={tab}"):
        body = client.get(path).text
        assert [name for name, visible in shown(body).items() if visible] == [tab], path
        assert f'data-settings-tab="{tab}" class="on" aria-current="page"' in body, path


def test_a_tab_nobody_knows_is_engines(client):
    assert shown(client.get("/settings/panel?tab=nope").text)["motores"] is True


def test_the_page_is_the_same_fragment_with_the_sidebar(client):
    body = client.get("/settings?tab=categorias").text
    assert '<aside class="sidebar"' in body and 'data-settings-root' in body


def test_opening_the_panel_asks_no_engine_anything(client, monkeypatch):
    monkeypatch.setattr(module, "build_engine",
                        lambda *a, **k: pytest.fail("Settings asked an engine"))
    assert client.get("/settings/panel").status_code == 200


# --- each pane its own form ------------------------------------------------------------

def test_each_pane_saves_on_its_own_with_a_save_button_without_js(client):
    body = client.get("/settings/panel").text
    forms = re.findall(r'<form action="/settings" method="post" data-settings[^>]*>.*?</form>',
                       body, re.S)
    assert len(forms) == 2
    assert 'name="tab" value="motores"' in forms[0] and 'name="chain"' in forms[0]
    assert 'name="tab" value="idioma"' in forms[1] and 'name="ui_language"' in forms[1]
    for form in forms:
        assert "data-nojs" in form


def test_the_action_buttons_post_their_own_forms(client):
    body = client.get("/settings/panel").text
    assert '<form id="find-opencode" action="/settings/models/opencode" method="post" data-settings-action>' in body


def test_language_and_saving_offers_the_handoff_rows(client):
    body = client.get("/settings/panel?tab=idioma").text
    for name in ("language", "ui_language", "default_content", "mentions"):
        assert f'type="radio" name="{name}"' in body, name
    assert 'type="number" name="batch"' in body
    for value in ("tools", "all", "discussed"):
        assert f'name="mentions" value="{value}"' in body


def test_import_offers_the_drop_and_the_batch(client):
    body = client.get("/settings/panel?tab=importar").text
    drop = re.search(r'<form action="/import"[^>]*>.*?</form>', body, re.S).group(0)
    assert 'enctype="multipart/form-data"' in drop and "data-settings-drop" in drop
    assert 'type="file" name="file"' in drop
    assert "Links waiting for analysis: 0" in body
    assert "Every link has been analysed." in body
    assert 'href="/retry"' in body


def test_a_running_batch_shows_its_count_instead_of_the_button(client):
    client.app.state.batch.start(3)
    body = client.get("/settings/panel?tab=importar").text
    assert "Analysing: 0/3" in body and 'action="/retry"' not in body


def test_categories_are_renamed_from_settings(client):
    body = client.get("/settings/panel?tab=categorias").text
    rows = re.findall(r'<form action="/categories/rename" method="post" class="cat-row" data-settings-rename>.*?</form>',
                      body, re.S)
    assert len(rows) == 2
    assert any('name="old" value="Redes"' in row and 'name="new" value="Redes"' in row
               for row in rows)
    assert 'data-merge="Merge «%1» into «%2»?"' in body


def test_the_categories_page_moved_into_settings(client):
    answer = client.get("/categories", follow_redirects=False)
    assert answer.status_code == 303
    assert answer.headers["location"] == "/settings?tab=categorias"
    assert not (WEB / "templates" / "categories.html").exists()


# --- the sidebar -------------------------------------------------------------------------

def test_the_foot_has_shortcuts_and_settings_only(client):
    side = sidebar(client.get("/").text)
    assert '<button type="button" class="foot-link js-only" data-modal="keys">' in side
    assert '<a href="/settings" class="foot-link" data-modal="settings">' in side
    assert 'href="/categories"' not in side and 'href="/retry"' not in side


def test_the_sections_show_their_keys(client):
    side = sidebar(client.get("/").text)
    for n in ("1", "2", "3"):
        assert f'<kbd class="key mono js-only">{n}</kbd>' in side


def test_settings_carries_the_batch_counter(client):
    client.app.state.batch.start(3)
    side = sidebar(client.get("/").text)
    assert re.search(r'data-modal="settings">Settings <b class="mono">0/3</b></a>', side)


def test_what_needs_javascript_is_hidden_without_it():
    css = (WEB / "static" / "app.css").read_text(encoding="utf-8")
    assert "html:not(.js) .js-only { display: none !important; }" in css
    assert 'classList.add("js")' in (WEB / "static" / "layout.js").read_text(encoding="utf-8")


def test_every_page_loads_the_settings_script(client):
    for path in ("/", "/ocio", "/ideas", "/settings", "/retry"):
        assert '<script src="/static/settings.js" defer></script>' in client.get(path).text, path
```

- [ ] **Step 2: Run them to see them fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_settings_tabs.py`
Expected: FAIL — `/settings/panel` is a 404, there is no `data-settings-tab`, and `/categories` answers 200.

- [ ] **Step 3: The server**

Replace `category_page`:

```python
    @app.get("/categories")
    def category_page():
        """Renaming lives in Settings now (spec §3.1): an old bookmark lands there."""
        return RedirectResponse("/settings?tab=categorias", status_code=303)
```

Replace `settings_page` with:

```python
    def settings_context(tab: str) -> dict:
        """What Settings draws, on the page and in the modal (spec §3.1): one
        function, so the two cannot drift apart."""
        saved = current["cfg"]
        library.refresh()
        order = [name for name in saved.chain if name in WEB_ENGINES]
        order += [name for name in WEB_ENGINES if name not in order]
        waiting = len(owed(Queue())[0])
        api = saved.engines.get("api", {})
        known = find_provider(str(api.get("provider", "anthropic")))
        return {"tab": tab if tab in dict(SETTINGS_TABS) else "motores",
                "tabs": SETTINGS_TABS, "cfg": saved, "ui": ui_language(),
                "engines": order, "config_path": config_file(),
                # The whole table, every row a choice: the addresses are the
                # point. Picking a provider should teach you what you are
                # pointing at, and where its key comes from.
                "providers": PROVIDERS, "picked": known.id if known else "",
                "keys": provider_keys(),
                # A provider somebody wrote by hand that this does not know.
                # Said out loud rather than quietly unticked.
                "stranger": "" if known else str(api.get("provider", "")),
                "by_hand": str(api.get("base_url", "")), "key": env_file_state(),
                # Read from disk, never asked for here: three engines with
                # their timeouts is up to twelve seconds to open Settings, and
                # the slow case -- a server that is down -- is the common one.
                "models": read_models(),
                # What "Analizar" would do: the saved size unless fewer links
                # than that are left.
                "owed": waiting, "size": min(saved.batch, waiting),
                # Both language pickers are built from this one order (they
                # once drifted into opposite orders).
                "languages": LANGUAGES, "language_names": NATIVE_NAMES,
                "categories": library.categories()}

    @app.get("/settings", response_class=HTMLResponse)
    def settings_page(request: Request, tab: str = ""):
        return page(request, "settings.html", **settings_context(tab))

    @app.get("/settings/panel", response_class=HTMLResponse)
    def settings_panel(request: Request, tab: str = ""):
        """Settings without the page around it, for the modal (spec §3.1)."""
        language = ui_language()
        return templates.TemplateResponse(
            request=request, name="settings-body.html",
            context={"t": translator(language), "lang": language,
                     "batch": progress.snapshot(), **settings_context(tab)})
```

Delete `src/oknowledge/web/templates/categories.html`.

- [ ] **Step 4: The fragment**

`src/oknowledge/web/templates/settings.html`:

```html
{% extends "base.html" %}
{% block title %}{{ t('Settings') }} - oknowledge{% endblock %}
{% block main %}{% include "settings-body.html" %}{% endblock %}
```

`src/oknowledge/web/templates/settings-body.html`:

```html
{# Settings (spec §3.1): the page /settings and the modal draw this same
   fragment. Four panes; only the one in `tab` is shown. Without JavaScript
   the tabs are links that reload and each form keeps its Save button;
   settings.js switches panes in place and saves every change. #}
<div class="settings-body" data-settings-root>
  <header class="settings-head">
    <div>
      <h1 class="settings-title">{{ t('Settings') }}</h1>
      <p class="settings-note">{{ t('The changes save themselves') }}</p>
    </div>
    <a class="btn icon settings-close" href="/" data-close aria-label="{{ t('Close') }}" title="{{ t('Close') }}">✕</a>
  </header>
  <nav class="settings-tabs" aria-label="{{ t('Settings') }}">
    {%- for key, label in tabs %}
    <a href="/settings?tab={{ key }}" data-settings-tab="{{ key }}" class="{% if key == tab %}on{% endif %}"{% if key == tab %} aria-current="page"{% endif %}>{{ t(label) }}</a>
    {%- endfor %}
  </nav>
  <div class="settings-scroll">

  <section class="settings-pane" data-settings-pane="motores"{% if tab != 'motores' %} hidden{% endif %}>
    <form action="/settings" method="post" data-settings>
      <input type="hidden" name="tab" value="motores">
      <p class="settings-hint">{{ t('They are used in order, top to bottom. You can put several models separated by commas.') }}</p>
      {% for name in engines %}
        <div class="row engine-row">
          <input type="checkbox" name="chain" value="{{ name }}" id="chain-{{ name }}"{% if name in cfg.chain %} checked{% endif %}>
          <label for="chain-{{ name }}" class="engine-name mono">{{ name }}</label>
          {# A box and not a <select>: an engine that is not installed, not
             running or behind somebody else's gateway cannot be asked, and
             that must not be the day you cannot name your model. It holds
             the models in the order they are tried, by comma. #}
          <input name="{{ name }}_model" placeholder="model" class="model-box"
                 aria-label="{{ name }} model"
                 value="{{ cfg.engines.get(name, {}).get('model', '') }}">
          <span class="engine-tools">
            {# What the engine said it has, as a picker that adds to the box
               and saves. Hidden until settings.js shows it. #}
            {% if models.get(name, {}).get('found') %}
              <select class="add-model" data-for="{{ name }}_model" aria-label="{{ t('Add a model') }}" hidden>
                <option value="">{{ t('Add a model…') }}</option>
                {% for found in models[name]['found'] %}<option value="{{ found }}">{{ found }}</option>{% endfor %}
              </select>
            {% endif %}
            {# Its own form, declared after this one: a form cannot nest, and
               this press must not save the box half-typed. #}
            <button type="submit" form="find-{{ name }}" class="link-button">{{ t('Find models') }}</button>
            {% if models.get(name, {}).get('at') %}<span class="meta">{{ t('Looked up %1', models[name]['at']) }}</span>{% endif %}
          </span>
        </div>
      {% endfor %}
      {# Outside the api block: who else can read the .env matters whatever
         engine is ticked (spec §3.1, "sigue siempre visible"). #}
      {% if key.exposed %}
        <p class="warn-block">{{ t('Anyone else with an account on this machine can read %1. Make it yours alone with chmod 600.', key.file) }}</p>
      {% endif %}
      {# Shown only while the api box above is ticked, by a CSS rule on the
         form: the providers mean nothing to the other engines. #}
      <div class="api-only">
      <h2 class="settings-sub">{{ t('Who the api engine talks to') }}</h2>
      {% if 'api' not in cfg.chain %}
        <p class="meta">{{ t('The api engine is not ticked above, so none of this is in use yet.') }}</p>
      {% endif %}
      {% if stranger %}
        <p class="meta">{{ t('config.toml names a provider this list does not have: %1. Saving will not replace it.', stranger) }}</p>
      {% endif %}
      {% if by_hand %}
        <p class="meta">{{ t('config.toml sends this engine to %1 by hand, and that address wins over the list.', by_hand) }}</p>
      {% endif %}
      <ul class="providers">
        {% for p in providers %}
          <li>
            {# The radio, the name and the detail are three children of the
               row and not nested: `:checked ~` only reaches a sibling. #}
            <input type="radio" name="api_provider" value="{{ p.id }}"
                   id="provider-{{ p.id }}"{% if p.id == picked %} checked{% endif %}>
            <label class="who" for="provider-{{ p.id }}"><b>{{ p.label }}</b>{% if p.id == picked %}<span class="tag">{{ t('in use') }}</span>{% endif %}{% if p.free %}<span class="tag">{{ t('free key') }}</span>{% endif %}</label>
            <div class="detail">
              <code>{{ p.url }}</code>
              <p class="meta">{{ keys[p.id].name }} · <a href="{{ p.console }}" target="_blank" rel="noreferrer">{{ t('get a key') }}</a>{% if p.note %} · {{ t(p.note) }}{% endif %}</p>
              {% if keys[p.id].ok %}
                <p class="meta">{{ t('The key for %1 is in place.', keys[p.id].name) }}</p>
              {% else %}
                <p class="warn-block">{{ t('There is no key yet. Paste %1=… into %2', keys[p.id].name, key.file) }}
                  {% if not key.exists %}
                    <button type="submit" form="make-env-{{ p.id }}">{{ t('Create that file') }}</button>
                  {% endif %}
                </p>
              {% endif %}
            </div>
          </li>
        {% endfor %}
      </ul>
      </div>
      <details class="where">
        <summary>{{ t('Where is this saved?') }}</summary>
        <p class="meta mono">{{ config_path }}</p>
        <p class="meta">{{ t('Saving rewrites %1 from scratch: your comments, your formatting and any key oknowledge does not read are not kept. The file it replaces is copied to config.toml.bak first.', config_path) }}</p>
      </details>
      <p data-nojs><button type="submit" class="btn">{{ t('Save') }}</button></p>
    </form>
    {% for name in engines %}
      <form id="find-{{ name }}" action="/settings/models/{{ name }}" method="post" data-settings-action></form>
    {% endfor %}
    {% if not key.exists %}
      {% for p in providers %}
        <form id="make-env-{{ p.id }}" action="/settings/env" method="post" data-settings-action><input type="hidden" name="provider" value="{{ p.id }}"></form>
      {% endfor %}
    {% endif %}
  </section>

  <section class="settings-pane" data-settings-pane="idioma"{% if tab != 'idioma' %} hidden{% endif %}>
    <form action="/settings" method="post" data-settings class="settings-rows">
      <input type="hidden" name="tab" value="idioma">
      <div class="setting">
        <div><p class="setting-name">{{ t('Summary language') }}</p></div>
        <span class="seg">{% for code in languages %}<label><input type="radio" name="language" value="{{ code }}"{% if cfg.language == code %} checked{% endif %}><span>{{ language_names[code] }}</span></label>{% endfor %}</span>
      </div>
      <div class="setting">
        <div><p class="setting-name">{{ t('Interface language') }}</p>
          <p class="setting-hint">{{ t('Shared with your other Omarchy plugins') }} · {{ t('Changing it reloads the page') }}</p></div>
        <span class="seg">{% for code in languages %}<label><input type="radio" name="ui_language" value="{{ code }}"{% if ui == code %} checked{% endif %}><span>{{ language_names[code] }}</span></label>{% endfor %}</span>
      </div>
      <div class="setting">
        <div><p class="setting-name">{{ t('Keep by default') }}</p>
          <p class="setting-hint">{{ t('What is marked when you paste a link') }}</p></div>
        <span class="seg">{% for value, label in (('full', t('Full')), ('summary', t('Summary'))) %}<label><input type="radio" name="default_content" value="{{ value }}"{% if cfg.default_content == value %} checked{% endif %}><span>{{ label }}</span></label>{% endfor %}</span>
      </div>
      <div class="setting">
        <div><p class="setting-name">{{ t('Mentions of a video') }}</p></div>
        <span class="seg">{% for value, label in (('tools', t('Tools')), ('all', t('All')), ('discussed', t('Only what it discusses'))) %}<label><input type="radio" name="mentions" value="{{ value }}"{% if cfg.mentions == value %} checked{% endif %}><span>{{ label }}</span></label>{% endfor %}</span>
      </div>
      <div class="setting">
        <div><p class="setting-name">{{ t('Links to analyse at a time') }}</p>
          <p class="setting-hint">{{ t('How many each batch takes') }}</p></div>
        <input type="number" name="batch" min="1" step="1" value="{{ cfg.batch }}" class="batch-box mono"
               aria-label="{{ t('Links to analyse at a time') }}">
      </div>
      <p data-nojs><button type="submit" class="btn">{{ t('Save') }}</button></p>
    </form>
  </section>

  <section class="settings-pane" data-settings-pane="importar"{% if tab != 'importar' %} hidden{% endif %}>
    {# The /import form of import.html: the preview and the confirmation
       stay on that page (spec "¿Importar WhatsApp desde el modal?"). #}
    <form action="/import" method="post" enctype="multipart/form-data" class="drop" data-settings-drop>
      <p class="drop-title">{{ t('Drop the WhatsApp export here') }}</p>
      <p class="meta">{{ t('In WhatsApp: open the chat, Export chat, Without media. Give it the .zip or the .txt inside it.') }}</p>
      <label class="btn">{{ t('Choose file') }}<input type="file" name="file" accept=".txt,.zip,text/plain,application/zip" required class="drop-file"></label>
      <button type="submit" class="btn" data-nojs>{{ t('Read it') }}</button>
    </form>
    <div class="setting">
      <p class="setting-name">{{ t('Links waiting for analysis: %1', owed) }}</p>
      {% if batch.running %}
        <span class="mono">{{ t('Analysing: %1/%2', batch.done, batch.total) }}</span>
      {% elif owed %}
        <form action="/retry" method="post" data-settings-action>
          <button type="submit" class="btn">{% if size == 1 %}{{ t('Analyse 1 link') }}{% else %}{{ t('Analyse %1 links', size) }}{% endif %}</button>
        </form>
      {% else %}
        <span class="meta">{{ t('Every link has been analysed.') }}</span>
      {% endif %}
    </div>
    <p><a href="/retry">{{ t('See activity') }} →</a></p>
  </section>

  <section class="settings-pane" data-settings-pane="categorias"{% if tab != 'categorias' %} hidden{% endif %}
           data-merge="{{ t('Merge «%1» into «%2»?') }}">
    {% if categories %}
      <ul class="cat-rows">
        {% for name, count in categories.items() %}
          <li>
            <form action="/categories/rename" method="post" class="cat-row" data-settings-rename>
              <i class="dot" style="background: {{ name|dot }}"></i>
              <input type="hidden" name="old" value="{{ name }}">
              <input name="new" value="{{ name }}" required autocomplete="off"
                     aria-label="{{ t('Rename') }}: {{ name }}">
              <b class="count mono">{{ count }}</b>
              <button type="submit" class="btn" data-nojs>{{ t('Save') }}</button>
            </form>
          </li>
        {% endfor %}
      </ul>
      <p class="settings-hint">{{ t('If you rename to one that already exists, they merge.') }}</p>
    {% else %}
      <p class="empty">{{ t('Nothing saved yet') }}</p>
    {% endif %}
  </section>

  </div>
</div>
```

- [ ] **Step 5: The sidebar, the base page and the scripts**

In `sidebar.html`, each section link ends with its key:

```html
        <span>{{ name }}</span><b class="count mono">{{ side.counts[key] }}</b><kbd class="key mono js-only">{{ loop.index }}</kbd></a>
```

and the foot becomes:

```html
  <nav class="foot">
    <button type="button" class="foot-link js-only" data-modal="keys">{{ t('Shortcuts') }} <kbd class="key mono">?</kbd></button>
    <a href="/settings" class="foot-link" data-modal="settings">{{ t('Settings') }}{% if batch.running %} <b class="mono">{{ batch.done }}/{{ batch.total }}</b>{% elif batch.busy %} <b class="mono">{{ batch.busy|length }}</b>{% endif %}</a>
  </nav>
```

In `base.html`, after `<script src="/static/layout.js"></script>`:

```html
  <script src="/static/settings.js" defer></script>
```

(`settings.js` keeps its picker code until Task 8. `requestSubmit()` now posts the Engines pane, with its `tab`, and comes back to `/settings?tab=motores`.)

At the top of the function in `layout.js`, right after `"use strict";`:

```js
  // What only works with JavaScript (checkboxes, key hints, "Atajos") is
  // drawn hidden and shown by this class (spec §1).
  document.documentElement.classList.add("js");
```

In `style.css`, delete the `.cat-grid`, `.cat-name` and `.cat-card` rules and their media query (≈257–271). Append to `app.css`:

```css
/* --- delivery 3: what needs JavaScript, and the keys ------------------- */
html:not(.js) .js-only { display: none !important; }
.key { display: inline-block; min-width: 16px; padding: 0 4px; border: 1px solid var(--b-input);
  border-radius: 4px; font-size: 10px; line-height: 16px; text-align: center; color: var(--t6); }
.sidebar .foot { display: flex; flex-direction: column; gap: 2px; }
.sidebar .foot-link { display: flex; align-items: center; gap: 8px; padding: 7px 10px; border-radius: 8px;
  color: var(--t5); background: none; border: 0; font: inherit; font-size: 13px; text-align: left;
  cursor: pointer; text-decoration: none; }
.sidebar .foot-link:hover { background: var(--s5); color: var(--t1); }
.sidebar .foot-link b { margin-left: auto; color: var(--t6); font-weight: 400; font-size: 12px; }

/* --- Settings (spec §3.1; handoff §4) ----------------------------------- */
.settings-body { display: flex; flex-direction: column; min-height: 0;
  line-height: normal; font-size: 13.5px; color: var(--t2); }
.settings-head { display: flex; align-items: flex-start; justify-content: space-between;
  padding: 18px 24px 0; }
.settings-title { font-size: 17px; font-weight: 600; margin: 0; color: var(--t1); }
.settings-note { font-size: 12px; color: #6d6f78; margin: 4px 0 0; }
.settings-tabs { display: flex; gap: 20px; padding: 14px 24px 0; border-bottom: 1px solid var(--b-input); }
.settings-tabs a { padding: 0 0 10px; margin-bottom: -1px; color: var(--t5); text-decoration: none;
  border-bottom: 2px solid transparent; }
.settings-tabs a.on { color: var(--t1); border-bottom-color: #e7e7ea; }
.settings-scroll { flex: 1; min-height: 0; overflow-y: auto; }
.settings-pane { display: flex; flex-direction: column; gap: 18px; padding: 20px 24px; }
.settings-pane[hidden] { display: none; }
.settings-pane form[data-settings] { display: flex; flex-direction: column; gap: 18px; }
.settings-hint, .setting-hint { font-size: 12px; color: #6d6f78; margin: 0; }
.settings-sub { font-size: 13px; font-weight: 500; color: var(--t1); margin: 0; }
.settings-pane input:not([type=checkbox]):not([type=radio]):not([type=file]),
.settings-pane select { background: #141519; border: 1px solid var(--b-input); border-radius: 8px;
  color: var(--t1); padding: 7px 10px; font: inherit; font-size: 13px; min-width: 0; }
.settings-pane .engine-row { display: grid; grid-template-columns: 20px 90px minmax(0, 1fr) auto;
  align-items: center; gap: 10px; padding: 0; }
.settings-pane .engine-tools { display: flex; align-items: center; gap: 8px; }
.link-button { background: none; border: 0; padding: 0; color: var(--acc); font: inherit;
  font-size: 12.5px; cursor: pointer; }
.link-button:hover { color: var(--acc-hi); }
.setting { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.setting-name { margin: 0; color: var(--t1); }
.settings-pane .seg { background: #141519; }
.batch-box { width: 60px; }
.drop { position: relative; border: 1.5px dashed #33353e; border-radius: 12px; padding: 30px;
  text-align: center; display: flex; flex-direction: column; align-items: center; gap: 10px; }
.drop.over { border-color: var(--b-sel); background: var(--s2); }
.drop-title { margin: 0; color: var(--t1); font-weight: 500; }
.drop-file { position: absolute; width: 1px; height: 1px; opacity: 0; }
.cat-rows { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.cat-row { display: grid; grid-template-columns: 8px minmax(0, 1fr) auto auto; align-items: center; gap: 10px; }
.where summary { cursor: pointer; color: var(--t5); font-size: 12.5px; }
```

- [ ] **Step 6: Spanish**

In `i18n.py` `STRINGS["es"]` add:

```python
        # Settings in panes, and the sidebar's foot (delivery 3, spec §3, §7).
        "The changes save themselves": "Los cambios se guardan solos",
        "They are used in order, top to bottom. You can put several models "
        "separated by commas.":
            "Se usan en orden, de arriba hacia abajo. Podés poner varios modelos "
            "separados por coma.",
        "Where is this saved?": "¿Dónde se guarda esto?",
        "Shared with your other Omarchy plugins": "Compartido con tus otros plugins de Omarchy",
        "Changing it reloads the page": "Cambiarlo recarga la página",
        "What is marked when you paste a link": "Lo que se marca al pegar un link",
        "Tools": "Herramientas",
        "How many each batch takes": "Cuántos procesa cada tanda",
        "Drop the WhatsApp export here": "Soltá acá el export de WhatsApp",
        "Choose file": "Elegir archivo",
        "Links waiting for analysis: %1": "Links esperando análisis: %1",
        "Analysing: %1/%2": "Analizando: %1/%2",
        "See activity": "Ver actividad",
        "If you rename to one that already exists, they merge.":
            "Si renombrás a una que ya existe, se unen.",
        "Merge «%1» into «%2»?": "¿Unir «%1» con «%2»?",
        "Shortcuts": "Atajos",
```

and change `"Only what it discusses": "Sólo lo que discute"` to `"Only what it discusses": "Sólo lo discutido"`.

Then run `tests/test_i18n.py` and delete every key it reports as "declared and never asked for". These are the strings of the old Settings and Categories pages, the sidebar's "Activity", "Tools and companies" and "Everything named". Expected, at least:
- "Tools and companies", "Everything named";
- "Priority runs top to bottom…", "Several models go by comma…", "Looking for models asks…", "What is marked in use is what is saved…";
- "Shared with my other Omarchy plugins, so this changes all of them at once.";
- "What the button at the end of this page…", "How many", "Analyse the links that are waiting", "As many as the box above says…", "Turns the links people shared…";
- "Renaming into a category that already exists merges the two.", "Merge into", "Activity".

Delete only what the test lists.

- [ ] **Step 7: The ledger**

- `tests/test_web_sidebar.py:40`: `assert 'href="/settings"' in side and 'href="/categories"' not in side and 'href="/retry"' not in side`.
- `tests/test_web_retry.py:268`: `assert "Links waiting for analysis: 4" in body`.
- `tests/test_web_retry.py:433-439`: replace the test with

```python
@pytest.mark.parametrize("path", ["/settings", "/settings/panel?tab=importar"])
def test_activity_is_reached_from_settings(setup, path):
    """It left the sidebar (spec §7): Settings → Import links it."""
    cfg, client = setup

    assert 'href="/retry"' in client.get(path).text
```

- `tests/test_web_activity.py:85-86`: replace the test with

```python
def test_the_nav_reaches_activity_through_settings(cfg):
    body = TestClient(create_app(cfg)).get("/settings?tab=importar").text
    assert 'href="/retry"' in body
```

- `tests/test_web_layout.py`: delete `test_categories_are_a_grid_not_rows` and `test_each_category_renames_from_its_own_card`, and the `# --- the categories page` header above them.
- `tests/test_web_settings.py:607-608`: `assert "used in order, top to bottom" in client.get("/settings").text`.

- [ ] **Step 8: Run the new tests and the ledger**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_settings_tabs.py tests/test_web_settings.py tests/test_web_sidebar.py tests/test_web_retry.py tests/test_web_activity.py tests/test_web_layout.py tests/test_web_write.py tests/test_web_cards.py tests/test_i18n.py`
Expected: PASS.

- [ ] **Step 9: Whole suite, commit**

Run the suite; expected green.

```bash
git add -A src/oknowledge tests/test_web_settings_tabs.py tests/test_web_sidebar.py tests/test_web_retry.py \
        tests/test_web_activity.py tests/test_web_layout.py tests/test_web_settings.py
git commit -m "Draw Settings as four panes from one fragment, fold Categories in, and give the sidebar its new foot"
```

(`git add -A src/oknowledge` records the deleted `categories.html`; check `git status` first that nothing else under `src/` is staged by surprise.)

---
### Task 7: app.js — one toast, the menus, the shortcuts help and the global keys

**Files:**
- Create: `src/oknowledge/web/static/app.js`
- Modify:
  - `src/oknowledge/web/app.py`: module-level `KEYS_HELP`; in `create_app`, `templates.env.globals["KEYS_HELP"]` (≈720).
  - `src/oknowledge/web/templates/base.html`: `data-undo`, the `#keys-help` dialog, and `app.js` first.
  - `data-slash` on `home.html`, `ocio-shelf.html` and `idea-shelf.html` (`#field-q`) and on `idea.html` (`#links-q`).
  - `src/oknowledge/web/static/shell.js`: its toast delegates; the menus block (≈399–421) goes.
  - `src/oknowledge/web/static/autosave.js`: its toast delegates; it extends `window.oknowledge`.
  - `src/oknowledge/web/static/app.css`: modals and the keys grid.
  - `src/oknowledge/i18n.py`.
- Create (scratch, not committed): `$SP/shots/serve3.py`, `$SP/pw/t7.js`
- Test: `tests/test_web_app_js.py` (new); ledger `tests/test_web_shell_js.py:47-49` (`"Escape"` leaves shell.js), `tests/test_packaging.py:95` (`app.js` joins the node check)

**Interfaces:**
- Consumes: `#toast` and its `form.toast-undo` (Task 3); `[data-modal]` in the sidebar foot (Task 6).
- Produces — `window.oknowledge`, created by `app.js`; later scripts add to it and never replace it:
  - `toast(text, {action, run, ms})` — one element `#toast`, class `live`, 2200 ms or 5000 ms with an action; a new toast replaces the last.
  - `send(url, formData) -> Promise<body>` — POST with `Accept: application/json`; it rejects with an `Error` whose `message` is the server's words and whose `status` is the HTTP status.
  - `undo(token, then?)` — `POST /undo/{token}`, toasts its notice, then calls `then(body)`, or `oknowledge.list.reload(firstRestoredId)`, or reloads the page.
  - `offerUndo(text, token, then?)` — a toast with "Deshacer" when there is a token, else a plain toast.
  - `closeMenus() -> bool` (true if one was open) and `openModal(dialog)`.
  - `keys` — `{key: fn}`. `fn(event)` returning `false` means "not handled" (no `preventDefault`).
- Global keys:
  - `/` focuses `[data-slash]`; `1` `2` `3` go to `/`, `/ocio`, `/ideas`; `?` toggles `#keys-help`.
  - Esc runs its chain: open modal (native) → menus → blur a field → `keys.Escape`.
  - Rules: Cmd, Ctrl or Alt means nothing; in a field only Esc works; with a modal open only Esc works (and `?` in the help); Enter on a link, button or summary is left alone.
- `KEYS_HELP` — 11 rows of `(keys tuple, text)`.

- [ ] **Step 1: Write the failing tests**

`tests/test_web_app_js.py`:

```python
"""app.js (spec §1-§4): the one toast, the menus, the two modals and the keys,
on every page. The key rules run in node over a fake page (Review Focus 3:
nothing typed into a field or a modal ever moves the list or the page)."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.model import Note
from oknowledge.vault import note_path, rebuild_indexes, write_note
from oknowledge.web.app import create_app

STATIC = Path(__file__).resolve().parent.parent / "src" / "oknowledge" / "web" / "static"
APP = STATIC / "app.js"


@pytest.fixture
def client(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    write_note(cfg, Note(id="a1", url="https://e.com/a1", title="A", category="Redes", tags=[],
                         type="article", source="e.com", saved="2026-10-03", summary="s"), "es")
    idea = new_idea("Una idea.", "Idea", "2026-10-13", "2026-10-13T00:00:00.000001+00:00")
    write_note(cfg, idea, "es", path=note_path(cfg, idea, shelf=cfg.ideas))
    for shelf in (cfg.links, cfg.ideas):
        rebuild_indexes(cfg, "es", shelf=shelf)
    client = TestClient(create_app(cfg))
    client.idea = idea.id
    return client


def between(text, start, end):
    head = text.index(start)
    return text[head:text.index(end, head)]


# --- the page -------------------------------------------------------------------

@pytest.mark.parametrize("path", ["/", "/ocio", "/ideas", "/settings", "/retry", "/import", "idea"])
def test_every_page_loads_app_js_before_the_others(client, path):
    body = client.get(f"/ideas/{client.idea}" if path == "idea" else path).text
    first = body.index('<script src="/static/app.js" defer></script>')
    for name in re.findall(r'<script src="/static/([a-z]+)\.js" defer></script>', body):
        if name != "app":
            assert first < body.index(f'<script src="/static/{name}.js" defer></script>'), name


def test_the_keys_help_is_on_every_page_with_its_eleven_rows(client):
    body = client.get("/").text
    found = re.search(r'<dialog id="keys-help" class="modal keys".*?</dialog>', body, re.S).group(0)
    assert found.count("<dt>") == 11
    for text in ("Keyboard shortcuts", "Search or paste a link", "Library · Leisure · Ideas",
                 "Open the original link", "Close / deselect"):
        assert text in found
    assert '<kbd class="mono">1</kbd><kbd class="mono">2</kbd><kbd class="mono">3</kbd>' in found
    assert '<kbd class="mono">esc</kbd>' in found


def test_the_body_carries_the_undo_word(client):
    assert 'data-undo="Undo"' in client.get("/").text


@pytest.mark.parametrize("path", ["/", "/ocio", "/ideas"])
def test_the_unified_field_answers_to_the_slash(client, path):
    assert re.search(r'<input type="text" name="q" id="field-q"[^>]*data-slash', client.get(path).text)


def test_on_an_idea_the_slash_goes_to_the_links_search(client):
    assert re.search(r'id="links-q"[^>]*data-slash', client.get(f"/ideas/{client.idea}").text)


# --- the source --------------------------------------------------------------------

def test_the_toast_is_one_element_timed_here():
    text = APP.read_text(encoding="utf-8")
    body = between(text, "function toast", "function send")
    assert "replaceChildren" in body and "5000" in body and "2200" in body
    assert 'getElementById("toast")' in text


def test_the_server_toast_is_taken_over_and_its_undo_sent_as_json():
    text = APP.read_text(encoding="utf-8")
    assert "form.toast-undo" in text and '"/undo/"' in text
    assert 'Accept: "application/json"' in text


def test_menus_close_each_other_and_modals_open_with_show_modal():
    text = APP.read_text(encoding="utf-8")
    assert '"toggle"' in text and "details.menu" in text
    assert "showModal" in text and "[data-modal]" in text and '"keys-help"' in text


def test_shell_and_autosave_no_longer_draw_their_own_toast():
    for name in ("shell.js", "autosave.js"):
        assert 'className = "notice toast"' not in (STATIC / name).read_text(encoding="utf-8"), name
    shell = (STATIC / "shell.js").read_text(encoding="utf-8")
    assert 'addEventListener("toggle"' not in shell
    autosave = (STATIC / "autosave.js").read_text(encoding="utf-8")
    assert "window.oknowledge = {" not in autosave
    assert "window.oknowledge || (window.oknowledge = {})" in autosave


# --- the key rules, in node ------------------------------------------------------------

HARNESS = r"""
const source = require("fs").readFileSync(process.argv[2], "utf8");
const handlers = {};
const out = {};
let dialog = null;
const field = (type) => ({ tagName: "INPUT", type, isContentEditable: false, closest: () => null,
                           blur() { out.blurred = (out.blurred || 0) + 1; } });
global.window = global;
global.location = { href: "/", pathname: "/", reload() {} };
global.document = {
  body: { dataset: {}, tagName: "BODY" },
  addEventListener: (type, fn) => { (handlers[type] = handlers[type] || []).push(fn); },
  getElementById: () => null,
  querySelector: (sel) => (sel === "dialog[open]" ? dialog : null),
  querySelectorAll: () => [],
};
document.activeElement = document.body;
eval(source);
const calls = [];
window.oknowledge.keys.j = () => { calls.push("j"); };
window.oknowledge.keys.Escape = () => { calls.push("esc"); };
function press(key, extra) {
  const event = Object.assign({ key, defaultPrevented: false, isComposing: false, metaKey: false,
    ctrlKey: false, altKey: false, shiftKey: false,
    preventDefault() { this.defaultPrevented = true; } }, extra || {});
  (handlers.keydown || []).forEach((fn) => fn(event));
  return event;
}
press("j"); out.plain = calls.slice();
press("j", { ctrlKey: true }); press("j", { metaKey: true }); press("j", { altKey: true });
out.modifiers = calls.slice();
document.activeElement = field("text");
press("j"); press("1"); out.inField = [calls.slice(), location.href];
press("Escape"); out.escInField = [out.blurred, calls.slice()];
document.activeElement = field("checkbox");
press("j"); out.onCheckbox = calls.slice();
dialog = { id: "settings-modal", close() {} };
document.activeElement = field("text");
press("j"); press("1"); press("x");
document.activeElement = document.body;
press("j"); press("2"); out.inModal = [calls.slice(), location.href];
dialog = { id: "keys-help", close() { out.helpClosed = true; } };
press("?");
dialog = null;
document.activeElement = document.body;
press("Escape"); out.escClears = calls.slice();
press("3"); out.section = location.href;
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def keys(tmp_path_factory):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    harness = tmp_path_factory.mktemp("keys") / "harness.js"
    harness.write_text(HARNESS, encoding="utf-8")
    done = subprocess.run([node, str(harness), str(APP)], capture_output=True, text=True,
                          timeout=30, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_a_key_the_screen_registered_runs(keys):
    assert keys["plain"] == ["j"]


def test_cmd_ctrl_or_alt_mean_nothing(keys):
    assert keys["modifiers"] == ["j"]


def test_in_a_field_keys_are_text_and_esc_only_blurs(keys):
    assert keys["inField"] == [["j"], "/"]
    assert keys["escInField"] == [1, ["j"]]


def test_a_checkbox_is_not_a_field(keys):
    assert keys["onCheckbox"] == ["j", "j"]


def test_with_a_modal_open_no_key_reaches_the_page(keys):
    assert keys["inModal"] == [["j", "j"], "/"]
    assert keys["helpClosed"] is True


def test_esc_with_nothing_else_to_do_clears_the_selection(keys):
    assert keys["escClears"] == ["j", "j", "esc"]


def test_the_number_keys_go_to_the_sections(keys):
    assert keys["section"] == "/ideas"
```

- [ ] **Step 2: Run them to see them fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_app_js.py`
Expected: FAIL. There is no `app.js` (the module fixture's node run fails), no `#keys-help`, no `data-slash`, and `shell.js` still has its toast.

- [ ] **Step 3: `app.js`**

`src/oknowledge/web/static/app.js`:

```js
// What every page shares (docs/2026-10-14-rediseno-modales-teclado-design.md
// §1-§4): the one toast, the menus, the two modals and the keys. Loaded
// first of the deferred scripts, so the others find window.oknowledge here
// and add their parts to it. Without this file every page still works: the
// server's toast hides itself, menus are <details>, "Ajustes" is a link.
(function () {
  "use strict";
  var ok = window.oknowledge || (window.oknowledge = {});
  var texts = document.body.dataset;
  ok.keys = ok.keys || {};

  // --- the toast (spec §2) ------------------------------------------------------
  var timer = null;

  function box() { return document.getElementById("toast"); }

  function hide() {
    clearTimeout(timer);
    var el = box();
    if (!el) return;
    el.hidden = true;
    el.replaceChildren();
  }

  // One at a time: a new toast replaces the last one, and its button.
  function toast(text, opts) {
    var el = box();
    if (!el || !text) return;
    opts = opts || {};
    clearTimeout(timer);
    el.classList.remove("undo");
    el.classList.add("live");
    var words = document.createElement("span");
    words.className = "toast-text";
    words.textContent = text;
    el.replaceChildren(words);
    if (opts.action && opts.run) {
      var button = document.createElement("button");
      button.type = "button";
      button.textContent = opts.action;
      button.addEventListener("click", function () { hide(); opts.run(); });
      el.appendChild(button);
    }
    el.hidden = false;
    timer = setTimeout(hide, opts.ms || (opts.action ? 5000 : 2200));
  }

  // A write, as JSON: the body of {"ok": true}, or an Error with the
  // server's words (or the page's "could not be saved") and the status.
  function send(url, data) {
    return fetch(url, { method: "POST", body: data || new FormData(),
                        headers: { Accept: "application/json" } })
      .then(function (r) {
        return r.json().catch(function () { return { ok: false }; }).then(function (body) {
          if (r.ok && body.ok) return body;
          var error = new Error(body.error || texts.saveFailed || "");
          error.status = r.status;
          throw error;
        });
      });
  }

  // Deshacer (spec §6.3). `then(body)` is the screen's own follow-up;
  // without one the list reloads on the first note back, or the page does.
  function undo(token, then) {
    return send("/undo/" + encodeURIComponent(token))
      .then(function (body) {
        toast(body.notice);
        if (then) then(body);
        else if (ok.list) ok.list.reload(body.restored && body.restored[0]);
        else location.reload();
      })
      .catch(function (error) { toast(error.message); });
  }

  function offerUndo(text, token, then) {
    if (!token) { toast(text); return; }
    toast(text, { action: texts.undo, run: function () { undo(token, then); } });
  }

  // --- menus (spec §1): one open at a time; a click outside or Esc closes ----
  function closeMenus() {
    var open = document.querySelectorAll("details.menu[open]");
    open.forEach(function (d) { d.open = false; });
    return open.length > 0;
  }

  document.addEventListener("toggle", function (event) {
    var opened = event.target;
    if (!opened.matches || !opened.matches("details.menu") || !opened.open) return;
    document.querySelectorAll("details.menu[open]").forEach(function (d) {
      if (d !== opened) d.open = false;
    });
  }, true);

  document.addEventListener("click", function (event) {
    if (!event.target.closest("details.menu")) closeMenus();
  });

  // --- the modals (spec §3) ------------------------------------------------------
  function openDialog() { return document.querySelector("dialog[open]"); }

  function openModal(dialog) {
    if (!dialog || dialog.open) return;
    closeMenus();
    dialog.showModal();
  }

  function toggleKeys() {
    var help = document.getElementById("keys-help");
    if (!help) return;
    if (help.open) help.close();
    else if (!openDialog()) openModal(help);
  }

  document.addEventListener("click", function (event) {
    var opener = event.target.closest("[data-modal]");
    if (opener && event.button === 0 && !event.metaKey && !event.ctrlKey &&
        !event.shiftKey && !event.altKey) {
      if (opener.dataset.modal === "keys") { event.preventDefault(); toggleKeys(); return; }
      // On /settings itself the link stays a link: the page is the settings.
      if (opener.dataset.modal === "settings" && ok.openSettings &&
          location.pathname !== "/settings") {
        event.preventDefault();
        ok.openSettings();
        return;
      }
    }
    var closer = event.target.closest("dialog [data-close]");
    if (closer) { event.preventDefault(); closer.closest("dialog").close(); return; }
    // A click on the backdrop lands on the <dialog> itself.
    if (event.target.matches && event.target.matches("dialog.modal[open]")) event.target.close();
  });

  // --- keys (spec §4) -----------------------------------------------------------------
  // Where a key is text, not a command. A checkbox or a radio is not typing:
  // with the focus on a ticked box, j, x and ⌫ still work.
  function typing(el) {
    if (!el || el === document.body) return false;
    if (el.isContentEditable) return true;
    var tag = el.tagName;
    if (tag === "TEXTAREA" || tag === "SELECT") return true;
    if (tag !== "INPUT") return false;
    return ["checkbox", "radio", "button", "submit", "reset", "file", "range", "color"]
      .indexOf(el.type) < 0;
  }

  var SECTIONS = { "1": "/", "2": "/ocio", "3": "/ideas" };

  document.addEventListener("keydown", function (event) {
    if (event.defaultPrevented || event.isComposing) return;
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    var key = event.key;
    var dialog = openDialog();
    if (dialog) {
      // The dialog closes itself on Esc; "?" also closes the help.
      if (key === "?" && dialog.id === "keys-help") { event.preventDefault(); dialog.close(); }
      return;
    }
    var active = document.activeElement;
    if (key === "Escape") {
      if (closeMenus()) return;
      if (typing(active)) { active.blur(); return; }
      if (ok.keys.Escape) ok.keys.Escape(event);
      return;
    }
    if (typing(active)) return;
    // Enter on a link, a button or a summary already does its own thing.
    if (key === "Enter" && active && active.closest && active.closest("a, button, summary")) return;
    if (key === "?") { event.preventDefault(); toggleKeys(); return; }
    if (key === "/") {
      var slash = document.querySelector("[data-slash]");
      if (slash) { event.preventDefault(); slash.focus(); if (slash.select) slash.select(); }
      return;
    }
    if (SECTIONS[key]) { event.preventDefault(); location.href = SECTIONS[key]; return; }
    var own = ok.keys[key];
    if (own && own(event) !== false) event.preventDefault();
  });

  ok.toast = toast;
  ok.send = send;
  ok.undo = undo;
  ok.offerUndo = offerUndo;
  ok.closeMenus = closeMenus;
  ok.openModal = openModal;

  // The toast the server drew after a redirect: taken over and timed here,
  // and its Deshacer sent as JSON (spec §2). Without this file it is a form.
  (function () {
    var el = box();
    if (!el || el.hidden) return;
    var form = el.querySelector("form.toast-undo");
    el.classList.add("live");
    timer = setTimeout(hide, form ? 5000 : 2200);
    if (!form) return;
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var token = decodeURIComponent((form.getAttribute("action") || "").split("/undo/")[1] || "");
      hide();
      undo(token);
    });
  })();
})();
```

- [ ] **Step 4: The help, the base page and the other scripts**

In `app.py`, after `ENGINE_ICONS`:

```python
KEYS_HELP = (
    (("/",), "Search or paste a link"),
    (("1", "2", "3"), "Library · Leisure · Ideas"),
    (("j", "k", "←", "→"), "Previous / next"),
    (("↑", "↓"), "Row up / down"),
    (("↵",), "Open the original link"),
    (("f",), "Favorite"),
    (("e",), "Add a tag"),
    (("x",), "Select"),
    (("⌫",), "Delete the selected"),
    (("v",), "List / cards"),
    (("esc",), "Close / deselect"),
)
"""The shortcuts help (spec §3.2), in its order: the keys and a t() key."""
```

and in `create_app`, beside `templates.env.globals["engines"]`: `templates.env.globals["KEYS_HELP"] = KEYS_HELP`.

In `base.html`:
- add ` data-undo="{{ t('Undo') }}"` to `<body>`, after `data-failed=…`;
- right after the `#toast` div:

```html
  {# The shortcuts help (spec §3.2): drawn on every page, opened by app.js
     with ? or "Atajos". Without JavaScript it never opens. #}
  <dialog id="keys-help" class="modal keys" aria-labelledby="keys-title">
    <div class="modal-head"><h2 id="keys-title">{{ t('Keyboard shortcuts') }}</h2>
      <button type="button" class="btn icon" data-close aria-label="{{ t('Close') }}" title="{{ t('Close') }}">✕</button></div>
    <dl class="keys-grid">
      {%- for combo, text in KEYS_HELP %}
      <dt>{% for key in combo %}<kbd class="mono">{{ key }}</kbd>{% endfor %}</dt><dd>{{ t(text) }}</dd>
      {%- endfor %}
    </dl>
  </dialog>
```

- the scripts become:

```html
  {# Not deferred: it has to fold the page before the first paint. #}
  <script src="/static/layout.js"></script>
  <script src="/static/app.js" defer></script>
  <script src="/static/settings.js" defer></script>
  {% block scripts %}{% endblock %}
```

Add ` data-slash` to `#field-q` in `home.html`, `ocio-shelf.html` and `idea-shelf.html` (after its `placeholder`), and to `#links-q` in `idea.html` (after `data-results`).

In `shell.js`, replace `function toast` with:

```js
  // The one toast is app.js's (spec §2).
  function toast(text) {
    var ok = window.oknowledge;
    if (text && ok && ok.toast) ok.toast(text);
  }
```

and replace the whole `// --- menus` block (the `toggle` listener, `closeMenus`, the click listener and the Escape `keydown`) with:

```js
  // --- menus ------------------------------------------------------------------
  // Their rule is app.js's now, on every page (one open at a time, a click
  // outside or Esc closes them); an inline write only closes them.
  function closeMenus() {
    var ok = window.oknowledge;
    if (ok && ok.closeMenus) ok.closeMenus();
  }
```

In `autosave.js`, replace `function toast` with the same delegating `toast` (comment "The one toast is app.js's (spec §2)."). Replace the last two lines (`window.oknowledge = {…}; bind(document);`) with:

```js
  // app.js made window.oknowledge (the toast, the menus, the keys); this
  // adds the saving. Never replaced: every script hangs its part on it.
  var ok = window.oknowledge || (window.oknowledge = {});
  ok.post = post;
  ok.bind = bind;
  ok.settle = settle;
  ok.dirty = dirty;
  bind(document);
```

Append to `app.css`:

```css
/* --- modals (spec §3; handoff §4-§5) ---------------------------------------- */
.modal { background: #1b1c21; border: 1px solid #2e3038; border-radius: 14px; color: var(--t2);
  padding: 0; box-shadow: var(--shadow); line-height: normal; }
.modal::backdrop { background: #0009; }
.modal-head { display: flex; align-items: center; justify-content: space-between; padding: 18px 22px 0; }
.modal-head h2 { margin: 0; font-size: 15px; font-weight: 600; color: var(--t1); }
.modal.keys { width: 420px; max-width: calc(100vw - 32px); }
.keys-grid { display: grid; grid-template-columns: auto 1fr; gap: 10px 18px; margin: 0;
  padding: 16px 22px 22px; font-size: 13px; align-items: center; }
.keys-grid dt { display: flex; gap: 4px; }
.keys-grid dd { margin: 0; color: var(--t3); }
.keys-grid kbd { display: inline-block; min-width: 18px; padding: 1px 5px; border: 1px solid #2a2b32;
  border-radius: 4px; font-size: 10px; text-align: center; color: var(--t2); }
```

In `i18n.py` add:

```python
        # The shortcuts help (delivery 3, spec §3.2).
        "Keyboard shortcuts": "Atajos de teclado",
        "Search or paste a link": "Buscar o pegar un link",
        "Library · Leisure · Ideas": "Biblioteca · Ocio · Ideas",
        "Previous / next": "Anterior / siguiente",
        "Row up / down": "Fila arriba / abajo",
        "Open the original link": "Abrir original",
        "Add a tag": "Agregar etiqueta",
        "Select": "Seleccionar",
        "Delete the selected": "Borrar seleccionados",
        "List / cards": "Lista / tarjetas",
        "Close / deselect": "Cerrar / deseleccionar",
```

Ledger:
- `tests/test_web_shell_js.py:47-49`: drop `"Escape"` from the parametrize list (it is `app.js`'s now and pinned above).
- `tests/test_packaging.py:95`: `["app.js", "autosave.js", "idea.js", "shell.js"]`.

- [ ] **Step 5: Run the tests**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_app_js.py tests/test_web_shell_js.py tests/test_packaging.py tests/test_web_autosave_settle.py tests/test_web_idea_scripts.py tests/test_web_ocio_scripts.py tests/test_i18n.py`
Expected: PASS. The autosave harness still works: it finds no `window.oknowledge`, creates one, and its failed save calls a `toast` that has no `ok.toast` to reach, which does nothing.

- [ ] **Step 6: Check it in a browser**

```bash
SP=/tmp/claude-1000/-home-fer-Projects-gym/d89ecc8a-2029-44cb-b47f-742ed00daeae/scratchpad
cat > "$SP/shots/serve3.py" <<'EOF'
"""Delivery 2's scratch server, in Spanish, with the shared language file in
the scratchpad instead of ~/.config/omarchy."""
import json
import runpy
from pathlib import Path

HERE = Path(__file__).parent
shared = HERE / "state" / "plugin-language.json"
shared.parent.mkdir(parents=True, exist_ok=True)
if not shared.exists():
    shared.write_text(json.dumps({"language": "es"}), encoding="utf-8")

import oknowledge.i18n as i18n  # noqa: E402

i18n.SHARED_FILE = shared
runpy.run_path(str(HERE / "serve.py"), run_name="__main__")
EOF
cat > "$SP/pw/t7.js" <<'EOF'
const { chromium } = require("playwright");
const fs = require("fs");
const BASE = "http://127.0.0.1:8812";
const IDEA = fs.readFileSync(process.argv[2], "utf8").trim();
(async () => {
  const browser = await chromium.launch({ executablePath: "/usr/bin/chromium" });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const out = {};
  const open = (id) => page.evaluate((id) => document.getElementById(id).open, id);
  await page.goto(BASE + "/");
  await page.keyboard.press("?"); out.helpByKey = await open("keys-help");
  await page.keyboard.press("Escape"); out.helpEsc = !(await open("keys-help"));
  await page.click('[data-modal="keys"]'); out.helpByFoot = await open("keys-help");
  await page.keyboard.press("?"); out.helpQuestionCloses = !(await open("keys-help"));
  await page.keyboard.press("/");
  out.slash = await page.evaluate(() => document.activeElement.id);
  await page.keyboard.type("1");
  out.typedNotNavigated = [await page.inputValue("#field-q"), new URL(page.url()).pathname];
  await page.keyboard.press("Escape");
  out.escBlurs = await page.evaluate(() => document.activeElement === document.body);
  await page.keyboard.press("Control+2");
  out.ctrlIgnored = new URL(page.url()).pathname;
  await Promise.all([page.waitForURL("**/ocio**"), page.keyboard.press("2")]);
  out.twoGoesToOcio = new URL(page.url()).pathname;
  await page.goto(BASE + "/ideas/" + IDEA);
  await page.click("details.menu.more > summary");
  await page.click("details.menu.scope > summary");
  out.oneMenuAtATime = await page.evaluate(() => document.querySelectorAll("details.menu[open]").length);
  await page.keyboard.press("Escape");
  out.escClosesMenus = await page.evaluate(() => document.querySelectorAll("details.menu[open]").length);
  await page.keyboard.press("/");
  out.ideaSlash = await page.evaluate(() => document.activeElement.id);
  // Delete from the panel's ⋯ (still a form until Task 9): the server's toast
  // offers Deshacer, app.js sends it as JSON and the note comes back.
  await page.goto(BASE + "/");
  const id = await page.evaluate(() => document.querySelector("#panel [data-panel]").dataset.panel);
  await page.click("#panel details.menu.more > summary");
  await Promise.all([page.waitForURL(/notice=trashed|\/$/), page.click("#panel details.menu.more button.danger")]);
  out.toastOffersUndo = await page.evaluate(() => !!document.querySelector("#toast.live button"));
  out.goneFromList = await page.evaluate((id) => !document.getElementById("card-" + id), id);
  await Promise.all([page.waitForEvent("load"), page.click("#toast button")]);
  out.backInList = await page.evaluate((id) => !!document.getElementById("card-" + id), id);
  console.log(JSON.stringify(out));
  await browser.close();
})();
EOF
rm -rf "$SP/shots/vault" "$SP/shots/state" "$SP/shots/config"
~/.local/share/oknowledge/venv/bin/python "$SP/shots/serve3.py" > "$SP/serve.log" 2>&1 &
echo $! > "$SP/serve.pid"
until curl -sf http://127.0.0.1:8812/ >/dev/null; do sleep 0.2; done
cd "$SP/pw" && { [ -d node_modules/playwright ] || npm install --no-save --silent playwright; } && node t7.js "$SP/shots/idea"
ps -p "$(cat "$SP/serve.pid")" -o args= | grep -q serve3.py && kill "$(cat "$SP/serve.pid")"
```

Expected, one line:
`{"helpByKey":true,"helpEsc":true,"helpByFoot":true,"helpQuestionCloses":true,"slash":"field-q","typedNotNavigated":["1","/"],"escBlurs":true,"ctrlIgnored":"/","twoGoesToOcio":"/ocio","oneMenuAtATime":1,"escClosesMenus":0,"ideaSlash":"links-q","toastOffersUndo":true,"goneFromList":true,"backInList":true}`

If a value differs, fix `app.js` (or the template hook it names) and run Step 6 again. The Deshacer reloads the page because nothing has set `oknowledge.list` yet (Task 9).

- [ ] **Step 7: Whole suite, commit**

Run the suite; expected green.

```bash
git add src/oknowledge/web/static/app.js src/oknowledge/web/static/shell.js \
        src/oknowledge/web/static/autosave.js src/oknowledge/web/static/app.css \
        src/oknowledge/web/app.py src/oknowledge/web/templates src/oknowledge/i18n.py \
        tests/test_web_app_js.py tests/test_web_shell_js.py tests/test_packaging.py
git commit -m "Give every page one toast, one menu rule, the shortcuts help and the global keys"
```

---
### Task 8: The Settings modal, and settings.js saves every change

**Files:**
- Modify:
  - `src/oknowledge/web/templates/base.html`: the empty `#settings-modal`.
  - `src/oknowledge/web/static/settings.js`: rewritten.
  - `src/oknowledge/web/static/app.css`: the Settings modal.
  - `src/oknowledge/i18n.py`.
- Create (scratch, not committed): `$SP/pw/t8.js`
- Test: `tests/test_web_settings_modal.py` (new); ledger `tests/test_packaging.py:95` (`settings.js` joins the node check)

**Interfaces:**
- Consumes:
  - the hooks of `settings-body.html` (Task 6);
  - the JSON of every Settings write (Task 5);
  - `ok.send`, `ok.toast` and `ok.openModal` (Task 7);
  - the `[data-modal="settings"]` click (Task 7 calls `ok.openSettings()`).
- Produces:
  - `ok.openSettings(tab?)` opens `#settings-modal` and fetches `GET /settings/panel?tab=<last tab opened on this page>`. If the fetch fails, it shows `data-failed` and a Close button.
  - `ok.bindSettings(root, onPage)` binds one `.settings-body`.
    - Tabs switch in place; on the page they also `replaceState` `?tab=`.
    - Each `form[data-settings]` saves on `change` and on `submit`, with one request in flight; a change during it is sent after.
    - `reload` → `location.reload()`.
    - Each `form[data-settings-action]` posts as JSON, toasts its answer and redraws the body.
    - Each `form[data-settings-rename]` saves on Enter or on leaving the field. It asks `confirm()` first when the new name is another category's. Every rename that lands redraws the body; in the modal, it reloads the page when the modal closes.
    - The drop zone sends the file at once (to the `/import` preview page).
    - The `[data-nojs]` buttons hide.

- [ ] **Step 1: Write the failing tests**

`tests/test_web_settings_modal.py`:

```python
"""Settings as a modal (spec §3.1): an empty dialog on every page that
settings.js fills from /settings/panel, saves as it changes, and that says so
when the server cannot be reached (Review Focus 5)."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.vault import rebuild_indexes, write_note
from oknowledge.web.app import create_app

SETTINGS = (Path(__file__).resolve().parent.parent / "src" / "oknowledge" / "web" / "static"
            / "settings.js")


@pytest.fixture(autouse=True)
def state_tree(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr("oknowledge.web.app.CONFIG_PATH", tmp_path / "config" / "config.toml")


@pytest.fixture
def client(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    write_note(cfg, Note(id="a1", url="https://e.com/a1", title="A", category="Redes", tags=[],
                         type="article", source="e.com", saved="2026-10-03", summary="s"), "es")
    rebuild_indexes(cfg, "es")
    return TestClient(create_app(cfg))


def between(text, start, end):
    head = text.index(start)
    return text[head:text.index(end, head)]


@pytest.mark.parametrize("path", ["/", "/ocio", "/ideas", "/retry", "/settings"])
def test_every_page_has_the_empty_settings_dialog(client, path):
    found = re.search(r'<dialog id="settings-modal" class="modal settings"[^>]*></dialog>',
                      client.get(path).text)
    assert found
    assert ('data-failed="The settings could not be loaded. Check that oknowledge is still running."'
            in found.group(0))


def test_the_modal_says_when_the_settings_cannot_be_loaded():
    text = SETTINGS.read_text(encoding="utf-8")
    opening = between(text, "ok.openSettings = function", "ok.bindSettings = ")
    assert '"/settings/panel' in opening and ".catch(" in opening
    failing = between(text, "function failed", "ok.openSettings = function")
    assert "modal.dataset.failed" in failing
    assert 'setAttribute("data-close", "")' in failing and "texts.close" in failing


def test_each_pane_saves_itself_one_request_at_a_time():
    text = SETTINGS.read_text(encoding="utf-8")
    saving = between(text, "function autosave", "function syncKeep")
    assert '"change"' in saving and '"submit"' in saving
    assert "busy" in saving and "again" in saving
    assert "body.reload" in saving and "location.reload()" in saving


def test_a_rename_into_another_category_asks_first():
    text = SETTINGS.read_text(encoding="utf-8")
    renaming = between(text, "function renames", "function drops")
    assert "confirm(" in renaming and "dataset.merge" in renaming
    assert "renamed = true" in renaming


def test_the_model_picker_saves_once():
    picking = between(SETTINGS.read_text(encoding="utf-8"), "function pickers", "function autosave")
    assert "stopPropagation" in picking and "requestSubmit" in picking


def test_settings_js_hides_the_save_buttons_and_never_writes_the_page_storage():
    text = SETTINGS.read_text(encoding="utf-8")
    assert "[data-nojs]" in text
    assert "localStorage" not in text


def test_the_fragment_and_the_page_carry_the_same_hooks(client):
    fragment = client.get("/settings/panel").text
    page = client.get("/settings").text
    for hook in ("data-settings-root", 'data-settings-tab="idioma"', "data-settings-rename",
                 "data-settings-drop", "data-settings-action"):
        assert hook in fragment and hook in page, hook
```

- [ ] **Step 2: Run them to see them fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_settings_modal.py`
Expected: FAIL. There is no `#settings-modal`, and `settings.js` has no `openSettings`. `test_the_fragment_and_the_page_carry_the_same_hooks` passes already (Task 6).

- [ ] **Step 3: The dialog**

In `base.html`, after the `#keys-help` dialog:

```html
  {# Settings (spec §3.1): filled by settings.js from /settings/panel. Empty
     without JavaScript: the sidebar's "Ajustes" is then a link to /settings. #}
  <dialog id="settings-modal" class="modal settings" aria-label="{{ t('Settings') }}" data-failed="{{ t('The settings could not be loaded. Check that oknowledge is still running.') }}"></dialog>
```

Keep it on one line: the test matches `[^>]*></dialog>`.

- [ ] **Step 4: `settings.js`**

`src/oknowledge/web/static/settings.js`:

```js
// Settings (docs/2026-10-14-rediseno-modales-teclado-design.md §3.1): the
// same fragment on the page /settings and in the modal, bound here. Every
// change saves itself; without this script each pane has its Save button
// and the tabs are links.
(function () {
  "use strict";
  var ok = window.oknowledge || (window.oknowledge = {});
  var texts = document.body.dataset;
  var modal = document.getElementById("settings-modal");
  var lastTab = "";
  var renamed = false;

  function toast(text) { if (text && ok.toast) ok.toast(text); }

  // --- tabs -----------------------------------------------------------------------
  function showTab(root, key, onPage) {
    root.querySelectorAll("a[data-settings-tab]").forEach(function (a) {
      var on = a.dataset.settingsTab === key;
      a.classList.toggle("on", on);
      if (on) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    });
    root.querySelectorAll("section[data-settings-pane]").forEach(function (pane) {
      pane.hidden = pane.dataset.settingsPane !== key;
    });
    lastTab = key;
    if (onPage) history.replaceState(null, "", "/settings?tab=" + encodeURIComponent(key));
  }

  // --- the model pickers ----------------------------------------------------------
  // A model picked is added at the end of its box (the order they are
  // tried) and the pane saves. The picker's own change stops here: the
  // pane's change listener would save a second time.
  function pickers(root) {
    root.querySelectorAll("select.add-model").forEach(function (picker) {
      var box = picker.form && picker.form.elements[picker.dataset.for];
      if (!box) return;
      picker.hidden = false;
      picker.addEventListener("change", function (event) {
        event.stopPropagation();
        var model = picker.value;
        if (!model) return;
        var models = box.value.split(",").map(function (m) { return m.trim(); })
                              .filter(function (m) { return m; });
        if (models.indexOf(model) < 0) models.push(model);
        box.value = models.join(", ");
        picker.value = "";
        picker.form.requestSubmit();
      });
    });
  }

  // --- a pane saves itself -----------------------------------------------------------
  // The whole pane, on every change. One request at a time: a change while
  // one is out is sent when it lands, with what the pane holds by then.
  function autosave(form) {
    var busy = false;
    var again = false;
    function save() {
      if (busy) { again = true; return; }
      busy = true;
      ok.send(form.getAttribute("action"), new FormData(form))
        .then(function (body) {
          if (body.reload) { location.reload(); return; }
          toast(body.notice);
          syncKeep(form);
        })
        .catch(function (error) { toast(error.message); })
        .then(function () {
          busy = false;
          if (again) { again = false; save(); }
        });
    }
    form.addEventListener("change", save);
    form.addEventListener("submit", function (event) { event.preventDefault(); save(); });
  }

  // "Keep by default" saved: the unified field's Full | Summary says the same.
  function syncKeep(form) {
    var picked = form.querySelector('input[name="default_content"]:checked');
    if (!picked) return;
    var same = document.querySelector('#unified input[name="content"][value="' + picked.value + '"]');
    if (same) same.checked = true;
  }

  // --- forms that do something (find models, create .env, analyse) ---------------
  function actions(root, onPage) {
    root.querySelectorAll("form[data-settings-action]").forEach(function (form) {
      form.addEventListener("submit", function (event) {
        event.preventDefault();
        ok.send(form.getAttribute("action"), new FormData(form, event.submitter || undefined))
          .then(function (body) { toast(body.notice); redraw(root, onPage); })
          .catch(function (error) { toast(error.message); });
      });
    });
  }

  // --- categories ---------------------------------------------------------------------
  // On Enter or on leaving the field, if the name changed. Merging two
  // categories has no Deshacer: it is asked first.
  function renames(root, onPage) {
    var pane = root.querySelector('[data-settings-pane="categorias"]');
    if (!pane) return;
    var known = Array.prototype.map.call(
      pane.querySelectorAll('form[data-settings-rename] input[name="old"]'),
      function (input) { return input.value; });
    pane.querySelectorAll("form[data-settings-rename]").forEach(function (form) {
      var box = form.elements["new"];
      var old = form.elements.old.value;
      var sending = false;
      function rename() {
        var name = box.value.trim();
        if (sending || !name || name === old) return;
        if (known.indexOf(name) >= 0 &&
            !confirm(pane.dataset.merge.replace("%1", old).replace("%2", name))) {
          box.value = old;
          return;
        }
        sending = true;
        ok.send(form.getAttribute("action"), new FormData(form))
          .then(function (body) {
            renamed = true;
            toast(body.notice);
            redraw(root, onPage);
          })
          .catch(function (error) { sending = false; toast(error.message); });
      }
      box.addEventListener("change", rename);
      form.addEventListener("submit", function (event) { event.preventDefault(); rename(); });
    });
  }

  // --- the WhatsApp export ----------------------------------------------------------
  // Dropped or chosen, it goes at once to /import, whose page shows the
  // preview and asks before saving anything.
  function drops(root) {
    root.querySelectorAll("form[data-settings-drop]").forEach(function (form) {
      var file = form.querySelector('input[type="file"]');
      if (!file) return;
      file.addEventListener("change", function () { if (file.files.length) form.submit(); });
      form.addEventListener("dragover", function (event) {
        event.preventDefault();
        form.classList.add("over");
      });
      form.addEventListener("dragleave", function () { form.classList.remove("over"); });
      form.addEventListener("drop", function (event) {
        event.preventDefault();
        form.classList.remove("over");
        if (!event.dataTransfer || !event.dataTransfer.files.length) return;
        file.files = event.dataTransfer.files;
        form.submit();
      });
    });
  }

  // The body again, as the server draws it now (models found, a .env
  // created, a category renamed), on the tab that was open.
  function redraw(root, onPage) {
    return fetch("/settings/panel?tab=" + encodeURIComponent(lastTab),
                 { headers: { Accept: "text/html" } })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.text(); })
      .then(function (html) {
        var box = document.createElement("template");
        box.innerHTML = html.trim();
        var fresh = box.content.querySelector("[data-settings-root]");
        if (!fresh || !root.isConnected) return;
        root.replaceWith(fresh);
        bind(fresh, onPage);
      })
      .catch(function () { /* what is on screen stays; the next change tries again */ });
  }

  function bind(root, onPage) {
    if (!root) return;
    root.querySelectorAll("[data-nojs]").forEach(function (el) { el.hidden = true; });
    var on = root.querySelector("a[data-settings-tab].on");
    lastTab = on ? on.dataset.settingsTab : lastTab;
    root.addEventListener("click", function (event) {
      var tab = event.target.closest("a[data-settings-tab]");
      if (!tab || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey) return;
      event.preventDefault();
      showTab(root, tab.dataset.settingsTab, onPage);
    });
    pickers(root);
    root.querySelectorAll("form[data-settings]").forEach(autosave);
    actions(root, onPage);
    renames(root, onPage);
    drops(root);
  }

  // --- the modal ---------------------------------------------------------------------
  function failed() {
    var p = document.createElement("p");
    p.className = "modal-failed";
    p.textContent = modal.dataset.failed || "";
    var close = document.createElement("button");
    close.type = "button";
    close.className = "btn";
    close.setAttribute("data-close", "");
    close.textContent = texts.close || "";
    var foot = document.createElement("p");
    foot.className = "modal-failed-foot";
    foot.appendChild(close);
    modal.replaceChildren(p, foot);
    close.focus();
  }

  ok.openSettings = function (tab) {
    if (!modal) { location.href = "/settings"; return; }
    var key = tab || lastTab || "motores";
    renamed = false;
    modal.replaceChildren();
    modal.classList.add("loading");
    ok.openModal(modal);
    fetch("/settings/panel?tab=" + encodeURIComponent(key), { headers: { Accept: "text/html" } })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.text(); })
      .then(function (html) {
        if (!modal.open) return;
        modal.classList.remove("loading");
        modal.innerHTML = html;
        bind(modal.querySelector("[data-settings-root]"), false);
      })
      .catch(function () {
        if (!modal.open) return;
        modal.classList.remove("loading");
        failed();
      });
  };
  ok.bindSettings = bind;

  if (modal) {
    // Esc closes the modal (it is a <dialog>). A text box being typed in
    // loses the focus first, so its change fires and saves.
    modal.addEventListener("cancel", function () {
      var active = document.activeElement;
      if (active && modal.contains(active) && active.blur) active.blur();
    });
    // A category renamed changes the list and the sidebar under the modal.
    modal.addEventListener("close", function () { if (renamed) location.reload(); });
  }

  // The page /settings: the same fragment, bound in place.
  var page = document.querySelector(".settings-body[data-settings-root]");
  if (page && !(modal && modal.contains(page))) bind(page, true);
})();
```

- [ ] **Step 5: CSS and words**

Append to `app.css`:

```css
/* The Settings modal (spec §3.1): head and tabs fixed, the body scrolls. */
.modal.settings { width: 640px; height: 520px; max-width: calc(100vw - 32px);
  max-height: calc(100vh - 32px); overflow: hidden; }
.modal.settings .settings-body { height: 100%; display: flex; flex-direction: column; }
.modal.settings .settings-scroll { flex: 1; overflow-y: auto; }
.modal.settings.loading { cursor: progress; }
.modal-failed { margin: 0; padding: 26px 22px 12px; color: var(--t2); font-size: 14px; }
.modal-failed-foot { margin: 0; padding: 0 22px 22px; text-align: right; }
.drop.over { border-color: var(--acc); background: var(--s3); }
```

In `i18n.py`:

```python
        # The Settings modal (delivery 3, spec §3.1).
        "The settings could not be loaded. Check that oknowledge is still running.":
            "No se pudieron cargar los ajustes. Fijate que oknowledge siga andando.",
```

Ledger: in `tests/test_packaging.py:95` the list becomes `["app.js", "autosave.js", "idea.js", "settings.js", "shell.js"]`.

- [ ] **Step 6: Run the tests**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_settings_modal.py tests/test_web_settings_tabs.py tests/test_web_settings.py tests/test_packaging.py tests/test_i18n.py`
Expected: PASS.

- [ ] **Step 7: Check it in a browser (Review Focus 3 and 5)**

`$SP/pw/t8.js`:

```js
const { chromium } = require("playwright");
const BASE = "http://127.0.0.1:8812";
(async () => {
  const browser = await chromium.launch({ executablePath: "/usr/bin/chromium" });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const out = {};
  const modalOpen = () => page.evaluate(() => document.getElementById("settings-modal").open);
  const saved = () => page.waitForResponse((r) => r.url().endsWith("/settings") &&
                                                  r.request().method() === "POST");
  await page.goto(BASE + "/");
  await page.click('[data-modal="settings"]');
  await page.waitForSelector("#settings-modal .settings-body");
  out.opened = [await modalOpen(), new URL(page.url()).pathname];
  // Review Focus 3: every key typed in the modal is text.
  const box = '#settings-modal input[name="ollama_model"]';
  await page.fill(box, "");
  await page.click(box);
  await page.keyboard.type("j1x/?");
  out.typed = [await page.inputValue(box), new URL(page.url()).pathname, await modalOpen()];
  const first = saved();
  await page.keyboard.press("Escape");          // blurs and saves, then closes
  out.savedOnEsc = (await (await first).json()).ok;
  out.closedOnEsc = !(await modalOpen());
  await page.click('[data-modal="settings"]');
  await page.waitForSelector("#settings-modal .settings-body");
  out.kept = await page.inputValue(box);
  await page.fill(box, "");
  const cleared = saved();
  await page.click('#settings-modal a[data-settings-tab="idioma"]');   // leaving the box saves it
  await cleared;
  out.tabInPlace = await page.evaluate(() =>
    !document.querySelector('#settings-modal [data-settings-pane="idioma"]').hidden &&
    document.querySelector('#settings-modal [data-settings-pane="motores"]').hidden);
  // The batch size autosaves; the interface language reloads.
  const batch = saved();
  await page.fill('#settings-modal input[name="batch"]', "7");
  await page.keyboard.press("Tab");
  out.batchSaved = (await (await batch).json()).ok;
  await Promise.all([page.waitForEvent("load"),
                     page.click('#settings-modal input[name="ui_language"][value="en"]')]);
  out.reloadedInEnglish = await page.evaluate(() => document.documentElement.lang);
  await page.click('[data-modal="settings"]');
  await page.waitForSelector("#settings-modal .settings-body");
  out.reopenedOnLastTab = await page.evaluate(() =>
    !document.querySelector('#settings-modal [data-settings-pane="idioma"]').hidden);
  await Promise.all([page.waitForEvent("load"),
                     page.click('#settings-modal input[name="ui_language"][value="es"]')]);
  // A rename into another category asks first.
  await page.click('[data-modal="settings"]');
  await page.waitForSelector("#settings-modal .settings-body");
  await page.click('#settings-modal a[data-settings-tab="categorias"]');
  const names = await page.$$eval('#settings-modal form[data-settings-rename] input[name="old"]',
                                  (inputs) => inputs.map((i) => i.value));
  let asked = "";
  page.once("dialog", (d) => { asked = d.message(); d.accept(); });
  const renamedResponse = page.waitForResponse((r) => r.url().endsWith("/categories/rename"));
  await page.fill('#settings-modal li:first-child input[name="new"]', names[1]);
  await page.keyboard.press("Enter");
  await renamedResponse;
  out.askedToMerge = asked.indexOf(names[1]) >= 0;
  await Promise.all([page.waitForEvent("load"), page.keyboard.press("Escape")]);
  out.reloadedAfterRename = true;
  // Review Focus 5: the server does not answer.
  await page.route("**/settings/panel**", (route) => route.abort());
  await page.click('[data-modal="settings"]');
  await page.waitForSelector("#settings-modal .modal-failed");
  out.failedSays = await page.textContent("#settings-modal .modal-failed");
  await page.click("#settings-modal [data-close]");
  out.failedCloses = !(await modalOpen());
  out.stayed = new URL(page.url()).pathname;
  // On /settings the foot's link is a link, and the page autosaves too.
  await page.unroute("**/settings/panel**");
  await page.goto(BASE + "/settings?tab=idioma");
  const onPage = saved();
  await page.click('.settings-body input[name="mentions"][value="all"]');
  out.pageSaves = (await (await onPage).json()).ok;
  out.noSaveButtons = await page.$$eval(".settings-body [data-nojs]",
                                        (els) => els.every((el) => el.hidden));
  console.log(JSON.stringify(out));
  await browser.close();
})();
```

Run it as in Task 7 Step 6 (reset the vault, start `serve3.py`, `node t8.js`, kill the server). Expected, one line:

`{"opened":[true,"/"],"typed":["j1x/?","/",true],"savedOnEsc":true,"closedOnEsc":true,"kept":"j1x/?","tabInPlace":true,"batchSaved":true,"reloadedInEnglish":"en","reopenedOnLastTab":false,"askedToMerge":true,"reloadedAfterRename":true,"failedSays":"No se pudieron cargar los ajustes. Fijate que oknowledge siga andando.","failedCloses":true,"stayed":"/","pageSaves":true,"noSaveButtons":true}`

`reopenedOnLastTab` is `false` by design: the reload starts a new page, and "the last tab opened on this page" starts over at Motores. The rename goes through the first row (`li:first-child`), into the second row's name; `serve.py` seeds links in several categories, so `names[1]` exists. It merges two categories of the scratch vault, which the next reset puts back. If a value differs, fix `settings.js` and run again.

- [ ] **Step 8: Whole suite, commit**

```bash
git add src/oknowledge/web/static/settings.js src/oknowledge/web/static/app.css \
        src/oknowledge/web/templates/base.html src/oknowledge/i18n.py \
        tests/test_web_settings_modal.py tests/test_packaging.py
git commit -m "Open Settings as a modal that saves every change"
```

---
### Task 9: The list keys, and a delete from the panel that offers Deshacer

**Files:**
- Modify:
  - `src/oknowledge/web/static/shell.js`:
    - `markCurrent` covers ideas;
    - `loadList` takes a `reason` and tells `#list`, and keeps the ideas cursor;
    - `more` tells `#list`;
    - the inline-submit handler handles a delete;
    - new list helpers, `ok.list` and the keys.
  - `src/oknowledge/web/templates/panel.html`:
    - Delete becomes `data-inline`;
    - `data-open` on "Open original";
    - `id="tag-add"` and `required` on "+ tag".
  - `src/oknowledge/web/templates/card-panel.html`: `data-open` on "Open in …" and `id="tag-add"` on "+ tag".
  - `src/oknowledge/web/templates/idea-list.html`: `data-current=""` on `#items`.
  - `src/oknowledge/web/templates/base.html`: `data-opening` on `<body>`.
  - `src/oknowledge/i18n.py`.
- Create (scratch, not committed): `$SP/pw/t9.js`
- Test: `tests/test_web_list_keys.py` (new). No ledger: `tests/test_web_panel.py:117` looks for `action="/item/a1/delete"`, which the inline form still has.

**Interfaces:**
- Consumes: `ok.keys`, `ok.offerUndo`, `ok.toast` (Task 7); the delete JSON `{"notice", "undo"}` (Task 3).
- Produces:
  - `ok.list`:
    - `current()` returns the picked id (`#items[data-current]`);
    - `pick(id)` opens the panel, or moves the ideas cursor;
    - `next(id)` returns the one after `id` on screen, else the one before, else `""`;
    - `reload(pickId?)` reloads the list as a `"refresh"`, and opens `pickId` when given;
    - `shown()` returns the `li.item` elements on screen.
  - `#list` dispatches `oknowledge:list` (bubbling) with `detail.reason`:
    - `"filter"` from a filter, a search or the remembered layout;
    - `"refresh"` from a reload of the same list, a view switch or an edit;
    - `"more"` from a chunk added.

    Note: spec §5 lists a view switch under `filter`. The same notes are on screen, so it is a `refresh` here, and the selection survives a `v`.
  - Keys:
    - `j`/`→` and `k`/`←` step through the list;
    - `↓`/`↑` move ± a row;
    - Enter opens the original, or the idea;
    - `f` is ★ (library);
    - `e` focuses `#tag-add`;
    - `v` switches the view.
  - `oknowledge:list` is what `select.js` (Task 10) listens to.

- [ ] **Step 1: Write the failing tests**

`tests/test_web_list_keys.py`:

```python
"""The keys of the lists (spec §4) and the panel's delete with Deshacer
(spec §6.4): the hooks the server draws for them, and shell.js's rules."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.model import Note
from oknowledge.vault import note_path, rebuild_indexes, write_note
from oknowledge.web.app import create_app

SHELL = (Path(__file__).resolve().parent.parent / "src" / "oknowledge" / "web" / "static"
         / "shell.js")
CARD = "c00000000001"


@pytest.fixture
def client(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    write_note(cfg, Note(id="a1", url="https://www.e.com/a1", title="A", category="Redes",
                         tags=[], type="article", source="e.com", saved="2026-10-03",
                         summary="s"), "es")
    card = Note(id=CARD, url="https://www.imdb.com/title/tt1", title="Dune", category="Películas",
                tags=[], type="movie", source="imdb.com", saved="2026-10-02", summary="s",
                engine="")
    write_note(cfg, card, "es", path=note_path(cfg, card, shelf=cfg.ocio))
    idea = new_idea("Una idea.", "Idea", "2026-10-13", "2026-10-13T00:00:00.000001+00:00")
    write_note(cfg, idea, "es", path=note_path(cfg, idea, shelf=cfg.ideas))
    for shelf in (cfg.links, cfg.ocio, cfg.ideas):
        rebuild_indexes(cfg, "es", shelf=shelf)
    return TestClient(create_app(cfg))


def between(text, start, end):
    head = text.index(start)
    return text[head:text.index(end, head)]


# --- the hooks ----------------------------------------------------------------------

def test_the_panels_delete_is_inline_and_asks_nothing(client):
    panel = client.get("/panel/a1").text
    form = re.search(r'<form method="post" action="/item/a1/delete"[^>]*>', panel).group(0)
    assert "data-inline" in form and "data-ask" not in form


def test_the_original_link_is_marked_for_enter(client):
    assert re.search(r'<a class="btn primary" href="https://www.e.com/a1"[^>]*data-open',
                     client.get("/panel/a1").text)
    assert re.search(r'<a class="btn primary" href="https://www.imdb.com/title/tt1"[^>]*data-open',
                     client.get(f"/panel/{CARD}").text)


def test_the_tag_box_answers_to_e_and_never_posts_empty(client):
    for path in ("/panel/a1", f"/panel/{CARD}"):
        form = re.search(r'<form method="post" action="/item/[^"]+/tags" data-inline class="tag-new">.*?</form>',
                         client.get(path).text, re.S).group(0)
        box = re.search(r'<input name="add"[^>]*>', form).group(0)
        assert 'id="tag-add"' in box and "required" in box, path


def test_the_ideas_list_keeps_a_cursor(client):
    assert '<ul class="items tiles" id="items" data-current="">' in client.get("/ideas").text


def test_the_body_carries_the_opening_words(client):
    assert 'data-opening="Opening %1…"' in client.get("/").text


# --- shell.js -------------------------------------------------------------------------

def test_shell_registers_the_list_keys():
    text = SHELL.read_text(encoding="utf-8")
    for key in ('keys.j', 'keys.k', 'keys.ArrowRight', 'keys.ArrowLeft', 'keys.ArrowDown',
                'keys.ArrowUp', 'keys.Enter', 'keys.f', 'keys.e', 'keys.v'):
        assert key in text, key


def test_a_row_is_the_items_level_with_the_first():
    rows = between(SHELL.read_text(encoding="utf-8"), "function rowWidth", "function step")
    assert "offsetTop" in rows


def test_moving_keeps_the_pick_in_view():
    assert 'scrollIntoView({ block: "nearest" })' in SHELL.read_text(encoding="utf-8")


def test_the_list_tells_why_it_changed():
    text = SHELL.read_text(encoding="utf-8")
    assert '"oknowledge:list"' in text and "bubbles: true" in text
    for reason in ('"filter"', '"refresh"', '"more"'):
        assert reason in text, reason


def test_a_delete_from_the_panel_picks_the_next_and_offers_undo():
    text = SHELL.read_text(encoding="utf-8")
    handler = between(text, "// --- edits in place", "// --- links being read")
    assert "neighbour(" in handler and "offerUndo(answer.notice, answer.undo)" in handler
    assert "emptyPanel()" in handler


def test_the_list_is_offered_to_the_other_scripts():
    text = SHELL.read_text(encoding="utf-8")
    assert re.search(r"ok\.list = \{", text)
    for name in ("current:", "pick:", "next:", "reload:", "shown:"):
        assert name in between(text, "ok.list = {", "};"), name
```

- [ ] **Step 2: Run them to see them fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_list_keys.py`
Expected: FAIL on every test.

- [ ] **Step 3: The hooks**

In `panel.html`:
- Delete:

```html
      <form method="post" action="/item/{{ note.id|slug }}/delete" data-inline>
        <button class="danger">{{ t('Delete') }}</button>
      </form>
```

- "Open original" gains ` data-open` after `rel="noreferrer"`.
- The "+ tag" input:

```html
      <input name="add" id="tag-add" required autocomplete="off" aria-label="{{ t('+ tag') }}" placeholder="{{ t('+ tag') }}">
```

In `card-panel.html`:
- "Open in …" gains ` data-open` after `rel="noreferrer"`;
- the "+ tag" input gains `id="tag-add"` after `name="add"`.

In `idea-list.html`:

```html
    <ul class="items {{ 'rows' if view.vista == 'lista' else 'tiles' }}" id="items" data-current="">
```

In `base.html`, `<body>` gains `data-opening="{{ t('Opening %1…') }}"` after `data-undo=…`.

In `i18n.py`:

```python
        # Enter on a list (delivery 3, spec §4).
        "Opening %1…": "Abriendo %1…",
```

- [ ] **Step 4: `shell.js`**

1. **Hand-over.** At the top, after `var texts = document.body.dataset;`, add:

```js
  var ok = window.oknowledge || (window.oknowledge = {});
  ok.keys = ok.keys || {};
```

2. **`markCurrent`.** Generalise it:

```js
  function markCurrent(id) {
    list.querySelectorAll("li.item.on").forEach(function (li) { li.classList.remove("on"); });
    var li = itemOf(id);
    if (li) li.classList.add("on");
    var items = document.getElementById("items");
    if (items) items.dataset.current = id;
  }
```

3. **`loadList`.**
   - The signature becomes `function loadList(url, keepScroll, reason)`.
   - After `var top = …` add `var cursor = panel ? "" : current();   // the ideas list's`.
   - After `observe(); watch();` inside the success branch add:

```js
        // The ideas list has no panel to follow: its cursor is put back.
        if (!panel && cursor && itemOf(cursor)) markCurrent(cursor);
        told(reason || "filter");
```

4. **`more`.** After its `watch();`, add `told("more");`.

5. **The callers.** Pass the reason:
   - data-view → `loadList(shape.href, true, "refresh")`;
   - the remembered layout → `loadList(now.href, false, "refresh")`;
   - the inline-edit and `watch()` reloads → `loadList(here().href, true, "refresh")`;
   - the field's input and the data-nav click keep the default (`"filter"`).

6. **The list helpers.** Add them before `// --- the list column`:

```js
  // --- the list on screen (spec §4, §5) --------------------------------------
  function shown() {
    return Array.prototype.slice.call(list.querySelectorAll("#items > li.item"));
  }

  function idOf(li) { return li.id.replace(/^(card|idea)-/, ""); }

  function itemOf(id) {
    return id ? document.getElementById("card-" + id) || document.getElementById("idea-" + id)
              : null;
  }

  function current() {
    var items = document.getElementById("items");
    return items ? items.dataset.current || "" : "";
  }

  // The one after `id` on screen, else the one before, else "" (Ruling 25).
  function neighbour(id) {
    var items = shown();
    for (var at = 0; at < items.length; at++) {
      if (idOf(items[at]) !== id) continue;
      var near = items[at + 1] || items[at - 1];
      return near ? idOf(near) : "";
    }
    return "";
  }

  // The list changed under the selection (select.js listens).
  function told(reason) {
    list.dispatchEvent(new CustomEvent("oknowledge:list", { bubbles: true,
                                                           detail: { reason: reason } }));
  }

  // Picked by a key: the panel opens it, or on /ideas the cursor moves.
  function pick(id) {
    if (!id) return;
    if (panel) loadPanel(id); else markCurrent(id);
    var li = itemOf(id);
    if (li) li.scrollIntoView({ block: "nearest" });
  }
```

7. **The inline-submit handler.** In `// --- edits in place`, replace the handler body from `var data = …` to the end:

```js
    var data = new FormData(target, event.submitter || undefined);
    closeMenus();
    // The panel's Delete (not a mention's): the one after it is picked
    // before the list changes (Ruling 25), and the toast offers Deshacer.
    var deleting = /^\/item\/[^/]+\/delete$/.test(new URL(target.action, location.href).pathname);
    var shownNow = panel && panel.querySelector("[data-panel]");
    var gone = shownNow ? shownNow.dataset.panel : "";
    var next = deleting ? neighbour(gone) : "";
    fetch(target.action, { method: "POST", body: data,
                           headers: { Accept: "application/json" } })
      .then(function (r) {
        return r.json().catch(function () { return { ok: false }; });
      })
      .then(function (answer) {
        if (!answer.ok) { toast(answer.error || texts.saveFailed); return; }
        if (deleting) {
          ok.offerUndo(answer.notice, answer.undo);
          if (next) {
            loadList(here().href, true, "refresh");
            loadPanel(next);
          } else {
            emptyPanel();
            loadList(here().href, true, "refresh");
          }
          return;
        }
        // A write that starts a run (a rewrite) is told by its watcher when
        // it ends; its own notice says "reload in a moment", which is wrong
        // here. The server marks those (`runs`); every other notice is said.
        if (!answer.runs) toast(answer.notice || "");
        var shown = panel && panel.querySelector("[data-panel]");
        if (shown && shown.dataset.panel && stillPicked(shown.dataset.panel)) {
          loadPanel(shown.dataset.panel, true);    // deleted: gone
        }
        loadList(here().href, true, "refresh");
      })
      .catch(function () { toast(texts.saveFailed); });
```

`loadList` runs before `loadPanel(next)`. The list notes the pick it was asked under, and `loadPanel` then moves that pick. When the list lands it follows the URL's `sel` (`next`), not the server's `current`.

8. **The keys and `ok.list`.** Add this block before `// --- the pick in the URL`:

```js
  // --- keys (spec §4) -----------------------------------------------------------------
  // A row is the items level with the first one: one in a list, the
  // columns that fit in a grid.
  function rowWidth() {
    var items = shown();
    if (!items.length) return 1;
    var top = items[0].offsetTop;
    var n = 0;
    while (n < items.length && items[n].offsetTop === top) n++;
    return n || 1;
  }

  // With nothing picked, any move picks the first one.
  function step(by) {
    var items = shown();
    if (!items.length) return;
    var at = -1;
    var id = current();
    for (var i = 0; i < items.length; i++) if (idOf(items[i]) === id) at = i;
    if (at < 0) { pick(idOf(items[0])); return; }
    var to = Math.max(0, Math.min(items.length - 1, at + by));
    if (to !== at) pick(idOf(items[to]));
  }

  ok.keys.j = ok.keys.ArrowRight = function () { step(1); };
  ok.keys.k = ok.keys.ArrowLeft = function () { step(-1); };
  ok.keys.ArrowDown = function () { step(rowWidth()); };
  ok.keys.ArrowUp = function () { step(-rowWidth()); };

  // Enter: the original in another tab (library, Ocio), or the idea's screen.
  ok.keys.Enter = function () {
    if (!panel) {
      var li = itemOf(current());
      var hit = li && li.querySelector("a.hit");
      if (!hit) return false;
      location.href = hit.href;
      return;
    }
    var open = panel.querySelector("a[data-open]");
    if (!open) return false;
    window.open(open.href, "_blank", "noopener");
    toast((texts.opening || "").replace("%1", new URL(open.href).hostname.replace(/^www\./, "")));
  };

  // f: the panel's ★, as a click (the library only: Ocio has no favourites).
  ok.keys.f = function () {
    var star = mode === "library" && panel && panel.querySelector("form.push button.star");
    if (!star) return false;
    star.click();
  };

  // e: the panel's "+ tag" (the keydown's default is prevented, so no "e").
  ok.keys.e = function () {
    var box = panel && document.getElementById("tag-add");
    if (!box || !panel.contains(box)) return false;
    box.focus();
  };

  // v: the layout that is not on. Ocio has none: nothing happens.
  ok.keys.v = function () {
    var other = list.querySelector("a[data-view]:not(.on)");
    if (!other) return false;
    other.click();
  };

  ok.list = {
    current: current,
    pick: pick,
    next: neighbour,
    shown: shown,
    // After an undo or a bulk action: the same list again, and `id` opened
    // (the first one restored, or the one after those deleted).
    reload: function (id) {
      var done = loadList(here().href, true, "refresh");
      if (id && panel) loadPanel(id, true);
      else if (id && done) done.then(function () { if (itemOf(id)) markCurrent(id); });
      return done;
    },
  };
```

Keep the file's end as it is: `observe();\n  watch();\n})();`.

- [ ] **Step 5: Run the tests**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_list_keys.py tests/test_web_shell_js.py tests/test_web_panel.py tests/test_web_ocio_panel.py tests/test_web_ocio_scripts.py tests/test_web_undo.py tests/test_packaging.py tests/test_i18n.py`
Expected: PASS.

- [ ] **Step 6: Check it in a browser**

`$SP/pw/t9.js`:

```js
const { chromium } = require("playwright");
const BASE = "http://127.0.0.1:8812";
(async () => {
  const browser = await chromium.launch({ executablePath: "/usr/bin/chromium" });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  const out = {};
  const sel = () => new URL(page.url()).searchParams.get("sel");
  const settle = () => page.waitForLoadState("networkidle");
  await page.goto(BASE + "/?vista=tarjetas");
  const first = sel();
  await page.keyboard.press("j"); await settle();
  out.jMoves = sel() !== first;
  await page.keyboard.press("k"); await settle();
  out.kBack = sel() === first;
  const perRow = await page.evaluate(() => {
    const items = [...document.querySelectorAll("#items > li.item")];
    return items.filter((li) => li.offsetTop === items[0].offsetTop).length;
  });
  await page.keyboard.press("ArrowDown"); await settle();
  out.downIsARow = await page.evaluate(([id, n]) => {
    const items = [...document.querySelectorAll("#items > li.item")].map((li) => li.id.slice(5));
    return items.indexOf(new URLSearchParams(location.search).get("sel")) === items.indexOf(id) + n;
  }, [first, perRow]);
  await page.keyboard.press("ArrowUp"); await settle();
  out.upBack = sel() === first;
  const [popup] = await Promise.all([context.waitForEvent("page"), page.keyboard.press("Enter")]);
  out.enterOpens = popup.url().length > 0;
  out.openingToast = await page.textContent("#toast");
  await popup.close();
  const starred = () => page.evaluate(() => document.querySelector("#panel form.push button.star").classList.contains("on"));
  const before = await starred();
  await page.keyboard.press("f"); await settle();
  out.fStars = (await starred()) !== before;
  await page.keyboard.press("f"); await settle();
  await page.keyboard.press("e");
  out.eFocuses = await page.evaluate(() => document.activeElement.id);
  await page.keyboard.type("probando");
  await page.keyboard.press("Enter"); await settle();
  out.tagAddedAndRefocused = await page.evaluate(() => document.activeElement.id === "tag-add" &&
    [...document.querySelectorAll("#panel .chip")].some((c) => c.textContent.includes("#probando")));
  await page.keyboard.press("Escape");
  await page.keyboard.press("v"); await settle();
  out.vSwitches = new URL(page.url()).searchParams.get("vista");
  // Delete from the panel: the next one is picked, the toast offers Deshacer.
  const gone = sel();
  const after = await page.evaluate((id) => {
    const items = [...document.querySelectorAll("#items > li.item")].map((li) => li.id.slice(5));
    const at = items.indexOf(id);
    return items[at + 1] || items[at - 1];
  }, gone);
  await page.click("#panel details.menu.more > summary");
  await page.click("#panel details.menu.more button.danger"); await settle();
  out.nextPicked = sel() === after;
  out.undoOffered = await page.evaluate(() => document.querySelector("#toast button") !== null);
  await page.click("#toast button"); await settle();
  out.restoredAndOpened = sel() === gone &&
    (await page.evaluate((id) => !!document.getElementById("card-" + id), gone));
  // Ocio: j between posters; f does nothing; Enter opens the card's link.
  await page.goto(BASE + "/ocio");
  const poster = sel();
  await page.keyboard.press("j"); await settle();
  out.ocioMoves = sel() !== poster;
  // The ideas list: j moves the cursor, Enter opens the idea.
  await page.goto(BASE + "/ideas");
  await page.keyboard.press("j");
  out.ideaCursor = await page.evaluate(() => document.querySelector("#items").dataset.current !== "" &&
                                             !!document.querySelector("#items > li.item.on"));
  await Promise.all([page.waitForURL(/\/ideas\/[^/?]+/), page.keyboard.press("Enter")]);
  out.enterOpensIdea = /\/ideas\/[^/?]+$/.test(new URL(page.url()).pathname);
  console.log(JSON.stringify(out));
  await browser.close();
})();
```

Run it as in Task 7 Step 6, with `node t9.js`. Expected, one line:

`{"jMoves":true,"kBack":true,"downIsARow":true,"upBack":true,"enterOpens":true,"openingToast":"Abriendo <the link's domain>…","fStars":true,"eFocuses":"tag-add","tagAddedAndRefocused":true,"vSwitches":"lista","nextPicked":true,"undoOffered":true,"restoredAndOpened":true,"ocioMoves":true,"ideaCursor":true,"enterOpensIdea":true}`

`openingToast` names the picked link's domain. `tagAddedAndRefocused` holds because `loadPanel` already puts the focus back on the element with the same `id`, which the box now has (spec §9). Every other value must match.

- [ ] **Step 7: Whole suite, commit**

```bash
git add src/oknowledge/web/static/shell.js src/oknowledge/web/templates src/oknowledge/i18n.py \
        tests/test_web_list_keys.py
git commit -m "Move through the lists with the keyboard, and delete from the panel with Deshacer"
```

---
### Task 10: Ticking several, and the bar that acts on them

**Files:**
- Create: `src/oknowledge/web/templates/bulk-bar.html`, `src/oknowledge/web/static/select.js`
- Modify:
  - `src/oknowledge/web/templates/shelf-items.html` (the `item` macro, not `pending`), `posters.html` and `idea-items.html`: the checkbox.
  - `home.html`, `ocio-shelf.html`, `idea-shelf.html`: include the bar and load `select.js`.
  - `src/oknowledge/web/app.py`: in `create_app`, the template globals `KIND_ONE`, `IDEA_WORDS` and `IDEA_DOTS` (≈720).
  - `src/oknowledge/web/static/app.css` and `src/oknowledge/i18n.py`.
- Create (scratch, not committed): `$SP/pw/t10.js`
- Test: `tests/test_web_select.py` (new); ledger `tests/test_packaging.py:95` (`select.js` joins the node check)

**Interfaces:**
- Consumes:
  - `POST /bulk/{action}` and its JSON (Task 4);
  - `ok.send`, `ok.toast`, `ok.offerUndo`, `ok.closeMenus` and `ok.keys` (Task 7);
  - `ok.list` and `oknowledge:list` (Task 9).
- Produces:
  - Markup:
    - `<label class="check js-only"><input type="checkbox" name="ids" value="{id}" form="bulk" aria-label="Select {title}"></label>`, before `a.hit` in each tickable item;
    - `<form id="bulk" class="bulk js-only" method="post" action="/bulk/…" hidden data-one data-many>`.
  - Keys:
    - `x` ticks or unticks the picked item (not an "Analysing…" one);
    - `Backspace`/`Delete` delete the ticked, with Deshacer;
    - `Escape` (last in app.js's chain) clears.
  - The selection survives a `refresh` and a `more`, and clears on a `filter`.

- [ ] **Step 1: Write the failing tests**

`tests/test_web_select.py`:

```python
"""Multi-selection (spec §5): a checkbox outside the link on each item that
can be ticked, and one bar per section with that section's actions."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.model import Note
from oknowledge.vault import note_path, rebuild_indexes, write_note
from oknowledge.web.app import create_app

WEB = Path(__file__).resolve().parent.parent / "src" / "oknowledge" / "web"
SELECT = WEB / "static" / "select.js"
CARD = "c00000000001"


@pytest.fixture
def client(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    for id, category in (("a1", "Redes"), ("b2", "Cocina")):
        write_note(cfg, Note(id=id, url=f"https://e.com/{id}", title=f"T {id}", category=category,
                             tags=[], type="article", source="e.com", saved="2026-10-03",
                             summary="s"), "es")
    card = Note(id=CARD, url="https://www.imdb.com/title/tt1", title="Dune", category="Películas",
                tags=[], type="movie", source="imdb.com", saved="2026-10-02", summary="s",
                engine="")
    write_note(cfg, card, "es", path=note_path(cfg, card, shelf=cfg.ocio))
    idea = new_idea("Una idea.", "VPN", "2026-10-13", "2026-10-13T00:00:00.000001+00:00")
    write_note(cfg, idea, "es", path=note_path(cfg, idea, shelf=cfg.ideas))
    for shelf in (cfg.links, cfg.ocio, cfg.ideas):
        rebuild_indexes(cfg, "es", shelf=shelf)
    client = TestClient(create_app(cfg))
    client.idea = idea.id
    return client


def bar(body):
    return re.search(r'<form id="bulk".*?</form>', body, re.S).group(0)


def between(text, start, end):
    head = text.index(start)
    return text[head:text.index(end, head)]


# --- checkboxes ----------------------------------------------------------------------

@pytest.mark.parametrize("path, id, title", [("/", "a1", "T a1"), ("/?vista=lista", "a1", "T a1"),
                                             ("/ocio", CARD, "Dune"), ("/ideas", "idea", "VPN"),
                                             ("/ideas?vista=lista", "idea", "VPN")])
def test_each_item_has_its_checkbox_outside_the_link(client, path, id, title):
    id = client.idea if id == "idea" else id
    body = client.get(path).text
    item = re.search(rf'<li class="item[^"]*" id="(?:card|idea)-{id}".*?</li>', body, re.S).group(0)
    check = (f'<label class="check js-only"><input type="checkbox" name="ids" value="{id}" '
             f'form="bulk" aria-label="Select {title}"></label>')
    assert check in item
    assert item.index(check) < item.index('<a class="hit"')


def test_an_item_being_analysed_has_no_checkbox():
    text = (WEB / "templates" / "shelf-items.html").read_text(encoding="utf-8")
    assert 'class="check' not in between(text, "{% macro pending", "{%- endmacro %}")


def test_settings_and_the_idea_screen_have_no_bar(client):
    for path in ("/settings", f"/ideas/{client.idea}", "/retry"):
        assert 'id="bulk"' not in client.get(path).text, path


# --- the bar -------------------------------------------------------------------------------

def test_the_library_bar_moves_to_a_category_stars_and_deletes(client):
    found = bar(client.get("/").text)
    assert 'class="bulk js-only"' in found and " hidden" in found
    assert 'data-one="1 selected" data-many="%1 selected"' in found
    assert 'formaction="/bulk/category" name="category" value="Redes"' in found
    assert 'formaction="/bulk/category" name="category" value="Cocina"' in found
    assert 'name="new_category"' in found
    assert 'formaction="/bulk/mark" name="mark" value="⭐"' in found
    assert 'formaction="/bulk/delete"' in found and "data-clear" in found
    # The hidden first button: Enter in "New category" moves.
    assert found.index('class="default-submit"') < found.index('name="new_category"')


def test_the_ocio_bar_changes_the_kind_and_has_no_star(client):
    found = bar(client.get("/ocio").text)
    for kind in ("movie", "series", "anime", "book"):
        assert f'formaction="/bulk/kind" name="kind" value="{kind}"' in found
    assert "/bulk/mark" not in found and "/bulk/category" not in found
    assert 'formaction="/bulk/delete"' in found


def test_the_ideas_bar_changes_the_state_and_has_no_star(client):
    found = bar(client.get("/ideas").text)
    for state in ("pending", "doing", "done", "dropped"):
        assert f'formaction="/bulk/state" name="state" value="{state}"' in found
    assert "/bulk/mark" not in found and "/bulk/kind" not in found
    assert 'formaction="/bulk/delete"' in found


@pytest.mark.parametrize("path", ["/", "/ocio", "/ideas"])
def test_select_js_comes_after_shell_js(client, path):
    body = client.get(path).text
    assert (body.index('<script src="/static/shell.js" defer></script>')
            < body.index('<script src="/static/select.js" defer></script>'))


# --- select.js -------------------------------------------------------------------------------

def test_select_follows_the_list():
    text = SELECT.read_text(encoding="utf-8")
    listening = between(text, '"oknowledge:list"', "});")
    assert '"filter"' in listening


def test_select_registers_its_keys():
    text = SELECT.read_text(encoding="utf-8")
    for key in ("keys.x", "keys.Backspace", "keys.Delete", "keys.Escape"):
        assert key in text, key


def test_select_sends_the_ticked_ids_and_offers_undo():
    text = SELECT.read_text(encoding="utf-8")
    sending = between(text, "function submit", "function pickAfter")
    assert 'data.delete("ids")' in sending and 'data.append("ids"' in sending
    assert "ok.offerUndo(body.notice, body.undo" in sending and "ok.list.reload(" in sending
```

- [ ] **Step 2: Run them to see them fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_select.py`
Expected: FAIL. `test_an_item_being_analysed_has_no_checkbox` and `test_settings_and_the_idea_screen_have_no_bar` pass already.

- [ ] **Step 3: The checkboxes**

In `shelf-items.html`, in the `item` macro, right after the `<li …>` line (before `<a class="hit"`):

```html
  <label class="check js-only"><input type="checkbox" name="ids" value="{{ note.id }}" form="bulk" aria-label="{{ t('Select %1', note.title) }}"></label>
```

The same line goes in `posters.html` (`poster` macro). In `idea-items.html`, `aria-label="{{ t('Select %1', note.title or t('Untitled idea')) }}"`.

- [ ] **Step 4: The bar**

`src/oknowledge/web/templates/bulk-bar.html`:

```html
{# The bar of a multi-selection (spec §5): drawn hidden, shown by select.js
   while something is ticked. The boxes belong to this form by form="bulk".
   Without JavaScript neither the boxes nor the bar are drawn. Each button
   names its action; the hidden first one is the default, so Enter in
   "New category" moves. #}
<form id="bulk" class="bulk js-only" method="post" action="/bulk/{{ {'links': 'category', 'ocio': 'kind'}.get(bulk_section, 'state') }}" hidden
      data-one="{{ t('1 selected') }}" data-many="{{ t('%1 selected') }}">
  {% if bulk_section == 'links' %}<button type="submit" class="default-submit" formaction="/bulk/category" tabindex="-1" aria-hidden="true"></button>{% endif %}
  <input type="hidden" name="back" value="">
  <span class="bulk-count" data-count></span>
  <span class="bulk-sep"></span>
  <details class="menu up bulk-move">
    <summary>{{ t('Move to') }} ▾</summary>
    <div class="menu-list">
      {% if bulk_section == 'links' %}
        {% for name in categories %}
          <button formaction="/bulk/category" name="category" value="{{ name }}"><i class="dot" style="background: {{ name|dot }}"></i>{{ name }}</button>
        {% endfor %}
        <input name="new_category" class="menu-new" autocomplete="off" aria-label="{{ t('New category') }}" placeholder="{{ t('New category') }}">
      {% elif bulk_section == 'ocio' %}
        {% for kind, one in KIND_ONE.items() %}
          <button formaction="/bulk/kind" name="kind" value="{{ kind }}">{{ t(one) }}</button>
        {% endfor %}
      {% else %}
        {% for state, word in IDEA_WORDS.items() %}
          <button formaction="/bulk/state" name="state" value="{{ state }}"><i class="dot" style="background: {{ IDEA_DOTS[state] }}"></i>{{ t(word) }}</button>
        {% endfor %}
      {% endif %}
    </div>
  </details>
  {% if bulk_section == 'links' %}<button formaction="/bulk/mark" name="mark" value="⭐" class="bulk-star">★ {{ t('Favorite') }}</button>{% endif %}
  <button formaction="/bulk/delete" class="bulk-delete">{{ t('Delete') }}</button>
  <button type="button" class="bulk-clear" data-clear aria-label="{{ t('Clear the selection') }}" title="{{ t('Clear the selection') }}">✕</button>
</form>
```

In `app.py` `create_app`, next to `KEYS_HELP`:

```python
    # The bulk bar's choices (spec §5), on whatever page includes it.
    templates.env.globals["KIND_ONE"] = KIND_ONE
    templates.env.globals["IDEA_WORDS"] = IDEA_WORDS
    templates.env.globals["IDEA_DOTS"] = IDEA_DOTS
```

`KIND_ONE` follows `cards.KINDS` order (`movie`, `series`, `anime`, `book`), and the page contexts that already pass these names keep winning over the globals.

In `home.html`, after `<div class="list" id="list">…</div>`:

```html
  {% with bulk_section = 'links' %}{% include "bulk-bar.html" %}{% endwith %}
```

`ocio-shelf.html` gets the same with `'ocio'`, and `idea-shelf.html` with `'ideas'`. Their `{% block scripts %}` gains `<script src="/static/select.js" defer></script>` after `shell.js`.

- [ ] **Step 5: `select.js`**

`src/oknowledge/web/static/select.js`:

```js
// Multi-selection (docs/2026-10-14-rediseno-modales-teclado-design.md §5):
// the ticked ids, the bar, and its actions sent as JSON. Lives across the
// list's reloads (shell.js's "oknowledge:list"): a refresh keeps what is
// still on screen, a new filter clears. Without JavaScript nothing of this
// is drawn.
(function () {
  "use strict";
  var ok = window.oknowledge || (window.oknowledge = {});
  ok.keys = ok.keys || {};
  var bar = document.getElementById("bulk");
  var list = document.getElementById("list");
  if (!bar || !list) return;
  var picked = [];          // ids, in the order they were ticked

  function boxes() {
    return Array.prototype.slice.call(list.querySelectorAll('input[type="checkbox"][name="ids"]'));
  }

  function draw() {
    var n = picked.length;
    boxes().forEach(function (box) {
      box.checked = picked.indexOf(box.value) >= 0;
      var li = box.closest("li.item");
      if (li) li.classList.toggle("picked", box.checked);
    });
    list.classList.toggle("picking", n > 0);
    bar.querySelector("[data-count]").textContent =
      n === 1 ? bar.dataset.one : (bar.dataset.many || "").replace("%1", n);
    if (!n) ok.closeMenus();
    bar.hidden = n === 0;
  }

  function toggle(id, on) {
    var at = picked.indexOf(id);
    if (on && at < 0) picked.push(id);
    if (!on && at >= 0) picked.splice(at, 1);
    draw();
  }

  function clear() {
    picked = [];
    draw();
  }

  list.addEventListener("change", function (event) {
    var box = event.target;
    if (box.matches && box.matches('input[type="checkbox"][name="ids"]')) toggle(box.value, box.checked);
  });

  bar.addEventListener("click", function (event) {
    if (event.target.closest("[data-clear]")) { event.preventDefault(); clear(); }
  });

  // The list was drawn again: a new filter clears, the same list keeps
  // the ids still on screen and forgets the rest.
  list.addEventListener("oknowledge:list", function (event) {
    if (event.detail && event.detail.reason === "filter") { clear(); return; }
    var there = boxes().map(function (box) { return box.value; });
    picked = picked.filter(function (id) { return there.indexOf(id) >= 0; });
    draw();
  });

  // --- sending -------------------------------------------------------------------
  bar.addEventListener("submit", function (event) {
    event.preventDefault();
    submit(event.submitter);
  });

  function submit(submitter) {
    if (!picked.length) return;
    var url = (submitter && submitter.getAttribute("formaction")) || bar.getAttribute("action");
    bar.elements.back.value = location.pathname + location.search;
    var data = new FormData(bar, submitter || undefined);
    data.delete("ids");
    picked.forEach(function (id) { data.append("ids", id); });
    ok.closeMenus();
    var deleting = /\/bulk\/delete$/.test(url);
    var after = deleting ? pickAfter() : "";
    ok.send(url, data)
      .then(function (body) {
        clear();
        if (deleting) {
          ok.offerUndo(body.notice, body.undo, function (back) {
            ok.list.reload(back.restored && back.restored[0]);
          });
        } else {
          ok.toast(body.notice);
        }
        if (bar.elements.new_category) bar.elements.new_category.value = "";
        ok.list.reload(after);
      })
      .catch(function (error) {
        ok.toast(error.message);
        // All of them gone meanwhile: the list says so.
        if (error.status === 404) { clear(); ok.list.reload(); }
      });
  }

  // After a delete: the pick stays if it was not ticked; else the first
  // item after it that was not, else the one before.
  function pickAfter() {
    var id = ok.list.current();
    if (!id || picked.indexOf(id) < 0) return id;
    var items = ok.list.shown().map(function (li) { return li.id.replace(/^(card|idea)-/, ""); });
    var at = items.indexOf(id);
    for (var i = at + 1; i < items.length; i++) if (picked.indexOf(items[i]) < 0) return items[i];
    for (var j = at - 1; j >= 0; j--) if (picked.indexOf(items[j]) < 0) return items[j];
    return "";
  }

  // --- keys (spec §4) --------------------------------------------------------------
  // x: the picked item, when it has a box (an "Analysing…" one has not).
  ok.keys.x = function () {
    var id = ok.list && ok.list.current();
    var has = id && boxes().some(function (box) { return box.value === id; });
    if (!has) return false;
    toggle(id, picked.indexOf(id) < 0);
  };

  ok.keys.Backspace = ok.keys.Delete = function () {
    if (!picked.length) return false;
    submit(bar.querySelector('button[formaction="/bulk/delete"]'));
  };

  // Last in Esc's chain (app.js): no modal, no menu, no field.
  ok.keys.Escape = function () {
    if (!picked.length) return false;
    clear();
  };

  draw();
})();
```

The page's own delete in the panel (Task 9) still picks its neighbour; `pickAfter` is the bulk counterpart. With no pick left the panel keeps the deleted note until the reloaded list names its own `current`. That case is a whole list deleted, and Ruling 25 covers only the panel's delete.

- [ ] **Step 6: CSS and words**

Append to `app.css`:

```css
/* --- multi-selection (spec §5; handoff 03) ------------------------------------ */
.items .item { position: relative; }
.check { position: absolute; top: 8px; left: 8px; z-index: 2; display: grid; place-items: center;
  opacity: 0; transition: opacity .12s; }
.items .item:hover .check, .items .item.picked .check, .picking .check, .check:focus-within { opacity: 1; }
.check input { appearance: none; -webkit-appearance: none; width: 18px; height: 18px; margin: 0;
  border: 1.5px solid #55575f; border-radius: 5px; background: #17181dcc; cursor: pointer; }
.check input:checked { background: #e7e7ea url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 12 12'%3E%3Cpath d='M2.5 6.4l2.3 2.3 4.7-5' fill='none' stroke='%23141519' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E") center / 12px no-repeat;
  border-color: #e7e7ea; }
.check input:focus-visible { outline: 2px solid var(--acc); outline-offset: 1px; }
/* A row: the box takes the first column of "18px 8px 1fr auto" (Ruling 21). */
.rows .check { top: 50%; left: 10px; margin-top: -9px; }
.js .rows .hit { padding-left: 36px; }
.js .rows .sub .dot { left: 36px; }
.js .idea-shelf .rows .hit { padding-left: 54px; }
/* A poster: its kind chip moves right of the box while the box shows. */
.poster:hover .chip.kind, .poster.picked .chip.kind, .picking .poster .chip.kind { left: 34px; }

.center { position: relative; }
.bulk { position: absolute; left: 50%; bottom: 20px; transform: translateX(-50%); z-index: 20;
  display: flex; align-items: center; gap: 2px; padding: 6px; background: #24252c;
  border: 1px solid var(--b-menu); border-radius: 12px; box-shadow: var(--shadow);
  font-size: 13px; white-space: nowrap; }
.bulk[hidden] { display: none; }
.bulk-count { padding: 6px 10px; color: var(--t1); font-weight: 600; }
.bulk-sep { width: 1px; align-self: stretch; margin: 4px 4px; background: var(--b-menu); }
.bulk > button, .bulk summary { padding: 6px 10px; border: 0; border-radius: 7px; background: none;
  color: var(--t2); font: inherit; cursor: pointer; list-style: none; }
.bulk summary::-webkit-details-marker { display: none; }
.bulk > button:hover, .bulk summary:hover, .bulk details[open] summary { background: var(--s7); color: var(--t1); }
.bulk .bulk-star { color: var(--fav); }
.bulk .bulk-delete { color: var(--danger); }
.bulk .bulk-clear { color: var(--t5); }
.bulk .menu-list { bottom: calc(100% + 8px); left: 0; min-width: 200px; }
.bulk .menu-new { margin: 4px 6px 6px; }
```

Ledger: in `tests/test_packaging.py:95` the list becomes `["app.js", "autosave.js", "idea.js", "select.js", "settings.js", "shell.js"]`.

In `i18n.py`:

```python
        # Multi-selection (delivery 3, spec §5).
        "Select %1": "Seleccionar %1",
        "1 selected": "1 seleccionado",
        "%1 selected": "%1 seleccionados",
        "Move to": "Mover a",
        "Clear the selection": "Limpiar la selección",
```

- [ ] **Step 7: Run the tests**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_select.py tests/test_web_bulk.py tests/test_web_list_keys.py tests/test_web_layout.py tests/test_web_ocio_shelf.py tests/test_web_ideas_list.py tests/test_packaging.py tests/test_i18n.py`
Expected: PASS. The tests that find items with `<li class="item[^"]*" id="card-…"` still match: the box comes after the `<li>` tag.

- [ ] **Step 8: Check it in a browser (Review Focus 4)**

`$SP/pw/t10.js`:

```js
const { chromium } = require("playwright");
const BASE = "http://127.0.0.1:8812";
(async () => {
  const browser = await chromium.launch({ executablePath: "/usr/bin/chromium" });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const out = {};
  const settle = () => page.waitForLoadState("networkidle");
  const ids = () => page.$$eval('#items input[name="ids"]', (boxes) => boxes.map((b) => b.value));
  const count = () => page.textContent("#bulk [data-count]");
  const barShown = () => page.evaluate(() => !document.getElementById("bulk").hidden);
  await page.goto(BASE + "/");
  const all = await ids();
  // Tick two with the mouse: the bar says so, the panel did not change.
  const sel = new URL(page.url()).searchParams.get("sel");
  await page.hover(`#card-${all[1]}`);
  await page.check(`#card-${all[1]} input[name="ids"]`);
  await page.hover(`#card-${all[2]}`);
  await page.check(`#card-${all[2]} input[name="ids"]`);
  out.two = [await barShown(), await count(), new URL(page.url()).searchParams.get("sel") === sel];
  // x ticks the picked one; Esc clears.
  await page.keyboard.press("x");
  out.three = await count();
  await page.keyboard.press("Escape");
  out.cleared = !(await barShown());
  // The selection survives the poller's refresh and a view switch, and clears on a filter.
  await page.check(`#card-${all[1]} input[name="ids"]`);
  await page.keyboard.press("v"); await settle();
  out.survivesView = await page.isChecked(`#card-${all[1]} input[name="ids"]`);
  await page.keyboard.press("v"); await settle();
  await page.click(".sidebar a.filter:not(.on)"); await settle();
  out.clearsOnFilter = !(await barShown());
  // Review Focus 4: two ticked, one deleted meanwhile (another tab), then Move to.
  await page.goto(BASE + "/");
  await page.check(`#card-${all[3]} input[name="ids"]`);
  await page.check(`#card-${all[4]} input[name="ids"]`);
  await page.evaluate((id) => fetch(`/item/${id}/delete`, { method: "POST",
    headers: { Accept: "application/json" } }), all[4]);
  await page.click("#bulk summary");
  const target = await page.$eval("#bulk .menu-list button[name=category]", (b) => b.value);
  await page.click("#bulk .menu-list button[name=category]"); await settle();
  out.partial = await page.textContent("#toast .toast-text");
  out.movedOne = await page.evaluate(([id, cat]) =>
    document.querySelector(`#card-${id} .sub`).textContent.includes(cat), [all[3], target]);
  // Bulk ★ and bulk delete with ⌫, then Deshacer.
  await page.check(`#card-${all[5]} input[name="ids"]`);
  await page.check(`#card-${all[6]} input[name="ids"]`);
  await page.click("#bulk .bulk-star"); await settle();
  out.starred = await page.evaluate((ids) => ids.every((id) =>
    document.querySelector(`#card-${id} .flag.fav`)), [all[5], all[6]]);
  await page.check(`#card-${all[5]} input[name="ids"]`);
  await page.check(`#card-${all[6]} input[name="ids"]`);
  await page.locator("body").focus();
  await page.keyboard.press("Backspace"); await settle();
  out.deleted = await page.evaluate((ids) => ids.every((id) => !document.getElementById("card-" + id)),
                                    [all[5], all[6]]);
  out.undoText = await page.textContent("#toast button");
  await page.click("#toast button"); await settle();
  out.restored = await page.evaluate((ids) => ids.every((id) => !!document.getElementById("card-" + id)),
                                     [all[5], all[6]]);
  // Ocio and Ideas: the bar's own actions.
  await page.goto(BASE + "/ocio");
  const posters = await ids();
  await page.hover(`#card-${posters[0]}`);
  await page.check(`#card-${posters[0]} input[name="ids"]`);
  await page.click("#bulk summary");
  await page.click('#bulk button[name=kind][value="book"]'); await settle();
  out.ocioKind = await page.textContent("#toast .toast-text");
  await page.goto(BASE + "/ideas");
  const ideas = await ids();
  await page.hover(`#idea-${ideas[0]}`);
  await page.check(`#idea-${ideas[0]} input[name="ids"]`);
  await page.click("#bulk summary");
  await page.click('#bulk button[name=state][value="done"]'); await settle();
  out.ideaState = await page.textContent("#toast .toast-text");
  console.log(JSON.stringify(out));
  await browser.close();
})();
```

Run it as in Task 7 Step 6, with `node t10.js`. Expected values:
- `two`: `[true, "2 seleccionados", true]`; `three`: `"3 seleccionados"`; `cleared`, `survivesView`, `clearsOnFilter`: `true`;
- `partial`: `"1 movido a <target> · 1 no se pudo cambiar"` (Task 4's `bulk_words`); `movedOne`: `true`;
- `starred`, `deleted`, `restored`: `true`; `undoText`: `"Deshacer"`;
- `ocioKind` and `ideaState`: `"1 movido a "` followed by the kind's or the state's word (`bulk_words`' label).

If a value differs, fix `select.js`, the CSS or the bar and run again.

- [ ] **Step 9: Whole suite, commit**

```bash
git add src/oknowledge/web/static/select.js src/oknowledge/web/static/app.css \
        src/oknowledge/web/templates src/oknowledge/web/app.py src/oknowledge/i18n.py \
        tests/test_web_select.py tests/test_packaging.py
git commit -m "Tick several notes and act on them from a floating bar"
```

---
### Task 11: Leftovers from deliveries 1 and 2 (spec §9)

**Files:**
- Modify:
  - `src/oknowledge/web/static/shell.js`: `loadList`'s `.catch`, `more`, `watch`, the data-nav click and `setActive`.
  - `src/oknowledge/web/static/idea.js`: the tag box keeps the focus.
  - `src/oknowledge/web/templates/idea.html`: `id="tag-add"`.
- Create (scratch, not committed): `$SP/pw/t11.js`
- Test: `tests/test_web_leftovers.py` (new)

**Interfaces:**
- Consumes: `asked` (`loadList`'s counter), `timer` (the field's debounce) and `refresh()` in `idea.js`, which returns its promise.
- Produces: no new names. Each item of spec §9 is a guard in an existing function. The "+ tag" required and refocus in the panel and the one toast were done in Tasks 9 and 7.

- [ ] **Step 1: Write the failing tests**

`tests/test_web_leftovers.py`:

```python
"""Spec §9: what deliveries 1 and 2 left open in shell.js and idea.js. Each
is a guard on a race that a browser check cannot time reliably, so the
guard itself is what is pinned."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.vault import note_path, rebuild_indexes, write_note
from oknowledge.web.app import create_app

STATIC = Path(__file__).resolve().parent.parent / "src" / "oknowledge" / "web" / "static"
SHELL = STATIC / "shell.js"
IDEA = STATIC / "idea.js"


def between(text, start, end):
    head = text.index(start)
    return text[head:text.index(end, head)]


def test_a_failed_list_navigates_only_if_it_was_the_last_asked():
    body = between(SHELL.read_text(encoding="utf-8"), "function loadList", "function sideFilters")
    assert ".catch(function () { if (mine === asked) location.href = target.href; });" in body


def test_more_from_a_list_that_changed_since_is_dropped():
    body = between(SHELL.read_text(encoding="utf-8"), "function more", "// --- menus")
    assert "var mine = asked;" in body and "if (mine !== asked) return;" in body


def test_the_poller_stops_for_an_id_no_longer_on_screen():
    body = between(SHELL.read_text(encoding="utf-8"), "watched[id] = setInterval", 'fetch("/item/"')
    assert "onScreen(id)" in body and "clearInterval(watched[id])" in body


def test_a_filter_click_cancels_the_pending_search():
    text = SHELL.read_text(encoding="utf-8")
    assert re.search(r"clearTimeout\(timer\);[^\n]*\n\s*setActive\(link\);", text)


def test_a_link_outside_the_sidebar_leaves_its_highlight_alone():
    body = between(SHELL.read_text(encoding="utf-8"), "function setActive", "\n  }\n")
    assert body.index('if (!link.closest(".sidebar")) return;') < body.index("querySelectorAll")


def test_the_idea_tag_box_gets_the_focus_back():
    text = IDEA.read_text(encoding="utf-8")
    assert 'refresh(["idea-controls", "idea-tags"]).then(' in text
    assert 'getElementById("tag-add")' in text


@pytest.fixture
def client(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    idea = new_idea("Una idea.", "Idea", "2026-10-13", "2026-10-13T00:00:00.000001+00:00")
    write_note(cfg, idea, "es", path=note_path(cfg, idea, shelf=cfg.ideas))
    rebuild_indexes(cfg, "es", shelf=cfg.ideas)
    client = TestClient(create_app(cfg))
    client.idea = idea.id
    return client


def test_the_idea_tag_box_has_its_id(client):
    body = client.get(f"/ideas/{client.idea}").text
    assert re.search(r'<input name="add" id="tag-add" required', body)
```

- [ ] **Step 2: Run them to see them fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_leftovers.py`
Expected: FAIL on every test.

- [ ] **Step 3: `shell.js`**

1. In `loadList`, the last line becomes:

```js
      .catch(function () { if (mine === asked) location.href = target.href; });
```

2. In `more`, after `link.dataset.loading = "1";` add `var mine = asked;`. The first line of its success handler becomes:

```js
      .then(function (html) {
        // The list was drawn again meanwhile: this chunk belongs to the old one.
        if (mine !== asked) return;
```

3. In `watch`, add before the function:

```js
  // Still in the list or the panel: an id that left both (filtered out,
  // deleted) is not asked about any more.
  function onScreen(id) {
    var mark = '[data-working="' + CSS.escape(id) + '"]';
    return !!(list.querySelector(mark) || (panel && panel.querySelector(mark)));
  }
```

   and make the interval's first lines:

```js
      watched[id] = setInterval(function () {
        if (!onScreen(id)) { clearInterval(watched[id]); delete watched[id]; return; }
        fetch("/item/" + encodeURIComponent(id) + "/state")
```

4. In the click handler's last `else` (the data-nav branch):

```js
    } else {
      clearTimeout(timer);         // a search typed just before must not land after this
      setActive(link);
```

5. `setActive`:

```js
  function setActive(link) {
    // A sort link in the list head is not a filter: the sidebar keeps its row.
    if (!link.closest(".sidebar")) return;
    var apart = link.closest(".sidebar .group[data-apart]");
    (apart || document).querySelectorAll(apart ? ".filter.on" : ".sidebar .filter.on")
      .forEach(function (a) { a.classList.remove("on"); });
    link.classList.add("on");
  }
```

- [ ] **Step 4: `idea.js` and `idea.html`**

In `idea.js`, the submit handler's last branch becomes:

```js
        else refresh(["idea-controls", "idea-tags"]).then(function () {
          // "+ tag" again, for the next one (spec §9).
          if (!form.classList.contains("tag-new")) return;
          var box = document.getElementById("tag-add");
          if (box) box.focus();
        });
```

In `idea.html`, the "+ tag" input:

```html
        <input name="add" id="tag-add" required autocomplete="off" aria-label="{{ t('+ tag') }}" placeholder="{{ t('+ tag') }}">
```

- [ ] **Step 5: Run the tests**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_leftovers.py tests/test_web_shell_js.py tests/test_web_idea_scripts.py tests/test_web_idea_screen.py tests/test_packaging.py`
Expected: PASS.

- [ ] **Step 6: Check it in a browser**

`$SP/pw/t11.js`:

```js
const { chromium } = require("playwright");
const fs = require("fs");
const BASE = "http://127.0.0.1:8812";
const IDEA = fs.readFileSync(process.argv[2], "utf8").trim();
(async () => {
  const browser = await chromium.launch({ executablePath: "/usr/bin/chromium" });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const out = {};
  // Two tags in a row on an idea, without touching the mouse.
  await page.goto(BASE + "/ideas/" + IDEA);
  await page.click("#tag-add");
  for (const tag of ["uno", "dos"]) {
    const landed = page.waitForResponse((r) => r.url().includes("/tags"));
    await page.keyboard.type(tag);
    await page.keyboard.press("Enter");
    await landed;
    await page.waitForFunction((t) => document.getElementById("idea-tags").textContent.includes("#" + t), tag);
  }
  out.twoTags = await page.evaluate(() => document.activeElement.id);
  // A filter clicked while a search is pending: the filter wins.
  await page.goto(BASE + "/");
  await page.fill("#field-q", "wireguard");
  const filter = await page.$eval(".sidebar a.filter:not(.on)", (a) => a.getAttribute("href"));
  await page.click(".sidebar a.filter:not(.on)");
  await page.waitForTimeout(600);
  out.filterWins = new URL(page.url()).searchParams.get("q") === null;
  out.filterHref = filter.length > 0;
  console.log(JSON.stringify(out));
  await browser.close();
})();
```

Run it as in Task 7 Step 6, with `node t11.js "$SP/shots/idea"`. Expected: `{"twoTags":"tag-add","filterWins":true,"filterHref":true}`.

- [ ] **Step 7: Whole suite, commit**

```bash
git add src/oknowledge/web/static/shell.js src/oknowledge/web/static/idea.js \
        src/oknowledge/web/templates/idea.html tests/test_web_leftovers.py
git commit -m "Close the list races and keep the tag box focused, from the earlier deliveries"
```

---

### Task 12: The handoff's words, and the screenshots

**Files:**
- Modify: `tests/test_web_redesign_spanish.py` (append); whatever CSS the screenshots show is off (`src/oknowledge/web/static/app.css`); `src/oknowledge/i18n.py` if a word differs.
- Create (scratch, not committed): `$SP/pw/shots3.js`, `$SP/d3/*.png`

**Interfaces:**
- Consumes: everything above.
- Produces: no new names.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_web_redesign_spanish.py` (its `client` fixture is in Spanish):

```python
# --- delivery 3 (docs/2026-10-14-rediseno-modales-teclado-design.md §10) ----------

SETTINGS = ["Ajustes", "Los cambios se guardan solos", "Motores", "Idioma y guardado", "Importar",
            "Categorías", "Buscar modelos",
            "Se usan en orden, de arriba hacia abajo. Podés poner varios modelos separados por coma.",
            "¿Dónde se guarda esto?", "Idioma de los resúmenes", "Idioma de la interfaz",
            "Compartido con tus otros plugins de Omarchy", "Cambiarlo recarga la página",
            "Guardar por defecto", "Lo que se marca al pegar un link", "Menciones de un video",
            "Links a analizar por vez", "Cuántos procesa cada tanda",
            "Soltá acá el export de WhatsApp", "Elegir archivo", "Links esperando análisis: 0",
            "Ver actividad", "Si renombrás a una que ya existe, se unen.",
            "¿Unir «%1» con «%2»?"]

EVERY_PAGE = ["Atajos", "Atajos de teclado", "Buscar o pegar un link", "Biblioteca · Ocio · Ideas",
              "Anterior / siguiente", "Fila arriba / abajo", "Abrir original", "Favorito",
              "Agregar etiqueta", "Seleccionar", "Borrar seleccionados", "Lista / tarjetas",
              "Cerrar / deseleccionar", 'data-undo="Deshacer"', 'data-opening="Abriendo %1…"',
              "No se pudieron cargar los ajustes. Fijate que oknowledge siga andando."]

BULK = ['data-one="1 seleccionado"', 'data-many="%1 seleccionados"', "Mover a",
        "Nueva categoría", "★ Favorito", "Borrar", "Limpiar la selección",
        "Seleccionar WireGuard"]


@pytest.mark.parametrize("text", SETTINGS)
def test_settings_says_it_as_the_handoff_does(client, text):
    assert text in client.get("/settings/panel").text


@pytest.mark.parametrize("text", EVERY_PAGE)
def test_every_page_says_the_shortcuts_as_the_handoff_does(client, text):
    assert text in client.get("/").text


@pytest.mark.parametrize("text", BULK)
def test_the_selection_says_it_as_the_handoff_does(client, text):
    assert text in client.get("/").text


def test_deleting_and_undoing_say_it_as_the_spec_does(client):
    json = {"Accept": "application/json"}
    deleted = client.post("/item/l00000000001/delete", headers=json).json()
    assert deleted["notice"] == "Borrado"
    back = client.post(f"/undo/{deleted['undo']}", headers=json).json()
    assert back["notice"] == "Restaurado"
    again = client.post(f"/undo/{deleted['undo']}", headers=json)
    assert again.json()["error"] == "Ya no se puede deshacer"
```

- [ ] **Step 2: Run them**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_redesign_spanish.py`
Expected: PASS if every earlier task used the spec's words. A failure names the string: fix its entry in `i18n.py` (the spec's §10 words win) and run again. In Spanish the pane hint is "Cuántos procesa cada tanda", whose English key is "How many each batch takes" (Task 6).

- [ ] **Step 3: The screenshots**

`$SP/pw/shots3.js`:

```js
const { chromium } = require("playwright");
const OUT = process.argv[2];
const BASE = "http://127.0.0.1:8812";
(async () => {
  const browser = await chromium.launch({ executablePath: "/usr/bin/chromium" });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  // 03: three ticked in the library's cards, the bar at the bottom.
  await page.goto(BASE + "/?vista=tarjetas");
  const ids = await page.$$eval('#items input[name="ids"]', (b) => b.slice(0, 3).map((x) => x.value));
  for (const id of ids) { await page.hover(`#card-${id}`); await page.check(`#card-${id} input[name="ids"]`); }
  await page.mouse.move(700, 450);
  await page.screenshot({ path: `${OUT}/03.png` });
  await page.keyboard.press("Escape");
  // 07 and 08: the Settings modal on Motores, then on Idioma y guardado.
  await page.click('[data-modal="settings"]');
  await page.waitForSelector("#settings-modal .settings-body");
  await page.screenshot({ path: `${OUT}/07.png` });
  await page.click('#settings-modal a[data-settings-tab="idioma"]');
  await page.screenshot({ path: `${OUT}/08.png` });
  await page.keyboard.press("Escape");
  // 09: the shortcuts.
  await page.keyboard.press("?");
  await page.screenshot({ path: `${OUT}/09.png` });
  await browser.close();
})();
```

Run:

```bash
SP=/tmp/claude-1000/-home-fer-Projects-gym/d89ecc8a-2029-44cb-b47f-742ed00daeae/scratchpad
mkdir -p "$SP/d3"
rm -rf "$SP/shots/vault" "$SP/shots/state" "$SP/shots/config"
~/.local/share/oknowledge/venv/bin/python "$SP/shots/serve3.py" > "$SP/serve.log" 2>&1 &
echo $! > "$SP/serve.pid"
until curl -sf http://127.0.0.1:8812/ >/dev/null; do sleep 0.2; done
cd "$SP/pw" && node shots3.js "$SP/d3"
ps -p "$(cat "$SP/serve.pid")" -o args= | grep -q serve3.py && kill "$(cat "$SP/serve.pid")"
```

Expected: `$SP/d3/03.png`, `07.png`, `08.png` and `09.png` exist.

- [ ] **Step 4: Compare and fix**

Read each one beside its handoff image:
- `$SP/d3/03.png` with `design_handoff_oknowledge_redesign/screenshots/03-pantalla.png`;
- `07.png` with `07-pantalla.png`;
- `08.png` with `08-pantalla.png`;
- `09.png` with `09-pantalla.png`.

Check, in this order:
1. **Placement.** The bar sits bottom-centre of the middle column; the modal is centred; the help is 420 px wide.
2. **Sizes.** Settings is 640×520, with the head and the tabs fixed; checkboxes are 18 px.
3. **Colours.** Use the tokens in Global Constraints.
4. **Words.** Each one as in Step 1.

Fix the CSS in `app.css` and repeat Step 3 until the four match. Two differences are expected and stay:
- the four tabs (spec "¿Pestañas de Ajustes?": the handoff has three);
- the keys help's outlined `kbd` (Ruling 14).

- [ ] **Step 5: Whole suite, commit**

Run the suite; expected green, ≈2759 + this branch's new tests.

```bash
git add tests/test_web_redesign_spanish.py src/oknowledge/web/static/app.css src/oknowledge/i18n.py
git commit -m "Say delivery 3 in the handoff's words and match its screenshots"
```

---

## Self-review

- **Spec coverage.**
  - §1 shared scripts → Tasks 7, 8, 9 and 10.
  - §2 the toast → Tasks 3 and 7.
  - §3.1 Settings → Tasks 5, 6 and 8; §3.2 the shortcuts → Task 7.
  - §4 the keys → Tasks 7, 9 and 10.
  - §5 selection → Task 10; §5.1 bulk routes → Task 4.
  - §6 delete and undo → Tasks 1, 2, 3 and 9.
  - §7 the sidebar → Task 6; §8 without JS → Tasks 3, 6 and 10 (`.js-only`, the server toast's form, the Save buttons).
  - §9 leftovers → Tasks 7 (one toast), 9 (`required` and `#tag-add` in the panel) and 11.
  - §10 words → each task, then Task 12; §11 tests → each task's Step 1 and the browser checks.
  - Out of scope (phone, a trash browser, Shift ranges, the queue) is untouched.
- **Review Focus.** Each of the five has a named test in its owning task:
  1. Task 1's `restore_note` refusals and Task 3's `test_undo_after_the_note_was_*`;
  2. `test_a_lot_is_used_once` and `test_a_second_undo_is_gone`;
  3. the Task 7 harness and the Task 8 browser check;
  4. `test_bulk_*_with_an_id_deleted_meanwhile` and the Task 10 browser check;
  5. `test_the_modal_says_when_the_settings_cannot_be_loaded` and the Task 8 browser check.
- **Names that cross tasks:**
  - `Trashed`, `restore_note`, `rebuild=` (1 → 2, 3, 4);
  - `undo.remember`/`restore` (2 → 3, 4);
  - `answer(..., undo=, reload=)` (3 → 4, 5);
  - `delete_one` (3 → 4);
  - `settings_url`, `SETTINGS_TABS` (5 → 6);
  - the `data-settings-*` hooks (6 → 8);
  - `ok.toast`, `ok.send`, `ok.offerUndo`, `ok.keys`, `ok.closeMenus`, `ok.openModal` (7 → 8, 9, 10);
  - `ok.list`, `oknowledge:list` (9 → 10);
  - `#tag-add` (9, 11).

  Each is defined where its task's Interfaces says.
- **Ledger.** Every existing test this branch changes is named in the task that changes it:
  - `test_vault_edit` (1);
  - `test_web_write`, `test_web_ocio_panel`, `test_web_ideas_mine`, `test_web_idea_screen` and `test_web_panel` (3);
  - `test_web_write` (4);
  - `test_web_sidebar`, `test_web_retry`, `test_web_activity`, `test_web_layout` and `test_web_settings` (6);
  - `test_web_shell_js` and `test_packaging` (7, 8, 10).
- **No placeholders.** Every step has its code or its command, and every expected outcome is written out. The browser checks print one JSON line to compare.
- **Script order** on a page: `layout.js` (head, not deferred), then `app.js`, then `settings.js`, then the page's scripts (`autosave.js`, `shell.js`, `select.js`, `idea.js`). Each one extends `window.oknowledge` and never replaces it.
