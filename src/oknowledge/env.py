"""The .env beside the config, and nothing else about it.

An API key has to reach the engine somehow, and the two ways that existed were
both wrong for this machine. In config.toml it sits in the file the settings
page rewrites from scratch. In the shell's profile it never arrives at all:
the panel launches the CLI and the server from the graphical session, which
never read a .bashrc.

So: a .env beside the config.toml -- wherever places.py puts that -- read
here and nowhere else. Two rules that the
rest of the program depends on and that the tests pin:

- what is read never reaches os.environ. The pipeline launches opencode as a
  subprocess, and a key in the environment is a key that subprocess inherits.
- what is read is never stored on Config, which is printed, saved and dumped.
  The engine asks for the one variable it needs, when it needs it.

Reading never raises. A file somebody edited by hand is a file with a typo in
it, and the answer to a typo is "no key", which the page already knows how to
explain -- not a traceback over a link somebody pasted.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

from . import places
from .config import CONFIG_PATH

FILE = ".env"
_PRIVACY = {
    False: "Nobody but you can read this file; keep it that way.",
    True: "This file is as private as the folder it is in; keep it there.",
}

LIMIT = 64 * 1024
"""Past this, it is not an env file. Reading the first 64 KB instead would
hand out half a key, and half a key is a 401 nobody can explain."""


def path(config: Path | None = None) -> Path:
    """Beside the config.toml, whichever one is in play."""
    return Path(config or CONFIG_PATH).parent / FILE


def read(config: Path | None = None) -> dict[str, str]:
    """Every NAME=value the file holds, or {} if it holds none.

    The last line wins, like every other env file. `export` is allowed because
    people paste lines they copied from a shell, and matching quotes come off.
    Nothing else is unescaped: this is a file of keys, not a shell script.
    """
    target = path(config)
    try:
        if target.stat().st_size > LIMIT:
            return {}
        raw = target.read_bytes()
    except OSError:
        return {}
    found: dict[str, str] = {}
    for line in raw.decode("utf-8", "replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name = name.strip()
        if name.startswith("export "):
            name = name[len("export "):].strip()
        if not name.isidentifier():
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        found[name] = value
    return found


def value(name: str, config: Path | None = None) -> str:
    """The variable's value: the real environment first, then the file.

    That order on purpose -- an export in a shell stays the quick way to try a
    key without editing anything. A variable set to nothing is not a key, so
    it does not hide the file either.
    """
    return os.environ.get(name, "") or read(config).get(name, "")


def present(name: str, config: Path | None = None) -> bool:
    """Whether a key can be found, without handing it to the caller.

    What the settings page asks. It has no business holding the key itself.
    """
    return bool(value(name, config))


def present_each(names: Iterable[str], config: Path | None = None) -> dict[str, bool]:
    """The same answer as present(), for many names and one read of the file.

    What the settings page asks. It draws a row per provider -- thirteen of
    them -- and present() reads the file per call, so a row a read is the same
    small file opened thirteen times to render one page.

    The rule is present()'s rule, written out again because the file is read
    up front here: the real environment first, and a variable set to nothing
    is not a key. A test pins the two against each other.
    """
    found = read(config)
    return {name: bool(os.environ.get(name, "") or found.get(name, ""))
            for name in names}


def create(name: str, config: Path | None = None) -> bool:
    """Make an empty .env with `name` ready to paste into. True if it wrote it.

    A file that already exists is never touched, whatever is in it: this is
    the only writer, and the thing it would be overwriting is a secret that
    exists nowhere else. Created 0600 by the open itself, so there is no
    moment when it is readable and about to hold a key -- on POSIX. On Windows
    that mode is decoration, and the second header line says so rather than
    promising what the system will not keep.
    """
    target = path(config)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        handle = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except OSError:
        return False
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            out.write("# Read by oknowledge. One NAME=value per line.\n"
                      f"# {_PRIVACY[places.WINDOWS]}\n"
                      f"{name}=\n")
    except OSError:
        return False
    return True


def exposed(config: Path | None = None) -> bool:
    """Whether anyone but you can read it. False when there is no file.

    False on Windows always, and not because it is safe there: the mode is not
    what decides it and os.stat reports 0o666 for every file, so this would
    answer "anyone can read your key" forever. A warning that is always on is
    a warning nobody reads, and this one would be wrong as well.
    """
    if places.WINDOWS:
        return False
    try:
        return bool(path(config).stat().st_mode & 0o077)
    except OSError:
        return False
