"""The API-key engine. Ready even when it is not in the chain.

The key is never stored in the vault or the repo and never appears in a
message: it comes from an environment variable, or from the config.toml that
lives with 600 permissions.
"""

from __future__ import annotations

import os

import httpx

from .base import EngineError

ENDPOINTS = {
    "anthropic": "https://api.anthropic.com/v1/messages",
    "openai": "https://api.openai.com/v1/chat/completions",
}


def _server_message(response) -> str:
    """The server's own explanation, if it sent one (never the request headers)."""
    try:
        error = response.json().get("error", "")
    except Exception:
        return ""
    if isinstance(error, dict):
        error = error.get("message", "")
    return str(error).strip()[:300]


class ApiEngine:
    name = "api"

    def __init__(self, provider: str, model: str, key_env: str = "",
                 key: str = "", base_url: str = "", timeout: int = 300,
                 max_tokens: int = 2000):
        if provider not in ENDPOINTS:
            raise EngineError(f"unknown provider: {provider!r}")
        self.provider = provider
        self.model = model
        self.key_env = key_env
        self.key = key
        self.url = base_url or ENDPOINTS[provider]
        self.timeout = timeout
        self.max_tokens = max_tokens

    def _secret(self) -> str:
        secret = self.key or (os.environ.get(self.key_env, "") if self.key_env else "")
        if not secret:
            raise EngineError(f"no API key: set {self.key_env or 'ai.api.key'}")
        return secret

    @staticmethod
    def _redact(text: str, secret: str) -> str:
        return text.replace(secret, "***")

    def complete(self, prompt: str) -> str:
        secret = self._secret()
        messages = [{"role": "user", "content": prompt}]
        if self.provider == "anthropic":
            headers = {"x-api-key": secret, "anthropic-version": "2023-06-01"}
            body = {"model": self.model, "max_tokens": self.max_tokens, "messages": messages}
        else:
            headers = {"Authorization": f"Bearer {secret}"}
            body = {"model": self.model, "messages": messages}
        try:
            response = httpx.post(self.url, headers=headers, json=body, timeout=self.timeout)
            if response.status_code >= 400:
                raise EngineError(
                    f"{self.provider} failed: "
                    f"{self._redact(_server_message(response), secret) or f'HTTP {response.status_code}'}"
                )
            data = response.json()
            if self.provider == "anthropic":
                text = data["content"][0]["text"]
            else:
                text = data["choices"][0]["message"]["content"]
        except EngineError:
            raise
        except httpx.TimeoutException as error:
            raise EngineError(f"{self.provider} timed out after {self.timeout}s") from error
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise EngineError(f"{self.provider} sent an unexpected reply: {error!r}") from error
        except Exception as error:
            raise EngineError(
                f"{self.provider} failed: {self._redact(str(error), secret)}"
            ) from error
        if not isinstance(text, str) or not text.strip():
            raise EngineError(f"{self.provider} sent an unexpected reply: no text")
        return text
