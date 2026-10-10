"""Who can read the files this program writes.

On POSIX that is a question with an answer: the mode says it and chmod sets
it. On Windows the mode is decoration -- chmod accepts 0o600 and changes
nothing an attacker would notice, and os.stat reports 0o666 for every file --
so what keeps a key private there is the ACL on the user's profile folder.
The point of this module is that the code stops saying otherwise.
"""

import os
import stat

import pytest

from marks import posix_only
from oknowledge import perms


def a_file(tmp_path):
    path = tmp_path / "secret"
    path.write_text("x", encoding="utf-8")
    path.chmod(0o644)
    return path


def test_on_posix_the_file_ends_up_yours_alone(tmp_path, monkeypatch):
    monkeypatch.setattr(perms.places, "WINDOWS", False)
    path = a_file(tmp_path)

    perms.only_you(path)

    assert stat.S_IMODE(path.stat().st_mode) == 0o600


@posix_only
def test_on_windows_nothing_is_touched(tmp_path, monkeypatch):
    """Not a no-op out of laziness: a chmod there returns success and changes
    nothing, which is the most expensive kind of line to have in a file about
    secrets -- it reads like a guarantee."""
    path = a_file(tmp_path)          # before the guard: Path.chmod is os.chmod
    monkeypatch.setattr(perms.places, "WINDOWS", True)
    monkeypatch.setattr(os, "chmod", lambda *a, **k: pytest.fail("chmod on Windows"))

    perms.only_you(path)

    assert stat.S_IMODE(path.stat().st_mode) == 0o644


def test_a_mode_that_cannot_be_set_is_still_said_out_loud(tmp_path, monkeypatch):
    """The one thing that must not happen quietly. If chmod fails on POSIX the
    file is written and more readable than it should be; the caller gets to
    decide, which for config.save() means the save fails loudly."""
    monkeypatch.setattr(perms.places, "WINDOWS", False)

    with pytest.raises(OSError):
        perms.only_you(tmp_path / "nothing-here")
