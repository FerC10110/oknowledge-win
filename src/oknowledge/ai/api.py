"""The API-key engine. Ready even when it is not in the chain.

Which provider, and where it lives, is not written here: it is a row in
ai/providers.py, and the settings page draws the same row this reads. Two
protocols cover all of them, which is why a new provider is a row and not an
engine.

The key is never stored in the vault or the repo and never appears in a
message. It comes from the .env beside the config, from the environment, or
from a config.toml that lives with 600 permissions.
"""

from __future__ import annotations

from pathlib import Path

import httpx

from .. import env
from .base import EngineError, clean_models
from .providers import PROVIDERS, find, models_url


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
                 max_tokens: int = 2000, config: Path | None = None):
        row = find(provider)
        if row is None:
            known = ", ".join(p.id for p in PROVIDERS)
            raise EngineError(f"unknown provider: {provider!r}; there is {known}")
        # The id is what the user picked and what every message says. The
        # protocol is how to shape the request, and a dozen providers share
        # two of them.
        self.provider = provider
        self.protocol = row.protocol
        self.model = model
        # A variable named in the config wins, so a gateway of your own can
        # keep its own name for the key.
        self.key_env = key_env or row.key_env
        self.key = key
        self.url = base_url or row.url
        self.timeout = timeout
        self.max_tokens = max_tokens
        # Which config.toml this run read, so the .env beside it is the one
        # read -- the same file the settings page tells you to paste into.
        self.config = config

    def _secret(self) -> str:
        """The key, from the config, the environment, or the .env -- in that order.

        The file is read here and not at startup: a key that is loaded before
        anybody needs it is a key sitting in memory for an hour of batch, and
        one that nothing in the chain was ever going to ask for.
        """
        secret = self.key or (env.value(self.key_env, self.config)
                              if self.key_env else "")
        if not secret:
            raise EngineError(
                f"no API key: paste {self.key_env or 'ai.api.key'}=… "
                f"into {env.path(self.config)}")
        return secret

    @staticmethod
    def _redact(text: str, secret: str) -> str:
        return text.replace(secret, "***")

    def complete(self, prompt: str) -> str:
        secret = self._secret()
        messages = [{"role": "user", "content": prompt}]
        if self.protocol == "anthropic":
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
            if self.protocol == "anthropic":
                text = data["content"][0]["text"]
            else:
                text = data["choices"][0]["message"]["content"]
        # Every branch below passes its text through _redact, including the
        # ones whose message looks safe today: the key can arrive in the URL
        # (a gateway base_url with ?key=), and from an EngineError it reaches
        # the queue entry, the CLI's stderr and the page in the browser.
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

        Asked beside the completions endpoint, so a compatible API that lives
        under a path -- Gemini's, a gateway of your own -- is asked where it
        actually is. Without a key nothing is asked at all: a 401 is a round
        trip to learn what the empty key already said.
        """
        try:
            secret = self._secret()
        except EngineError:
            return []
        where = models_url(self.url)
        headers = ({"x-api-key": secret, "anthropic-version": "2023-06-01"}
                   if self.protocol == "anthropic"
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
