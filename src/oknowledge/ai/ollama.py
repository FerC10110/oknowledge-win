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


def _systemctl(*args: str, user: bool = True):
    """Run systemctl read-only or as the user; None when it is not available."""
    argv = ["systemctl", *(["--user"] if user else []), *args]
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=15)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _has_unit(user: bool) -> bool:
    result = _systemctl("list-unit-files", UNIT, user=user)
    return result is not None and UNIT in result.stdout


def ensure_running(url: str, timeout: float = 15.0) -> None:
    """Make sure ollama answers, starting it only in a managed, unprivileged way.

    Never starts anything when the server is already up. A user unit is started
    through systemd. A system unit needs root, and a background queue must never
    escalate privileges, so it is reported instead of started. Only with no unit
    at all does it spawn a detached `ollama serve`.
    """
    if _answers(url):
        return
    by_hand = "start it with `systemctl --user start ollama` or `ollama serve`"
    if _has_unit(user=True):
        started = _systemctl("start", UNIT)
        if started is None or started.returncode != 0:
            detail = started.stderr.strip()[:200] if started else "systemctl unavailable"
            raise EngineError(f"ollama could not be started via systemd ({detail}); {by_hand}")
    elif _has_unit(user=False):
        raise EngineError(
            "ollama is installed as a system service but is not running: "
            "start it now with `sudo systemctl start ollama`, "
            "and make it start on boot with `sudo systemctl enable --now ollama`"
        )
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
