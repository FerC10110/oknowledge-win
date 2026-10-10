"""The .env beside the config: where an API key can live.

Three things this file has to get right. It must never hand a key to anybody
who did not ask for one -- not to os.environ, where the opencode subprocess
would inherit it, and not to Config, where a debug dump would print it. It
must not fall over on a file somebody edited by hand. And it must lose to the
real environment, so an export in a shell is still the quick way to try a key.
"""

import os
import stat

import pytest

from marks import posix_only
from oknowledge import env


@pytest.fixture
def config(tmp_path):
    """Where the config.toml would be; the .env sits beside it."""
    return tmp_path / "config" / "config.toml"


def written(config, text: str):
    config.parent.mkdir(parents=True, exist_ok=True)
    env.path(config).write_text(text, encoding="utf-8")


# --- reading ------------------------------------------------------------------

def test_the_env_sits_beside_the_config(config):
    assert env.path(config) == config.parent / ".env"


def test_a_key_in_the_file_is_a_key(config):
    written(config, "GROQ_API_KEY=sk-fromfile\n")
    assert env.value("GROQ_API_KEY", config) == "sk-fromfile"


def test_the_real_environment_wins_over_the_file(config, monkeypatch):
    written(config, "GROQ_API_KEY=sk-fromfile\n")
    monkeypatch.setenv("GROQ_API_KEY", "sk-fromshell")
    assert env.value("GROQ_API_KEY", config) == "sk-fromshell"


def test_a_variable_set_to_nothing_does_not_hide_the_file(config, monkeypatch):
    written(config, "GROQ_API_KEY=sk-fromfile\n")
    monkeypatch.setenv("GROQ_API_KEY", "")
    assert env.value("GROQ_API_KEY", config) == "sk-fromfile"


def test_no_file_is_no_key_and_no_crash(config):
    assert env.read(config) == {}
    assert env.value("GROQ_API_KEY", config) == ""


def test_a_directory_where_the_file_should_be_is_no_key(config):
    env.path(config).mkdir(parents=True)
    assert env.read(config) == {}


def test_a_file_written_by_a_person_is_read_the_way_a_person_writes_it(config):
    written(config, "\n".join([
        "# the key for groq",
        "",
        "  GROQ_API_KEY = sk-spaced  ",
        'OPENAI_API_KEY="sk-quoted"',
        "export MISTRAL_API_KEY='sk-exported'",
        "  # an indented comment",
    ]) + "\n")
    assert env.read(config) == {"GROQ_API_KEY": "sk-spaced",
                                "OPENAI_API_KEY": "sk-quoted",
                                "MISTRAL_API_KEY": "sk-exported"}


def test_a_file_written_on_windows_is_still_a_file(config):
    written(config, "GROQ_API_KEY=sk-crlf\r\nOPENAI_API_KEY=sk-two\r\n")
    assert env.read(config)["GROQ_API_KEY"] == "sk-crlf"


def test_what_is_not_a_variable_is_skipped_and_the_rest_is_kept(config):
    written(config, "this line says nothing\n2COOL=x\nhas space=x\nGOOD=y\n")
    assert env.read(config) == {"GOOD": "y"}


def test_the_last_line_wins_like_every_other_env_file(config):
    written(config, "GROQ_API_KEY=old\nGROQ_API_KEY=new\n")
    assert env.read(config)["GROQ_API_KEY"] == "new"


def test_a_value_with_an_equals_sign_in_it_keeps_it(config):
    written(config, "GROQ_API_KEY=a=b=c\n")
    assert env.read(config)["GROQ_API_KEY"] == "a=b=c"


def test_something_far_too_big_to_be_an_env_file_is_not_one(config):
    # Cutting it short would hand out half a key, and half a key is a 401
    # nobody can explain. A file this size is the wrong file.
    written(config, "GROQ_API_KEY=sk-real\n" + "# padding\n" * 20_000)
    assert env.path(config).stat().st_size > env.LIMIT
    assert env.read(config) == {}


def test_a_file_that_is_not_text_is_no_key(config):
    config.parent.mkdir(parents=True)
    env.path(config).write_bytes(b"\xff\xfe\x00KEY=x\n")
    # Decoded with replacements, so the name is no longer a name: nothing is
    # offered, and nothing is raised either.
    assert env.read(config) == {}


def test_reading_the_file_tells_the_environment_nothing(config):
    # The pipeline launches opencode as a subprocess. A key in os.environ is a
    # key that subprocess is handed.
    written(config, "SECRET_TEST_KEY=sk-private\n")
    env.read(config)
    env.value("SECRET_TEST_KEY", config)
    assert "SECRET_TEST_KEY" not in os.environ


def test_a_key_that_is_there_is_present_and_one_that_is_not_is_not(config):
    written(config, "GROQ_API_KEY=sk-x\n")
    assert env.present("GROQ_API_KEY", config)
    assert not env.present("OPENAI_API_KEY", config)


# --- making the file ----------------------------------------------------------

def test_the_file_is_created_for_you_to_paste_into(config):
    assert env.create("GROQ_API_KEY", config) is True
    text = env.path(config).read_text(encoding="utf-8")
    assert "GROQ_API_KEY=" in text
    # The line is there and the key is not: the file is a place to paste into,
    # so the page must still say the key is missing.
    assert env.read(config) == {"GROQ_API_KEY": ""}
    assert env.present("GROQ_API_KEY", config) is False


def test_the_file_it_creates_is_yours_alone(config):
    env.create("GROQ_API_KEY", config)
    assert stat.S_IMODE(env.path(config).stat().st_mode) == 0o600


def test_a_file_that_already_exists_is_never_touched(config):
    written(config, "GROQ_API_KEY=sk-mine\n")
    assert env.create("OPENAI_API_KEY", config) is False
    assert env.path(config).read_text(encoding="utf-8") == "GROQ_API_KEY=sk-mine\n"


@posix_only
def test_a_folder_that_cannot_be_written_is_an_answer_not_a_crash(config):
    config.parent.mkdir(parents=True)
    config.parent.chmod(0o500)
    try:
        assert env.create("GROQ_API_KEY", config) is False
    finally:
        config.parent.chmod(0o700)


@posix_only
def test_a_file_the_rest_of_the_machine_can_read_is_worth_saying(config):
    written(config, "GROQ_API_KEY=sk-x\n")
    # Both halves of "anyone else": the group alone and the world alone.
    env.path(config).chmod(0o640)
    assert env.exposed(config) is True
    env.path(config).chmod(0o604)
    assert env.exposed(config) is True
    env.path(config).chmod(0o600)
    assert env.exposed(config) is False


def test_a_file_that_is_not_there_is_not_exposed(config):
    assert env.exposed(config) is False


@posix_only
def test_on_windows_the_mode_is_not_worth_saying(config, monkeypatch):
    """Windows reports 0o666 for everything, so this check would warn that
    anyone can read your key, forever, on every machine. A warning that is
    always on is a warning nobody reads, and this one would also be wrong:
    what keeps the file private there is the folder it is in."""
    written(config, "GROQ_API_KEY=sk-x\n")
    env.path(config).chmod(0o644)

    monkeypatch.setattr(env.places, "WINDOWS", True)
    assert env.exposed(config) is False
    monkeypatch.setattr(env.places, "WINDOWS", False)
    assert env.exposed(config) is True


def test_the_file_it_creates_does_not_promise_what_the_system_will_not_keep(config, monkeypatch):
    """The header line oknowledge writes into the file is a claim about who can
    read it. On Windows the claim is false, so there it says something true
    instead: the file is as private as the folder it sits in."""
    monkeypatch.setattr(env.places, "WINDOWS", True)
    env.create("GROQ_API_KEY", config)
    windows = env.path(config).read_text(encoding="utf-8")

    assert "Nobody but you" not in windows
    assert "folder" in windows

    other = config.parent / "other" / "config.toml"
    monkeypatch.setattr(env.places, "WINDOWS", False)
    env.create("GROQ_API_KEY", other)

    assert "Nobody but you" in env.path(other).read_text(encoding="utf-8")
