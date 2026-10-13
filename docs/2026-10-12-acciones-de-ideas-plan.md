# Idea actions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Four buttons on an idea's page — Already out there?, Improve, Expand, Links that may help — each writing its own section into the idea's note. Every opencode run is sandboxed in bubblewrap.

**Architecture:** Engines gain an optional `search(prompt)` beside `complete(prompt)`. opencode and the Anthropic API implement it, and both prove that the model actually searched. Every opencode argv is wrapped by `sandboxed()`, which runs it under `bwrap` with an empty `/home` except opencode's own four folders. A pure module, `idea_actions.py`, renders prompts, validates the JSON answers and writes markdown sections. `pipeline.run_idea_action` follows the skeleton of `complete_idea`: model outside the lock, re-read under it, write one key. The web layer adds one POST route, an in-memory `Working` registry and a small safe markdown renderer.

**Tech Stack:** Python 3.12, FastAPI + Jinja2, httpx, pytest, bubblewrap.

**Spec:** `docs/2026-10-12-acciones-de-ideas-design.md`

## Global Constraints

- Code, routes, commits, CLI and docstrings in English; the UI goes through `t()` with a Spanish row in `i18n.py`.
- Never `datetime.utcnow()` / `utcfromtimestamp()`; dates come from `pipeline.today()`.
- No commit carries `Co-Authored-By`, `Claude-Session` or "Generated with Claude Code" lines.
- An API key is never printed, logged or put in an error message (`ApiEngine._redact`).
- Tests never touch the network and never launch real opencode or bwrap.
- Section headings: es `Ya existe` / `Mejoras` / `Ampliación` / `Links que pueden servir`; en `Already out there` / `Improvements` / `Expansion` / `Links that may help`.
- Caps: 8 matches, 8 improvements, 10 expansions, 10 suggestions, 60 candidates, 200 characters of summary per candidate.
- The bwrap error text: `opencode needs bubblewrap to run sandboxed: install it (pacman -S bubblewrap)`.
- The no-search error text: `the model did not search the web`.
- The chain-cannot-search error text: `no engine in the chain can search the web`.
- Suite command: `~/.local/share/oknowledge/venv/bin/python -m pytest -q` (2053 passing at the start).

## Review Focus

1. **A model that answers "new" without searching.** Expected: an error, never a section. Pinned in Task 2 (`test_search_without_a_search_tool_is_an_error`) and Task 3 (`test_api_search_without_a_search_result_is_an_error`).
2. **A section heading typed inside your own idea text** (`## Mejoras` under `Mi nota`). Expected: it stays your text. Pinned in Task 5 (`test_a_heading_inside_your_text_stays_yours`).
3. **A `javascript:` URL or raw HTML in a model answer or a hand-edited section.** Expected: shown as text, never as a link or markup. Pinned in Task 6 (`test_only_web_urls_survive`) and Task 8 (`test_a_section_cannot_inject_markup_or_script_links`).
4. **An idea deleted or edited while the model thinks.** Expected: it is not resurrected, and your edit survives. Pinned in Task 7.
5. **A suggestion whose link was renamed or deleted.** Expected: a dimmed row with no Add button. Pinned in Task 8 (`test_a_gone_suggestion_is_dimmed_and_cannot_be_added`).

---

### Task 1: Sandbox every opencode run

**Files:**
- Modify: `src/oknowledge/ai/opencode.py`
- Modify: `tests/test_engines.py` (one autouse fixture at the top)
- Test: `tests/test_opencode_sandbox.py` (create)

**Interfaces:**
- Produces: `NO_BWRAP: str`, `opencode_dirs() -> list[Path]`, `sandboxed(argv: list[str], cwd: str) -> list[str]` in `oknowledge.ai.opencode`; `OpenCodeEngine._run(argv: list[str]) -> subprocess.CompletedProcess`. `complete()` now runs `sandboxed(argv, cwd)`.

- [ ] **Step 1: Write the failing tests**

`tests/test_opencode_sandbox.py`:

```python
"""Every opencode run goes through bubblewrap.

opencode is an agent with bash and the network, and the prompt it gets
carries text from a web page. Restricting its tools from its own config
costs the free tier (measured: 403), so it is locked in from the outside:
an empty /home except opencode's own four folders.
"""

import subprocess
from pathlib import Path

import pytest

from oknowledge.ai.base import EngineError
from oknowledge.ai.opencode import NO_BWRAP, OpenCodeEngine, opencode_dirs, sandboxed

XDG = ("XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME")


@pytest.fixture
def home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    for var in XDG:
        monkeypatch.delenv(var, raising=False)
    return home


def which(found):
    return lambda name: found.get(name)


def pairs(argv, flag):
    """Every (source, target) mounted with `flag`."""
    return [(argv[i + 1], argv[i + 2]) for i, part in enumerate(argv) if part == flag]


ARGV = ["opencode", "run", "--pure", "-m", "opencode/x-free", "hola"]


def test_the_sandbox_runs_bwrap_and_ends_with_the_real_command(home, tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", which({"bwrap": "/usr/bin/bwrap",
                                               "opencode": "/usr/bin/opencode"}))
    argv = sandboxed(ARGV, str(tmp_path / "work"))
    assert argv[0] == "/usr/bin/bwrap"
    assert argv[-6:] == ["/usr/bin/opencode", "run", "--pure", "-m", "opencode/x-free", "hola"]
    for flag in ("--unshare-all", "--share-net", "--die-with-parent"):
        assert flag in argv


def test_the_home_is_empty_and_your_files_are_not_mounted(home, tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", which({"bwrap": "/usr/bin/bwrap",
                                               "opencode": "/usr/bin/opencode"}))
    argv = sandboxed(ARGV, str(tmp_path / "work"))
    tmpfs = [argv[j + 1] for j, part in enumerate(argv) if part == "--tmpfs"]
    assert tmpfs == ["/tmp", "/home"]
    mounted = [src for flag in ("--bind", "--ro-bind", "--ro-bind-try")
               for src, _ in pairs(argv, flag)]
    assert str(home) not in mounted
    for secret in (".config/oknowledge", ".ssh", "Projects"):
        assert not any(secret in src for src in mounted), secret


def test_opencode_keeps_its_own_four_folders_and_they_exist(home, tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", which({"bwrap": "/usr/bin/bwrap",
                                               "opencode": "/usr/bin/opencode"}))
    argv = sandboxed(ARGV, str(tmp_path / "work"))
    folders = [home / ".local/share/opencode", home / ".config/opencode",
               home / ".cache/opencode", home / ".local/state/opencode"]
    assert opencode_dirs() == folders
    for folder in folders:
        assert (str(folder), str(folder)) in pairs(argv, "--bind")
        assert folder.is_dir()


def test_the_xdg_variables_move_opencode_s_folders(home, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    assert opencode_dirs()[0] == tmp_path / "data" / "opencode"


def test_the_resolver_and_the_work_folder_are_mounted(home, tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", which({"bwrap": "/usr/bin/bwrap",
                                               "opencode": "/usr/bin/opencode"}))
    argv = sandboxed(ARGV, str(tmp_path / "work"))
    assert ("/run/systemd/resolve", "/run/systemd/resolve") in pairs(argv, "--ro-bind-try")
    assert (str(tmp_path / "work"), "/work") in pairs(argv, "--bind")
    assert argv[argv.index("--chdir") + 1] == "/work"
    assert argv[argv.index("--setenv") + 1:argv.index("--setenv") + 3] == ["HOME", str(home)]


def test_a_binary_outside_usr_has_its_folder_mounted_read_only(home, tmp_path, monkeypatch):
    binary = tmp_path / "mise" / "opencode" / "1.18.35" / "opencode"
    binary.parent.mkdir(parents=True)
    binary.write_text("")
    monkeypatch.setattr("shutil.which", which({"bwrap": "/usr/bin/bwrap",
                                               "opencode": str(binary)}))
    argv = sandboxed(ARGV, str(tmp_path / "work"))
    assert (str(binary.parent), str(binary.parent)) in pairs(argv, "--ro-bind")
    assert argv[-6] == str(binary)


def test_a_binary_under_usr_needs_no_extra_mount(home, tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", which({"bwrap": "/usr/bin/bwrap",
                                               "opencode": "/usr/bin/opencode"}))
    argv = sandboxed(ARGV, str(tmp_path / "work"))
    assert ("/usr/bin", "/usr/bin") not in pairs(argv, "--ro-bind")


def test_without_bwrap_it_refuses_with_the_way_to_install_it(home, tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", which({"opencode": "/usr/bin/opencode"}))
    with pytest.raises(EngineError) as raised:
        sandboxed(ARGV, str(tmp_path))
    assert str(raised.value) == NO_BWRAP
    assert "pacman -S bubblewrap" in NO_BWRAP


def test_without_opencode_it_says_so(home, tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", which({"bwrap": "/usr/bin/bwrap"}))
    with pytest.raises(EngineError, match="opencode is not installed.*'opencode'"):
        sandboxed(ARGV, str(tmp_path))


def test_complete_runs_inside_the_sandbox(monkeypatch):
    seen = {}

    def wrap(argv, cwd):
        seen["inner"] = argv
        return ["bwrap", "--", *argv]

    def run(argv, **kwargs):
        seen["ran"] = argv
        return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")

    monkeypatch.setattr("oknowledge.ai.opencode.sandboxed", wrap)
    monkeypatch.setattr("subprocess.run", run)
    assert OpenCodeEngine(model="opencode/x-free").complete("hola") == "ok"
    assert seen["ran"] == ["bwrap", "--", *seen["inner"]]
    assert seen["inner"][:5] == ["opencode", "run", "--pure", "-m", "opencode/x-free"]


def test_without_bwrap_opencode_is_never_launched(monkeypatch):
    def run(argv, **kwargs):
        raise AssertionError("opencode ran outside the sandbox")

    def refuse(argv, cwd):
        raise EngineError(NO_BWRAP)

    monkeypatch.setattr("oknowledge.ai.opencode.sandboxed", refuse)
    monkeypatch.setattr("subprocess.run", run)
    with pytest.raises(EngineError, match="bubblewrap"):
        OpenCodeEngine(model="opencode/x-free").complete("hola")
```

At the top of `tests/test_engines.py`, after the imports, add:

```python
@pytest.fixture(autouse=True)
def no_sandbox(monkeypatch):
    """These tests are about opencode's own argv and errors: the sandbox
    around it has its own file, test_opencode_sandbox.py."""
    monkeypatch.setattr("oknowledge.ai.opencode.sandboxed", lambda argv, cwd: argv)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest tests/test_opencode_sandbox.py -q`
Expected: collection ERROR, `ImportError: cannot import name 'NO_BWRAP'`.

- [ ] **Step 3: Implement**

In `src/oknowledge/ai/opencode.py`, replace the module docstring and imports with the following, and add the helpers after `LIST_TIMEOUT`:

```python
"""opencode, the engine that needs no credentials.

It is an agent, not a text service: it has bash and the network, and the
prompt it gets carries text from a web page. Restricting its tools from its
own config makes the free tier refuse it (measured: 403), so every run is
locked in from the outside, with bubblewrap: an empty /home except
opencode's own folders, an empty temporary directory to work in, --pure.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .base import EngineError, clean_models
```

```python
NO_BWRAP = "opencode needs bubblewrap to run sandboxed: install it (pacman -S bubblewrap)"

_XDG = (("XDG_DATA_HOME", ".local/share"), ("XDG_CONFIG_HOME", ".config"),
        ("XDG_CACHE_HOME", ".cache"), ("XDG_STATE_HOME", ".local/state"))


def opencode_dirs() -> list[Path]:
    """opencode's own four folders: its sessions, its config, its cache and
    its state. The only part of the home it gets to see."""
    home = Path.home()
    return [Path(os.environ.get(var) or home / default) / "opencode"
            for var, default in _XDG]


def sandboxed(argv: list[str], cwd: str) -> list[str]:
    """`argv` wrapped in bubblewrap.

    Only what opencode needs is mounted: the system read-only, the resolver
    the network needs, its own folders, the binary's folder and `cwd` as
    /work. Your vault, your projects, ~/.config/oknowledge with the API keys
    and ~/.ssh are not there at all -- there is nothing to read them from.
    """
    bwrap = shutil.which("bwrap")
    if bwrap is None:
        raise EngineError(NO_BWRAP)
    found = shutil.which(argv[0])
    if found is None:
        raise EngineError(f"opencode is not installed (no '{argv[0]}' on PATH)")
    # A mise shim points at the real executable, which is what gets mounted.
    binary = os.path.realpath(found)
    wrapped = [bwrap, "--unshare-all", "--share-net", "--die-with-parent",
               "--ro-bind", "/usr", "/usr", "--symlink", "usr/bin", "/bin",
               "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib", "/lib64",
               "--ro-bind", "/etc", "/etc",
               "--ro-bind-try", "/run/systemd/resolve", "/run/systemd/resolve",
               "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--tmpfs", "/home"]
    for folder in opencode_dirs():
        folder.mkdir(parents=True, exist_ok=True)
        wrapped += ["--bind", str(folder), str(folder)]
    where = os.path.dirname(binary)
    if not where.startswith("/usr/"):
        wrapped += ["--ro-bind", where, where]
    wrapped += ["--bind", cwd, "/work", "--chdir", "/work",
                "--setenv", "HOME", str(Path.home()), binary, *argv[1:]]
    return wrapped
```

Replace `OpenCodeEngine.complete` with a shared runner plus `complete`:

```python
    def _run(self, argv: list[str]) -> subprocess.CompletedProcess:
        """One run of opencode, inside the sandbox, with every way it can
        fail turned into an EngineError."""
        try:
            with tempfile.TemporaryDirectory() as cwd:
                # stdin must be closed: opencode blocks on an open non-TTY pipe.
                # stdout only is the answer; its header and ANSI codes go to stderr.
                return subprocess.run(
                    sandboxed(argv, cwd), cwd=cwd, capture_output=True, text=True,
                    timeout=self.timeout, stdin=subprocess.DEVNULL,
                )
        except FileNotFoundError as error:
            raise EngineError(f"opencode is not installed (no '{self.binary}' on PATH): {error}") from error
        except subprocess.TimeoutExpired as error:
            raise EngineError(f"opencode timed out after {self.timeout}s") from error
        except OSError as error:
            raise EngineError(f"opencode could not be run: {error}") from error

    def complete(self, prompt: str) -> str:
        proc = self._run([self.binary, "run", "--pure", "-m", self.model, prompt])
        if proc.returncode != 0:
            raise EngineError(f"opencode failed: {proc.stderr.strip()[:300]}")
        if not proc.stdout.strip():
            raise EngineError("opencode returned an empty answer")
        return proc.stdout
```

`models()` stays as it is: it sends no prompt, so there is nothing to lock in.

- [ ] **Step 4: Run them to verify they pass**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest tests/test_opencode_sandbox.py tests/test_engines.py tests/test_ai_models.py -q`
Expected: all pass.

- [ ] **Step 5: Mutation check**

Run each mutant against `tests/test_opencode_sandbox.py` and confirm each is killed:
- `'"--tmpfs", "/home"]'` → `'"--tmpfs", "/tmp"]'`
- `'if bwrap is None:'` → `'if False:'`
- `'sandboxed(argv, cwd), cwd=cwd'` → `'argv, cwd=cwd'`
- `'if not where.startswith("/usr/"):'` → `'if False:'`

Command shape: `~/.local/share/oknowledge/venv/bin/python /home/fer/.claude/jobs/d89ecc8a/tmp/mutate.py src/oknowledge/ai/opencode.py tests/test_opencode_sandbox.py 'OLD|||NEW'`

- [ ] **Step 6: Full suite and commit**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest -q`
Expected: all pass.

```bash
git add src/oknowledge/ai/opencode.py tests/test_opencode_sandbox.py tests/test_engines.py
git commit -m "fix: run opencode inside bubblewrap, with an empty home"
```

---

### Task 2: `search()` for opencode, ollama and the fake engine

**Files:**
- Modify: `src/oknowledge/ai/base.py` (the `Engine` protocol)
- Modify: `src/oknowledge/ai/opencode.py`
- Modify: `src/oknowledge/ai/ollama.py`
- Modify: `src/oknowledge/ai/fake.py`
- Test: `tests/test_engine_search.py` (create)

**Interfaces:**
- Consumes: `OpenCodeEngine._run`, `sandboxed` (Task 1).
- Produces: `Engine.searches: bool`, `Engine.search(prompt: str) -> str`; `NO_SEARCH = "the model did not search the web"` in `ai/base.py`; `parse_events(stdout: str) -> str` in `ai/opencode.py`; `OpenCodeEngine.searches = True`, `OllamaEngine.searches = False`, `FakeEngine.searches = True`.

- [ ] **Step 1: Write the failing tests**

`tests/test_engine_search.py`:

```python
"""Searching the web is a capability, not a mode of complete().

An engine that can search says so with `searches`. One that searches proves
it: a "nothing like this exists" from a model that never looked is worse
than no answer.
"""

import json
import subprocess

import pytest

from oknowledge.ai.base import NO_SEARCH, EngineError
from oknowledge.ai.fake import FakeEngine
from oknowledge.ai.ollama import OllamaEngine
from oknowledge.ai.opencode import OpenCodeEngine, parse_events


def event(**part):
    return json.dumps({"type": part.get("type", "text"), "part": part})


SEARCHED = event(type="tool", tool="websearch", state={"status": "completed"})
FETCHED = event(type="tool", tool="webfetch", state={"status": "completed"})
ANSWER = event(type="text", text='{"verdict": "new"}')


@pytest.fixture
def ran(monkeypatch):
    seen = {"stdout": "", "code": 0, "stderr": ""}

    def run(argv, **kwargs):
        seen["argv"] = argv
        return subprocess.CompletedProcess(argv, seen["code"], stdout=seen["stdout"],
                                           stderr=seen["stderr"])

    monkeypatch.setattr("oknowledge.ai.opencode.sandboxed", lambda argv, cwd: ["bwrap", *argv])
    monkeypatch.setattr("subprocess.run", run)
    return seen


def test_opencode_searches_and_ollama_does_not():
    assert OpenCodeEngine(model="m").searches is True
    assert OllamaEngine(model="q", url="http://x", ensure=lambda: None).searches is False


def test_opencode_search_asks_for_json_events_inside_the_sandbox(ran):
    ran["stdout"] = "\n".join([SEARCHED, ANSWER])
    assert OpenCodeEngine(model="opencode/x-free").search("busca") == '{"verdict": "new"}'
    assert ran["argv"][0] == "bwrap"
    assert ran["argv"][1:] == ["opencode", "run", "--pure", "--format", "json",
                               "-m", "opencode/x-free", "busca"]


def test_complete_does_not_ask_for_events(ran):
    ran["stdout"] = "plain"
    OpenCodeEngine(model="m").complete("hola")
    assert "--format" not in ran["argv"]


def test_the_answer_is_every_text_part_in_order():
    stdout = "\n".join([event(type="text", text="uno "), SEARCHED,
                        event(type="text", text="dos"), "not json", "[1]"])
    assert parse_events(stdout) == "uno dos"


def test_search_without_a_search_tool_is_an_error():
    with pytest.raises(EngineError) as raised:
        parse_events(ANSWER)
    assert str(raised.value) == NO_SEARCH


def test_a_fetch_counts_as_searching():
    assert parse_events("\n".join([FETCHED, ANSWER])) == '{"verdict": "new"}'


def test_a_search_that_failed_does_not_count():
    failed = event(type="tool", tool="websearch", state={"status": "error"})
    with pytest.raises(EngineError, match=NO_SEARCH):
        parse_events("\n".join([failed, ANSWER]))


def test_an_error_event_is_the_error_even_with_exit_one(ran):
    ran["code"] = 1
    ran["stdout"] = json.dumps({"type": "error", "error": {
        "name": "APIError", "data": {"message": "Upstream request failed: Endpoint is unavailable."}}})
    with pytest.raises(EngineError, match="opencode failed: Upstream request failed"):
        OpenCodeEngine(model="m").search("busca")


def test_a_failure_with_no_events_reports_stderr(ran):
    ran["code"] = 1
    ran["stderr"] = "boom"
    with pytest.raises(EngineError, match="opencode failed: boom"):
        OpenCodeEngine(model="m").search("busca")


def test_searching_with_no_text_is_an_empty_answer():
    with pytest.raises(EngineError, match="empty answer"):
        parse_events(SEARCHED)


def test_the_fake_engine_searches_with_its_replies():
    fake = FakeEngine(["uno", "dos"])
    assert fake.searches is True
    assert fake.search("p1") == "uno"
    assert fake.complete("p2") == "dos"
    assert fake.prompts == ["p1", "p2"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest tests/test_engine_search.py -q`
Expected: collection ERROR, `ImportError: cannot import name 'NO_SEARCH'`.

- [ ] **Step 3: Implement**

In `src/oknowledge/ai/base.py`, replace the `Engine` protocol with:

```python
NO_SEARCH = "the model did not search the web"
"""What an engine that can search says when its model answered without
looking. A "nothing like this exists" from memory is worse than no answer."""


class Engine(Protocol):
    name: str
    searches: bool
    """Whether search() exists: the engine can look things up on the web."""

    def complete(self, prompt: str) -> str: ...

    def search(self, prompt: str) -> str: ...
```

In `src/oknowledge/ai/opencode.py`, add `import json` to the imports, change `from .base import EngineError, clean_models` to `from .base import NO_SEARCH, EngineError, clean_models`, and add above the class:

```python
SEARCH_TOOLS = ("websearch", "webfetch")


def parse_events(stdout: str) -> str:
    """The answer in `opencode run --format json` output, once the model is
    seen to have searched.

    One JSON event per line. The answer is the text parts, in order; a
    search is a websearch or webfetch tool part that completed. An error
    event is the error, whatever else came before it.
    """
    texts: list[str] = []
    searched = False
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "error":
            error = event.get("error")
            data = error.get("data") if isinstance(error, dict) else None
            message = data.get("message") if isinstance(data, dict) else None
            raise EngineError(f"opencode failed: {str(message or error)[:300]}")
        part = event.get("part")
        if not isinstance(part, dict):
            continue
        if part.get("type") == "text" and isinstance(part.get("text"), str):
            texts.append(part["text"])
        elif (part.get("type") == "tool" and part.get("tool") in SEARCH_TOOLS
              and isinstance(part.get("state"), dict)
              and part["state"].get("status") == "completed"):
            searched = True
    text = "".join(texts).strip()
    if not searched:
        raise EngineError(NO_SEARCH)
    if not text:
        raise EngineError("opencode returned an empty answer")
    return text
```

In `OpenCodeEngine`, add `searches = True` below `name = "opencode"`, and add after `complete`:

```python
    def search(self, prompt: str) -> str:
        proc = self._run([self.binary, "run", "--pure", "--format", "json",
                          "-m", self.model, prompt])
        if proc.returncode != 0:
            # A refused model says why in an error event, which parse_events
            # raises. Anything else is stderr's to explain.
            try:
                parse_events(proc.stdout)
            except EngineError as error:
                if str(error).startswith("opencode failed:"):
                    raise
            raise EngineError(f"opencode failed: {proc.stderr.strip()[:300]}")
        return parse_events(proc.stdout)
```

In `src/oknowledge/ai/ollama.py`, add `searches = False` directly below the class's `name = "ollama"` line.

In `src/oknowledge/ai/fake.py`, add `searches = True` below `name = "fake"`, and add after `complete`:

```python
    def search(self, prompt: str) -> str:
        """The same replies as complete(): a test decides what was found."""
        return self.complete(prompt)
```

- [ ] **Step 4: Run them to verify they pass**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest tests/test_engine_search.py tests/test_engines.py -q`
Expected: all pass.

- [ ] **Step 5: Mutation check** (against `tests/test_engine_search.py`)

- `'searched = True'` → `'searched = False'`
- `'and part["state"].get("status") == "completed"):'` → `'):'`
- `'if str(error).startswith("opencode failed:"):'` → `'if False:'`
- `'"--format", "json",'` → `''`

- [ ] **Step 6: Full suite and commit**

```bash
git add src/oknowledge/ai/base.py src/oknowledge/ai/opencode.py src/oknowledge/ai/ollama.py src/oknowledge/ai/fake.py tests/test_engine_search.py
git commit -m "feat: engines that can search say so, and opencode proves it searched"
```

---

### Task 3: `search()` for the Anthropic API

**Files:**
- Modify: `src/oknowledge/ai/api.py`
- Test: `tests/test_api_search.py` (create)

**Interfaces:**
- Consumes: `NO_SEARCH` (Task 2).
- Produces: `ApiEngine.searches` (property: `self.protocol == "anthropic"`), `ApiEngine.search(prompt) -> str`, `SEARCH_TOOL` dict.

- [ ] **Step 1: Write the failing tests**

`tests/test_api_search.py`:

```python
"""The API engine searches only with Anthropic's own web search tool."""

import pytest

from oknowledge.ai.api import SEARCH_TOOL, ApiEngine
from oknowledge.ai.base import NO_SEARCH, EngineError

KEY = "sk-test-0123456789"


class Reply:
    def __init__(self, data, status=200):
        self._data = data
        self.status_code = status

    def json(self):
        return self._data


@pytest.fixture
def posted(monkeypatch):
    seen = {"reply": Reply({"content": [{"type": "text", "text": "hola"}]})}

    def post(url, headers=None, json=None, timeout=None):
        seen["body"] = json
        return seen["reply"]

    monkeypatch.setattr("httpx.post", post)
    return seen


def anthropic():
    return ApiEngine(provider="anthropic", model="claude-x", key=KEY)


def test_only_the_anthropic_protocol_searches():
    assert anthropic().searches is True
    assert ApiEngine(provider="groq", model="m", key=KEY).searches is False


def test_search_asks_for_the_web_search_tool(posted):
    posted["reply"] = Reply({"content": [
        {"type": "server_tool_use", "name": "web_search"},
        {"type": "web_search_tool_result", "content": []},
        {"type": "text", "text": "Encontré "},
        {"type": "text", "text": "dos."}]})
    assert anthropic().search("busca") == "Encontré dos."
    assert posted["body"]["tools"] == [SEARCH_TOOL]
    assert SEARCH_TOOL["type"] == "web_search_20250305"


def test_complete_never_sends_the_tool(posted):
    anthropic().complete("hola")
    assert "tools" not in posted["body"]


def test_api_search_without_a_search_result_is_an_error(posted):
    posted["reply"] = Reply({"content": [{"type": "text", "text": "de memoria"}]})
    with pytest.raises(EngineError) as raised:
        anthropic().search("busca")
    assert str(raised.value) == NO_SEARCH


def test_a_provider_that_cannot_search_says_so_without_calling(posted):
    with pytest.raises(EngineError, match="groq cannot search the web"):
        ApiEngine(provider="groq", model="m", key=KEY).search("busca")
    assert "body" not in posted


def test_the_key_never_reaches_a_search_error(posted):
    posted["reply"] = Reply({"error": {"message": f"bad key {KEY}"}}, status=401)
    with pytest.raises(EngineError) as raised:
        anthropic().search("busca")
    assert KEY not in str(raised.value)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest tests/test_api_search.py -q`
Expected: collection ERROR, `ImportError: cannot import name 'SEARCH_TOOL'`.

- [ ] **Step 3: Implement**

In `src/oknowledge/ai/api.py`, change `from .base import EngineError, clean_models` to `from .base import NO_SEARCH, EngineError, clean_models`, and add below `LIST_TIMEOUT`:

```python
SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search", "max_uses": 5}
"""Anthropic's own web search, run on their side. The openai-compatible
providers each have a variant of their own, and none is spoken here."""
```

Add to `ApiEngine`:

```python
    @property
    def searches(self) -> bool:
        return self.protocol == "anthropic"
```

Rename the body of `complete` to `_ask(self, prompt: str, search: bool) -> str` with these three changes, and make `complete` and `search` call it:

```python
    def complete(self, prompt: str) -> str:
        return self._ask(prompt, search=False)

    def search(self, prompt: str) -> str:
        if not self.searches:
            raise EngineError(f"{self.provider} cannot search the web")
        return self._ask(prompt, search=True)
```

Inside `_ask`:
1. After `body = {"model": self.model, "max_tokens": self.max_tokens, "messages": messages}` (the anthropic branch), add:
   ```python
            if search:
                body["tools"] = [SEARCH_TOOL]
   ```
2. Replace
   ```python
            if self.protocol == "anthropic":
                text = data["content"][0]["text"]
   ```
   with
   ```python
            if self.protocol == "anthropic" and search:
                # With a tool the answer is many blocks, cut around its
                # citations: content[0] is no longer the text.
                blocks = data["content"]
                if not any(b.get("type") == "web_search_tool_result" for b in blocks):
                    raise EngineError(NO_SEARCH)
                text = "".join(b["text"] for b in blocks if b.get("type") == "text")
            elif self.protocol == "anthropic":
                text = data["content"][0]["text"]
   ```

Everything else in `_ask` (the redaction, the error branches) stays exactly as it was in `complete`.

- [ ] **Step 4: Run them to verify they pass**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest tests/test_api_search.py tests/test_engines.py tests/test_providers.py -q`
Expected: all pass.

- [ ] **Step 5: Mutation check** (against `tests/test_api_search.py`)

- `'            if search:\n                body["tools"]'` → `'            if True:\n                body["tools"]'`
- `'if not any(b.get("type") == "web_search_tool_result" for b in blocks):'` → `'if False:'`
- `'text = "".join(b["text"] for b in blocks if b.get("type") == "text")'` → `'text = blocks[0]["text"]'`

- [ ] **Step 6: Full suite and commit**

```bash
git add src/oknowledge/ai/api.py tests/test_api_search.py
git commit -m "feat: the API engine searches with Anthropic's web search tool"
```

---

### Task 4: The chain asks or searches

**Files:**
- Modify: `src/oknowledge/ai/__init__.py`
- Test: `tests/test_chain_search.py` (create)

**Interfaces:**
- Consumes: `Engine.searches`, `Engine.search` (Tasks 2–3).
- Produces: `ask_with_chain(cfg, prompt: str, parse: Callable[[str], T]) -> tuple[T, str, str]`, `search_with_chain(cfg, prompt, parse) -> tuple[T, str, str]`, `can_search(cfg) -> bool`. Each tuple is (parsed result, engine name, model).

- [ ] **Step 1: Write the failing tests**

`tests/test_chain_search.py`:

```python
"""The chain, asked to think or to search."""

import pytest

from oknowledge.ai import AllEnginesFailed, ask_with_chain, can_search, search_with_chain
from oknowledge.ai.base import AnalysisError, EngineError
from oknowledge.config import Config


class Stub:
    def __init__(self, name, searches, reply="r", error=None):
        self.name, self.searches, self.reply, self.error = name, searches, reply, error
        self.model = f"{name}-1"
        self.calls = []

    def complete(self, prompt):
        self.calls.append(("complete", prompt))
        if self.error:
            raise self.error
        return self.reply

    def search(self, prompt):
        self.calls.append(("search", prompt))
        if self.error:
            raise self.error
        return self.reply


@pytest.fixture
def engines(monkeypatch):
    table = {}

    def build(name, cfg):
        if name not in table:
            raise EngineError(f"unknown engine: {name!r}")
        return table[name]

    monkeypatch.setattr("oknowledge.ai.build_engine", build)
    return table


def chain(tmp_path, *names):
    return Config(vault=tmp_path, chain=names)


def test_search_skips_the_engines_that_cannot_search(tmp_path, engines):
    engines["ollama"] = Stub("ollama", False)
    engines["opencode"] = Stub("opencode", True, reply="hallado")
    assert search_with_chain(chain(tmp_path, "ollama", "opencode"), "p", str.upper) == (
        "HALLADO", "opencode", "opencode-1")
    assert engines["ollama"].calls == []
    assert engines["opencode"].calls == [("search", "p")]


def test_a_chain_with_no_searcher_calls_nobody(tmp_path, engines):
    engines["ollama"] = Stub("ollama", False)
    with pytest.raises(AllEnginesFailed, match="no engine in the chain can search the web"):
        search_with_chain(chain(tmp_path, "ollama"), "p", str)
    assert engines["ollama"].calls == []


def test_ask_uses_complete_on_every_engine(tmp_path, engines):
    engines["ollama"] = Stub("ollama", False, reply="pensado")
    assert ask_with_chain(chain(tmp_path, "ollama"), "p", str)[0] == "pensado"
    assert engines["ollama"].calls == [("complete", "p")]


def test_a_useless_answer_falls_through_to_the_next_engine(tmp_path, engines):
    engines["a"] = Stub("a", True, reply="malo")
    engines["b"] = Stub("b", True, reply="bueno")

    def parse(reply):
        if reply == "malo":
            raise AnalysisError("no JSON")
        return reply

    assert search_with_chain(chain(tmp_path, "a", "b"), "p", parse)[:2] == ("bueno", "b")


def test_every_failure_is_named(tmp_path, engines):
    engines["a"] = Stub("a", True, error=EngineError("429"))
    with pytest.raises(AllEnginesFailed, match="a: 429"):
        search_with_chain(chain(tmp_path, "a"), "p", str)


def test_an_empty_chain_is_its_own_error(tmp_path, engines):
    with pytest.raises(AllEnginesFailed, match="chain is empty"):
        ask_with_chain(chain(tmp_path), "p", str)


def test_can_search_says_the_same_without_calling(tmp_path, engines):
    engines["ollama"] = Stub("ollama", False)
    engines["opencode"] = Stub("opencode", True)
    assert can_search(chain(tmp_path, "ollama")) is False
    assert can_search(chain(tmp_path, "ollama", "opencode")) is True
    assert can_search(chain(tmp_path, "nope")) is False
    assert engines["opencode"].calls == []
```

- [ ] **Step 2: Run them to verify they fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest tests/test_chain_search.py -q`
Expected: collection ERROR, `ImportError: cannot import name 'ask_with_chain'`.

- [ ] **Step 3: Implement**

In `src/oknowledge/ai/__init__.py`, add `from typing import TypeVar` to the imports, and append at the end of the file:

```python
T = TypeVar("T")


def _through_chain(cfg: Config, prompt: str, parse: Callable[[str], T],
                   web: bool) -> tuple[T, str, str]:
    """Each listed engine in order, until one answers something `parse`
    accepts. With `web`, only the engines that can search are asked, and
    they are asked to search."""
    if not cfg.chain:
        raise AllEnginesFailed("no engine is enabled: [ai] chain is empty")
    failures = []
    answered = False
    asked = False
    for name in cfg.chain:
        try:
            engine = build_engine(name, cfg)
            if web and not getattr(engine, "searches", False):
                continue
            asked = True
            reply = engine.search(prompt) if web else engine.complete(prompt)
            result = parse(reply)
        except AnalysisError as error:
            answered = True
            failures.append(f"{name}: {error}")
            continue
        except EngineError as error:
            failures.append(f"{name}: {error}")
            continue
        return result, name, str(getattr(engine, "model", ""))
    if web and not asked:
        raise AllEnginesFailed("no engine in the chain can search the web")
    raise AllEnginesFailed("every engine failed: " + "; ".join(failures),
                           answered=answered)


def ask_with_chain(cfg: Config, prompt: str,
                   parse: Callable[[str], T]) -> tuple[T, str, str]:
    """Ask the chain to think about `prompt`. Returns (parsed, engine, model)."""
    return _through_chain(cfg, prompt, parse, web=False)


def search_with_chain(cfg: Config, prompt: str,
                      parse: Callable[[str], T]) -> tuple[T, str, str]:
    """Ask the first engines of the chain that can search the web."""
    return _through_chain(cfg, prompt, parse, web=True)


def can_search(cfg: Config) -> bool:
    """Whether search_with_chain has anyone to ask. Calls no model: building
    an engine reads its config and nothing else."""
    for name in cfg.chain:
        try:
            if getattr(build_engine(name, cfg), "searches", False):
                return True
        except EngineError:
            continue
    return False
```

- [ ] **Step 4: Run them to verify they pass**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest tests/test_chain_search.py -q`
Expected: all pass.

- [ ] **Step 5: Mutation check** (against `tests/test_chain_search.py`)

- `'if web and not getattr(engine, "searches", False):\n                continue'` → `'if False:\n                continue'`
- `'reply = engine.search(prompt) if web else engine.complete(prompt)'` → `'reply = engine.complete(prompt)'`
- `'if web and not asked:'` → `'if False:'`
- `'            if getattr(build_engine(name, cfg), "searches", False):\n                return True'` → `'            if True:\n                return True'`

- [ ] **Step 6: Full suite and commit**

```bash
git add src/oknowledge/ai/__init__.py tests/test_chain_search.py
git commit -m "feat: the chain can be asked to search, by the engines that can"
```

---

### Task 5: An idea's sections in the note

**Files:**
- Modify: `src/oknowledge/model.py` (`Note.actions`)
- Modify: `src/oknowledge/vault.py` (`ACTIONS`, `ACTION_HEADINGS`, `render`, `_split_body`, `read_note`, `all_entries`)
- Test: `tests/test_idea_actions_vault.py` (create)

**Interfaces:**
- Produces: `Note.actions: dict[str, str]` (default `{}`); `ACTIONS = ("exists", "improve", "expand", "links")` and `ACTION_HEADINGS` in `oknowledge.vault`; `all_entries(cfg, shelf=None) -> list[tuple[Path, Note]]`.

- [ ] **Step 1: Write the failing tests**

`tests/test_idea_actions_vault.py`:

```python
"""An idea's action sections live in its note, between the points and
your text, as markdown you can edit in Obsidian."""

import pytest

from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.model import Note
from oknowledge.vault import (
    ACTION_HEADINGS, ACTIONS, all_entries, find_note, note_path, read_note,
    render, write_note,
)

INSTANT = "2026-10-12T21:04:05.123456+00:00"


@pytest.fixture
def cfg(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    return Config(vault=vault)


def idea(**fields):
    note = new_idea("Una app de rutinas.", "Gym", "2026-10-12", INSTANT)
    note.points = ["Para quien entrena solo."]
    for key, value in fields.items():
        setattr(note, key, value)
    return note


def roundtrip(cfg, note, language="es"):
    path = write_note(cfg, note, language, path=note_path(cfg, note, shelf=cfg.ideas))
    return read_note(path), path


def test_the_four_actions_and_their_headings():
    assert ACTIONS == ("exists", "improve", "expand", "links")
    assert ACTION_HEADINGS["es"] == {"exists": "Ya existe", "improve": "Mejoras",
                                     "expand": "Ampliación",
                                     "links": "Links que pueden servir"}
    assert ACTION_HEADINGS["en"] == {"exists": "Already out there",
                                     "improve": "Improvements", "expand": "Expansion",
                                     "links": "Links that may help"}


@pytest.mark.parametrize("language", ["es", "en"])
def test_every_section_comes_back(cfg, language):
    sections = {"exists": "**Hay parecidas.**\n\n- [X](https://x.com) — igual",
                "improve": "- **Lento** — cachear", "expand": "- Modo offline",
                "links": "*Entre: Redes.*\n\n- [[2026-10-02-vpn]] — sirve"}
    after, _ = roundtrip(cfg, idea(actions=dict(sections)), language)
    assert after.actions == sections
    assert after.my_note == "Una app de rutinas."
    assert after.points == ["Para quien entrena solo."]


def test_sections_sit_after_the_points_and_before_your_text(cfg):
    _, path = roundtrip(cfg, idea(actions={"improve": "- a", "exists": "b"}))
    text = path.read_text(encoding="utf-8")
    order = [text.index(h) for h in ("## Puntos clave", "## Ya existe", "## Mejoras", "## Mi nota")]
    assert order == sorted(order)


def test_an_idea_without_actions_writes_no_heading(cfg):
    assert render(idea(), "es") == render(idea(actions={"improve": "  "}), "es")
    assert "## Mejoras" not in render(idea(), "es")


def test_a_heading_inside_your_text_stays_yours(cfg):
    mine = "Primero esto.\n\n## Mejoras\n\n- mía"
    after, _ = roundtrip(cfg, idea(my_note=mine))
    assert after.my_note == mine
    assert after.actions == {}


def test_a_card_keeps_a_typed_heading_in_its_summary(cfg):
    card = Note(id="aaaaaaaaaaaa", url="https://imdb.com/title/tt1", title="T",
                category="Películas", tags=[], type="movie", source="imdb.com",
                saved="2026-10-11", summary="Un cyborg.\n\n## Mejoras\n\n- nada")
    path = write_note(cfg, card, "es", path=note_path(cfg, card, shelf=cfg.ocio))
    after = read_note(path)
    assert "## Mejoras" in after.summary
    assert after.actions == {}


def test_a_hand_edited_section_survives_another_action(cfg):
    note, path = roundtrip(cfg, idea(actions={"improve": "- a mano"}))
    note.actions["expand"] = "- nueva"
    write_note(cfg, note, "es", path=path)
    assert read_note(path).actions == {"improve": "- a mano", "expand": "- nueva"}


def test_all_entries_pairs_each_note_with_its_file(cfg):
    note, path = roundtrip(cfg, idea())
    assert all_entries(cfg, cfg.ideas) == [(path, find_note(cfg, note.id, shelf=cfg.ideas)[1])]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest tests/test_idea_actions_vault.py -q`
Expected: collection ERROR, `ImportError: cannot import name 'ACTION_HEADINGS'`.

- [ ] **Step 3: Implement**

In `src/oknowledge/model.py`, add to `Note` after `related`:

```python
    actions: dict[str, str] = field(default_factory=dict)
    """An idea's action sections -- Already out there, Improvements,
    Expansion, Links that may help -- each as the markdown in the file,
    keyed by vault.ACTIONS. Text and not structure, for the reason my_note
    is: you can edit them in Obsidian, and an edit has to survive the app
    reading the note and writing it back. Only an idea has them."""
```

In `src/oknowledge/vault.py`, below `HEADINGS`:

```python
ACTIONS = ("exists", "improve", "expand", "links")
"""What can be asked about an idea, in the order its sections are written."""

ACTION_HEADINGS = {
    "es": {"exists": "Ya existe", "improve": "Mejoras", "expand": "Ampliación",
           "links": "Links que pueden servir"},
    "en": {"exists": "Already out there", "improve": "Improvements",
           "expand": "Expansion", "links": "Links that may help"},
}
```

Next to `_MINE_HEADINGS`:

```python
_ACTION_HEADINGS = {f"## {heading}": action for table in ACTION_HEADINGS.values()
                    for action, heading in table.items()}
```

In `render`, directly after the `if note.points:` block:

```python
    # Before Mi nota: in an idea that section runs to the end of the file.
    named = ACTION_HEADINGS.get(language, ACTION_HEADINGS["en"])
    for action in ACTIONS:
        text = note.actions.get(action, "").strip()
        if text:
            parts.append(f"## {named[action]}\n\n{text}\n")
```

Change `_split_body`:
- The signature becomes `def _split_body(body: str, mine_to_end: bool = False, actions: bool = False) -> tuple[str, list[str], list[Mention] | None, list[str], str, str | None, dict[str, str]]:`. Add to its docstring: `` `actions` reads an idea's action sections; anywhere else those headings are just text. ``
- Before the loop, add `found: dict[str, list[str]] = {}` and `current: list[str] = []`.
- Directly after the `if mode == "mine" and mine_to_end:` branch, add:
  ```python
        elif actions and mode != "content" and marker in _ACTION_HEADINGS:
            mode = "action"
            current = found.setdefault(_ACTION_HEADINGS[marker], [])
  ```
- Directly before the final `else: original.append(line)`, add:
  ```python
        elif mode == "action":
            current.append(line)
  ```
- The return becomes:
  ```python
    sections = {action: "\n".join(lines).strip() for action, lines in found.items()}
    return ("\n".join(summary).strip(), points, mentions, extra,
            "\n".join(mine).strip(), content or None,
            {action: text for action, text in sections.items() if text})
  ```

In `read_note`, replace the `_split_body` call and add the field:

```python
    is_idea = required["type"] == "idea"
    summary, points, mentions, extra, mine, body, actions = _split_body(
        rest, mine_to_end=is_idea, actions=is_idea)
```

and pass `actions=actions,` to `Note(...)`.

Below `all_notes`:

```python
def all_entries(cfg: Config, shelf: Shelf | None = None) -> list[tuple[Path, Note]]:
    """Every readable note on the shelf with the file it is in: the file
    name is what a wikilink to it says."""
    return _scan(cfg, shelf)[0]
```

- [ ] **Step 4: Run them to verify they pass**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest tests/test_idea_actions_vault.py tests/test_vault.py tests/test_ideas_vault.py -q`
Expected: all pass.

- [ ] **Step 5: Mutation check** (against `tests/test_idea_actions_vault.py`)

- `'elif actions and mode != "content" and marker in _ACTION_HEADINGS:'` → `'elif mode != "content" and marker in _ACTION_HEADINGS:'`
- `'        rest, mine_to_end=is_idea, actions=is_idea)'` → `'        rest, mine_to_end=is_idea, actions=False)'`
- `'        if text:\n            parts.append(f"## {named[action]}'` → `'        if True:\n            parts.append(f"## {named[action]}'`
- `'        elif mode == "action":\n            current.append(line)'` → `'        elif mode == "action":\n            pass'`

- [ ] **Step 6: Full suite and commit**

```bash
git add src/oknowledge/model.py src/oknowledge/vault.py tests/test_idea_actions_vault.py
git commit -m "feat: an idea's action sections are read and written with its note"
```

---

### Task 6: The four actions — prompts, answers and sections

**Files:**
- Create: `src/oknowledge/idea_actions.py`
- Create: `src/oknowledge/prompts/idea-exists.txt`, `idea-improve.txt`, `idea-expand.txt`, `idea-links.txt`
- Test: `tests/test_idea_actions.py` (create)

**Interfaces:**
- Consumes: `ask_with_chain`, `search_with_chain` (Task 4); `ACTIONS`, `all_entries`, `Note.actions` (Task 5); `extract_json`, `_is_placeholder`, `LANGUAGE_NAMES`, `AnalysisError` from `ai/base.py`.
- Produces: `compose(cfg, note, action: str, category: str, day: str) -> tuple[str, str, str]` (section markdown, engine, model; engine and model are `""` when no model was asked); `render_action_prompt(action, note, language, candidates="") -> str`; `candidates(note, entries, category) -> list[tuple[Path, Note]]`; the parsers `exists_found`, `exists_section`, `improve_section`, `expand_section`, `links_section`, `no_candidates`.

- [ ] **Step 1: Write the failing tests**

`tests/test_idea_actions.py`:

```python
"""What each action asks, and what of the answer is kept.

The model answers JSON; the app writes the markdown. Nothing the model
says reaches the note without passing through here.
"""

import json
from pathlib import Path

import pytest

from oknowledge import idea_actions as acts
from oknowledge.ai.base import AnalysisError
from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.model import Note

INSTANT = "2026-10-12T21:04:05.123456+00:00"


def idea(text="Una app que arme la rutina del gimnasio.", title="Gym con IA", **fields):
    note = new_idea(text, title, "2026-10-12", INSTANT)
    note.tags, note.summary = ["gimnasio"], "Rutinas solas."
    for key, value in fields.items():
        setattr(note, key, value)
    return note


def link(n, title, category="Salud", summary="", tags=()):
    return (Path(f"/v/links/2026-10-0{n}-{title.lower().replace(' ', '-')}.md"),
            Note(id=f"{n:012d}", url=f"https://e.com/{n}", title=title, category=category,
                 tags=list(tags), type="article", source="e.com", saved=f"2026-10-0{n}",
                 summary=summary))


# --- prompts ------------------------------------------------------------------

@pytest.mark.parametrize("action", ["exists", "improve", "expand", "links"])
def test_every_prompt_carries_the_idea(action):
    prompt = acts.render_action_prompt(action, idea(), "es", candidates="c1")
    assert "Una app que arme la rutina del gimnasio." in prompt
    assert "Gym con IA" in prompt and "gimnasio" in prompt and "Rutinas solas." in prompt
    assert "español" in prompt
    assert "{{" not in prompt


def test_a_text_that_looks_like_a_placeholder_is_not_substituted():
    prompt = acts.render_action_prompt("improve", idea(text="{{TITLE}} literal"), "es")
    assert "{{TITLE}} literal" in prompt


def test_the_links_prompt_lists_the_candidates():
    assert "id1 | WireGuard" in acts.render_action_prompt("links", idea(), "es",
                                                          candidates="id1 | WireGuard")


# --- already out there --------------------------------------------------------

def found(**data):
    return acts.exists_found(data)


def test_the_verdict_matches_and_difference_are_written():
    text = acts.exists_section(found(
        verdict="similar",
        matches=[{"name": "Linkwise", "url": "https://linkwise.app/", "note": "resume links"}],
        difference="La tuya arma rutinas."), "es", "2026-10-12", "opencode/mimo")
    assert text.splitlines()[0] == "**Hay parecidas.** Buscado el 2026-10-12 con opencode/mimo."
    assert "- [Linkwise](https://linkwise.app/) — resume links" in text
    assert text.splitlines()[-1] == "**Lo tuyo:** La tuya arma rutinas."


def test_an_unknown_verdict_counts_as_similar():
    assert found(verdict="maybe", matches=[]).verdict == "similar"


def test_only_web_urls_survive():
    kept = found(verdict="exists", matches=[
        {"name": "a", "url": "javascript:alert(1)"}, {"name": "b", "url": "file:///etc"},
        {"name": "c", "url": "https://ok.com/x y"}, {"name": "d", "url": "https://ok.com/d"},
        {"name": "e)", "url": "https://ok.com/e)"}]).matches
    assert [m[0] for m in kept] == ["d"]


def test_at_most_eight_matches_and_placeholders_dropped():
    many = [{"name": f"n{i}", "url": f"https://e.com/{i}"} for i in range(12)]
    assert len(found(verdict="similar", matches=many).matches) == 8
    assert found(verdict="similar", matches=[{"name": "<nombre>", "url": "https://e.com"}]).matches == []


def test_new_with_nothing_says_so_in_english_too():
    text = acts.exists_section(found(verdict="new", matches=[]), "en", "2026-10-12", "m")
    assert text.startswith("**I found nothing like it.** Searched on 2026-10-12 with m.")


def test_an_answer_with_no_verdict_and_no_matches_is_no_use():
    with pytest.raises(AnalysisError):
        found(difference="x")


def test_a_bracket_in_a_name_cannot_break_the_link():
    text = acts.exists_section(found(verdict="exists", matches=[
        {"name": "a]b", "url": "https://e.com"}]), "es", "d", "m")
    assert "[a\\]b](https://e.com)" in text


# --- improve and expand -------------------------------------------------------

def test_improvements_are_weak_point_and_fix():
    assert acts.improve_section({"items": [{"weak": "Lento", "fix": "cachear"},
                                           {"fix": "solo el arreglo"}]}) == (
        "- **Lento** — cachear\n- solo el arreglo")


def test_improvements_are_capped_at_eight():
    items = [{"weak": f"w{i}", "fix": f"f{i}"} for i in range(11)]
    assert len(acts.improve_section({"items": items}).splitlines()) == 8


def test_expansion_is_a_list_capped_at_ten():
    assert acts.expand_section({"items": [f"idea {i}" for i in range(14)]}).count("\n- ") == 9


@pytest.mark.parametrize("data", [{}, {"items": []}, {"items": "x"}, {"items": [3, None]}])
def test_an_empty_or_malformed_list_is_no_use(data):
    with pytest.raises(AnalysisError):
        acts.improve_section(data)
    with pytest.raises(AnalysisError):
        acts.expand_section(data)


# --- links --------------------------------------------------------------------

def test_candidates_keep_the_category_drop_the_related_and_rank_by_shared_words():
    entries = [link(1, "Recetas", category="Cocina", summary="gimnasio rutina"),
               link(2, "Rutina de fuerza", summary="rutina gimnasio progresión"),
               link(3, "Dormir mejor", summary="sueño"),
               link(4, "Ya sumado", summary="rutina gimnasio")]
    note = idea(related=[entries[3][0].stem])
    chosen = acts.candidates(note, entries, "Salud")
    assert [n.title for _, n in chosen] == ["Rutina de fuerza", "Dormir mejor"]
    assert [n.title for _, n in acts.candidates(note, entries, "")][0] in (
        "Rutina de fuerza", "Recetas")


def test_candidates_are_capped_at_sixty():
    entries = [link(1, f"L{i}") for i in range(70)]
    assert len(acts.candidates(idea(), entries, "")) == 60


def test_a_candidate_line_is_id_title_category_and_a_short_summary():
    line = acts.candidate_lines([link(1, "WireGuard", category="Redes", summary="x" * 300)])
    assert line == "000000000001 | WireGuard | Redes | " + "x" * 200


def test_suggestions_keep_only_known_ids_with_their_file_name():
    allowed = {"000000000001": "2026-10-01-wireguard"}
    text = acts.links_section({"links": [{"id": "000000000001", "why": "es la vpn"},
                                         {"id": "inventado", "why": "x"},
                                         {"id": "000000000001", "why": "repetido"}]},
                              allowed, "Redes", "es")
    assert text == "*Entre: Redes.*\n\n- [[2026-10-01-wireguard]] — es la vpn"


def test_none_fitting_is_said_not_failed():
    assert acts.links_section({"links": []}, {}, "Redes", "es") == (
        "*Entre: Redes.*\n\nNinguno de estos links le sirve a la idea.")


def test_suggestions_are_capped_at_ten():
    allowed = {str(i): f"s{i}" for i in range(15)}
    text = acts.links_section({"links": [{"id": str(i), "why": ""} for i in range(15)]},
                              allowed, "Redes", "es")
    assert text.count("[[") == 10


def test_a_links_answer_without_links_is_no_use():
    with pytest.raises(AnalysisError):
        acts.links_section({"other": 1}, {}, "Redes", "es")


# --- compose ------------------------------------------------------------------

class Engine:
    model = "fake-1"

    def __init__(self, reply, searches=True):
        self.reply, self.searches, self.calls = reply, searches, []

    def complete(self, prompt):
        self.calls.append(("complete", prompt))
        return self.reply

    def search(self, prompt):
        self.calls.append(("search", prompt))
        return self.reply


@pytest.fixture
def cfg(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    return Config(vault=vault, chain=("fake",))


@pytest.fixture
def engine(monkeypatch):
    holder = Engine(json.dumps({"items": ["Modo offline"]}))
    monkeypatch.setattr("oknowledge.ai.build_engine", lambda name, cfg: holder)
    return holder


def test_exists_searches_and_signs_with_the_model(cfg, engine):
    engine.reply = json.dumps({"verdict": "new", "matches": []})
    text, used, model = acts.compose(cfg, idea(), "exists", "", "2026-10-12")
    assert engine.calls[0][0] == "search"
    assert "Buscado el 2026-10-12 con fake-1." in text
    assert (used, model) == ("fake", "fake-1")


def test_expand_thinks_without_searching(cfg, engine):
    text, _, _ = acts.compose(cfg, idea(), "expand", "", "2026-10-12")
    assert engine.calls[0][0] == "complete"
    assert text == "- Modo offline"


def test_links_with_no_candidates_asks_nobody(cfg, engine):
    text, used, model = acts.compose(cfg, idea(), "links", "Cocina", "2026-10-12")
    assert engine.calls == []
    assert text == "*Entre: Cocina.*\n\nNo hay links en Cocina que no estén ya relacionados."
    assert (used, model) == ("", "")


def test_links_offers_the_library_and_writes_the_file_name(cfg, engine):
    from oknowledge.vault import write_note
    path = write_note(cfg, link(1, "WireGuard", category="Redes")[1], "es")
    engine.reply = json.dumps({"links": [{"id": "000000000001", "why": "la vpn"}]})
    text, _, _ = acts.compose(cfg, idea(), "links", "", "2026-10-12")
    assert "000000000001 | WireGuard | Redes" in engine.calls[0][1]
    assert text == f"*Entre: tu biblioteca.*\n\n- [[{path.stem}]] — la vpn"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest tests/test_idea_actions.py -q`
Expected: collection ERROR, `ModuleNotFoundError: No module named 'oknowledge.idea_actions'`.

- [ ] **Step 3: Write the four prompts**

`src/oknowledge/prompts/idea-exists.txt`:

```
Sos alguien que investiga si una idea ya existe. Te doy una idea tal como
alguien la escribió. Buscá en internet con tu herramienta de búsqueda —no
contestes de memoria— si ya hay algo que haga lo mismo o algo parecido:
apps, productos, proyectos de código abierto, servicios.

Respondé ÚNICAMENTE con un objeto JSON, sin texto antes ni después, con esta forma
(lo que está entre <> es lo que tenés que reemplazar por tu respuesta):

{
  "verdict": "<exists, similar o new>",
  "matches": [{"name": "<nombre>", "url": "<la URL que encontraste>", "note": "<en qué se parece, una frase>"}],
  "difference": "<en qué se diferencia la idea de lo que encontraste, una o dos frases>"
}

"exists" si encontraste algo que hace lo mismo; "similar" si hay cosas
parecidas pero no iguales; "new" si no encontraste nada parecido. Hasta 8
resultados, el más parecido primero, cada uno con la URL que encontraste:
no inventes URLs. Todo el texto va en {{LANGUAGE}}.

El título: {{TITLE}}
Las etiquetas: {{TAGS}}
El resumen: {{SUMMARY}}

La idea:

{{TEXT}}
```

`src/oknowledge/prompts/idea-improve.txt`:

```
Sos alguien que ayuda a mejorar ideas. Te doy una idea tal como alguien la
escribió. Señalá sus puntos débiles —lo que no está resuelto, lo que puede
fallar, lo que nadie pagaría— y para cada uno proponé cómo resolverlo.

Respondé ÚNICAMENTE con un objeto JSON, sin texto antes ni después, con esta forma
(lo que está entre <> es lo que tenés que reemplazar por tu respuesta):

{
  "items": [{"weak": "<el punto débil, pocas palabras>", "fix": "<cómo resolverlo, una o dos frases>"}]
}

De 3 a 8 ítems, el más importante primero. Concretos para esta idea, no
consejos que sirven para cualquiera. Todo el texto va en {{LANGUAGE}}.

El título: {{TITLE}}
Las etiquetas: {{TAGS}}
El resumen: {{SUMMARY}}

La idea:

{{TEXT}}
```

`src/oknowledge/prompts/idea-expand.txt`:

```
Sos alguien que ayuda a ampliar ideas. Te doy una idea tal como alguien la
escribió. Proponé lo que no escribió y podría sumarle: funciones, públicos,
usos, próximos pasos para probarla.

Respondé ÚNICAMENTE con un objeto JSON, sin texto antes ni después, con esta forma
(lo que está entre <> es lo que tenés que reemplazar por tu respuesta):

{
  "items": ["<una propuesta, una o dos frases>"]
}

De 3 a 10 ítems. Nada que la idea ya diga. Todo el texto va en {{LANGUAGE}}.

El título: {{TITLE}}
Las etiquetas: {{TAGS}}
El resumen: {{SUMMARY}}

La idea:

{{TEXT}}
```

`src/oknowledge/prompts/idea-links.txt`:

```
Sos alguien que ayuda a conectar ideas con lo que ya se leyó. Te doy una
idea y una lista de links guardados, uno por línea, con la forma
"id | título | categoría | resumen". Elegí los que le sirven a la idea:
porque resuelven parte de ella, porque son competencia, porque enseñan algo
que hace falta para hacerla.

Respondé ÚNICAMENTE con un objeto JSON, sin texto antes ni después, con esta forma
(lo que está entre <> es lo que tenés que reemplazar por tu respuesta):

{
  "links": [{"id": "<el id tal cual está en la lista>", "why": "<por qué le sirve, una frase>"}]
}

Hasta 10, el que más sirve primero. Sólo ids de la lista. Si ninguno sirve,
"links" va vacío. Todo el texto va en {{LANGUAGE}}.

El título: {{TITLE}}
Las etiquetas: {{TAGS}}
El resumen: {{SUMMARY}}

La idea:

{{TEXT}}

Los links:

{{CANDIDATES}}
```

- [ ] **Step 4: Write `src/oknowledge/idea_actions.py`**

```python
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
```

- [ ] **Step 5: Run them to verify they pass**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest tests/test_idea_actions.py -q`
Expected: all pass.

- [ ] **Step 6: Mutation check** (against `tests/test_idea_actions.py`)

- `'if not name or not isinstance(url, str) or not _WEB_URL.fullmatch(url.strip()):'` → `'if not name:'`
- `'and path.stem not in note.related]'` → `']'`
- `'if stem is None or stem in seen:'` → `'if False:'`
- `'return sorted(pool, key=shared, reverse=True)[:MAX_CANDIDATES]'` → `'return pool[:MAX_CANDIDATES]'`
- `'        if not pool:\n            return no_candidates'` → `'        if False:\n            return no_candidates'`
- `'found, engine, model = ai.search_with_chain('` → `'found, engine, model = ai.ask_with_chain('`

- [ ] **Step 7: Full suite and commit**

```bash
git add src/oknowledge/idea_actions.py src/oknowledge/prompts/idea-*.txt tests/test_idea_actions.py
git commit -m "feat: the four idea actions, from prompt to section"
```

---

### Task 7: Running one action on an idea

**Files:**
- Modify: `src/oknowledge/pipeline.py`
- Test: `tests/test_pipeline_idea_actions.py` (create)

**Interfaces:**
- Consumes: `compose` (Task 6), `Note.actions` (Task 5).
- Produces: `run_idea_action(cfg, idea: str, action: str, category: str = "", trace: Tracer | None = None) -> str | None`. It returns `None` when the section was written, and otherwise the reason it was not, as text for the page. It raises `ValueError` for an unknown action.

- [ ] **Step 1: Write the failing tests**

`tests/test_pipeline_idea_actions.py`:

```python
"""One action on one idea, behind the page.

The model is asked outside the lock; the idea is read again under it and
only that action's section is written. Everything else in the note --
your text above all -- is as you left it.
"""

import json

import pytest

from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.pipeline import run_idea_action
from oknowledge.queue import Locked
from oknowledge.vault import find_note, note_path, write_note

INSTANT = "2026-10-12T21:04:05.123456+00:00"


@pytest.fixture(autouse=True)
def state_tree(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))


@pytest.fixture
def cfg(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    return Config(vault=vault, chain=("fake",))


def put(cfg, **fields):
    note = new_idea("Una app de rutinas.", "Gym", "2026-10-12", INSTANT)
    for key, value in fields.items():
        setattr(note, key, value)
    path = write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ideas))
    return note, path


def now(cfg, note):
    return find_note(cfg, note.id, shelf=cfg.ideas)


@pytest.fixture
def engine(monkeypatch):
    class Faker:
        model = "fake-1"
        searches = True

        def __init__(self):
            self.reply = json.dumps({"items": ["Modo offline"]})
            self.meanwhile = None
            self.used = []

        def _answer(self, how):
            self.used.append(how)
            if self.meanwhile is not None:
                self.meanwhile()
            return self.reply

        def complete(self, prompt):
            return self._answer("complete")

        def search(self, prompt):
            return self._answer("search")

    faker = Faker()
    monkeypatch.setattr("oknowledge.ai.build_engine", lambda name, cfg: faker)
    return faker


def test_an_action_writes_its_own_section(cfg, engine):
    note, _ = put(cfg)
    assert run_idea_action(cfg, note.id, "expand") is None
    assert now(cfg, note)[1].actions == {"expand": "- Modo offline"}


def test_nothing_else_in_the_idea_changes(cfg, engine):
    note, _ = put(cfg, state="doing", score=4, related=["2026-10-02-vpn"],
                  tags=["gym"], summary="Rutinas.", points=["Uno."])
    run_idea_action(cfg, note.id, "expand")
    after = now(cfg, note)[1]
    assert (after.my_note, after.title, after.tags, after.summary, after.points,
            after.related, after.state, after.score) == (
        "Una app de rutinas.", "Gym", ["gym"], "Rutinas.", ["Uno."],
        ["2026-10-02-vpn"], "doing", 4)


def test_another_action_s_section_is_kept(cfg, engine):
    note, _ = put(cfg, actions={"improve": "- a mano"})
    run_idea_action(cfg, note.id, "expand")
    assert now(cfg, note)[1].actions == {"improve": "- a mano", "expand": "- Modo offline"}


def test_asking_again_replaces_only_that_section(cfg, engine):
    note, _ = put(cfg, actions={"expand": "- viejo"})
    run_idea_action(cfg, note.id, "expand")
    assert now(cfg, note)[1].actions["expand"] == "- Modo offline"


def test_exists_searches(cfg, engine):
    engine.reply = json.dumps({"verdict": "new", "matches": []})
    note, _ = put(cfg)
    assert run_idea_action(cfg, note.id, "exists") is None
    assert engine.used == ["search"]


def test_an_idea_deleted_while_the_model_thinks_is_not_resurrected(cfg, engine):
    note, path = put(cfg)
    engine.meanwhile = path.unlink
    assert run_idea_action(cfg, note.id, "expand") == "the idea is no longer there"
    assert now(cfg, note) is None


def test_text_you_typed_while_it_thought_survives(cfg, engine):
    note, path = put(cfg)

    def edit():
        fresh = now(cfg, note)[1]
        fresh.my_note = "Lo cambié mientras pensaba."
        write_note(cfg, fresh, "es", path=path)

    engine.meanwhile = edit
    run_idea_action(cfg, note.id, "expand")
    after = now(cfg, note)[1]
    assert after.my_note == "Lo cambié mientras pensaba."
    assert after.actions == {"expand": "- Modo offline"}


def test_a_useless_answer_leaves_the_file_as_it_was(cfg, engine):
    note, path = put(cfg, actions={"expand": "- viejo"})
    before = path.read_bytes()
    engine.reply = "no json at all"
    problem = run_idea_action(cfg, note.id, "expand")
    assert problem and "fake" in problem
    assert path.read_bytes() == before


def test_a_busy_idea_says_so(cfg, engine, monkeypatch):
    class Busy:
        def lock(self, link):
            raise Locked(link)

    monkeypatch.setattr("oknowledge.pipeline.Queue", Busy)
    note, _ = put(cfg)
    assert run_idea_action(cfg, note.id, "expand") == "the idea was busy: ask again"


def test_a_missing_idea_asks_nobody(cfg, engine):
    assert run_idea_action(cfg, "nope", "expand") == "the idea is no longer there"
    assert engine.used == []


def test_an_unknown_action_is_a_programming_error(cfg, engine):
    note, _ = put(cfg)
    with pytest.raises(ValueError):
        run_idea_action(cfg, note.id, "delete")


def test_it_is_traced_start_and_end(cfg, engine):
    note, _ = put(cfg)
    steps = []
    run_idea_action(cfg, note.id, "expand", trace=steps.append)
    assert [(s.name, s.state) for s in steps] == [("expand", "start"), ("expand", "ok")]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest tests/test_pipeline_idea_actions.py -q`
Expected: collection ERROR, `ImportError: cannot import name 'run_idea_action'`.

- [ ] **Step 3: Implement**

In `src/oknowledge/pipeline.py`, add `from .idea_actions import compose as compose_action` beside `from .ideas import clean_title`, and add `ACTIONS` to the `from .vault import (...)` list. Then add after `retitle_idea`:

```python
def run_idea_action(cfg: Config, idea: str, action: str, category: str = "",
                    trace: Tracer | None = None) -> str | None:
    """One action on one idea, behind the page: None when its section is
    written, otherwise why not, in words the page can show.

    The skeleton of complete_idea(): the model outside the lock, the idea
    read again under it, and only this action's section written. Two
    actions on one idea can run at once for that reason -- each writes its
    own key into what it has just read.
    """
    if action not in ACTIONS:
        raise ValueError(f"no such action: {action!r}")
    tell = guarded(trace or SILENT)
    found = find_note(cfg, idea, shelf=cfg.ideas)
    if found is None:
        return "the idea is no longer there"
    clock = time.monotonic()
    tell(Step(link=idea, name=action, state="start", seconds=0.0))

    def failed(why: str) -> str:
        tell(Step(link=idea, name=action, state="fail",
                  seconds=time.monotonic() - clock, detail=why))
        return why

    try:
        text, engine, model = compose_action(cfg, found[1], action, category, today())
    except AllEnginesFailed as error:
        return failed(str(error))
    try:
        with Queue().lock(idea):
            fresh = find_note(cfg, idea, shelf=cfg.ideas)
            if fresh is None:
                # Thrown away in the meantime: writing would resurrect it.
                return failed("the idea is no longer there")
            path, note = fresh
            note.actions[action] = text
            write_note(cfg, note, cfg.language, path=path)
    except Locked:
        return failed("the idea was busy: ask again")
    except (OSError, ProtectedNote) as error:
        return failed(str(error))
    tell(Step(link=idea, name=action, state="ok",
              seconds=time.monotonic() - clock, engine=engine, detail=model))
    return None
```

Confirm that `AllEnginesFailed`, `ProtectedNote`, `write_note` and `find_note` are already imported in `pipeline.py` (`complete_idea` uses all four). Add any that are missing to the existing import lines.

- [ ] **Step 4: Run them to verify they pass**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest tests/test_pipeline_idea_actions.py -q`
Expected: all pass.

- [ ] **Step 5: Mutation check** (against `tests/test_pipeline_idea_actions.py`)

- `'            if fresh is None:\n                # Thrown away in the meantime: writing would resurrect it.\n                return failed'` → `'            if False:\n                # Thrown away in the meantime: writing would resurrect it.\n                return failed'`
- `'            path, note = fresh\n            note.actions[action] = text'` → `'            path, note = found\n            note.actions[action] = text'`
- `'    if found is None:\n        return "the idea is no longer there"\n    clock'` → `'    if False:\n        return "the idea is no longer there"\n    clock'`

- [ ] **Step 6: Full suite and commit**

```bash
git add src/oknowledge/pipeline.py tests/test_pipeline_idea_actions.py
git commit -m "feat: run one action on an idea, writing only its section"
```

---

### Task 8: The buttons on the idea's page

**Files:**
- Create: `src/oknowledge/web/working.py`
- Create: `src/oknowledge/web/markup.py`
- Modify: `src/oknowledge/web/app.py`
- Modify: `src/oknowledge/web/templates/item.html`
- Modify: `src/oknowledge/web/static/style.css`
- Modify: `src/oknowledge/i18n.py`
- Modify: `tests/test_web_write.py` (`WRITE_ROUTES`, `VAULT_WRITERS`)
- Test: `tests/test_web_idea_actions.py` (create)

**Interfaces:**
- Consumes: `run_idea_action` (Task 7), `can_search` (Task 4), `ACTIONS`, `normalize_related` (vault).
- Produces: `POST /item/{id}/actions/{action}` (form field `category`); `POST /item/{link}/ideas` gains the form field `back` (`"idea"` returns to the idea); `app.state.working` is a `Working`; notices `thinking` and `cannot-search`.

- [ ] **Step 1: Write the failing tests**

`tests/test_web_idea_actions.py`:

```python
"""The four buttons on an idea's page, and what they show."""

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.model import Note
from oknowledge.vault import find_note, note_path, rebuild_indexes, write_note
from oknowledge.web.app import create_app
from oknowledge.web.markup import blocks, inline, split_suggestions
from oknowledge.web.working import Working

LINK = "bbbbbbbbbbbb"


@pytest.fixture(autouse=True)
def state_tree(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr("oknowledge.web.app.CONFIG_PATH",
                        tmp_path / "config" / "config.toml")


def make(tmp_path, chain=("opencode",)):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True, exist_ok=True)
    cfg = Config(vault=vault, chain=chain)
    rebuild_indexes(cfg, "es")
    return cfg


@pytest.fixture
def cfg(tmp_path):
    return make(tmp_path)


@pytest.fixture
def ran(monkeypatch):
    calls = []
    outcome = {"problem": None}

    def run(cfg, idea, action, category="", trace=None):
        calls.append((idea, action, category))
        return outcome["problem"]

    monkeypatch.setattr("oknowledge.web.app.run_idea_action", run)
    return calls, outcome


def put(cfg, **fields):
    note = new_idea("x", "VPN propia", "2026-10-12", "2026-10-12T00:00:00.000001+00:00")
    for key, value in fields.items():
        setattr(note, key, value)
    write_note(cfg, note, "es", path=note_path(cfg, note, shelf=cfg.ideas))
    return note


def a_link(cfg):
    path = write_note(cfg, Note(id=LINK, url="https://wireguard.com", title="WireGuard",
                                category="Redes", tags=[], type="article",
                                source="wireguard.com", saved="2026-10-10",
                                summary="Una vpn."), "es")
    rebuild_indexes(cfg, "es")
    return path


# --- the route ------------------------------------------------------------------

def test_a_button_queues_its_action_and_says_it_is_thinking(cfg, ran):
    note = put(cfg)
    reply = TestClient(create_app(cfg)).post(f"/item/{note.id}/actions/improve",
                                             follow_redirects=False)
    assert reply.status_code == 303
    assert reply.headers["location"] == f"/item/{note.id}?notice=thinking"
    assert ran[0] == [(note.id, "improve", "")]


def test_links_carries_the_category(cfg, ran):
    note = put(cfg)
    TestClient(create_app(cfg)).post(f"/item/{note.id}/actions/links",
                                     data={"category": "Redes"})
    assert ran[0] == [(note.id, "links", "Redes")]


def test_an_unknown_action_is_404(cfg, ran):
    note = put(cfg)
    assert TestClient(create_app(cfg)).post(
        f"/item/{note.id}/actions/delete").status_code == 404
    assert ran[0] == []


def test_a_missing_idea_goes_back_to_the_ideas(cfg, ran):
    reply = TestClient(create_app(cfg)).post("/item/nope/actions/improve",
                                             follow_redirects=False)
    assert reply.headers["location"] == "/ideas?notice=no-such-idea"
    assert ran[0] == []


def test_exists_without_a_searcher_is_refused_up_front(tmp_path, ran):
    cfg = make(tmp_path, chain=("ollama",))
    note = put(cfg)
    reply = TestClient(create_app(cfg)).post(f"/item/{note.id}/actions/exists",
                                             follow_redirects=False)
    assert reply.headers["location"] == f"/item/{note.id}?notice=cannot-search"
    assert ran[0] == []


def test_a_second_click_while_it_runs_queues_nothing(cfg, ran):
    note = put(cfg)
    app = create_app(cfg)
    app.state.working.start(note.id, "improve")
    TestClient(app).post(f"/item/{note.id}/actions/improve")
    assert ran[0] == []


# --- the registry ---------------------------------------------------------------

def test_working_runs_one_of_each_and_remembers_the_last_failure():
    working = Working()
    assert working.start("i", "improve") is True
    assert working.start("i", "improve") is False
    assert working.start("i", "expand") is True
    assert working.of("i") == ({"improve", "expand"}, {})
    working.finish("i", "improve", "boom")
    assert working.of("i") == ({"expand"}, {"improve": "boom"})
    assert working.start("i", "improve") is True
    working.finish("i", "improve", None)
    assert working.of("i")[1] == {}
    assert working.of("other") == (set(), {})


# --- the page -------------------------------------------------------------------

def page(cfg, note, app=None):
    return TestClient(app or create_app(cfg)).get(f"/item/{note.id}").text


def test_the_four_buttons_are_there(cfg):
    note = put(cfg)
    text = page(cfg, note)
    for action in ("exists", "improve", "expand", "links"):
        assert f'action="/item/{note.id}/actions/{action}"' in text


def test_a_running_action_says_thinking_and_is_disabled(cfg):
    note = put(cfg)
    app = create_app(cfg)
    app.state.working.start(note.id, "expand")
    assert "thinking…" in page(cfg, note, app)


def test_the_last_failure_is_shown_and_cleared_by_a_success(cfg, ran):
    note = put(cfg)
    app = create_app(cfg)
    client = TestClient(app)
    ran[1]["problem"] = "opencode: 429"
    client.post(f"/item/{note.id}/actions/improve")
    assert "Last time it failed: opencode: 429" in client.get(f"/item/{note.id}").text
    ran[1]["problem"] = None
    client.post(f"/item/{note.id}/actions/improve")
    assert "Last time it failed" not in client.get(f"/item/{note.id}").text


def test_exists_is_disabled_with_its_reason_when_nobody_searches(tmp_path):
    cfg = make(tmp_path, chain=("ollama",))
    note = put(cfg)
    assert "No engine in your chain searches the web" in page(cfg, note)


def test_exists_is_offered_when_the_chain_searches(cfg):
    note = put(cfg)
    assert "No engine in your chain searches the web" not in page(cfg, note)


def test_a_section_with_text_is_drawn_under_its_heading(cfg):
    note = put(cfg, actions={"improve": "- **Lento** — cachear"})
    text = page(cfg, note)
    assert "Improvements" in text
    assert "<strong>Lento</strong> — cachear" in text
    assert "Ask again" in text


def test_a_section_cannot_inject_markup_or_script_links(cfg):
    note = put(cfg, actions={"exists": "<script>x</script> [mal](javascript:alert(1)) "
                                       "[bien](https://ok.com)"})
    text = page(cfg, note)
    assert "<script>x</script>" not in text
    assert 'href="javascript:' not in text
    assert '<a href="https://ok.com" target="_blank" rel="noreferrer">bien</a>' in text


def test_a_suggestion_offers_add_to_the_idea(cfg):
    path = a_link(cfg)
    note = put(cfg, actions={"links": f"*Entre: Redes.*\n\n- [[{path.stem}]] — la vpn"})
    text = page(cfg, note)
    assert f'action="/item/{LINK}/ideas"' in text
    assert f'name="idea" value="{note.id}"' in text
    assert 'name="back" value="idea"' in text
    assert "la vpn" in text


def test_a_suggestion_already_linked_offers_nothing(cfg):
    path = a_link(cfg)
    note = put(cfg, related=[path.stem],
               actions={"links": f"- [[{path.stem}]] — la vpn"})
    text = page(cfg, note)
    assert "already linked" in text
    assert 'name="back" value="idea"' not in text


def test_a_gone_suggestion_is_dimmed_and_cannot_be_added(cfg):
    note = put(cfg, actions={"links": "- [[2026-01-01-borrado]] — ya no está"})
    text = page(cfg, note)
    assert "2026-01-01-borrado" in text
    assert 'name="back" value="idea"' not in text


def test_the_category_picker_lists_the_library(cfg):
    a_link(cfg)
    note = put(cfg)
    assert '<option value="Redes">Redes</option>' in page(cfg, note)


def test_add_from_the_idea_goes_back_to_the_idea(cfg):
    path = a_link(cfg)
    note = put(cfg)
    reply = TestClient(create_app(cfg)).post(
        f"/item/{LINK}/ideas", data={"idea": note.id, "back": "idea"},
        follow_redirects=False)
    assert reply.headers["location"].startswith(f"/item/{note.id}")
    assert find_note(cfg, note.id, shelf=cfg.ideas)[1].related == [path.stem]


def test_add_from_the_link_still_goes_back_to_the_link(cfg):
    a_link(cfg)
    note = put(cfg)
    reply = TestClient(create_app(cfg)).post(
        f"/item/{LINK}/ideas", data={"idea": note.id}, follow_redirects=False)
    assert reply.headers["location"].startswith(f"/item/{LINK}")


# --- the markup -----------------------------------------------------------------

def test_inline_escapes_first_and_links_only_the_web():
    assert str(inline("<b>[x](https://e.com/?a=1&b=2)</b>")) == (
        '&lt;b&gt;<a href="https://e.com/?a=1&amp;b=2" target="_blank" '
        'rel="noreferrer">x</a>&lt;/b&gt;')
    assert "<a" not in str(inline("[x](data:text/html,hi)"))
    assert str(inline("**a** and *b*")) == "<strong>a</strong> and <em>b</em>"


def test_blocks_group_bullets_into_one_list():
    drawn = blocks("**Hay.** Buscado.\n\n- uno\n- dos\n\n*Entre: Redes.*")
    assert [kind for kind, _ in drawn] == ["p", "ul", "p"]
    assert [str(item) for item in drawn[1][1]] == ["uno", "dos"]
    assert str(drawn[2][1]) == "<em>Entre: Redes.</em>"


def test_suggestions_are_split_from_the_rest():
    other, rows = split_suggestions(
        "*Entre: Redes.*\n\n- [[a/2026-x.md|alias]] — porque\n- [[b]]\nNinguno.")
    assert rows == [("2026-x", "porque"), ("b", "")]
    assert other == "*Entre: Redes.*\n\nNinguno."
```

In `tests/test_web_write.py`, add to `WRITE_ROUTES` (beside the other idea routes):

```python
    # Asking the model about an idea. A cross-site POST here would spend the
    # user's quota and write a section into one of their ideas.
    ("/item/a1/actions/improve", {}),
```

and add `"run_idea_action"` to `VAULT_WRITERS`.

- [ ] **Step 2: Run them to verify they fail**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest tests/test_web_idea_actions.py -q`
Expected: collection ERROR, `ModuleNotFoundError: No module named 'oknowledge.web.markup'`.

- [ ] **Step 3: Write `src/oknowledge/web/working.py`**

```python
"""Which actions are running on which idea, and how the last one ended.

In memory, like Batch: a run only exists while this process does, so a
restart leaves nothing to explain and every button free again.
"""

from __future__ import annotations

import threading


class Working:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._running: set[tuple[str, str]] = set()
        self._failed: dict[tuple[str, str], str] = {}

    def start(self, idea: str, action: str) -> bool:
        """Claim the run. False means that action is already running there."""
        with self._lock:
            if (idea, action) in self._running:
                return False
            self._running.add((idea, action))
            return True

    def finish(self, idea: str, action: str, problem: str | None) -> None:
        with self._lock:
            self._running.discard((idea, action))
            if problem:
                self._failed[(idea, action)] = problem
            else:
                self._failed.pop((idea, action), None)

    def of(self, idea: str) -> tuple[set[str], dict[str, str]]:
        """(the actions running on this idea, the last failure of each)."""
        with self._lock:
            return ({action for i, action in self._running if i == idea},
                    {action: why for (i, action), why in self._failed.items() if i == idea})
```

- [ ] **Step 4: Write `src/oknowledge/web/markup.py`**

```python
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
```

- [ ] **Step 5: Wire the route and the page in `src/oknowledge/web/app.py`**

Imports:
- extend `from ..ai import build_engine` to `from ..ai import build_engine, can_search`;
- extend `from ..pipeline import complete_idea, retitle_idea, today` with `run_idea_action`;
- add `from ..vault import ACTIONS`;
- add `from .markup import blocks, split_suggestions` and `from .working import Working`.

In `NOTICES`:

```python
    # An idea's action: it runs behind the page, like a card's summary.
    "thinking": "Thinking it over. Reload in a moment to read it.",
    "cannot-search": "No engine in your chain searches the web: "
                     "opencode or the Anthropic API do.",
```

Module level, beside `STATE_WORDS`:

```python
ACTION_TITLES = {"exists": "Already out there", "improve": "Improvements",
                 "expand": "Expansion", "links": "Links that may help"}
"""Each section's heading on the page. The note's own headings are
vault.ACTION_HEADINGS, in the content language; these follow the UI."""
ACTION_BUTTONS = {"exists": "Already out there?", "improve": "Improve",
                  "expand": "Expand", "links": "Links that may help"}
```

In `create_app`, after `progress = Batch()`:

```python
    # Which idea actions are running, and how each one last ended. In memory
    # and per process, like the batch.
    working = Working()
    app.state.working = working
```

In `item()`, inside `if where.name == "ideas":`, after `extra["related"] = ...`:

```python
            running, failed = working.of(link_id)
            rest, rows = split_suggestions(note.actions.get("links", ""))
            extra.update(
                actions=ACTIONS, action_titles=ACTION_TITLES,
                action_buttons=ACTION_BUTTONS, running=running, failed=failed,
                searchable=can_search(current["cfg"]),
                link_categories=list(library.categories()),
                sections={action: blocks(rest if action == "links"
                                         else note.actions.get(action, ""))
                          for action in ACTIONS},
                suggested=[(stem, why, by_stem.get(stem), stem in note.related)
                           for stem, why in rows])
```

Replace `join_idea` with this version. The only changes are the `back` field and where it returns:

```python
    @app.post("/item/{link_id}/ideas")
    def join_idea(link_id: str, idea: str = Form(""), back: str = Form("")):
        """Add this link to one of your ideas.

        The idea's note is the one written -- the relation lives there, so
        the idea reads on its own in Obsidian -- under the idea's lock, and
        read again inside it. Only a link joins: a card or another idea is
        not something an idea is built from. `back=idea` is the Add button
        of a suggestion on the idea's page, which returns there.
        """
        library.refresh()
        entry = library.entry(link_id)
        if entry is None:
            raise HTTPException(status_code=404, detail="no such link")
        stem = entry.path.stem
        home = item_url(idea) if back == "idea" else item_url(link_id)
        try:
            result = edit(idea, lambda cfg, language: add_related(
                cfg, idea, stem, language), "saved", "indexes-stale", shelves=ideas)
        except IdeaFull:
            return see_other(home, notice="idea-full")
        if result.notice == MISSING:
            return see_other(item_url(link_id), notice="no-such-idea")
        return see_other(home, notice=result.notice)
```

The new route goes after `leave_idea`:

```python
    def act(live: Config, idea: str, action: str, category: str) -> None:
        """The background half of an action: run it, then say how it ended."""
        problem: str | None = "it stopped before it could say why"
        try:
            problem = run_idea_action(live, idea, action, category,
                                      trace=progress.note)
        except Exception as error:        # a background task has nowhere to raise to
            problem = str(error) or type(error).__name__
        finally:
            working.finish(idea, action, problem)

    @app.post("/item/{link_id}/actions/{action}")
    def ask_about_idea(background: BackgroundTasks, link_id: str, action: str,
                       category: str = Form("")):
        """One of the four actions on an idea, behind the page.

        Already out there? needs an engine that searches; when the chain has
        none it is refused here, before anything is queued, and the page
        already shows the button off with the reason.
        """
        if action not in ACTIONS:
            raise HTTPException(status_code=404, detail="no such action")
        ideas.refresh()
        if ideas.by_id(link_id) is None:
            return see_other("/ideas", notice="no-such-idea")
        live = current["cfg"]
        if action == "exists" and not can_search(live):
            return see_other(item_url(link_id), notice="cannot-search")
        if working.start(link_id, action):
            background.add_task(act, live, link_id, action, category)
        return see_other(item_url(link_id), notice="thinking")
```

`Config` is imported in `app.py` already (`from ..config import ... Config`).

- [ ] **Step 6: The template**

In `src/oknowledge/web/templates/item.html`, inside `{% if idea %}`, directly after the `{% endif %}` that closes `{% if related %}` and before `{% include "mine-buttons.html" %}`:

```jinja
        {# The four actions. Each writes its own section into the idea's
           note, beside your text and never over it. #}
        <section class="idea-actions">
          {% for action in actions %}
            {% set has = note.actions.get(action) %}
            {% set busy = action in running %}
            {% set blocked = action == 'exists' and not searchable %}
            <div class="idea-action">
              {% if has %}
                <h2>{{ t(action_titles[action]) }}</h2>
                {% for kind, body in sections[action] %}
                  {% if kind == 'ul' %}<ul>{% for item in body %}<li>{{ item }}</li>{% endfor %}</ul>
                  {% else %}<p>{{ body }}</p>{% endif %}
                {% endfor %}
                {% if action == 'links' and suggested %}
                  <ul class="related">
                    {% for stem, why, found, linked in suggested %}
                      <li{% if not found %} class="gone"{% endif %}>
                        {% if found %}
                          <a href="/item/{{ found.id|slug }}">{{ found.title }}</a>
                          <span class="cat">{{ found.category }}</span>
                        {% else %}
                          <span title="{{ t('This note is not in your library any more') }}">{{ stem }}</span>
                        {% endif %}
                        {% if why %}<span class="why">{{ why }}</span>{% endif %}
                        {% if found and linked %}
                          <span class="meta">{{ t('already linked') }}</span>
                        {% elif found %}
                          <form action="/item/{{ found.id|slug }}/ideas" method="post">
                            <input type="hidden" name="idea" value="{{ note.id }}">
                            <input type="hidden" name="back" value="idea">
                            <button type="submit">{{ t('Add to the idea') }}</button>
                          </form>
                        {% endif %}
                      </li>
                    {% endfor %}
                  </ul>
                {% endif %}
              {% endif %}
              <form action="/item/{{ note.id|slug }}/actions/{{ action }}" method="post" class="row">
                {% if action == 'links' %}
                  <label for="field-among">{{ t('Among') }}</label>
                  <select id="field-among" name="category">
                    <option value="">{{ t('All categories') }}</option>
                    {% for name in link_categories %}<option value="{{ name }}">{{ name }}</option>{% endfor %}
                  </select>
                {% endif %}
                <button type="submit"{% if busy or blocked %} disabled{% endif %}>
                  {%- if busy %}{{ t('thinking…') }}
                  {%- elif has %}{{ t('Ask again') }}
                  {%- else %}{{ t(action_buttons[action]) }}{% endif -%}
                </button>
              </form>
              {% if blocked %}
                <p class="meta">{{ t('No engine in your chain searches the web: opencode or the Anthropic API do.') }}</p>
              {% endif %}
              {% if failed.get(action) %}
                <p class="failed">{{ t('Last time it failed: %1', failed[action]) }}</p>
              {% endif %}
            </div>
          {% endfor %}
        </section>
```

- [ ] **Step 7: Strings and style**

In `src/oknowledge/i18n.py`, add to `STRINGS["es"]`, beside the idea strings. Grep first, and skip any key that already exists.

```python
        "Thinking it over. Reload in a moment to read it.":
            "Pensándolo. Recargá en un momento para leerlo.",
        "No engine in your chain searches the web: opencode or the Anthropic API do.":
            "Ningún motor de tu cadena busca en internet: opencode o la API de Anthropic sí.",
        "Already out there": "Ya existe",
        "Already out there?": "¿Ya existe?",
        "Improvements": "Mejoras",
        "Improve": "Mejorar",
        "Expansion": "Ampliación",
        "Expand": "Ampliar",
        "Links that may help": "Links que pueden servir",
        "Ask again": "Pedir de nuevo",
        "thinking…": "pensando…",
        "Last time it failed: %1": "La última vez falló: %1",
        "Among": "Entre",
        "All categories": "Todas",
        "Add to the idea": "Sumar a la idea",
        "already linked": "ya relacionado",
```

In `src/oknowledge/web/static/style.css`, append:

```css
/* An idea's four actions: each section above its own button. */
.idea-actions { display: grid; gap: 1rem; margin-top: 1.5rem; }
.idea-action h2 { margin-bottom: .25rem; }
.idea-action .why { color: var(--dim); margin-left: .5rem; }
.idea-action .failed { color: var(--danger, #b3261e); }
.idea-action button[disabled] { opacity: .6; cursor: default; }
```

- [ ] **Step 8: Run them to verify they pass**

Run: `~/.local/share/oknowledge/venv/bin/python -m pytest tests/test_web_idea_actions.py tests/test_web_write.py tests/test_i18n.py tests/test_web_ideas_related.py -q`
Expected: all pass.

- [ ] **Step 9: Mutation check** (against `tests/test_web_idea_actions.py`)

- `'if action == "exists" and not can_search(live):'` → `'if False:'`
- `'        if working.start(link_id, action):\n            background.add_task'` → `'        if True:\n            background.add_task'`
- `'home = item_url(idea) if back == "idea" else item_url(link_id)'` → `'home = item_url(link_id)'`
- `'    safe = str(escape(text))'` → `'    safe = str(text)'` (in `markup.py`)
- `'(https?://[^\s()<>]+)'` → `'([^\s()<>]+)'` (in `markup.py`)
- `'                for stem, why in rows])'` → `'                for stem, why in rows if False])'`

- [ ] **Step 10: Full suite and commit**

```bash
git add src/oknowledge/web/working.py src/oknowledge/web/markup.py src/oknowledge/web/app.py src/oknowledge/web/templates/item.html src/oknowledge/web/static/style.css src/oknowledge/i18n.py tests/test_web_idea_actions.py tests/test_web_write.py
git commit -m "feat: the four action buttons on an idea's page"
```

---

### Task 9: README, and the live check

**Files:**
- Modify: `README.md`

- [ ] **Step 1: README**

Under the existing `### Ideas` section, add:

```markdown
#### Asking about an idea

Four buttons on an idea's page, each writing its own section into the
idea's note, between the points and your text:

- **Already out there?** searches the web for the same thing or something
  close, with links. It needs an engine that searches: opencode, or the API
  engine with the Anthropic provider. The answer is checked: a model that
  answers without having searched is an error, not a verdict.
- **Improve** points out weak spots and how to fix them.
- **Expand** proposes what the idea does not say yet.
- **Links that may help** picks, among your saved links of a category,
  the ones that serve the idea, each with an **Add to the idea** button.

Asking again replaces that section only. Your text is never touched.

#### opencode runs sandboxed

Every opencode run goes through [bubblewrap](https://github.com/containers/bubblewrap)
(`pacman -S bubblewrap`). opencode is an agent with a shell and the network,
and its prompt carries text from web pages. Inside the sandbox it sees the
system read-only and its own folders, and nothing else of your home: not
your vault, not `~/.config/oknowledge` and its keys, not `~/.ssh`. Without
bubblewrap opencode does not run, and the chain moves on to the next engine.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: idea actions and the opencode sandbox"
```

- [ ] **Step 3: Live check on a scratch vault (never the real one)**

1. Create a scratch vault and config in the scratchpad. Its `config.toml` sets `vault = "<scratch>/vault"`, `[ai] chain = ["opencode"]` and `[ai.opencode] model = "opencode/mimo-v2.6-flash-free"`. Run `oknowledge --config <scratch>/config.toml serve` on a free port (see `oknowledge serve --help` for the port flag) in the background, and note the real python PID, not the wrapper's.
2. Save one idea through the page (`POST /ideas/guardar`) and one link note (written with `write_note` from a short Python snippet).
3. `POST /item/<idea>/actions/exists`. Wait, then read the idea's note. Expected: a `## Ya existe` section with at least one real `https://` row and the line `Buscado el … con opencode/mimo-v2.6-flash-free.`
4. `POST /item/<idea>/actions/improve` and `…/links`. Expected: both sections are written, and `Mi nota` is unchanged byte for byte.
5. Sandbox proof: run the engine's `complete()` once from Python with the prompt `Use your bash tool to run: ls ~/Projects ; ls ~/.config . Reply with the output.` Expected: `~/Projects` does not exist, and `~/.config` lists only `opencode`.
6. Kill the server by its verified PID (check `ps -o cmd= -p <pid>` first).

---

## Self-review notes

- Spec A (sandbox) → Task 1. B (`search`) → Tasks 2–4. C (the actions and their JSON) → Task 6. D (the note) → Task 5. E (the flow, the page, Add, the failure line, thinking) → Tasks 7–8. "Cuando algo falla" rows → Tasks 2, 3, 6, 7, 8. "Cómo se verifica" 1–8 → Tasks 1–9.
- Types used across tasks: `compose(cfg, note, action, category, day) -> (str, str, str)`; `run_idea_action(...) -> str | None`; `Working.of(idea) -> (set[str], dict[str, str])`; `split_suggestions(text) -> (str, list[(stem, why)])`.
