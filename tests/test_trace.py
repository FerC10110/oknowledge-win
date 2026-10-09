import dataclasses

import pytest

from oknowledge.trace import SILENT, Step, guarded


def test_a_tracer_that_explodes_never_reaches_the_caller():
    """The whole reason the wrapper exists: tracing is new code in the
    critical path, and the rule of the module is that a link never dies for
    something that is not the link."""
    def angry(step):
        raise RuntimeError("boom")

    guarded(angry)(Step(link="a", name="extract", state="ok", seconds=1.0))


def test_no_tracer_is_one_comparison_and_nothing_else():
    assert guarded(None) is SILENT
    assert SILENT(Step(link="a", name="extract", state="start", seconds=0.0)) is None


def test_a_tracer_that_works_sees_every_step_in_order():
    seen = []
    trace = guarded(seen.append)
    trace(Step(link="a", name="find", state="start", seconds=0.0))
    trace(Step(link="a", name="find", state="ok", seconds=0.5, detail="no note yet"))
    assert [(s.name, s.state) for s in seen] == [("find", "start"), ("find", "ok")]
    assert seen[1].detail == "no note yet"


def test_a_step_says_nothing_it_was_not_told():
    step = Step(link="a", name="save", state="ok", seconds=0.1)
    assert (step.engine, step.detail) == ("", "")


def test_a_step_is_data_and_nothing_else():
    """Nobody downstream may hold a step and watch it change under them: the
    page keeps the last two hundred and reads them on every refresh."""
    step = Step(link="a", name="save", state="ok", seconds=0.1)
    assert dataclasses.is_dataclass(step)
    with pytest.raises(dataclasses.FrozenInstanceError):
        step.state = "fail"


def test_a_ctrl_c_through_the_tracer_still_stops_the_run():
    """`except Exception`, not `except BaseException`: an interrupt is the
    user talking, and swallowing it would make a long batch unstoppable."""
    def interrupted(step):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        guarded(interrupted)(Step(link="a", name="analyze", state="start", seconds=0.0))
