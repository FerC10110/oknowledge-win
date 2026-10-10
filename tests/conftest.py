"""Shared test setup.

Session-scoped so every test module inherits it: the extractors in later tasks
pull in trafilatura too, and the warning below only bites the first load.
"""

import warnings

import pytest


@pytest.fixture(scope="session", autouse=True)
def warm_up_tld():
    """tld (a trafilatura dependency) warns about codecs.open() when it first
    loads its suffix list; under -W error that breaks it for the rest of the
    run. Load it once with the third-party warning silenced."""
    from tld import get_tld

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        get_tld("https://e.com/x", fail_silently=False)


@pytest.fixture(autouse=True)
def no_network_and_no_subprocess(monkeypatch):
    """Nothing reaches the network or runs a program unless a test fakes it first.

    Tests that need either replace these afterwards (their monkeypatch runs
    later and is undone first). pytest.fail raises a BaseException, so no
    `except Exception` in the code under test can swallow the alarm."""
    import subprocess

    import httpx

    def refuse(*args, **kwargs):
        pytest.fail("a test reached the network or ran a program without faking it")

    # The real transport is the only one that opens sockets; MockTransport is untouched.
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)
    for name in ("run", "Popen", "check_output", "check_call", "call"):
        monkeypatch.setattr(subprocess, name, refuse)


@pytest.fixture(autouse=True)
def isolated_config_path(tmp_path, monkeypatch):
    """No test may write the real ~/.config/oknowledge/config.toml.

    Every module that binds the name gets its own copy, so all three are
    redirected. This is the second pin of its kind for the same reason as the
    first (the state tree): a test whose writes land in tmp_path only while
    the code under test is correct is not pinned at all. `config.save()`
    defaults to `cfg.source or CONFIG_PATH`, so a test that saves a Config it
    built itself -- or any test at all while that default is broken, as a
    mutant demonstrated by overwriting the real file -- aims at the user's own
    config. The path handed out here does not exist, so a `load()` that reaches
    it fails with the ordinary "no config file at ..." instead of reading the
    user's.
    """
    from oknowledge import cli, config
    from oknowledge.web import app

    path = tmp_path / "isolated-config" / "config.toml"
    for module in (config, cli, app):
        monkeypatch.setattr(module, "CONFIG_PATH", path)
    return path


@pytest.fixture(autouse=True)
def isolated_state_tree(tmp_path, monkeypatch):
    """The twin of the pin above, for the same reason.

    The queue lives under $XDG_STATE_HOME, and until now the pin was made
    per-module, in the files whose tests reach the queue on purpose. That is
    the arrangement that let a cross-site test reach the real tree once the
    middleware it was testing was mutated away: safe while the code is
    correct, which is not what a pin is. The modules that pin it themselves
    still do -- their fixtures run after this one and win -- and one of them
    asserts the result.
    """
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg-state"))
