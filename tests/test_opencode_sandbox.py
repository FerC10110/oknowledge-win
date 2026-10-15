"""On Windows opencode runs without a sandbox.

The Linux version locks every opencode run in with bubblewrap and pasta;
neither exists here, and the choice was to keep opencode rather than lose it.
It is an agent with a shell and the network, and a search prompt carries
text from web pages: the README says so where it names the engine.
"""

import subprocess

import pytest

from oknowledge.ai.opencode import OpenCodeEngine, sandboxed

ARGV = ["opencode", "run", "--pure", "-m", "opencode/x-free", "hola"]


def nothing_installed(name):
    return None


def test_the_command_runs_as_it_is(tmp_path):
    assert sandboxed(ARGV, str(tmp_path)) == ARGV


def test_it_needs_neither_bubblewrap_nor_pasta(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", nothing_installed)
    assert sandboxed(ARGV, str(tmp_path)) == ARGV


def test_opencode_runs_in_an_empty_folder_of_its_own(monkeypatch):
    seen = {}

    def run(argv, **kwargs):
        seen["argv"], seen["cwd"] = argv, kwargs["cwd"]
        return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")

    monkeypatch.setattr("subprocess.run", run)
    monkeypatch.setattr("oknowledge.ai.opencode.isolation", lambda name: "--pure")    # a 1.x
    assert OpenCodeEngine(model="opencode/x-free").complete("hola") == "ok"
    assert seen["argv"] == ARGV
    assert seen["cwd"] and "oknowledge" not in seen["cwd"].lower()


# --- opencode 2.0 dropped --pure: a run of its own is --standalone -----------------------------

@pytest.mark.parametrize("said, flag", [
    ("opencode v2.0.29\n", "--standalone"),
    ("2.1.0\n", "--standalone"),
    ("opencode v1.18.35\n", "--pure"),
    ("1.18.28\n", "--pure"),
    ("", "--standalone"),
    ("who knows\n", "--standalone"),
])
def test_the_run_flag_follows_the_version(monkeypatch, said, flag):
    from oknowledge.ai import opencode
    asked = []

    def run(argv, **kw):
        asked.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout=said, stderr="")
    monkeypatch.setattr(subprocess, "run", run)
    assert opencode.isolation("opencode") == flag
    assert asked == [["opencode", "--version"]]


def test_a_version_that_cannot_be_asked_is_taken_as_the_new_one(monkeypatch):
    from oknowledge.ai import opencode

    def run(argv, **kw):
        raise OSError("gone")
    monkeypatch.setattr(subprocess, "run", run)
    assert opencode.isolation("opencode") == "--standalone"


def test_the_version_is_asked_once(monkeypatch):
    from oknowledge.ai import opencode
    asked = []
    monkeypatch.setattr(subprocess, "run", lambda argv, **kw: asked.append(argv) or
                        subprocess.CompletedProcess(argv, 0, stdout="2.0.29", stderr=""))
    opencode.isolation("opencode")
    opencode.isolation("opencode")
    assert len(asked) == 1


def test_the_engine_runs_with_the_versions_flag(monkeypatch):
    from oknowledge.ai import opencode
    seen = {}
    monkeypatch.setattr(opencode, "isolation", lambda name: "--standalone")

    def run(argv, **kwargs):
        seen["argv"] = argv
        return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")
    monkeypatch.setattr(subprocess, "run", run)
    OpenCodeEngine(model="opencode/x-free").complete("hola")
    assert seen["argv"] == ["opencode", "run", "--standalone", "-m", "opencode/x-free", "hola"]
