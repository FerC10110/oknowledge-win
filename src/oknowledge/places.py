"""Two questions: where the config lives, and where the state lives.

                    Linux                        Windows
    config          ~/.config/oknowledge         %APPDATA%\\oknowledge
    state           ~/.local/state/oknowledge    %LOCALAPPDATA%\\oknowledge

The split on Windows is the one that matters. %APPDATA% roams -- a domain
account can carry it to another machine -- and %LOCALAPPDATA% does not. The
config is a file you wrote and would want on both machines; the queue is a
list of locks and half-finished work that belongs to the machine that started
it. So: config roams, state stays.

XDG_CONFIG_HOME and XDG_STATE_HOME are honoured on both systems. Not for
Windows users, who will never set them, but because it leaves one code path
instead of two, and the tests that pin it run everywhere.
"""

from __future__ import annotations

import os
from pathlib import Path

APP = "oknowledge"

# Read through the module (`places.WINDOWS`), not captured by the functions, so
# a test can ask the other system's question without reaching for os.name --
# patching that in the middle of a test changes what os.path answers too.
WINDOWS = os.name == "nt"


def _set(value: str) -> bool:
    """The XDG spec: a relative path means the variable is not set."""
    return bool(value) and os.path.isabs(value)


def _base(xdg: str, windows: str, fallback: tuple[str, ...]) -> Path:
    chosen = os.environ.get(xdg, "")
    if not _set(chosen) and WINDOWS:
        chosen = os.environ.get(windows, "")
    if _set(chosen):
        return Path(chosen)
    # A Windows session with no %APPDATA% is a broken session, but the answer
    # to "where does this live" is still a path: the error people get should
    # be about the file, not about a variable they have never heard of.
    return Path.home().joinpath(*fallback)


def config_dir() -> Path:
    return _base("XDG_CONFIG_HOME", "APPDATA", (".config",)) / APP


def state_dir() -> Path:
    return _base("XDG_STATE_HOME", "LOCALAPPDATA", (".local", "state")) / APP
