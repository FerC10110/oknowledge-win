import dataclasses
from pathlib import Path

import pytest

from oknowledge.config import Config, ConfigError, load, save


def write_config(tmp_path, body):
    path = tmp_path / "config.toml"
    path.write_text(body, encoding="utf-8")
    return path


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
    assert cfg.idle_timeout == 900


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
