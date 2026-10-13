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
NO_PASTA = "opencode needs pasta to run in a network of its own: install it (pacman -S passt)"

PASTA = ["--quiet", "--config-net", "-D", "none", "-t", "none", "-u", "none", "-T", "none", "-U", "none",
         "--no-map-gw"]
"""A network namespace with a way out to the internet and none back to this
machine: no port forwarded either way and the gateway not mapped to the host,
so localhost inside is the sandbox's own, and the host's address is shadowed
by the copy pasta gives the namespace. No nameserver is handed out (pasta
would warn on stderr that it found none): names resolve through resolved's
socket, which is a file, not an address."""

_XDG = (("data", ".local/share"), ("config", ".config"),
        ("cache", ".cache"), ("state", ".local/state"))


def opencode_dirs() -> list[tuple[Path, Path]]:
    """(a folder of ours, where opencode looks for it) for its four folders.

    Never your real ones: your opencode config holds plugins that run, with
    no sandbox, the next time you open opencode yourself, and its data holds
    every session you ever had. A command planted from a web page must reach
    neither, so the sandbox gets a set of its own, kept beside oknowledge's
    data, mounted where opencode expects to find them.
    """
    home = Path.home()
    private = Path(os.environ.get("XDG_DATA_HOME") or home / ".local/share") / "oknowledge" / "opencode"
    return [(private / name, home / default / "opencode") for name, default in _XDG]


def sandboxed(argv: list[str], cwd: str) -> list[str]:
    """`argv` wrapped in bubblewrap.

    Only what opencode needs is mounted: the system read-only, the resolver
    the network needs, a private set of its folders, the binary's folder and
    `cwd` as /work. Your vault, your projects, ~/.config/oknowledge with the API keys
    and ~/.ssh are not there at all -- there is nothing to read them from.

    The network is pasta's, not the host's: the oknowledge server listens on
    this machine and takes a POST that carries no Origin, and a page's
    instructions must not be able to reach it.
    """
    bwrap = shutil.which("bwrap")
    if bwrap is None:
        raise EngineError(NO_BWRAP)
    pasta = shutil.which("pasta")
    if pasta is None:
        raise EngineError(NO_PASTA)
    found = shutil.which(argv[0])
    if found is None:
        raise EngineError(f"opencode is not installed (no '{argv[0]}' on PATH)")
    # A mise shim points at the real executable, which is what gets mounted.
    binary = os.path.realpath(found)
    where = os.path.dirname(binary)
    # Nothing of your environment goes in: an exported token is one `env`
    # away from a page's instructions, and DISPLAY is a way out to the screen.
    path = "/usr/bin:/bin" if where.startswith("/usr/") else f"/usr/bin:/bin:{where}"
    # --share-net shares pasta's namespace, not the host's.
    wrapped = [pasta, *PASTA, "--", bwrap, "--unshare-all", "--share-net", "--die-with-parent", "--clearenv",
               "--setenv", "PATH", path, "--setenv", "HOME", str(Path.home()),
               "--setenv", "LANG", os.environ.get("LANG") or "C.UTF-8",
               "--ro-bind", "/usr", "/usr", "--symlink", "usr/bin", "/bin",
               "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib", "/lib64",
               "--ro-bind", "/etc", "/etc",
               "--ro-bind-try", "/run/systemd/resolve", "/run/systemd/resolve",
               "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--tmpfs", "/home"]
    for ours, theirs in opencode_dirs():
        ours.mkdir(parents=True, exist_ok=True)
        wrapped += ["--bind", str(ours), str(theirs)]
    if not where.startswith("/usr/"):
        wrapped += ["--ro-bind", where, where]
    wrapped += ["--bind", cwd, "/work", "--chdir", "/work", binary, *argv[1:]]
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
