"""Where the files go -- including on a system this machine is not.

The Windows half of these tests runs here, because places.py asks one flag and
asks it when the question comes, so both answers can be had in one session.
What no test here can prove is that %APPDATA% is set and writable on a real
Windows machine. The README says which claims are in that bucket.
"""

import pytest

from oknowledge import places


@pytest.fixture(autouse=True)
def a_home_nobody_shares(tmp_path, monkeypatch):
    """conftest sets XDG_STATE_HOME for the whole suite, and half of what is
    being tested here is what happens when nothing is set."""
    monkeypatch.setenv("HOME", str(tmp_path))
    for name in ("XDG_CONFIG_HOME", "XDG_STATE_HOME", "APPDATA", "LOCALAPPDATA"):
        monkeypatch.delenv(name, raising=False)
    return tmp_path


@pytest.fixture
def linux(monkeypatch):
    monkeypatch.setattr(places, "WINDOWS", False)


@pytest.fixture
def windows(monkeypatch):
    """The flag and not os.name: patching os.name would change what os.path
    answers in the middle of a test, and this is a question about one module."""
    monkeypatch.setattr(places, "WINDOWS", True)


def test_on_linux_the_config_is_under_dot_config(linux, a_home_nobody_shares):
    assert places.config_dir() == a_home_nobody_shares / ".config" / "oknowledge"


def test_on_linux_the_state_is_under_local_state(linux, a_home_nobody_shares):
    assert places.state_dir() == a_home_nobody_shares / ".local" / "state" / "oknowledge"


def test_on_windows_the_config_goes_to_roaming_appdata(windows, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    assert places.config_dir() == tmp_path / "Roaming" / "oknowledge"


def test_on_windows_the_state_goes_to_the_local_one(windows, tmp_path, monkeypatch):
    """Local and not roaming on purpose: a queue that followed the user to
    another machine would hand that machine locks and half-done links that
    belong to a process it has never seen."""
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))

    assert places.state_dir() == tmp_path / "Local" / "oknowledge"
    assert places.state_dir() != places.config_dir()


@pytest.mark.parametrize("on_windows", [False, True])
def test_an_absolute_xdg_variable_wins_on_either_system(on_windows, tmp_path, monkeypatch):
    """The point of honouring them on Windows is that there is one code path
    and the tests do not need two."""
    monkeypatch.setattr(places, "WINDOWS", on_windows)
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg-state"))

    assert places.config_dir() == tmp_path / "xdg-config" / "oknowledge"
    assert places.state_dir() == tmp_path / "xdg-state" / "oknowledge"


@pytest.mark.parametrize("on_windows", [False, True])
def test_a_relative_xdg_variable_is_the_same_as_unset(on_windows, tmp_path, monkeypatch):
    """What the XDG spec says to do with one, and the behaviour the queue had
    before any of this moved."""
    monkeypatch.setattr(places, "WINDOWS", on_windows)
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.setenv("XDG_CONFIG_HOME", "relative/dir")
    monkeypatch.setenv("XDG_STATE_HOME", "relative/dir")

    config = tmp_path / ("Roaming" if on_windows else ".config")
    state = tmp_path / "Local" if on_windows else tmp_path / ".local" / "state"
    assert places.config_dir() == config / "oknowledge"
    assert places.state_dir() == state / "oknowledge"


def test_windows_with_no_appdata_still_answers(windows, a_home_nobody_shares):
    """A Windows session without %APPDATA% is broken, but the answer to "where
    does the config live" is still a path and not a crash."""
    assert places.config_dir().is_relative_to(a_home_nobody_shares)
    assert places.state_dir().is_relative_to(a_home_nobody_shares)


@pytest.mark.parametrize("on_windows", [False, True])
def test_the_last_part_is_always_the_app(on_windows, monkeypatch, tmp_path):
    monkeypatch.setattr(places, "WINDOWS", on_windows)
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))

    assert places.config_dir().name == "oknowledge"
    assert places.state_dir().name == "oknowledge"


def test_the_flag_agrees_with_the_platform():
    """Not a tautology: places.py asks os.name, this asks sys.platform. A flag
    that got flipped would pass every test above -- they all set it -- and this
    is the one that would not."""
    import sys

    assert places.WINDOWS == sys.platform.startswith("win")
