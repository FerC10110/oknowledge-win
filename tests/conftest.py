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
