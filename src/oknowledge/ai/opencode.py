"""opencode, the engine that needs no credentials.

It is an agent, not a text service: it has bash and the network, and the
prompt it gets carries text from a web page. Restricting its tools from its
own config makes the free tier refuse it (measured: 403). The Linux version
locks every run in from the outside with bubblewrap and pasta; on Windows
neither exists, and it runs in an empty temporary folder only, as a run of
its own (--pure on 1.x, --standalone on 2.x).
"""

from __future__ import annotations

import functools
import json
import re
import subprocess
import tempfile

from .base import NO_SEARCH, EngineError, clean_models


LIST_TIMEOUT = 5
"""Seconds to wait for a listing. `opencode models` answers instantly on this
machine; a completion gets 300 because it is doing work, and a question that
takes five seconds has already failed."""


def sandboxed(argv: list[str], cwd: str) -> list[str]:
    """`argv`, as it is: on Windows opencode runs without a sandbox.

    The Linux version wraps it in bubblewrap and pasta, and neither exists
    here. The name stays so the two versions call it the same way; `cwd`
    is still an empty temporary folder, so opencode starts away from your
    files, but nothing stops it from leaving.
    """
    return list(argv)


@functools.lru_cache(maxsize=None)
def isolation(name: str) -> str:
    """The flag that keeps a run to itself, by opencode's version.

    1.x had --pure: no plugins from outside. 2.0 dropped it and refuses the
    whole run over it ("Unrecognized flag"); there a run talks to a
    background service unless it is --standalone. A version nobody can read
    is taken as the new one: that is what an install gets today.
    """
    try:
        with tempfile.TemporaryDirectory() as cwd:
            proc = subprocess.run(sandboxed([name, "--version"], cwd), cwd=cwd,
                                  capture_output=True, text=True,
                                  timeout=LIST_TIMEOUT, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        proc = None
    said = re.search(r"(\d+)\.\d+", proc.stdout) if proc is not None else None
    return "--pure" if said and int(said.group(1)) < 2 else "--standalone"


def parse_opencode_models(text: str) -> list[str]:
    """The model names in `opencode models` output: one per line, as printed."""
    return clean_models(text.splitlines())


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


class OpenCodeEngine:
    name = "opencode"
    searches = True

    def __init__(self, model: str, binary: str = "opencode", timeout: int = 300):
        self.model = model
        self.binary = binary
        self.timeout = timeout

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
        proc = self._run([self.binary, "run", isolation(self.binary), "-m", self.model, prompt])
        if proc.returncode != 0:
            raise EngineError(f"opencode failed: {proc.stderr.strip()[:300]}")
        if not proc.stdout.strip():
            raise EngineError("opencode returned an empty answer")
        return proc.stdout

    def search(self, prompt: str) -> str:
        proc = self._run([self.binary, "run", isolation(self.binary), "--format", "json",
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

    def models(self) -> list[str]:
        """Every model opencode will accept, or [] if it cannot say.

        Never raises and never waits long: this answers a page the user is
        looking at, and an empty list leaves the box exactly as typable as it
        was before they asked.
        """
        try:
            proc = subprocess.run(
                [self.binary, "models"], capture_output=True, text=True,
                timeout=LIST_TIMEOUT, stdin=subprocess.DEVNULL,
            )
        except Exception:
            # Not installed, not runnable, too slow, or something nobody
            # thought of: all of them are "cannot say".
            return []
        if proc.returncode != 0:
            return []
        return parse_opencode_models(proc.stdout)
