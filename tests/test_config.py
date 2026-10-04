import dataclasses

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
