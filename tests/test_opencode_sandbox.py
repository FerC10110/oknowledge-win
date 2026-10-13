"""On Windows opencode runs without a sandbox.

The Linux version locks every opencode run in with bubblewrap and pasta;
neither exists here, and the choice was to keep opencode rather than lose it.
It is an agent with a shell and the network, and a search prompt carries
text from web pages: the README says so where it names the engine.
"""

import subprocess

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
    assert OpenCodeEngine(model="opencode/x-free").complete("hola") == "ok"
    assert seen["argv"] == ARGV
    assert seen["cwd"] and "oknowledge" not in seen["cwd"].lower()
