"""La configuración del usuario, con sus defaults y su validación.

El idioma de la interfaz no vive acá: es una preferencia del escritorio,
compartida con los demás plugins, y la lee i18n.py.
"""

from __future__ import annotations

import shutil
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .atomic import atomic_write

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


def _table(data: dict, key: str, where: str) -> dict:
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise ConfigError(f"{where} must be a table, not {value!r}")
    return value


def _integer(table: dict, key: str, default: int, where: str) -> int:
    value = table.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{where} must be a whole number, not {value!r}")
    return value


def load(path: Path = CONFIG_PATH) -> Config:
    """Read and validate the config. Whatever is wrong with the file, the answer
    is a ConfigError saying what, never a traceback: this is the file the user
    writes by hand. (A file that exists but cannot be opened is an OSError,
    which the caller reports as such.)"""
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"no config file at {path}")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        raise ConfigError(f"{path} is not valid UTF-8 text") from None
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"{path} is not valid TOML: {error}") from None

    raw_vault = data.get("vault")
    if not raw_vault:
        raise ConfigError("vault is required in the config file")
    if not isinstance(raw_vault, str):
        raise ConfigError(f"vault must be a path in quotes, not {raw_vault!r}")
    try:
        vault = Path(raw_vault).expanduser()
    except RuntimeError:                      # "~nosuchuser/x": no such home directory
        raise ConfigError(f"vault {raw_vault!r} starts with ~ but that home "
                          "directory does not exist") from None
    if not vault.is_dir():
        raise ConfigError(f"vault is not a directory: {vault}")

    folder = data.get("folder", "oknowledge")
    if not isinstance(folder, str) or not folder:
        raise ConfigError(f"folder must be a name in quotes, not {folder!r}")
    if folder in (".", "..") or "/" in folder or "\\" in folder:
        # Everything we write lives under <vault>/<folder>, and the containment
        # check is computed from that same root: a folder that escapes the vault
        # would escape the check with it.
        raise ConfigError(f"folder must be one plain folder name inside the vault, "
                          f"not {folder!r}")

    content = data.get("default_content", "full")
    if content not in CONTENT_MODES:
        raise ConfigError(f"default_content must be full or summary, not {content!r}")

    ai = _table(data, "ai", "ai")
    raw_chain = ai.get("chain", ("opencode",))
    if not isinstance(raw_chain, (list, tuple)) or not all(isinstance(n, str) for n in raw_chain):
        raise ConfigError(f"ai.chain must be a list of engine names, not {raw_chain!r}")
    chain = tuple(raw_chain)
    if not chain:
        raise ConfigError("ai.chain cannot be empty: nothing would analyse the page")
    for name in chain:
        if name not in ENGINE_NAMES:
            raise ConfigError(f"unknown engine in ai.chain: {name!r}")
    language = ai.get("language", "es")
    if not isinstance(language, str):
        raise ConfigError(f"ai.language must be text in quotes, not {language!r}")

    engines = {name: dict(value) for name, value in ai.items() if isinstance(value, dict)}
    web = _table(data, "web", "web")

    return Config(
        vault=vault,
        folder=folder,
        default_content=content,
        chain=chain,
        language=language,
        engines=engines,
        port=_integer(web, "port", 8787, "web.port"),
        idle_timeout=_integer(web, "idle_timeout", 900, "web.idle_timeout"),
    )


def save(cfg: Config, path: Path = CONFIG_PATH) -> Path:
    """Rewrite the config file from a Config, and say where it went.

    This is the file we tell the user to hand-write, so rewriting it loses
    every comment and every bit of formatting in it. The old file is copied to
    <name>.bak first, which is the only thing that makes losing them
    recoverable, and the settings page says so in as many words.

    Only values `load()` accepts are written, so a file saved here always
    loads again.
    """
    import tomli_w            # only this one function needs it: keep startup light

    path = Path(path)
    data = {
        "vault": str(cfg.vault),
        "folder": cfg.folder,
        "default_content": cfg.default_content,
        "ai": {"chain": list(cfg.chain), "language": cfg.language,
               **{name: dict(options) for name, options in cfg.engines.items()}},
        "web": {"port": cfg.port, "idle_timeout": cfg.idle_timeout},
    }
    text = tomli_w.dumps(data)          # before the backup: a bad value changes nothing

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_name(path.name + ".bak")
        shutil.copy2(path, backup)
        backup.chmod(0o600)
    atomic_write(path, text)
    path.chmod(0o600)
    return path
