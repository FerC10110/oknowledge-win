"""Marks the whole suite shares.

`posix_only` is for a test whose *claim* is about something Windows does not
have: a mode bit that takes effect, a fork, a flock, a symlink, a umask. There
are about forty-five of them and they are skipped on Windows rather than
deleted, because on Linux they are the proof they always were -- most of them
are how this suite says "and now the disk refuses", which has no equivalent
there.

What this is not is a claim that the rest of the suite passes on Windows. The
marks were chosen on a Linux machine by reading what each test asserts; the
first real run on Windows is likely to find a few more, and the README says
so.
"""

import os

import pytest

posix_only = pytest.mark.skipif(
    os.name == "nt",
    reason="the claim is about POSIX: file modes, fork, flock, symlinks or the umask",
)
