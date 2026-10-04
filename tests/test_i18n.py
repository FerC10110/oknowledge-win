import json

import pytest

from oknowledge import i18n


def write_pref(tmp_path, content):
    path = tmp_path / "plugin-language.json"
    path.write_text(content, encoding="utf-8")
    return path


def test_without_the_file_everything_is_english(tmp_path):
    assert i18n.ui_language(tmp_path / "nope.json") == "en"


def test_the_shared_file_switches_the_interface(tmp_path):
    path = write_pref(tmp_path, json.dumps({"language": "es"}))
    assert i18n.ui_language(path) == "es"


def test_a_broken_file_falls_back_quietly(tmp_path):
    assert i18n.ui_language(write_pref(tmp_path, "{no json")) == "en"


def test_a_language_we_do_not_have_falls_back(tmp_path):
    assert i18n.ui_language(write_pref(tmp_path, json.dumps({"language": "fr"}))) == "en"


def test_english_is_the_identity():
    t = i18n.translator("en")
    assert t("Search") == "Search"
    assert t("No results") == "No results"


def test_spanish_translates_what_it_knows_and_passes_through_the_rest():
    t = i18n.translator("es")
    assert t("Search") == "Buscar"
    assert t("Categories") == "Categorías"
    assert t("a string nobody translated") == "a string nobody translated"


def test_a_file_that_is_not_an_object_falls_back(tmp_path):
    assert i18n.ui_language(write_pref(tmp_path, "[1, 2]")) == "en"
    assert i18n.ui_language(write_pref(tmp_path, json.dumps({"language": ["es"]}))) == "en"


def test_an_unreadable_path_falls_back(tmp_path):
    assert i18n.ui_language(tmp_path) == "en"  # a directory
    bad = tmp_path / "bin.json"
    bad.write_bytes(b"\xff\xfe\x00")
    assert i18n.ui_language(bad) == "en"


def test_the_default_path_is_the_shared_omarchy_file(tmp_path, monkeypatch):
    import importlib

    monkeypatch.setenv("HOME", str(tmp_path))
    try:
        reloaded = importlib.reload(i18n)
        assert reloaded.SHARED_FILE == tmp_path / ".config" / "omarchy" / "plugin-language.json"
    finally:
        monkeypatch.undo()
        importlib.reload(i18n)


def test_the_default_lookup_uses_the_shared_file(isolated_ui_language):
    assert i18n.ui_language() == "en"
    isolated_ui_language.write_text(json.dumps({"language": "es"}), encoding="utf-8")
    assert i18n.ui_language() == "es"


# --- writing the shared preference ------------------------------------------

def test_setting_the_language_writes_it_where_ui_language_reads_it(tmp_path):
    path = tmp_path / "plugin-language.json"
    assert i18n.set_ui_language("es", path) == path
    assert i18n.ui_language(path) == "es"


def test_setting_the_language_keeps_what_other_plugins_put_there(tmp_path):
    """The file is shared by every Omarchy plugin: only `language` is ours."""
    path = write_pref(tmp_path, json.dumps(
        {"language": "en", "theme": "tokyo-night", "widgets": {"clock": True}}))

    i18n.set_ui_language("es", path)

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved == {"language": "es", "theme": "tokyo-night",
                     "widgets": {"clock": True}}


@pytest.mark.parametrize("content", ["{not json", "", "[1, 2]", '"text"', "null"])
def test_a_file_we_cannot_merge_with_starts_from_empty(tmp_path, content):
    path = write_pref(tmp_path, content)
    i18n.set_ui_language("es", path)
    assert json.loads(path.read_text(encoding="utf-8")) == {"language": "es"}


def test_a_missing_file_and_its_folder_are_created(tmp_path):
    path = tmp_path / "config" / "omarchy" / "plugin-language.json"
    i18n.set_ui_language("en", path)
    assert json.loads(path.read_text(encoding="utf-8")) == {"language": "en"}


def test_a_language_we_do_not_have_is_refused(tmp_path):
    path = tmp_path / "plugin-language.json"
    with pytest.raises(ValueError, match="fr"):
        i18n.set_ui_language("fr", path)
    assert not path.exists()


def test_without_a_path_it_writes_the_shared_file(tmp_path, monkeypatch):
    path = tmp_path / "shared.json"
    monkeypatch.setattr(i18n, "SHARED_FILE", path)
    i18n.set_ui_language("es")
    assert json.loads(path.read_text(encoding="utf-8"))["language"] == "es"
