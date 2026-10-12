"""La configuración del usuario, con sus defaults y su validación.

Dos idiomas, dos ejes: `[ai] language` es el de los resúmenes y `[web]
language` el de la interfaz. En la versión de Omarchy el segundo vivía en un
archivo compartido con los demás plugins; acá no hay otros plugins.
"""

from __future__ import annotations

import shutil
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from . import places
from .atomic import atomic_write
from .i18n import LANGUAGES
from .perms import only_you
from .trace import trace_run

FILE = "config.toml"


def config_path() -> Path:
    """Where the config would be, asked now rather than at import.

    CONFIG_PATH below is the same answer frozen, because that is what the CLI
    needs for its --config default and what three modules import. This is the
    form a test can ask without reloading the module.
    """
    return places.config_dir() / FILE


CONFIG_PATH = config_path()

# The first mistake somebody on Windows makes, and it is not their fault: a
# path copied from the address bar, put in the double quotes TOML asks for,
# turns \U into a unicode escape (an error) or \t and \n into a tab and a
# newline (no error at all, and a vault nobody can find).
QUOTED_PATH = ('a path with backslashes cannot go in double quotes: TOML reads '
               r'\U, \t and \n as escape codes. Write it with forward slashes, '
               '"C:/Users/you/vault", or in single quotes, '
               r"'C:\Users\you\vault'.")
ENGINE_NAMES = ("opencode", "ollama", "api", "fake")
CONTENT_MODES = ("full", "summary")
MENTION_MODES = ("tools", "all", "discussed")


class ConfigError(Exception):
    """La configuración falta, o está y no se puede usar."""


class PortUnavailable(Exception):
    """The web server could not listen on the configured port. Lives here, not in
    web.runner, so the CLI can catch it without importing the web stack."""


@dataclass(frozen=True)
class Shelf:
    """Una carpeta de notas con sus índices. `links` es la que siempre
    existió; `ocio` guarda las fichas. El nombre viaja porque es lo que
    distingue una ruta de la otra en la web."""

    name: str
    dir: Path
    index_dir: Path


@dataclass(frozen=True)
class Config:
    vault: Path
    folder: str = "oknowledge"
    default_content: str = "full"
    batch: int = 10
    """How many links one press of Process takes, and what `retry --limit`
    defaults to from the web. Ten rather than fifty: a run is minutes per link,
    so this is the number somebody waits through once before deciding."""
    chain: tuple[str, ...] = ("opencode",)
    language: str = "es"
    mentions: str = "tools"
    """Which mentions to ask a video for: tools | all | discussed. Only videos
    are asked at all -- see the design doc."""
    engines: dict[str, dict] = field(default_factory=dict)
    host: str = "127.0.0.1"
    """Which interface the web listens on. This machine and nothing else by
    default: it is the only default that cannot put somebody's notes on a
    network they did not mean to put them on. "0.0.0.0" to reach it from a
    phone on the same wifi -- and then anyone on that wifi can reach it too,
    which the server says out loud when it starts."""
    port: int = 8787
    idle_timeout: int = 900
    ui_language: str = "en"
    """What the buttons say: `[web] language`. A different axis from
    `language` above, which is what the summaries are written in, and they
    were always two. English by default because the keys in the code are the
    English text, so it is the one language that cannot be half-translated."""
    trace_to: str = ""
    """The run folder this process writes prompt-and-reply traces into, or ""
    for the usual case of not tracing at all. One value and not a flag plus a
    name: a run folder is what tracing *is*, and two fields could disagree.

    `[debug] trace = true` turns it into one folder per process, which is one
    folder per run. The web sets it per batch instead, with a replace(), so a
    box ticked once does not leave every later run writing the full text of
    every page to disk."""
    source: Path | None = None
    """The file this was read from, when it was read from one. `--config
    somewhere/else.toml` has to reach the settings page: saving to the default
    path would write a file the rest of the process does not read."""

    @property
    def root(self) -> Path:
        return self.vault / self.folder

    @property
    def links(self) -> Shelf:
        """The shelf that always existed. Its indexes sit at the root of the
        managed folder, beside links/, which is where the ones on disk are."""
        return Shelf("links", self.root / "links", self.root)

    @property
    def ocio(self) -> Shelf:
        """The cards. Indexes inside the folder itself, so rebuilding one
        shelf can never delete the other's: the sweep that removes an index
        left without notes only ever looks in its own shelf's index_dir."""
        return Shelf("ocio", self.root / "ocio", self.root / "ocio")

    @property
    def ideas(self) -> Shelf:
        """The ideas. Indexes inside the folder, like the cards, for the
        same reason: a rebuild of one shelf only ever sweeps its own."""
        return Shelf("ideas", self.root / "ideas", self.root / "ideas")

    def shelf(self, name: str) -> Shelf:
        """The shelf a name from a URL asks for. Anything unknown is the
        links shelf: an unknown name must not invent a folder."""
        return {"ocio": self.ocio, "ideas": self.ideas}.get(name, self.links)

    @property
    def links_dir(self) -> Path:
        return self.links.dir

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


def _host(web: dict) -> str:
    """The interface to listen on, or a ConfigError naming the key.

    Not resolved here: whether an address exists is the kernel's answer at
    bind time, and a config that refuses a hostname this machine cannot see
    yet would be a config that breaks when the network comes back. All this
    checks is that it is one word of text.
    """
    value = web.get("host", "127.0.0.1")
    host = value.strip() if isinstance(value, str) else ""
    if not host or any(ch.isspace() for ch in host):
        raise ConfigError(f"web.host must be an address to listen on, not {value!r}")
    return host


def _ui_language(web: dict) -> str:
    """The one place a language the program has no words for is refused.

    Not quietly degraded to English: it is a hand-written file, and a line
    that is silently ignored is a setting somebody will keep retyping.
    """
    value = web.get("language", "en")
    if value not in LANGUAGES:
        raise ConfigError(f"web.language must be one of {', '.join(LANGUAGES)}, "
                          f"not {value!r}")
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
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise ConfigError(f"{path} is not valid UTF-8 text") from None
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        hint = f" {QUOTED_PATH}" if "\\" in text else ""
        raise ConfigError(f"{path} is not valid TOML: {error}{hint}") from None

    raw_vault = data.get("vault")
    if not raw_vault:
        raise ConfigError("vault is required in the config file")
    if not isinstance(raw_vault, str):
        raise ConfigError(f"vault must be a path in quotes, not {raw_vault!r}")
    if not raw_vault.isprintable():
        # The half of the mistake above that TOML accepts. Caught here rather
        # than left to "not a directory", which would print the tab and the
        # newline and explain nothing.
        raise ConfigError(f"vault {raw_vault!r} came out with an escape code in "
                          f"it. {QUOTED_PATH}")
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

    # A batch of none is not a batch, and the button that runs it would do
    # nothing while looking like it worked.
    batch = _integer(data, "batch", 10, "batch")
    if batch < 1:
        raise ConfigError(f"batch must be at least 1, not {batch!r}")

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

    mentions = ai.get("mentions", "tools")
    if mentions not in MENTION_MODES:
        raise ConfigError(f"ai.mentions must be one of "
                          f"{', '.join(MENTION_MODES)}, not {mentions!r}")

    engines = {name: dict(value) for name, value in ai.items() if isinstance(value, dict)}
    web = _table(data, "web", "web")

    debug = _table(data, "debug", "debug")
    tracing = debug.get("trace", False)
    if not isinstance(tracing, bool):
        raise ConfigError(f"debug.trace must be true or false, not {tracing!r}")

    return Config(
        vault=vault,
        folder=folder,
        default_content=content,
        batch=batch,
        chain=chain,
        language=language,
        mentions=mentions,
        engines=engines,
        host=_host(web),
        port=_integer(web, "port", 8787, "web.port"),
        idle_timeout=_integer(web, "idle_timeout", 900, "web.idle_timeout"),
        ui_language=_ui_language(web),
        trace_to=trace_run() if tracing else "",
        source=path,
    )


def save(cfg: Config, path: Path | None = None) -> Path:
    """Rewrite the config file from a Config, and say where it went.

    This is the file we tell the user to hand-write, so rewriting it loses
    every comment and every bit of formatting in it. The old file is copied to
    <name>.bak first, which is the only thing that makes losing them
    recoverable, and the settings page says so in as many words.

    Only values `load()` accepts are written, so a file saved here always
    loads again.

    Without a path, the file the Config was read from, and the default location
    only for a Config nobody read from a file.
    """
    import tomli_w            # only this one function needs it: keep startup light

    path = Path(path if path is not None else cfg.source or CONFIG_PATH)
    data = {
        "vault": str(cfg.vault),
        "folder": cfg.folder,
        "default_content": cfg.default_content,
        "batch": cfg.batch,
        "ai": {"chain": list(cfg.chain), "language": cfg.language,
               "mentions": cfg.mentions,
               **{name: dict(options) for name, options in cfg.engines.items()}},
        "web": {"host": cfg.host, "port": cfg.port,
                "idle_timeout": cfg.idle_timeout, "language": cfg.ui_language},
        # Written only when it is on: a `trace = false` in everybody's config
        # file is a line that explains nothing and has to be read anyway.
        **({"debug": {"trace": True}} if cfg.trace_to else {}),
    }
    text = tomli_w.dumps(data)          # before the backup: a bad value changes nothing

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_name(path.name + ".bak")
        shutil.copy2(path, backup)
        only_you(backup)
    atomic_write(path, text)
    only_you(path)
    return path
