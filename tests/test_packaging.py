"""What the project declares about itself.

`pip install -e .[dev]` is the one command a contributor runs before anything
else, so a name in that list that nothing imports costs them a download and a
dependency tree for nothing (F7).
"""

import pathlib
import re
import tomllib
from fnmatch import fnmatch

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


def test_every_prompt_the_code_loads_is_declared_as_package_data():
    """An editable install finds a file the wheel would not ship. This is the
    only place that difference shows up before a user hits it."""
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    globs = data["tool"]["setuptools"]["package-data"]["oknowledge"]
    prompts = (ROOT / "src" / "oknowledge" / "prompts").rglob("*.txt")

    missing = [str(p) for p in prompts
               if not any(fnmatch(str(p.relative_to(ROOT / "src" / "oknowledge")), g)
                          for g in globs)]

    assert missing == [], f"loaded at runtime, shipped by nothing: {missing}"
