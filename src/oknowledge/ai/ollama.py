"""ollama: the only engine where the text never leaves the machine."""

from __future__ import annotations

import shutil
import subprocess
import time

import httpx

from .base import EngineError


def ensure_running(url: str, timeout: float = 15.0) -> None:
    """If ollama is installed but stopped, start it instead of failing."""
    try:
        httpx.get(f"{url}/api/tags", timeout=2.0).raise_for_status()
        return
    except Exception:
        pass
    if not shutil.which("ollama"):
        raise EngineError("ollama is not installed")
    subprocess.Popen(
        ["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            httpx.get(f"{url}/api/tags", timeout=2.0).raise_for_status()
            return
        except Exception:
            time.sleep(0.5)
    raise EngineError("ollama did not come up")


def _server_message(response) -> str:
    """The server's own explanation (e.g. "model 'x' not found"), if it sent one."""
    try:
        return str(response.json().get("error", "")).strip()
    except Exception:
        return ""


class OllamaEngine:
    name = "ollama"

    def __init__(self, model: str, url: str = "http://localhost:11434",
                 timeout: int = 300, ensure=None):
        self.model = model
        self.url = url.rstrip("/")
        self.timeout = timeout
        self._ensure = ensure if ensure is not None else lambda: ensure_running(self.url)

    def complete(self, prompt: str) -> str:
        self._ensure()
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "format": "json",
        }
        try:
            response = httpx.post(f"{self.url}/api/chat", json=body, timeout=self.timeout)
            if response.status_code >= 400:
                detail = _server_message(response) or f"HTTP {response.status_code}"
                raise EngineError(f"ollama failed: {detail}")
            content = response.json()["message"]["content"]
        except EngineError:
            raise
        except httpx.TimeoutException as error:
            raise EngineError(f"ollama timed out after {self.timeout}s") from error
        except (KeyError, TypeError, ValueError) as error:
            raise EngineError(f"ollama sent an unexpected reply: {error!r}") from error
        except Exception as error:
            raise EngineError(f"ollama failed: {error}") from error
        if not isinstance(content, str) or not content.strip():
            raise EngineError("ollama sent an unexpected reply: no text")
        return content
