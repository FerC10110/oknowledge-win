"""The API-key engine. Ready even when it is not in the chain.

The key is never stored in the vault or the repo and never appears in a
message: it comes from an environment variable, or from the config.toml that
lives with 600 permissions.
"""

from __future__ import annotations

import os

import httpx

from urllib.parse import urlsplit, urlunsplit

from .base import EngineError, clean_models

ENDPOINTS = {
    "anthropic": "https://api.anthropic.com/v1/messages",
    "openai": "https://api.openai.com/v1/chat/completions",
}


MESSAGE_LIMIT = 300
LIST_TIMEOUT = 5
"""Seconds to wait for a listing, against the 300 a completion gets: this one
answers a page somebody is looking at."""


def _server_message(response) -> str:
    """The server's own explanation, if it sent one (never the request headers).

    Returned whole, and cut by the caller *after* redacting: cutting first
    leaves the prefix of a key that straddles the limit, and ten characters of
    a live key is still ten characters of a live key.
    """
    try:
        error = response.json().get("error", "")
    except Exception:
        return ""
    if isinstance(error, dict):
        error = error.get("message", "")
    return str(error).strip()


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
                    f"{self._redact(_server_message(response), secret)[:MESSAGE_LIMIT] or f'HTTP {response.status_code}'}"
                )
            data = response.json()
            if self.provider == "anthropic":
                text = data["content"][0]["text"]
            else:
                text = data["choices"][0]["message"]["content"]
        # Every branch below passes its text through _redact, including the
        # ones whose message looks safe today: the key can arrive in the URL
        # (a gateway base_url with ?key=), and from an EngineError it reaches
        # the queue entry, the CLI's stderr and the widget's toast.
        except EngineError:
            raise
        except httpx.TimeoutException as error:
            detail = self._redact(str(error), secret)
            raise EngineError(
                f"{self.provider} timed out after {self.timeout}s"
                + (f": {detail}" if detail else "")
            ) from error
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise EngineError(
                f"{self.provider} sent an unexpected reply: "
                f"{self._redact(repr(error), secret)}"
            ) from error
        except Exception as error:
            raise EngineError(
                f"{self.provider} failed: {self._redact(str(error), secret)}"
            ) from error
        if not isinstance(text, str) or not text.strip():
            raise EngineError(f"{self.provider} sent an unexpected reply: no text")
        return text

    def models(self) -> list[str]:
        """What the provider says it offers, or [] if it will not say.

        Asked at the provider's own /v1/models, derived from wherever the
        completions endpoint lives so a gateway of your own is asked where it
        actually is. Without a key nothing is asked at all: a 401 is a round
        trip to learn what the empty key already said.
        """
        try:
            secret = self._secret()
        except EngineError:
            return []
        parts = urlsplit(self.url)
        where = urlunsplit((parts.scheme, parts.netloc, "/v1/models", "", ""))
        headers = ({"x-api-key": secret, "anthropic-version": "2023-06-01"}
                   if self.provider == "anthropic"
                   else {"Authorization": f"Bearer {secret}"})
        try:
            response = httpx.get(where, headers=headers, timeout=LIST_TIMEOUT)
            response.raise_for_status()
            listed = response.json().get("data", [])
            return clean_models(
                item.get("id") for item in listed if isinstance(item, dict))
        except Exception:
            # Including a key that is wrong, a provider that does not expose
            # this at all, and a gateway that answers something else entirely.
            return []
