"""Every opencode run goes through bubblewrap.

opencode is an agent with bash and the network, and the prompt it gets
carries text from a web page. Restricting its tools from its own config
costs the free tier (measured: 403), so it is locked in from the outside:
an empty /home except opencode's own four folders.
"""

import subprocess
from pathlib import Path

import pytest

from oknowledge.ai.base import EngineError
from oknowledge.ai.opencode import NO_BWRAP, OpenCodeEngine, opencode_dirs, sandboxed

XDG = ("XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME")


@pytest.fixture
def home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    for var in XDG:
        monkeypatch.delenv(var, raising=False)
    return home


def which(found):
    return lambda name: found.get(name)


def pairs(argv, flag):
    """Every (source, target) mounted with `flag`."""
    return [(argv[i + 1], argv[i + 2]) for i, part in enumerate(argv) if part == flag]


ARGV = ["opencode", "run", "--pure", "-m", "opencode/x-free", "hola"]


def test_the_sandbox_runs_bwrap_and_ends_with_the_real_command(home, tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", which({"bwrap": "/usr/bin/bwrap",
                                               "opencode": "/usr/bin/opencode"}))
    argv = sandboxed(ARGV, str(tmp_path / "work"))
    assert argv[0] == "/usr/bin/bwrap"
    assert argv[-6:] == ["/usr/bin/opencode", "run", "--pure", "-m", "opencode/x-free", "hola"]
    for flag in ("--unshare-all", "--share-net", "--die-with-parent"):
        assert flag in argv


def test_the_home_is_empty_and_your_files_are_not_mounted(home, tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", which({"bwrap": "/usr/bin/bwrap",
                                               "opencode": "/usr/bin/opencode"}))
    argv = sandboxed(ARGV, str(tmp_path / "work"))
    tmpfs = [argv[j + 1] for j, part in enumerate(argv) if part == "--tmpfs"]
    assert tmpfs == ["/tmp", "/home"]
    mounted = [src for flag in ("--bind", "--ro-bind", "--ro-bind-try")
               for src, _ in pairs(argv, flag)]
    assert str(home) not in mounted
    for secret in (".config/oknowledge", ".ssh", "Projects"):
        assert not any(secret in src for src in mounted), secret


def test_opencode_keeps_its_own_four_folders_and_they_exist(home, tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", which({"bwrap": "/usr/bin/bwrap",
                                               "opencode": "/usr/bin/opencode"}))
    argv = sandboxed(ARGV, str(tmp_path / "work"))
    folders = [home / ".local/share/opencode", home / ".config/opencode",
               home / ".cache/opencode", home / ".local/state/opencode"]
    assert opencode_dirs() == folders
    for folder in folders:
        assert (str(folder), str(folder)) in pairs(argv, "--bind")
        assert folder.is_dir()


def test_the_xdg_variables_move_opencode_s_folders(home, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    assert opencode_dirs()[0] == tmp_path / "data" / "opencode"


def test_the_resolver_and_the_work_folder_are_mounted(home, tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", which({"bwrap": "/usr/bin/bwrap",
                                               "opencode": "/usr/bin/opencode"}))
    argv = sandboxed(ARGV, str(tmp_path / "work"))
    assert ("/run/systemd/resolve", "/run/systemd/resolve") in pairs(argv, "--ro-bind-try")
    assert (str(tmp_path / "work"), "/work") in pairs(argv, "--bind")
    assert argv[argv.index("--chdir") + 1] == "/work"
    assert argv[argv.index("--setenv") + 1:argv.index("--setenv") + 3] == ["HOME", str(home)]


def test_a_binary_outside_usr_has_its_folder_mounted_read_only(home, tmp_path, monkeypatch):
    binary = tmp_path / "mise" / "opencode" / "1.18.35" / "opencode"
    binary.parent.mkdir(parents=True)
    binary.write_text("")
    monkeypatch.setattr("shutil.which", which({"bwrap": "/usr/bin/bwrap",
                                               "opencode": str(binary)}))
    argv = sandboxed(ARGV, str(tmp_path / "work"))
    assert (str(binary.parent), str(binary.parent)) in pairs(argv, "--ro-bind")
    assert argv[-6] == str(binary)


def test_a_binary_under_usr_needs_no_extra_mount(home, tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", which({"bwrap": "/usr/bin/bwrap",
                                               "opencode": "/usr/bin/opencode"}))
    argv = sandboxed(ARGV, str(tmp_path / "work"))
    assert ("/usr/bin", "/usr/bin") not in pairs(argv, "--ro-bind")


def test_without_bwrap_it_refuses_with_the_way_to_install_it(home, tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", which({"opencode": "/usr/bin/opencode"}))
    with pytest.raises(EngineError) as raised:
        sandboxed(ARGV, str(tmp_path))
    assert str(raised.value) == NO_BWRAP
    assert "pacman -S bubblewrap" in NO_BWRAP


def test_without_opencode_it_says_so(home, tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", which({"bwrap": "/usr/bin/bwrap"}))
    with pytest.raises(EngineError, match="opencode is not installed.*'opencode'"):
        sandboxed(ARGV, str(tmp_path))


def test_complete_runs_inside_the_sandbox(monkeypatch):
    seen = {}

    def wrap(argv, cwd):
        seen["inner"] = argv
        return ["bwrap", "--", *argv]

    def run(argv, **kwargs):
        seen["ran"] = argv
        return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")

    monkeypatch.setattr("oknowledge.ai.opencode.sandboxed", wrap)
    monkeypatch.setattr("subprocess.run", run)
    assert OpenCodeEngine(model="opencode/x-free").complete("hola") == "ok"
    assert seen["ran"] == ["bwrap", "--", *seen["inner"]]
    assert seen["inner"][:5] == ["opencode", "run", "--pure", "-m", "opencode/x-free"]


def test_without_bwrap_opencode_is_never_launched(monkeypatch):
    def run(argv, **kwargs):
        raise AssertionError("opencode ran outside the sandbox")

    def refuse(argv, cwd):
        raise EngineError(NO_BWRAP)

    monkeypatch.setattr("oknowledge.ai.opencode.sandboxed", refuse)
    monkeypatch.setattr("subprocess.run", run)
    with pytest.raises(EngineError, match="bubblewrap"):
        OpenCodeEngine(model="opencode/x-free").complete("hola")
