"""The in-memory record of one batch run, and the worker that drives it.

Nothing here touches disk. The record lives in the server's memory on
purpose: if the process dies the run died with it, so there is nothing to
resume and no stale file left behind to explain away.
"""

import pytest

from oknowledge.web import batch as module
from oknowledge.web.batch import Batch, run


class _Config:
    """As much of a Config as the worker reads: whether to trace, and nothing
    else. A real one needs a vault on disk, which none of this touches."""

    trace_to = ""


NO_TRACE = _Config()


def _result(status="ok", url="https://a.com/x"):
    from oknowledge.pipeline import Result
    return Result(id="abc", url=url, path=None, status=status)


# --- The record ---------------------------------------------------------------

def test_a_fresh_record_is_idle_and_empty():
    state = Batch().snapshot()

    assert not state.running
    assert (state.total, state.done, state.failed) == (0, 0, 0)
    assert state.error is None


def test_starting_a_run_records_how_much_work_it_is():
    held = Batch()

    assert held.start(50) is True
    state = held.snapshot()
    assert state.running
    assert state.total == 50


def test_a_second_start_while_a_run_is_in_flight_is_refused():
    """Two runs over one queue would fight for the same links and each would
    see the other's work as already done. One click at a time."""
    held = Batch()
    held.start(50)

    assert held.start(10) is False
    assert held.snapshot().total == 50          # the running total, untouched


def test_each_finished_link_moves_the_count():
    held = Batch()
    held.start(2)

    held.step(_result())

    assert held.snapshot().done == 1


def test_a_link_that_failed_is_counted_as_done_and_as_failed():
    """A bar that waits for a dead link to succeed never reaches its total."""
    held = Batch()
    held.start(2)

    held.step(_result(status="failed"))

    state = held.snapshot()
    assert (state.done, state.failed) == (1, 1)


@pytest.mark.parametrize("status", ["ok", "partial"])
def test_a_link_that_did_not_fail_is_not_counted_as_failed(status):
    held = Batch()
    held.start(1)

    held.step(_result(status=status))

    assert held.snapshot().failed == 0


def test_finishing_leaves_the_numbers_to_read():
    """The page is shown after the run ends, and "it worked" is not an answer:
    the user wants to know how many of the fifty came back."""
    held = Batch()
    held.start(2)
    held.step(_result())
    held.step(_result(status="failed"))

    held.finish()

    state = held.snapshot()
    assert not state.running
    assert (state.total, state.done, state.failed) == (2, 2, 1)


def test_a_new_run_does_not_inherit_the_last_one_s_numbers():
    held = Batch()
    held.start(2)
    held.step(_result())
    held.step(_result(status="failed"))
    held.finish("something broke")

    held.start(5)

    state = held.snapshot()
    assert (state.total, state.done, state.failed) == (5, 0, 0)
    assert state.error is None


def test_a_run_that_broke_says_so():
    held = Batch()
    held.start(2)

    held.finish("could not read the queue")

    state = held.snapshot()
    assert not state.running
    assert state.error == "could not read the queue"


def test_a_step_after_the_run_ended_is_ignored():
    """A link already written by a run the server forgot must not move the
    next run's bar: the hook is held by whoever retry() still has in flight."""
    held = Batch()
    held.start(1)
    held.finish()

    held.step(_result())

    assert held.snapshot().done == 0


# --- The worker ---------------------------------------------------------------

def test_the_worker_asks_retry_for_the_batch_size_and_passes_the_hook(monkeypatch):
    seen = {}

    def fake_retry(cfg, limit=None, on_step=None, trace=None):
        seen.update(cfg=cfg, limit=limit)
        on_step(_result())
        return []

    monkeypatch.setattr(module, "retry", fake_retry)
    held = Batch()
    held.start(10)

    run(NO_TRACE, held, 10)

    assert seen == {"cfg": NO_TRACE, "limit": 10}
    assert held.snapshot().done == 1


def test_the_worker_leaves_the_record_idle_when_it_is_done(monkeypatch):
    monkeypatch.setattr(module, "retry", lambda cfg, limit=None, on_step=None: [])
    held = Batch()
    held.start(10)

    run(NO_TRACE, held, 10)

    assert not held.snapshot().running


def test_a_run_that_blows_up_still_frees_the_button(monkeypatch):
    """Left running, the button is dead until the server restarts, and the user
    has no way to know why -- so the failure has to come back as text."""
    def explode(cfg, limit=None, on_step=None, trace=None):
        raise OSError("no space left on device")

    monkeypatch.setattr(module, "retry", explode)
    held = Batch()
    held.start(10)

    run(NO_TRACE, held, 10)             # must not raise: a task has nowhere to raise to

    state = held.snapshot()
    assert not state.running
    assert state.error is not None
    assert "no space left on device" in state.error
