"""Choosing a model from a list instead of typing it from memory.

The trap this design has to avoid is the page itself: three engines with
their timeouts is up to twelve seconds to open Settings, and the slow case --
a server that is not running -- is the common one. So nothing is asked until
a button is pressed, and what it finds is kept.
"""

import json
import stat
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from oknowledge import models_cache
from oknowledge.ai.base import EngineError
from oknowledge.ai.providers import PROVIDERS
from oknowledge.ai.fake import FakeEngine
from oknowledge.config import Config
from oknowledge.vault import rebuild_indexes
from oknowledge.web import app as module
from oknowledge.web.app import create_app


@pytest.fixture(autouse=True)
def state_tree(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr("oknowledge.web.app.CONFIG_PATH",
                        tmp_path / "config" / "config.toml")


@pytest.fixture
def client(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    rebuild_indexes(cfg, "es")
    return TestClient(create_app(cfg))


def listed(names, engine="opencode"):
    """An engine that answers `names` when asked what it has."""
    def build(name, cfg):
        assert name == engine, f"asked {name}, not {engine}"
        found = FakeEngine([])
        found.models = lambda: list(names)
        return found
    return build


# --- the page ----------------------------------------------------------------

def test_opening_settings_asks_no_engine_anything(client, monkeypatch):
    """Twelve seconds of waiting to open a page is this design's one trap.

    conftest already fails any test that runs a program or reaches the
    network. This says so on purpose: the point is the page, not the plumbing.
    """
    monkeypatch.setattr(module, "build_engine",
                        lambda *a, **k: pytest.fail("Settings asked an engine"))
    assert client.get("/settings").status_code == 200


def test_the_box_offers_a_list_and_stays_typable(client):
    body = client.get("/settings").text
    assert 'list="models-opencode"' in body
    assert '<datalist id="models-opencode">' in body
    # A <select> would be the obvious control and the wrong one: an engine
    # that cannot be asked has to leave you able to type the name yourself.
    assert '<select name="opencode_model"' not in body


def test_what_was_found_is_offered(client):
    models_cache.remember("opencode", ["a/one", "b/two"])
    body = client.get("/settings").text
    assert '<option value="a/one">' in body
    assert '<option value="b/two">' in body


def test_the_page_says_how_old_the_list_is(client):
    models_cache.remember("opencode", ["a/one"])
    today = models_cache.read()["opencode"]["at"]
    assert today in client.get("/settings").text


def test_a_list_nobody_has_looked_for_says_nothing_about_dates(client):
    assert "models-opencode" in client.get("/settings").text   # the datalist is there
    assert client.get("/settings").text.count("Looked up") == 0


# --- the button ---------------------------------------------------------------

def test_the_button_asks_the_engine_and_remembers_what_it_said(client, monkeypatch):
    monkeypatch.setattr(module, "build_engine", listed(["a/one", "b/two"]))

    answer = client.post("/settings/models/opencode", follow_redirects=False)

    assert answer.status_code == 303
    assert "notice=models-found" in answer.headers["location"]
    assert "n=2" in answer.headers["location"]
    assert models_cache.read()["opencode"]["found"] == ["a/one", "b/two"]


def test_a_search_that_finds_nothing_says_so_and_keeps_the_box_typable(client,
                                                                       monkeypatch):
    monkeypatch.setattr(module, "build_engine", listed([], engine="ollama"))

    answer = client.post("/settings/models/ollama", follow_redirects=False)

    assert "notice=models-none" in answer.headers["location"]
    body = client.get("/settings").text
    assert 'list="models-ollama"' in body          # the datalist is still there, empty


def test_an_engine_that_cannot_even_be_built_is_an_answer_not_a_crash(client,
                                                                      monkeypatch):
    def refuse(name, cfg):
        raise EngineError("unknown provider: 'nope'")

    monkeypatch.setattr(module, "build_engine", refuse)
    answer = client.post("/settings/models/api", follow_redirects=False)
    assert "notice=models-none" in answer.headers["location"]


def test_an_engine_that_explodes_is_an_answer_not_a_crash(client, monkeypatch):
    def angry(name, cfg):
        raise RuntimeError("?!")

    monkeypatch.setattr(module, "build_engine", angry)
    answer = client.post("/settings/models/api", follow_redirects=False)
    assert "notice=models-none" in answer.headers["location"]


def test_there_is_no_such_engine(client):
    assert client.post("/settings/models/../../etc", follow_redirects=False
                       ).status_code in (404, 307)
    assert client.post("/settings/models/nope").status_code == 404


def test_the_button_does_not_save_the_rest_of_the_form(client, monkeypatch):
    """It submits a form of its own, so whatever is typed in the big one is
    not written. The page says as much."""
    monkeypatch.setattr(module, "build_engine", listed(["a/one"]))
    client.post("/settings/models/opencode")
    body = client.get("/settings").text
    assert 'form="find-opencode"' in body
    assert 'id="find-opencode"' in body


# --- the cache itself ---------------------------------------------------------

def test_the_cache_keeps_the_other_engines(client):
    models_cache.remember("opencode", ["a/one"])
    models_cache.remember("ollama", ["q:7b"])
    assert set(models_cache.read()) == {"opencode", "ollama"}


def test_a_second_look_replaces_the_first(client):
    models_cache.remember("opencode", ["a/one"])
    models_cache.remember("opencode", ["b/two"])
    assert models_cache.read()["opencode"]["found"] == ["b/two"]


def test_a_cache_file_of_nonsense_is_an_empty_cache(client):
    models_cache.path().parent.mkdir(parents=True, exist_ok=True)
    models_cache.path().write_text("}{ not json", encoding="utf-8")
    assert models_cache.read() == {}
    assert client.get("/settings").status_code == 200


@pytest.mark.parametrize("content", [
    '["a list, not an object"]',
    '{"opencode": "a string, not an entry"}',
    '{"opencode": {"found": "a string, not a list"}}',
    '{"opencode": {"found": ["ok", 7, null], "at": 2026}}',
])
def test_a_cache_file_of_the_wrong_shape_is_read_for_what_it_has(client, content):
    """It lives in the state dir, where a user can edit it and another tool
    can write over it."""
    models_cache.path().parent.mkdir(parents=True, exist_ok=True)
    models_cache.path().write_text(content, encoding="utf-8")
    table = models_cache.read()
    assert isinstance(table, dict)
    for entry in table.values():
        assert isinstance(entry.get("found"), list)
        assert all(isinstance(name, str) for name in entry["found"])
        assert isinstance(entry.get("at"), str)
    assert client.get("/settings").status_code == 200


def test_a_state_dir_that_cannot_be_written_is_not_an_error(client, tmp_path):
    models_cache.path().parent.mkdir(parents=True, exist_ok=True)
    models_cache.path().mkdir()        # a folder where the file goes
    assert models_cache.remember("opencode", ["a/one"]) == {}


def test_what_is_remembered_is_json_a_person_can_read(client):
    models_cache.remember("opencode", ["a/one"])
    data = json.loads(models_cache.path().read_text(encoding="utf-8"))
    assert data["opencode"]["found"] == ["a/one"]
    assert data["opencode"]["at"].startswith("20")


# --- which provider the api engine talks to ----------------------------------
#
# The addresses are on the page on purpose: picking a provider should teach you
# what you are pointing at. The key never is -- the page asks whether one can
# be found, and that is all it is allowed to know.

def with_api(tmp_path, **options):
    """A client whose config has [ai.api] filled in the given way."""
    vault = tmp_path / "api-vault"
    (vault / "oknowledge" / "links").mkdir(parents=True, exist_ok=True)
    cfg = Config(vault=vault, engines={"api": dict(options)})
    rebuild_indexes(cfg, "es")
    return TestClient(create_app(cfg))


def dotenv(tmp_path, text):
    """The .env the page reads: beside the config, which state_tree pinned."""
    folder = tmp_path / "config"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / ".env"
    target.write_text(text, encoding="utf-8")
    target.chmod(0o600)
    return target


def chosen(body):
    """The select, on its own: the rest of the page names providers too."""
    start = body.index('name="api_provider"')
    return body[start:body.index("</select>", start)]


def test_the_page_offers_every_provider_and_marks_the_one_in_use(tmp_path):
    body = with_api(tmp_path, provider="groq").get("/settings").text
    offered = chosen(body)
    for p in PROVIDERS:
        assert f'value="{p.id}"' in offered, p.id
    assert 'value="groq" selected' in offered


def test_the_page_shows_where_each_provider_lives(tmp_path):
    body = with_api(tmp_path, provider="groq").get("/settings").text
    for p in PROVIDERS:
        assert p.url in body, p.id
        assert p.key_env in body, p.id
        assert p.console in body, p.id


def test_a_provider_that_gives_a_key_away_says_so_and_says_what_it_gives(tmp_path):
    body = with_api(tmp_path, provider="groq").get("/settings").text
    assert "14,400" in body                      # groq's free tier, on the page
    assert "free" in body.lower()


def test_with_no_key_the_page_says_which_variable_and_which_file(tmp_path,
                                                                 monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    body = with_api(tmp_path, provider="groq").get("/settings").text
    assert "GROQ_API_KEY" in body
    assert str(tmp_path / "config" / ".env") in body


def test_with_the_key_in_the_file_the_page_says_so_and_never_prints_it(
        tmp_path, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    dotenv(tmp_path, "GROQ_API_KEY=sk-very-secret\n")
    body = with_api(tmp_path, provider="groq").get("/settings").text
    assert "sk-very-secret" not in body
    assert "in place" in body


def test_a_key_in_the_environment_counts_as_a_key(tmp_path, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "sk-from-the-shell")
    body = with_api(tmp_path, provider="groq").get("/settings").text
    assert "sk-from-the-shell" not in body
    assert "in place" in body


def test_a_variable_named_in_the_config_is_the_one_the_page_asks_about(tmp_path,
                                                                      monkeypatch):
    monkeypatch.delenv("MY_OWN", raising=False)
    body = with_api(tmp_path, provider="groq", key_env="MY_OWN").get("/settings").text
    assert "MY_OWN" in body


def test_an_address_set_by_hand_is_said_to_win(tmp_path):
    body = with_api(tmp_path, provider="groq",
                    base_url="https://gw.example.com/v1/chat/completions"
                    ).get("/settings").text
    assert "https://gw.example.com/v1/chat/completions" in body
    assert "wins" in body


def test_a_provider_the_table_does_not_know_is_said_and_not_swallowed(tmp_path):
    # Hand-written in config.toml. The page must not look like it agrees.
    body = with_api(tmp_path, provider="my-own-thing").get("/settings").text
    assert "my-own-thing" in body
    assert "selected" not in chosen(body)


def test_a_file_the_rest_of_the_machine_can_read_is_called_out(tmp_path):
    dotenv(tmp_path, "GROQ_API_KEY=sk-x\n").chmod(0o644)
    body = with_api(tmp_path, provider="groq").get("/settings").text
    assert "chmod" in body


def test_the_button_that_makes_the_file_is_only_there_when_there_is_no_file(
        tmp_path, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    # The button, not the form it submits: the form is always on the page, and
    # the route it posts to is safe on its own.
    assert 'form="make-env"' in with_api(tmp_path, provider="groq").get("/settings").text
    dotenv(tmp_path, "GROQ_API_KEY=sk-x\n")
    assert 'form="make-env"' not in with_api(tmp_path,
                                             provider="groq").get("/settings").text


# --- making that file --------------------------------------------------------

def test_the_file_is_made_with_the_variable_the_saved_provider_needs(tmp_path):
    client = with_api(tmp_path, provider="groq")
    answer = client.post("/settings/env", follow_redirects=False)
    assert answer.status_code == 303
    made = tmp_path / "config" / ".env"
    assert "GROQ_API_KEY=" in made.read_text(encoding="utf-8")
    assert "sk" not in made.read_text(encoding="utf-8")   # a place to paste, no key


def test_the_file_it_makes_is_yours_alone(tmp_path):
    with_api(tmp_path, provider="groq").post("/settings/env")
    assert stat.S_IMODE((tmp_path / "config" / ".env").stat().st_mode) == 0o600


def test_a_file_that_is_already_there_is_never_overwritten(tmp_path):
    dotenv(tmp_path, "GROQ_API_KEY=sk-mine\n")
    answer = with_api(tmp_path, provider="groq").post("/settings/env",
                                                      follow_redirects=False)
    assert "env-there" in answer.headers["location"]
    assert (tmp_path / "config" / ".env").read_text(encoding="utf-8") == (
        "GROQ_API_KEY=sk-mine\n")


def test_a_folder_that_cannot_be_written_is_an_answer_not_a_crash(tmp_path):
    folder = tmp_path / "config"
    folder.mkdir(parents=True, exist_ok=True)
    folder.chmod(0o500)
    try:
        answer = with_api(tmp_path, provider="groq").post("/settings/env",
                                                          follow_redirects=False)
        assert "env-failed" in answer.headers["location"]
    finally:
        folder.chmod(0o700)


# --- on a phone --------------------------------------------------------------

def stylesheet():
    import oknowledge.web
    return (Path(oknowledge.web.__file__).parent / "static" / "style.css").read_text(
        encoding="utf-8")


def phone_rules():
    """The block that only applies to a narrow screen."""
    css = stylesheet()
    start = css.index("@media (max-width: 40rem) {\n  header")
    return css[start:css.index("\n}", start)]


def test_the_nine_addresses_wrap_instead_of_widening_the_page():
    css = stylesheet()
    block = css[css.index(".providers code"):]
    assert "overflow-wrap: anywhere" in block[:block.index("}")]


def test_the_header_stops_being_one_row_on_a_narrow_screen():
    """Three things in one flex row, and in Spanish the three links alone are
    wider than a phone: the search box was squeezed to nothing and the page
    scrolled sideways."""
    rules = phone_rules()
    assert "flex-wrap: wrap" in rules
    assert "header nav" in rules


def test_the_links_in_the_header_wrap_among_themselves():
    # Otherwise the nav is one unbreakable row and it is the thing that
    # overflows, whatever the header does.
    rules = phone_rules()
    nav = rules[rules.index("header nav {"):]
    assert "flex-wrap: wrap" in nav[:nav.index("}")]


def test_a_key_written_into_the_config_counts_and_is_still_not_printed(tmp_path,
                                                                       monkeypatch):
    """config.toml is a bad place for it, but saying "no key" over a key that
    works would be worse -- and the page must not print it either way."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    body = with_api(tmp_path, provider="groq",
                    key="sk-in-the-config").get("/settings").text
    assert "sk-in-the-config" not in body
    assert "in place" in body


def test_the_page_says_when_the_api_engine_is_not_even_switched_on(tmp_path):
    """Somebody who pastes a key and sees nothing happen should find out why
    on the page that sent them for the key."""
    body = with_api(tmp_path, provider="groq").get("/settings").text
    assert "not ticked" in body


def test_with_the_api_engine_in_the_chain_it_says_nothing_of_the_sort(tmp_path):
    vault = tmp_path / "on-vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault, chain=("api",), engines={"api": {"provider": "groq"}})
    rebuild_indexes(cfg, "es")
    assert "not ticked" not in TestClient(create_app(cfg)).get("/settings").text


# --- thirteen addresses, folded ----------------------------------------------

def folded(body):
    """What the page shows, and what it keeps behind the disclosure."""
    start = body.index('<details class="providers-all">')
    return body[:start], body[start:body.index("</details>", start)]


def test_the_provider_in_use_is_visible_without_opening_anything(tmp_path):
    visible, hidden = folded(with_api(tmp_path, provider="groq").get("/settings").text)
    assert "https://api.groq.com/openai/v1/chat/completions" in visible
    assert "api.groq.com" not in hidden


def test_every_other_address_is_behind_the_disclosure(tmp_path):
    """Thirteen addresses one under the other is a wall on a phone."""
    visible, hidden = folded(with_api(tmp_path, provider="groq").get("/settings").text)
    for p in PROVIDERS:
        if p.id != "groq":
            assert p.url in hidden, p.id
            assert p.url not in visible, p.id


def test_the_fold_says_how_many_it_is_hiding(tmp_path):
    body = with_api(tmp_path, provider="groq").get("/settings").text
    summary = body[body.index("<summary>"):body.index("</summary>")]
    assert str(len(PROVIDERS) - 1) in summary


def test_a_provider_the_table_does_not_know_leaves_the_whole_list_folded(tmp_path):
    visible, hidden = folded(
        with_api(tmp_path, provider="my-own-thing").get("/settings").text)
    for p in PROVIDERS:
        assert p.url in hidden, p.id
        assert p.url not in visible, p.id
