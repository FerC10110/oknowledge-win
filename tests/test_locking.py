"""Taking the lock on a link, on either system.

The contract is two sentences, and both implementations are held to it: taking
a lock somebody else holds fails instead of waiting, and the lock goes away
when the handle closes. That second one is what makes a process that died not
leave a link busy forever -- there is no timeout to guess at and no crashed
run left looking busy.

The Windows half is exercised against a stub of msvcrt. That proves the logic
and not the operating system, which is the honest limit of a fork written on
Linux; the README says so in as many words.
"""

import errno
import os
import sys
import types

import pytest

from oknowledge import locking


class FakeMsvcrt(types.ModuleType):
    """Enough of msvcrt to drive the Windows branch, and no more.

    It records the file position of every call, because msvcrt locks from
    wherever the handle happens to be and the byte we mean is the first one.
    """

    LK_NBLCK = 2
    LK_UNLCK = 0

    def __init__(self, busy=False, unlock_fails=False):
        super().__init__("msvcrt")
        self.busy, self.unlock_fails, self.calls = busy, unlock_fails, []

    def locking(self, fd, mode, nbytes):
        self.calls.append((mode, nbytes, os.lseek(fd, 0, os.SEEK_CUR)))
        if mode == self.LK_UNLCK:
            if self.unlock_fails:
                raise OSError(errno.EACCES, "it will not come back")
            return
        if self.busy:
            raise OSError(errno.EACCES, "somebody else has it")


@pytest.fixture
def windows(monkeypatch):
    def install(**how):
        fake = FakeMsvcrt(**how)
        monkeypatch.setitem(sys.modules, "msvcrt", fake)
        return fake
    return install


@pytest.fixture
def handle(tmp_path):
    """An open lock file, the way the queue opens one."""
    fd = os.open(tmp_path / "a.lock", os.O_CREAT | os.O_RDWR, 0o666)
    yield fd
    os.close(fd)


# --- what the system is asked for --------------------------------------------

def test_the_lock_is_taken_with_the_tool_the_system_has():
    pair = (locking.take, locking.probe)
    if os.name == "nt":
        assert pair == (locking._nt_take, locking._nt_probe)
    else:
        assert pair == (locking._posix_take, locking._posix_probe)


# --- windows ------------------------------------------------------------------

def test_a_file_nobody_holds_is_taken(windows, handle):
    fake = windows()
    assert locking._nt_take(handle) is True
    assert fake.calls == [(FakeMsvcrt.LK_NBLCK, 1, 0)]


def test_a_file_somebody_holds_is_not_taken(windows, handle):
    windows(busy=True)
    assert locking._nt_take(handle) is False


def test_the_byte_locked_is_the_first_one_whatever_the_handle_was_doing(windows,
                                                                       handle):
    fake = windows()
    os.lseek(handle, 50, os.SEEK_SET)      # a pid was written, say
    locking._nt_take(handle)
    assert fake.calls[0][2] == 0


def test_probing_a_free_file_gives_the_lock_straight_back(windows, handle):
    """There is no shared mode here, so the probe takes the lock for an instant
    and has to hand it back or the next take of our own would see it busy."""
    fake = windows()
    assert locking._nt_probe(handle) is False
    assert [mode for mode, _, _ in fake.calls] == [FakeMsvcrt.LK_NBLCK,
                                                   FakeMsvcrt.LK_UNLCK]


def test_probing_a_held_file_says_held_and_hands_nothing_back(windows, handle):
    fake = windows()
    fake.busy = True
    assert locking._nt_probe(handle) is True
    # Nothing was taken, so nothing may be released: releasing a lock we never
    # had is how you unlock somebody else's.
    assert FakeMsvcrt.LK_UNLCK not in [mode for mode, _, _ in fake.calls]


def test_a_lock_that_will_not_come_back_is_not_a_crash(windows, handle):
    """It goes when the handle closes anyway, which is the whole guarantee."""
    windows(unlock_fails=True)
    assert locking._nt_probe(handle) is False


# --- posix, against the real thing -------------------------------------------

def test_two_handles_cannot_both_take_it(tmp_path):
    path = tmp_path / "b.lock"
    first = os.open(path, os.O_CREAT | os.O_RDWR, 0o666)
    second = os.open(path, os.O_RDWR)
    try:
        assert locking._posix_take(first) is True
        assert locking._posix_take(second) is False
    finally:
        os.close(first)
        os.close(second)


def test_a_probe_sees_what_somebody_else_took(tmp_path):
    path = tmp_path / "c.lock"
    held = os.open(path, os.O_CREAT | os.O_RDWR, 0o666)
    looking = os.open(path, os.O_RDWR)
    try:
        assert locking._posix_probe(looking) is False
        locking._posix_take(held)
        assert locking._posix_probe(looking) is True
    finally:
        os.close(held)
        os.close(looking)


def test_a_probe_leaves_the_handle_holding_nothing(tmp_path):
    """Both probes hand back whatever they took. A shared lock left behind on
    the asking handle is a thing that makes the next question answer itself,
    and it kept one of these tests green for the wrong reason."""
    path = tmp_path / "e.lock"
    asking = os.open(path, os.O_CREAT | os.O_RDWR, 0o666)
    other = os.open(path, os.O_RDWR)
    try:
        assert locking._posix_probe(asking) is False
        # Nothing is in the way, so somebody else can still take it whole.
        assert locking._posix_take(other) is True
    finally:
        os.close(asking)
        os.close(other)


def test_closing_the_handle_is_what_releases_it(tmp_path):
    """The guarantee the whole queue rests on: a process that died holds
    nothing, so there is no stale lock to time out."""
    path = tmp_path / "d.lock"
    gone = os.open(path, os.O_CREAT | os.O_RDWR, 0o666)
    locking._posix_take(gone)
    os.close(gone)                          # as if the process had died

    after = os.open(path, os.O_RDWR)
    try:
        assert locking._posix_probe(after) is False
        assert locking._posix_take(after) is True
    finally:
        os.close(after)
