"""opencode, the engine that needs no credentials.

It is an agent, not a text service: it has bash and the network, and the
prompt it gets carries text from a web page. Restricting its tools from its
own config makes the free tier refuse it (measured: 403), so every run is
locked in from the outside, with bubblewrap: an empty /home except
opencode's own folders, an empty temporary directory to work in, --pure.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .base import NO_SEARCH, EngineError, clean_models


LIST_TIMEOUT = 5
"""Seconds to wait for a listing. `opencode models` answers instantly on this
machine; a completion gets 300 because it is doing work, and a question that
takes five seconds has already failed."""


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
        proc = self._run([self.binary, "run", "--pure", "-m", self.model, prompt])
        if proc.returncode != 0:
            raise EngineError(f"opencode failed: {proc.stderr.strip()[:300]}")
        if not proc.stdout.strip():
            raise EngineError("opencode returned an empty answer")
        return proc.stdout

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
