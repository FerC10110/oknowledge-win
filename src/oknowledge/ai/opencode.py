"""opencode, the engine that needs no credentials.

It runs in an empty temporary directory and with --pure: it is an agent, not a
text service, so everything that could tempt it to touch files is taken away.
"""

from __future__ import annotations

import subprocess
import tempfile

from .base import EngineError


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
                proc = subprocess.run(
                    argv, cwd=cwd, capture_output=True, text=True, timeout=self.timeout,
                )
        except FileNotFoundError as error:
            raise EngineError(f"opencode is not installed (no '{self.binary}' on PATH): {error}") from error
        except subprocess.TimeoutExpired as error:
            raise EngineError(f"opencode timed out after {self.timeout}s") from error
        if proc.returncode != 0:
            raise EngineError(f"opencode failed: {proc.stderr.strip()[:300]}")
        if not proc.stdout.strip():
            raise EngineError("opencode returned an empty answer")
        return proc.stdout
