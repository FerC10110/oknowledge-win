"""ollama: the only engine where the text never leaves the machine."""

from __future__ import annotations

import shutil
import subprocess
import time

import httpx

from .base import EngineError


UNIT = "ollama.service"


def _answers(url: str) -> bool:
    try:
        httpx.get(f"{url}/api/tags", timeout=2.0).raise_for_status()
        return True
    except Exception:
        return False


def _systemctl(*args: str):
    """Run `systemctl --user`; None when systemctl itself is not available."""
    try:
        return subprocess.run(
            ["systemctl", "--user", *args], capture_output=True, text=True, timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def ensure_running(url: str, timeout: float = 15.0) -> None:
    """Make sure ollama answers, starting it in a managed way if it is down.

    Never starts anything when the server is already up. Prefers the user's
    systemd unit so systemd owns the process; only without a unit does it spawn
    a detached `ollama serve`.
    """
    if _answers(url):
        return
    by_hand = "start it with `systemctl --user start ollama` or `ollama serve`"
    unit = _systemctl("cat", UNIT)
    if unit is not None and unit.returncode == 0:
        started = _systemctl("start", UNIT)
        if started is None or started.returncode != 0:
            detail = started.stderr.strip()[:200] if started else "systemctl unavailable"
            raise EngineError(f"ollama could not be started via systemd ({detail}); {by_hand}")
    else:
        if not shutil.which("ollama"):
            raise EngineError("ollama is not installed")
        subprocess.Popen(
            ["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _answers(url):
            return
        time.sleep(0.5)
    raise EngineError(f"ollama could not be started: it is not answering at {url}; {by_hand}")


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
                if response.status_code == 404 or "not found" in detail.lower():
                    detail += f" (pull it with: ollama pull {self.model})"
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
