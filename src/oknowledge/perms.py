"""Making a file yours alone, on the system where that means something.

POSIX answers "who can read this" with the mode, and chmod sets it. Windows
does not: chmod there accepts 0o600 and returns success, the file keeps
whatever the folder's ACL gives it, and os.stat reports 0o666 for everything.
What keeps a key private on Windows is that it lives under the user's profile
folder, which is a thing this program cannot improve on and should not
pretend to.

So the call is one line on POSIX and nothing on Windows -- and nothing, said
out loud here, instead of a chmod that looks like a guarantee in the one file
of this program that is about a secret.
"""

from __future__ import annotations

import os
from pathlib import Path

from . import places

MINE = 0o600


def only_you(path: Path) -> None:
    """chmod 0600, where the system keeps that promise.

    Raises on POSIX if it cannot: a config file that was written but left
    readable is something the caller has to hear about, and config.save() is
    the caller.
    """
    if places.WINDOWS:
        return
    os.chmod(path, MINE)
