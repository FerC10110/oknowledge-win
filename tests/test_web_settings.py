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

from marks import posix_only
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


def rows(body):
    """The provider list, cut into one chunk a row and keyed by provider.

    The list is the picker now: one radio a row, and the row you tick opens.
    Every claim about a provider is a claim about its own row, which is what
    makes "the page says NVIDIA_API_KEY somewhere" not good enough.
    """
    start = body.index('<ul class="providers">')
    whole = body[start:body.index("</ul>", start)]
    return {chunk.split('id="provider-', 1)[1].split('"', 1)[0]: chunk
            for chunk in whole.split("<li>")[1:]}


def test_every_provider_is_a_row_you_can_tick(tmp_path):
    drawn = rows(with_api(tmp_path, provider="groq").get("/settings").text)
    assert set(drawn) == {p.id for p in PROVIDERS}
    for p in PROVIDERS:
        assert 'name="api_provider"' in drawn[p.id], p.id
        assert f'value="{p.id}"' in drawn[p.id], p.id


def test_the_saved_provider_is_the_one_already_ticked(tmp_path):
    drawn = rows(with_api(tmp_path, provider="groq").get("/settings").text)
    assert [pid for pid, chunk in drawn.items() if "checked" in chunk] == ["groq"]


def test_a_row_is_ticked_by_its_name_and_not_only_by_the_dot(tmp_path):
    """The label carries the name, so the whole row is the target. A radio on
    its own is a 13-pixel circle, which on a phone is a miss."""
    drawn = rows(with_api(tmp_path, provider="groq").get("/settings").text)
    for p in PROVIDERS:
        assert f'id="provider-{p.id}"' in drawn[p.id], p.id
        assert f'for="provider-{p.id}"' in drawn[p.id], p.id


def test_the_page_shows_where_each_provider_lives(tmp_path):
    drawn = rows(with_api(tmp_path, provider="groq").get("/settings").text)
    for p in PROVIDERS:
        assert p.url in drawn[p.id], p.id
        assert p.key_env in drawn[p.id], p.id
        assert p.console in drawn[p.id], p.id


def test_a_provider_you_have_not_saved_still_tells_you_how_to_get_its_key(
        tmp_path, monkeypatch):
    """The whole point. Ticking NVIDIA used to leave the page explaining the
    Anthropic key, because every line of it was drawn from the saved row."""
    for name in ("NVIDIA_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    drawn = rows(with_api(tmp_path, provider="anthropic").get("/settings").text)
    nvidia = drawn["nvidia"]
    assert "NVIDIA_API_KEY" in nvidia
    assert "https://build.nvidia.com/" in nvidia
    assert str(tmp_path / "config" / ".env") in nvidia
    assert "ANTHROPIC_API_KEY" not in nvidia


def test_each_row_answers_for_its_own_key_and_not_for_the_saved_one(
        tmp_path, monkeypatch):
    for name in ("GROQ_API_KEY", "NVIDIA_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    dotenv(tmp_path, "GROQ_API_KEY=sk-x\n")
    drawn = rows(with_api(tmp_path, provider="groq").get("/settings").text)
    assert "in place" in drawn["groq"]
    assert "in place" not in drawn["nvidia"]
    assert "NVIDIA_API_KEY=" in drawn["nvidia"]


def test_the_whole_table_costs_one_read_of_the_env_file(tmp_path, monkeypatch):
    """Thirteen rows, one file. A read a row was the easy way to write this
    and it opens the same small file thirteen times to draw one page."""
    from oknowledge import env as env_module
    reads = []
    real = env_module.read
    monkeypatch.setattr(env_module, "read",
                        lambda where=None: reads.append(where) or real(where))
    with_api(tmp_path, provider="groq").get("/settings")
    assert len(reads) == 1


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
    drawn = rows(with_api(tmp_path, provider="groq",
                          key_env="MY_OWN").get("/settings").text)
    assert "MY_OWN" in drawn["groq"]
    # Everywhere in that row, not only in one of the two lines that name a
    # variable: the one it tells you to paste and the one it says is in place
    # have to be the same variable.
    assert "GROQ_API_KEY" not in drawn["groq"]
    # It belongs to the row the config names, not to every row: picking
    # another provider does not make that provider read somebody else's
    # variable.
    assert "MY_OWN" not in drawn["nvidia"]
    assert "NVIDIA_API_KEY" in drawn["nvidia"]


def test_the_row_with_its_own_variable_says_that_one_is_the_one_in_place(
        tmp_path, monkeypatch):
    """The other half of the line above: a key found in the variable the
    config names is reported as that variable, not as the table's."""
    monkeypatch.setenv("MY_OWN", "sk-x")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    drawn = rows(with_api(tmp_path, provider="groq",
                          key_env="MY_OWN").get("/settings").text)
    assert "in place" in drawn["groq"]
    assert "MY_OWN" in drawn["groq"]
    assert "GROQ_API_KEY" not in drawn["groq"]
    assert "sk-x" not in drawn["groq"]


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
    assert [pid for pid, chunk in rows(body).items() if "checked" in chunk] == []


@posix_only
def test_a_file_the_rest_of_the_machine_can_read_is_called_out(tmp_path):
    dotenv(tmp_path, "GROQ_API_KEY=sk-x\n").chmod(0o644)
    body = with_api(tmp_path, provider="groq").get("/settings").text
    assert "chmod" in body


def test_on_windows_the_page_says_where_the_key_is_instead_of_how_to_chmod_it(
        tmp_path, monkeypatch):
    """The same 0o644 file, on a system where that number means nothing. There
    is nothing to fix with chmod there, so the page says the thing the reader
    can act on: which file holds the key, and that it is as private as the
    folder it is in."""
    monkeypatch.setattr(module.places, "WINDOWS", True)
    path = dotenv(tmp_path, "GROQ_API_KEY=sk-x\n")
    path.chmod(0o644)

    body = with_api(tmp_path, provider="groq").get("/settings").text

    assert "chmod" not in body
    assert str(path) in body
    assert "sk-x" not in body                  # the key itself, never


@posix_only
def test_on_linux_that_line_is_not_said_at_all(tmp_path):
    """On a system where the mode decides who can read the file, "as private as
    the folder" is the wrong sentence: the answer is the mode, and when the
    mode is wrong the warning above says so."""
    dotenv(tmp_path, "GROQ_API_KEY=sk-x\n").chmod(0o600)

    body = with_api(tmp_path, provider="groq").get("/settings").text

    assert "private as the folder" not in body


def test_on_windows_a_file_that_is_not_there_is_not_described(tmp_path, monkeypatch):
    """Nothing to be private: the .env has not been created yet. Saying where
    the key is when there is no key is the kind of sentence that sends somebody
    looking for a file that does not exist."""
    monkeypatch.setattr(module.places, "WINDOWS", True)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    body = with_api(tmp_path, provider="groq").get("/settings").text

    assert "private as the folder" not in body
    assert 'form="make-env-' in body          # the button to make it, instead


def test_the_button_that_makes_the_file_is_only_there_when_there_is_no_file(
        tmp_path, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert 'form="make-env-' in with_api(tmp_path, provider="groq").get("/settings").text
    dotenv(tmp_path, "GROQ_API_KEY=sk-x\n")
    assert 'form="make-env-' not in with_api(tmp_path,
                                             provider="groq").get("/settings").text


def test_every_row_sends_its_own_provider_to_the_button(tmp_path, monkeypatch):
    """A form cannot nest inside the settings form, so the button cannot see
    what is ticked. Each row carries its own one-field form instead."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    body = with_api(tmp_path, provider="groq").get("/settings").text
    drawn = rows(body)
    for p in PROVIDERS:
        assert f'form="make-env-{p.id}"' in drawn[p.id], p.id
        start = body.index(f'<form id="make-env-{p.id}"')
        form = body[start:body.index("</form>", start)]
        assert 'action="/settings/env"' in form, p.id
        assert f'name="provider" value="{p.id}"' in form, p.id


# --- making that file --------------------------------------------------------

def test_the_file_is_made_with_the_variable_the_saved_provider_needs(tmp_path):
    client = with_api(tmp_path, provider="groq")
    answer = client.post("/settings/env", follow_redirects=False)
    assert answer.status_code == 303
    made = tmp_path / "config" / ".env"
    assert "GROQ_API_KEY=" in made.read_text(encoding="utf-8")
    assert "sk" not in made.read_text(encoding="utf-8")   # a place to paste, no key


def test_the_file_is_made_for_the_provider_you_ticked(tmp_path):
    client = with_api(tmp_path, provider="groq")
    answer = client.post("/settings/env", data={"provider": "nvidia"},
                         follow_redirects=False)
    assert answer.status_code == 303
    assert "NVIDIA_API_KEY=" in (tmp_path / "config"
                                 / ".env").read_text(encoding="utf-8")


def test_a_name_that_is_not_in_the_table_cannot_choose_the_variable(tmp_path):
    """The provider arrives from a form, so it is whatever somebody posts. A
    name the table does not have falls back to the saved row rather than
    writing a line named after it."""
    client = with_api(tmp_path, provider="groq")
    client.post("/settings/env", data={"provider": "../../etc/passwd"})
    text = (tmp_path / "config" / ".env").read_text(encoding="utf-8")
    assert "GROQ_API_KEY=" in text
    assert "passwd" not in text


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


@posix_only
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


# --- the row that is open ----------------------------------------------------
#
# No script on this page: a checked radio and the block beside it, which is a
# selector every browser has had for fifteen years.

def block(selector):
    css = stylesheet()
    start = css.index(selector + " {")
    return css[start:css.index("}", start)]


def test_a_row_keeps_its_detail_shut_until_it_is_ticked():
    assert "display: none" in block(".providers .detail")


def test_the_row_you_tick_is_the_one_that_opens():
    shown = block('.providers input[type="radio"]:checked ~ .detail')
    assert "display: block" in shown


def test_saving_settings_keeps_your_own_marks(tmp_path):
    """The page rewrites config.toml from scratch, and has no box for the
    marks: a list somebody typed by hand must not go with the rewrite."""
    from oknowledge.config import load
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault, marks=("🦄", "⭐"))
    rebuild_indexes(cfg, "es")
    client = TestClient(create_app(cfg))
    client.post("/settings", data={"chain": ["opencode"], "language": "es",
                                   "default_content": "full", "mentions": "tools",
                                   "ui_language": "es", "batch": "2"},
                follow_redirects=False)
    assert load(tmp_path / "config" / "config.toml").marks == ("🦄", "⭐")


# --- the api section only shows with the api engine ticked ---------------------

def api_section(html):
    """What sits inside the block the api checkbox shows and hides."""
    start = html.index('<div class="api-only">')
    return html[start:html.index('</ul>', start)]


def test_the_api_section_sits_in_its_own_block(client):
    page = client.get("/settings").text
    section = api_section(page)
    assert "providers" in section
    assert 'name="api_provider"' in section
    assert page.count('name="api_provider"') == section.count('name="api_provider"')


def test_the_api_block_sits_inside_the_form_with_the_checkbox(client):
    """The rule reads the checkbox through the form, so both have to share it."""
    page = client.get("/settings").text
    form = page[page.index('<form action="/settings"'):]
    form = form[:form.index("</form>")]
    assert 'name="chain" value="api"' in form
    assert '<div class="api-only">' in form


def test_unticking_api_hides_its_block_without_a_script():
    css = (Path(module.__file__).parent / "static" / "style.css").read_text()
    assert ('form:has(input[name="chain"][value="api"]:not(:checked)) .api-only'
            in css)
