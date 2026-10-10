"""Taking the lock on a link, on Linux and on Windows.

The queue rests on one guarantee: the lock belongs to the *open file*, so when
a process dies the system drops it. There is no timeout to guess at, and a run
that crashed never leaves a link looking busy forever. Both systems give that
guarantee -- flock does, and so does msvcrt.locking -- which is why this
module is twenty lines and not a heartbeat protocol.

Two functions, and the caller owns the handle:

    take(fd)   -> True if it is ours now, False if somebody else has it
    probe(fd)  -> True if somebody else has it right now, and either way this
                  handle is left holding nothing

The one real difference between the systems lives in `probe`. flock has a
shared mode, so a probe can ask without taking anything. msvcrt has no such
thing, so there the probe takes the lock for an instant and hands it straight
back. If another process tries to take it in that instant it will believe the
link is busy and leave it for the next run. That is the safe side of the
mistake -- never two processes on one note, sometimes one link postponed --
and it is the whole reason this comment exists.

msvcrt is imported inside the functions on purpose: the module does not exist
on Linux, and this way the Windows branch can still be read, imported and
tested here against a stub.
"""

from __future__ import annotations

import errno
import os

# What "somebody else has it" looks like. EACCES is the Windows answer and
# EWOULDBLOCK the POSIX one; the rest are what the C libraries have been known
# to use for the same thing.
BUSY = frozenset({errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK, errno.EDEADLK})

# One byte, from the start of the file. Which byte does not matter as long as
# everybody agrees, and the first one needs no file to exist first.
BYTES = 1


def _posix_take(fd: int) -> bool:
    import fcntl

    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as error:
        if error.errno in BUSY:
            return False
        raise
    return True


def _posix_probe(fd: int) -> bool:
    import fcntl

    try:
        fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
    except OSError as error:
        if error.errno in BUSY:
            return True
        raise
    # Given back, like the Windows branch gives its exclusive one back: both
    # probes leave the handle holding nothing. The queue closes the handle a
    # line later and would not notice, but a shared lock left behind is a
    # thing that makes the next question answer itself.
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass
    return False


def _nt_take(fd: int) -> bool:
    import msvcrt

    # msvcrt locks from wherever the handle happens to be, and the queue writes
    # a pid into this same file: without the rewind, two processes would lock
    # two different bytes and both think they won.
    os.lseek(fd, 0, os.SEEK_SET)
    try:
        msvcrt.locking(fd, msvcrt.LK_NBLCK, BYTES)
    except OSError:
        # Every OSError is read as "busy", including the ones that are not.
        # The cost of being wrong here is one link waiting for the next run;
        # the cost of raising is a link lost out of a batch of fifty.
        return False
    return True


def _nt_probe(fd: int) -> bool:
    import msvcrt

    if not _nt_take(fd):
        return True
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, BYTES)
    except OSError:
        # It goes when the handle closes, which is the guarantee that matters.
        pass
    return False


if os.name == "nt":
    take, probe = _nt_take, _nt_probe
else:
    take, probe = _posix_take, _posix_probe
