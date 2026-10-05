"""What the project declares about itself.

`pip install -e .[dev]` is the one command a contributor runs before anything
else, so a name in that list that nothing imports costs them a download and a
dependency tree for nothing (F7).
"""

import pathlib
import re
import tomllib

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
