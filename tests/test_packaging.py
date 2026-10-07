"""What the project declares about itself.

`pip install -e .[dev]` is the one command a contributor runs before anything
else, so a name in that list that nothing imports costs them a download and a
dependency tree for nothing (F7).
"""

import pathlib
import re
import tomllib
from pathlib import PurePosixPath

ROOT = pathlib.Path(__file__).resolve().parent.parent


def dev_dependencies():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    names = []
    for spec in data["project"]["optional-dependencies"]["dev"]:
        names.append(re.split(r"[<>=!~\[ ]", spec, maxsplit=1)[0])
    return names


def test_every_dev_dependency_is_one_the_repo_uses():
    code = "\n".join(p.read_text(encoding="utf-8")
                     for folder in ("src", "tests")
                     for p in (ROOT / folder).rglob("*.py"))
    unused = [name for name in dev_dependencies()
              if not re.search(rf"\b{re.escape(name.replace('-', '_'))}\b", code)]
    assert unused == [], f"declared for development and imported by nothing: {unused}"


def test_the_dev_extra_is_not_empty_either():
    """So the test above cannot pass by the list disappearing."""
    assert "pytest" in dev_dependencies()


def shipped(relative: str, globs) -> bool:
    """Whether a wheel would include this package-relative path.

    fnmatch is not usable here (its `*` crosses `/`, so a prompt in a
    subdirectory would look shipped by `prompts/*.txt`), nor PurePath.match
    (unanchored on the left). full_match anchors the whole path and keeps `*`
    single-level.
    """
    return any(PurePosixPath(relative).full_match(g) for g in globs)


def test_the_guard_can_fail_for_a_subdirectory():
    globs = ["prompts/*.txt"]

    assert shipped("prompts/analyze.txt", globs)
    assert not shipped("prompts/mentions/tools.txt", globs)


def test_every_prompt_the_code_loads_is_declared_as_package_data():
    """An editable install finds a file the wheel would not ship. This is the
    only place that difference shows up before a user hits it."""
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    globs = data["tool"]["setuptools"]["package-data"]["oknowledge"]
    package = ROOT / "src" / "oknowledge"

    missing = [str(p) for p in (package / "prompts").rglob("*.txt")
               if not shipped(p.relative_to(package).as_posix(), globs)]

    assert missing == [], f"loaded at runtime, shipped by nothing: {missing}"


# --- the browser's half, which Python never runs -----------------------------

# Captured at import, before conftest's autouse fixture replaces them for every
# test. run() reaches Popen, so both halves have to be the real ones, and they
# are put back for this one test only -- the way that fixture says to.
import shutil  # noqa: E402
import subprocess  # noqa: E402

import pytest  # noqa: E402

_REAL = {name: getattr(subprocess, name) for name in ("run", "Popen")}


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
@pytest.mark.parametrize("name", ["popup.js", "redo.js"])
def test_the_scripts_the_pages_load_are_valid_javascript(name, monkeypatch):
    """Nothing else in this suite runs these files. A typo in one of them is a
    button that silently does nothing in the browser and nothing at all here,
    which is the worst way for a page to break: no error, no test, no sign.
    """
    for attribute, real in _REAL.items():
        monkeypatch.setattr(subprocess, attribute, real)
    path = ROOT / "src" / "oknowledge" / "web" / "static" / name

    done = subprocess.run(["node", "--check", str(path)],
                          capture_output=True, text=True)

    assert done.returncode == 0, done.stderr
