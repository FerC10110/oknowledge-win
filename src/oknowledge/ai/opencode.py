"""opencode, the engine that needs no credentials.

It runs in an empty temporary directory and with --pure: it is an agent, not a
text service, so everything that could tempt it to touch files is taken away.
"""

from __future__ import annotations

import subprocess
import tempfile

from .base import EngineError, clean_models


LIST_TIMEOUT = 5
"""Seconds to wait for a listing. `opencode models` answers instantly on this
machine; a completion gets 300 because it is doing work, and a question that
takes five seconds has already failed."""


def parse_opencode_models(text: str) -> list[str]:
    """The model names in `opencode models` output: one per line, as printed."""
    return clean_models(text.splitlines())


class OpenCodeEngine:
    name = "opencode"

    def __init__(self, model: str, binary: str = "opencode", timeout: int = 300):
        self.model = model
        self.binary = binary
        self.timeout = timeout

    def complete(self, prompt: str) -> str:
        argv = [self.binary, "run", "--pure", "-m", self.model, prompt]
        try:
            with tempfile.TemporaryDirectory() as cwd:
                # stdin must be closed: opencode blocks on an open non-TTY pipe.
                # stdout only is the answer; its header and ANSI codes go to stderr.
                proc = subprocess.run(
                    argv, cwd=cwd, capture_output=True, text=True, timeout=self.timeout,
                    stdin=subprocess.DEVNULL,
                )
        except FileNotFoundError as error:
            raise EngineError(f"opencode is not installed (no '{self.binary}' on PATH): {error}") from error
        except subprocess.TimeoutExpired as error:
            raise EngineError(f"opencode timed out after {self.timeout}s") from error
        except OSError as error:
            raise EngineError(f"opencode could not be run: {error}") from error
        if proc.returncode != 0:
            raise EngineError(f"opencode failed: {proc.stderr.strip()[:300]}")
        if not proc.stdout.strip():
            raise EngineError("opencode returned an empty answer")
        return proc.stdout

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
