"""Who the api engine can be pointed at, and where each one lives.

Nothing here is engine code. The engine already speaks the two protocols that
matter and already takes an address, so a new provider is a row in this table:
its endpoint, the variable its key goes in, and where you get that key. The
settings page draws the same row it reads, which is why the address on screen
is the address that gets called.

Most rows hand out a key for nothing. That is the point of the list -- the two
that do not are the two whose protocols the rest are compatible with.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

PROTOCOLS = ("anthropic", "openai")
"""The two wire formats the engine knows. Everything else is compatible with
the second one, which is what makes a table enough."""

COMPLETION_SUFFIXES = ("/chat/completions", "/messages")
"""How a completions endpoint ends, in either protocol. Used to find the
listing endpoint beside it."""


@dataclass(frozen=True)
class Provider:
    id: str           # what goes in config.toml as [ai.api] provider
    label: str        # what the page calls it
    protocol: str     # one of PROTOCOLS: how to shape the request
    url: str          # where a completion is asked for
    key_env: str      # the variable the key goes in, in the .env
    console: str      # where you get that key
    free: bool        # whether it hands one out for nothing
    note: str = ""    # what the free tier gives; empty when there is none


PROVIDERS = (
    Provider(
        id="groq", label="Groq", protocol="openai",
        url="https://api.groq.com/openai/v1/chat/completions",
        key_env="GROQ_API_KEY", console="https://console.groq.com/keys",
        free=True,
        note="30 requests a minute, 14,400 a day. They do not train on what you send.",
    ),
    Provider(
        id="gemini", label="Google AI Studio (Gemini)", protocol="openai",
        url="https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        key_env="GOOGLE_API_KEY", console="https://aistudio.google.com/app/apikey",
        free=True,
        note="15 requests a minute, 1,500 a day. What you send on the free tier "
             "may be used to improve their models.",
    ),
    Provider(
        id="cerebras", label="Cerebras", protocol="openai",
        url="https://api.cerebras.ai/v1/chat/completions",
        key_env="CEREBRAS_API_KEY", console="https://cloud.cerebras.ai/",
        free=True,
        note="A million tokens a day, in a context of 8K: enough for a page, "
             "not for a long video.",
    ),
    Provider(
        id="openrouter", label="OpenRouter", protocol="openai",
        url="https://openrouter.ai/api/v1/chat/completions",
        key_env="OPENROUTER_API_KEY", console="https://openrouter.ai/keys",
        free=True,
        note="The models whose name ends in :free, 50 a day. One shop front for "
             "many providers.",
    ),
    Provider(
        id="mistral", label="Mistral", protocol="openai",
        url="https://api.mistral.ai/v1/chat/completions",
        key_env="MISTRAL_API_KEY", console="https://console.mistral.ai/api-keys",
        free=True,
        note="A free tier you switch on in the console, which asks for a phone number.",
    ),
    Provider(
        id="nvidia", label="NVIDIA NIM", protocol="openai",
        url="https://integrate.api.nvidia.com/v1/chat/completions",
        key_env="NVIDIA_API_KEY", console="https://build.nvidia.com/",
        free=True,
        note="A thousand credits when you sign up, and the open models of "
             "everyone else to spend them on.",
    ),
    Provider(
        id="together", label="Together AI", protocol="openai",
        url="https://api.together.xyz/v1/chat/completions",
        key_env="TOGETHER_API_KEY", console="https://api.together.ai/settings/api-keys",
        free=True,
        note="Some models are free, with a low limit, and signing up gives you "
             "a small credit.",
    ),
    # The two that are paid from the first token. They are here because they
    # are the two protocols, and because a config that already says one of
    # them has to keep working.
    Provider(
        id="anthropic", label="Anthropic", protocol="anthropic",
        url="https://api.anthropic.com/v1/messages",
        key_env="ANTHROPIC_API_KEY", console="https://console.anthropic.com/settings/keys",
        free=False,
    ),
    Provider(
        id="openai", label="OpenAI", protocol="openai",
        url="https://api.openai.com/v1/chat/completions",
        key_env="OPENAI_API_KEY", console="https://platform.openai.com/api-keys",
        free=False,
    ),
)

_BY_ID = {p.id: p for p in PROVIDERS}


def find(provider: str) -> Provider | None:
    """The row, or None for a name that is not in the table."""
    return _BY_ID.get(provider)


def models_url(url: str) -> str:
    """Where the server at `url` lists what it offers.

    Derived from the completions endpoint and not from the host, because a
    compatible API can live under a path -- Gemini's under /v1beta/openai/, a
    gateway of your own under /proxy/ -- and the host's root is a different
    API, or nobody at all. A key that travels in the query travels along.
    """
    parts = urlsplit(url)
    path = parts.path
    for suffix in COMPLETION_SUFFIXES:
        if path.endswith(suffix):
            path = path[: -len(suffix)]
            break
    return urlunsplit((parts.scheme, parts.netloc,
                       path.rstrip("/") + "/models", parts.query, ""))
