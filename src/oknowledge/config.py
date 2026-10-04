"""La configuración del usuario, con sus defaults y su validación.

El idioma de la interfaz no vive acá: es una preferencia del escritorio,
compartida con los demás plugins, y la lee i18n.py.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_PATH = Path.home() / ".config" / "oknowledge" / "config.toml"
ENGINE_NAMES = ("opencode", "ollama", "api", "fake")
CONTENT_MODES = ("full", "summary")


class ConfigError(Exception):
    """La configuración falta, o está y no se puede usar."""


@dataclass(frozen=True)
class Config:
    vault: Path
    folder: str = "oknowledge"
    default_content: str = "full"
    chain: tuple[str, ...] = ("opencode",)
    language: str = "es"
    engines: dict[str, dict] = field(default_factory=dict)
    port: int = 8787
    idle_timeout: int = 900

    @property
    def root(self) -> Path:
        return self.vault / self.folder

    @property
    def links_dir(self) -> Path:
        return self.root / "links"

    @property
    def attachments_dir(self) -> Path:
        return self.root / "attachments"


def load(path: Path = CONFIG_PATH) -> Config:
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"no config file at {path}")
    data = tomllib.loads(path.read_text(encoding="utf-8"))

    raw_vault = data.get("vault")
    if not raw_vault:
        raise ConfigError("vault is required in the config file")
    vault = Path(raw_vault).expanduser()
    if not vault.is_dir():
        raise ConfigError(f"vault is not a directory: {vault}")

    content = data.get("default_content", "full")
    if content not in CONTENT_MODES:
        raise ConfigError(f"default_content must be full or summary, not {content!r}")

    ai = data.get("ai", {})
    chain = tuple(ai.get("chain", ("opencode",)))
    if not chain:
        raise ConfigError("ai.chain cannot be empty: nothing would analyse the page")
    for name in chain:
        if name not in ENGINE_NAMES:
            raise ConfigError(f"unknown engine in ai.chain: {name!r}")

    engines = {name: dict(value) for name, value in ai.items() if isinstance(value, dict)}
    web = data.get("web", {})

    return Config(
        vault=vault,
        folder=data.get("folder", "oknowledge"),
        default_content=content,
        chain=chain,
        language=ai.get("language", "es"),
        engines=engines,
        port=int(web.get("port", 8787)),
        idle_timeout=int(web.get("idle_timeout", 900)),
    )
