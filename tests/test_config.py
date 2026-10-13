import dataclasses
from pathlib import Path

import pytest

from oknowledge.config import Config, ConfigError, config_path, load, save


def write_config(tmp_path, body):
    path = tmp_path / "config.toml"
    path.write_text(body, encoding="utf-8")
    return path


def test_the_batch_size_is_read_and_defaults_to_ten(tmp_path):
    """How many links one press of Process takes. Ten rather than fifty: a run
    is minutes per link, and the number people pick first is the one they wait
    through once before deciding."""
    vault = tmp_path / "vault"
    vault.mkdir()

    assert load(write_config(tmp_path, f'vault = "{vault}"\n')).batch == 10
    assert load(write_config(tmp_path, f'vault = "{vault}"\nbatch = 50\n')).batch == 50


@pytest.mark.parametrize("value", ["0", "-5", '"50"', "true", "2.5"])
def test_a_batch_size_that_is_not_one_is_refused_by_name(tmp_path, value):
    """It is the file the user hand-writes, so the answer says what is wrong."""
    vault = tmp_path / "vault"
    vault.mkdir()
    path = write_config(tmp_path, f'vault = "{vault}"\nbatch = {value}\n')

    with pytest.raises(ConfigError, match="batch"):
        load(path)


def test_saving_keeps_the_batch_size(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    out = tmp_path / "out.toml"

    save(Config(vault=vault, batch=25), out)

    assert load(out).batch == 25


def test_load_reads_the_values(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    path = write_config(tmp_path, f"""
vault = "{vault}"
default_content = "summary"

[ai]
chain = ["ollama", "opencode"]
language = "en"

[ai.ollama]
model = "qwen2.5:7b"

[web]
port = 9000
""")
    cfg = load(path)
    assert cfg.vault == vault
    assert cfg.default_content == "summary"
    assert cfg.chain == ("ollama", "opencode")
    assert cfg.language == "en"
    assert cfg.engines["ollama"]["model"] == "qwen2.5:7b"
    assert cfg.port == 9000


def test_what_the_file_omits_takes_the_default(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    cfg = load(write_config(tmp_path, f'vault = "{vault}"\n'))
    assert cfg.folder == "oknowledge"
    assert cfg.default_content == "full"
    assert cfg.chain == ("opencode",)
    assert cfg.language == "es"
    assert cfg.port == 8787
    # Never: the server is started by hand and left open in a browser tab,
    # and nothing starts it again once it has gone.
    assert cfg.idle_timeout == 0


def test_the_paths_hang_off_the_vault(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    cfg = load(write_config(tmp_path, f'vault = "{vault}"\n'))
    assert cfg.root == vault / "oknowledge"
    assert cfg.links_dir == vault / "oknowledge" / "links"
    assert cfg.attachments_dir == vault / "oknowledge" / "attachments"


def test_a_missing_file_says_so(tmp_path):
    with pytest.raises(ConfigError, match="no config file"):
        load(tmp_path / "nope.toml")


def test_a_vault_that_does_not_exist_is_an_error(tmp_path):
    path = write_config(tmp_path, 'vault = "/no/such/vault"\n')
    with pytest.raises(ConfigError, match="vault"):
        load(path)


def test_an_unknown_engine_in_the_chain_is_an_error(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    path = write_config(tmp_path, f'vault = "{vault}"\n\n[ai]\nchain = ["gpt5"]\n')
    with pytest.raises(ConfigError, match="gpt5"):
        load(path)


def test_an_empty_chain_is_an_error(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    path = write_config(tmp_path, f'vault = "{vault}"\n\n[ai]\nchain = []\n')
    with pytest.raises(ConfigError, match="chain"):
        load(path)


def test_an_unknown_content_mode_is_an_error(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    path = write_config(tmp_path, f'vault = "{vault}"\ndefault_content = "half"\n')
    with pytest.raises(ConfigError, match="half"):
        load(path)


# --- saving the config back -------------------------------------------------

def test_save_round_trips_through_load(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    path = write_config(tmp_path, f'''
vault = "{vault}"
folder = "notes"
default_content = "summary"

[ai]
chain = ["ollama", "opencode"]
language = "en"

[ai.ollama]
model = "qwen2.5:7b"
url = "http://localhost:11434"

[web]
port = 9000
idle_timeout = 60
''')
    cfg = load(path)
    save(cfg, path)
    assert load(path) == cfg


def test_save_keeps_the_previous_file_as_a_backup(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    path = write_config(tmp_path, f'# my comments\nvault = "{vault}"\n')
    cfg = load(path)

    save(dataclasses.replace(cfg, language="en"), path)

    backup = tmp_path / "config.toml.bak"
    assert backup.read_text(encoding="utf-8") == f'# my comments\nvault = "{vault}"\n'
    assert "# my comments" not in path.read_text(encoding="utf-8")
    assert load(path).language == "en"


def test_saving_over_nothing_needs_no_backup(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    path = tmp_path / "deep" / "config.toml"
    save(Config(vault=vault), path)
    assert not (tmp_path / "deep" / "config.toml.bak").exists()
    assert load(path).vault == vault


def test_a_saved_config_is_only_readable_by_you(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    path = write_config(tmp_path, f'vault = "{vault}"\n')
    save(load(path), path)
    assert path.stat().st_mode & 0o777 == 0o600
    assert (tmp_path / "config.toml.bak").stat().st_mode & 0o777 == 0o600


def test_a_loaded_config_remembers_which_file_it_came_from(tmp_path):
    """So that whoever saves it can write the file this process reads."""
    vault = tmp_path / "vault"
    vault.mkdir()
    path = write_config(tmp_path, f'vault = "{vault}"\n')

    assert load(path).source == path


def test_a_config_nobody_loaded_remembers_no_file(tmp_path):
    assert Config(vault=tmp_path).source is None


def test_save_without_a_path_writes_the_file_it_was_loaded_from(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    path = write_config(tmp_path, f'vault = "{vault}"\n')

    assert save(dataclasses.replace(load(path), language="en")) == path
    assert load(path).language == "en"


# --- the real config file is not reachable from here (item 0) ---------------
# A test wrote the user's own ~/.config/oknowledge/config.toml during a
# mutation run: save() defaults to `cfg.source or CONFIG_PATH`, this file does
# not build its Configs through load() in every test, and nothing pinned
# CONFIG_PATH. The pin now lives in conftest.py for the whole suite; these
# assert it, because a pin nobody asserts comes loose.

def test_no_test_can_reach_the_real_config_file(tmp_path):
    from oknowledge import cli, config
    from oknowledge.web import app

    real = Path.home() / ".config" / "oknowledge" / "config.toml"
    for module in (config, cli, app):
        assert module.CONFIG_PATH != real, f"{module.__name__} can write the real config"
        assert module.CONFIG_PATH.is_relative_to(tmp_path), module.__name__


def test_saving_a_config_nobody_loaded_cannot_reach_the_real_file(tmp_path):
    """The exact shape that leaked: no source, no path, so the default decides.

    The destination is asserted BEFORE the write. A guard that writes first
    and checks afterwards has already done the damage by the time it fails --
    which is literally what happened to this test the first time it was
    mutation-checked: with the pin mutated away it wrote the user's own
    config, and then reported the failure.
    """
    from oknowledge import config

    vault = tmp_path / "vault"
    vault.mkdir()
    assert config.CONFIG_PATH.is_relative_to(tmp_path)     # before anything is written

    written = save(Config(vault=vault))

    assert written == config.CONFIG_PATH
    assert load(written).vault == vault


def test_the_isolated_config_path_does_not_exist_until_something_writes_it():
    """So a load() that falls through to the default fails the ordinary way
    instead of quietly reading somebody else's config."""
    from oknowledge import config

    assert not config.CONFIG_PATH.exists()


# --- mention modes ---------------------------------------------------------

def vault_at(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    return vault


def test_the_default_mention_mode_is_tools(tmp_path):
    path = write_config(tmp_path, f'vault = "{vault_at(tmp_path)}"\n')

    assert load(path).mentions == "tools"


@pytest.mark.parametrize("mode", ["tools", "all", "discussed"])
def test_every_mention_mode_loads(tmp_path, mode):
    path = write_config(
        tmp_path, f'vault = "{vault_at(tmp_path)}"\n[ai]\nmentions = "{mode}"\n')

    assert load(path).mentions == mode


@pytest.mark.parametrize("value", ['"nope"', "3", "true", "[]"])
def test_a_mention_mode_we_do_not_know_names_the_ones_we_do(tmp_path, value):
    """This is the file the user hand-writes, so the answer says what is valid.
    A value that is not even a string lands in the same message, not a
    TypeError, because the check is membership in the tuple."""
    path = write_config(
        tmp_path, f'vault = "{vault_at(tmp_path)}"\n[ai]\nmentions = {value}\n')

    with pytest.raises(ConfigError, match="discussed"):
        load(path)


def test_a_saved_config_loads_again_with_its_mode(tmp_path):
    """save() only writes what load() accepts, and that has to include this."""
    path = write_config(
        tmp_path, f'vault = "{vault_at(tmp_path)}"\n[ai]\nmentions = "all"\n')
    again = save(load(path), tmp_path / "again.toml")

    assert load(again).mentions == "all"


# --- which interface the server listens on -----------------------------------
#
# The default is this machine and nothing else, because that is the only
# default that cannot expose somebody's notes by accident. Anything else is a
# line the user wrote on purpose.

def test_the_host_defaults_to_this_machine_alone(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    assert load(write_config(tmp_path, f'vault = "{vault}"\n')).host == "127.0.0.1"


def test_a_host_in_the_file_is_what_it_listens_on(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    cfg = load(write_config(tmp_path, f'''vault = "{vault}"

[web]
host = "0.0.0.0"
'''))
    assert cfg.host == "0.0.0.0"


def test_a_host_with_room_around_it_is_still_a_host(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    cfg = load(write_config(tmp_path, f'vault = "{vault}"\n\n[web]\nhost = "  0.0.0.0  "\n'))
    assert cfg.host == "0.0.0.0"


@pytest.mark.parametrize("value", ['""', '"   "', "8787", "true", '"two words"'])
def test_a_host_that_is_not_an_address_is_refused_by_name(tmp_path, value):
    vault = tmp_path / "vault"
    vault.mkdir()
    path = write_config(tmp_path, f'vault = "{vault}"\n\n[web]\nhost = {value}\n')
    with pytest.raises(ConfigError, match="web.host"):
        load(path)


def test_saving_keeps_the_host(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    out = tmp_path / "out.toml"
    save(Config(vault=vault, host="0.0.0.0"), out)
    assert load(out).host == "0.0.0.0"


# --- the first mistake a Windows user makes -----------------------------------

def test_a_windows_path_in_double_quotes_says_how_to_write_it(tmp_path):
    r"""`vault = "C:\Users\fer\vault"` is not valid TOML: \U starts a unicode
    escape. The message has to say what to write instead, because the file is
    hand-written and this is the first line of it.
    """
    path = write_config(tmp_path, 'vault = "C:\\Users\\fer\\vault"\n')

    with pytest.raises(ConfigError) as caught:
        load(path)

    said = str(caught.value)
    assert "C:/Users" in said and "'" in said


def test_a_windows_path_whose_escapes_happen_to_parse_is_caught_too(tmp_path):
    r"""The nastier half: `"C:\temp\new"` is *valid* TOML and means C:<tab>emp<lf>ew.
    Without this check the answer is "vault is not a directory" followed by a
    path with a newline in the middle of it, which explains nothing.
    """
    path = write_config(tmp_path, 'vault = "C:\\temp\\new"\n')

    with pytest.raises(ConfigError) as caught:
        load(path)

    said = str(caught.value)
    assert "C:/Users" in said and "not a directory" not in said


def test_a_vault_with_no_backslashes_gets_the_ordinary_message(tmp_path):
    """So the hint stays attached to the mistake it explains."""
    path = write_config(tmp_path, 'vault = "\n')

    with pytest.raises(ConfigError) as caught:
        load(path)

    assert "C:/Users" not in str(caught.value)


def test_the_config_file_sits_in_the_config_directory(monkeypatch, tmp_path):
    """conftest redirects CONFIG_PATH for every test in the suite -- it has to,
    or a test could overwrite the real one -- so this asks the question the
    constant was built from instead of asking the constant."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg-state"))

    assert config_path() == tmp_path / "xdg-config" / "oknowledge" / "config.toml"


# --- the interface language, which used to live in a file of Omarchy's --------

def test_the_interface_language_comes_from_the_web_table(tmp_path):
    """Two languages, two axes, and they were always separate: [ai] language is
    what the summaries are written in, [web] language is what the buttons say.
    On a machine with no Omarchy there is no shared file to keep it in, so it
    lives here, where the Settings page can write it."""
    vault = tmp_path / "vault"
    vault.mkdir()

    body = f'vault = "{vault}"\n[web]\nlanguage = "es"\n'
    assert load(write_config(tmp_path, body)).ui_language == "es"


def test_the_interface_language_defaults_to_english(tmp_path):
    """English and not Spanish, like the translator it feeds: the keys in the
    code are the English text, so English is the one language that cannot be
    half-translated."""
    vault = tmp_path / "vault"
    vault.mkdir()

    cfg = load(write_config(tmp_path, f'vault = "{vault}"\n'))

    assert cfg.ui_language == "en"
    assert cfg.language == "es"             # the summaries, untouched


@pytest.mark.parametrize("value", ['"fr"', '"es-AR"', "true", '""'])
def test_an_interface_language_nobody_translated_is_refused_by_name(tmp_path, value):
    vault = tmp_path / "vault"
    vault.mkdir()
    path = write_config(tmp_path, f'vault = "{vault}"\n[web]\nlanguage = {value}\n')

    with pytest.raises(ConfigError, match="web.language"):
        load(path)


def test_saving_keeps_the_interface_language(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    out = tmp_path / "out.toml"

    save(Config(vault=vault, ui_language="es"), out)

    assert load(out).ui_language == "es"


def test_the_marks_default_to_the_short_list(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    from oknowledge.marks import DEFAULT_MARKS
    assert load(write_config(tmp_path, f'vault = "{vault}"\n')).marks == DEFAULT_MARKS


def test_your_own_marks_are_read_and_the_bad_ones_dropped(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    path = write_config(tmp_path, f'vault = "{vault}"\n[web]\n'
                                  'marks = ["🦄", "hola", "⭐", "🦄", ""]\n')
    assert load(path).marks == ("🦄", "⭐")


@pytest.mark.parametrize("value", ['"⭐"', "3", "[1, 2]"])
def test_marks_that_are_not_a_list_of_text_are_refused_by_name(tmp_path, value):
    vault = tmp_path / "vault"
    vault.mkdir()
    path = write_config(tmp_path, f'vault = "{vault}"\n[web]\nmarks = {value}\n')
    with pytest.raises(ConfigError, match="web.marks"):
        load(path)


def test_saving_keeps_your_marks(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    out = tmp_path / "out.toml"
    save(Config(vault=vault, marks=("🦄", "⭐")), out)
    assert load(out).marks == ("🦄", "⭐")


def test_the_default_marks_are_not_written(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    out = tmp_path / "out.toml"
    save(Config(vault=vault), out)
    import tomllib
    assert "marks" not in tomllib.loads(out.read_text(encoding="utf-8"))["web"]
