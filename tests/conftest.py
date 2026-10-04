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
