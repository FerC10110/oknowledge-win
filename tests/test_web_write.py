"""The web routes that change the vault.

These are the only requests in the project that can destroy a user's work, so
most of this file is about what must NOT happen: a cross-site POST that
deletes a note, a category name that walks out of the vault, a browser left
hanging while an engine thinks, a settings save that wipes the shared
preference file other plugins write to.
"""

import dataclasses
import json
import os
import re
import tomllib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from marks import posix_only
from oknowledge.config import Config, load
from oknowledge.model import Mention, Note
from oknowledge.urls import search_url
from oknowledge.vault import (
    find_note, index_path, rebuild_indexes, trash_dir, write_note,
)
from oknowledge.web.app import create_app

WRITE_ROUTES = [
    ("/item/a1/category", {"category": "Redes"}),
    ("/item/a1/tags", {"tags": "vpn"}),
    ("/item/a1/delete", {}),
    ("/item/a1/mentions/delete", {"name": "x"}),
    ("/item/a1/reprocess", {"engine": "ollama"}),
    ("/categories/rename", {"old": "Networking", "new": "Redes"}),
    ("/settings", {"chain": ["ollama"], "language": "en",
                   "default_content": "summary", "ui_language": "es"}),
    # The two import routes. The origin check runs before routing, so a
    # cross-site POST here is refused without the file these would need.
    ("/import", {}),
    ("/import/confirm", {"token": "0" * 32}),
    # Starting a batch of re-analysis. A cross-site POST here would spend the
    # user's model quota, which is the kind of thing an origin check is for.
    ("/retry", {}),
    # Pasting a link. A cross-site POST here would have somebody else's page
    # read, summarised and written into this vault.
    ("/add", {"url": "https://e.com/zz", "content": "full"}),
    # Saving a card. A cross-site POST here would reach a catalog and write
    # a note into this vault, with a picture downloaded into it.
    ("/ocio/guardar", {"tipo": "movie", "ref": "tt0088247", "via": "movie"}),
    # Your own three fields on a card. A cross-site POST here would rewrite
    # what you thought of something, which is the one thing nothing else
    # writes.
    # Asking the model for a card's summary again. A cross-site POST here
    # would spend the user's quota, the same reason /retry is on this list.
    ("/item/a1/describe", {}),
    ("/item/a1/mine/state", {"state": "done"}),
    ("/item/a1/mine/score", {"score": "4"}),
    ("/item/a1/mine/note", {"my_note": "x"}),
    # Asking an engine for its models. A cross-site POST here would run
    # `opencode models` and reach the user's provider with their key.
    ("/settings/models/opencode", {}),
    # Making the .env. A cross-site POST here would write a file into the
    # user's config folder, which is nobody else's business.
    ("/settings/env", {}),
    ("/collections/add", {"name": "Casa", "id": ["a1"]}),
    ("/collections/remove", {"name": "Casa", "id": ["a1"]}),
    ("/item/a1/collections", {"add": "Casa"}),
]


def note(id, title, category, tags=("x",), type="article", mentions=None):
    return Note(id=id, url=f"https://e.com/{id}", title=title, category=category,
                tags=list(tags), type=type, source="e.com", saved="2026-10-03",
                summary=f"Resumen de {title}.", points=[], mentions=mentions)


def snapshot(root):
    """Every file under root with its text: what a request must not change."""
    return {str(p.relative_to(root)): p.read_bytes()
            for p in sorted(root.rglob("*")) if p.is_file()}


class Recorder:
    """An ASGI wrapper that notes when the response left the server.

    It is the only way to tell a handler that answers and then works from one
    that works and then answers: TestClient runs background tasks inside the
    same call either way.
    """

    def __init__(self, app, log):
        self.app, self.log = app, log

    async def __call__(self, scope, receive, send):
        async def watched(message):
            if message["type"] == "http.response.body" and not message.get("more_body"):
                self.log.append("response sent")
            await send(message)

        await self.app(scope, receive, watched)


@pytest.fixture(autouse=True)
def state_tree(tmp_path, monkeypatch):
    """Every test in this file, whether or not it uses `setup`: an edit takes
    the real queue lock, which creates a file under XDG_STATE_HOME."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))


@pytest.fixture
def config_path(tmp_path, monkeypatch):
    """Nothing here may touch the real ~/.config/oknowledge/config.toml."""
    path = tmp_path / "config" / "config.toml"
    monkeypatch.setattr("oknowledge.web.app.CONFIG_PATH", path)
    return path


def in_spanish(cfg):
    """The same vault with the interface in Spanish. The language is part of
    the Config now, so this is a different app and not a different file."""
    return TestClient(create_app(dataclasses.replace(cfg, ui_language="es")))


@pytest.fixture
def setup(tmp_path, config_path, monkeypatch):
    # The reprocess route reaches the queue. If the origin check ever breaks,
    # a cross-site test here would run the real pipeline: keep its state tree
    # inside tmp_path so a regression cannot touch ~/.local/state either.
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    write_note(cfg, note("a1", "WireGuard", "Networking"), "es")
    write_note(cfg, note("b2", "Masa madre", "Cocina"), "es")
    rebuild_indexes(cfg, "es")
    return cfg, TestClient(create_app(cfg))


def test_no_test_in_this_file_can_reach_the_real_state_directory(tmp_path):
    """Asked of a test that uses no fixture of ours: the pin is module-wide."""
    from oknowledge.queue import state_dir

    assert state_dir().is_relative_to(tmp_path)


def test_the_state_directory_is_under_tmp_path(setup, tmp_path):
    from oknowledge.queue import state_dir

    assert state_dir().is_relative_to(tmp_path)


# --- editing one note -------------------------------------------------------

def test_moving_a_note_from_the_item_page(setup):
    cfg, client = setup
    response = client.post("/item/a1/category", data={"category": "Redes"},
                           follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/item/a1")
    assert index_path(cfg, "Redes").exists()
    assert find_note(cfg, "a1")[1].category == "Redes"


def test_editing_tags_from_the_item_page(setup):
    cfg, client = setup
    client.post("/item/a1/tags", data={"tags": "vpn, Seguridad, vpn"})
    assert find_note(cfg, "a1")[1].tags == ["vpn", "seguridad"]


def test_a_category_that_leaves_the_folder_is_refused_by_the_web(setup, tmp_path):
    cfg, client = setup
    before = snapshot(tmp_path)
    response = client.post("/item/a1/category", data={"category": "../../evil"})
    assert response.status_code == 200
    assert "cannot be used" in response.text
    assert snapshot(tmp_path) == before


def test_editing_a_link_that_is_not_there_is_a_404(setup):
    _, client = setup
    assert client.post("/item/zzz/tags", data={"tags": "x"}).status_code == 404


# --- deleting ---------------------------------------------------------------

def test_deleting_from_the_item_page(setup):
    cfg, client = setup
    client.post("/item/a1/delete", follow_redirects=False)
    assert find_note(cfg, "a1") is None


def test_deleting_moves_the_note_to_the_trash_and_says_so(setup):
    cfg, client = setup
    body = client.post("/item/a1/delete").text
    assert [p.name for p in trash_dir(cfg).glob("*.md")]
    assert "trash" in body.lower()


def test_a_link_cannot_delete_a_note(setup):
    """A GET must never change anything: browsers and crawlers follow links."""
    cfg, client = setup
    assert client.get("/item/a1/delete").status_code == 405
    assert find_note(cfg, "a1") is not None


# --- categories -------------------------------------------------------------

def test_the_categories_page_lists_them_with_counts(setup):
    _, client = setup
    body = client.get("/categories").text
    assert "Networking" in body and "Cocina" in body


def test_renaming_a_category_from_the_web(setup):
    cfg, client = setup
    client.post("/categories/rename", data={"old": "Networking", "new": "Redes"})
    assert index_path(cfg, "Redes").exists()
    assert not index_path(cfg, "Networking").exists()


def test_renaming_reports_how_many_notes_moved(setup):
    cfg, client = setup
    write_note(cfg, note("c3", "SSH", "Networking"), "es")
    body = client.post("/categories/rename",
                       data={"old": "Networking", "new": "Redes"}).text
    assert "2 notes moved" in body


def test_renaming_into_a_name_we_refuse_changes_nothing(setup, tmp_path):
    _, client = setup
    before = snapshot(tmp_path)
    body = client.post("/categories/rename",
                       data={"old": "Networking", "new": "a/b"}).text
    assert "cannot be used" in body
    assert snapshot(tmp_path) == before


# --- re-running the analysis ------------------------------------------------

def test_reprocess_answers_before_the_analysis_runs(setup, monkeypatch):
    """Ruling 7: the chain can take minutes per engine. The page cannot wait."""
    cfg, _ = setup
    log = []
    monkeypatch.setattr("oknowledge.web.app.add_link",
                        lambda *args, **kwargs: log.append("analysis ran"))
    client = TestClient(Recorder(create_app(cfg), log))

    response = client.post("/item/a1/reprocess", follow_redirects=False)

    assert response.status_code == 303
    assert log == ["response sent", "analysis ran"]


def test_reprocess_asks_for_the_right_url_and_engine(setup, monkeypatch):
    _, client = setup
    calls = []
    monkeypatch.setattr("oknowledge.web.app.add_link",
                        lambda cfg, url, **kwargs: calls.append((url, kwargs)))
    client.post("/item/a1/reprocess", data={"engine": "ollama"})
    assert calls == [("https://e.com/a1", {"engine": "ollama", "reprocess": True,
                                           "trace": client.app.state.batch.note})]


def test_reprocess_without_an_engine_lets_the_chain_decide(setup, monkeypatch):
    _, client = setup
    calls = []
    monkeypatch.setattr("oknowledge.web.app.add_link",
                        lambda cfg, url, **kwargs: calls.append(kwargs))
    client.post("/item/a1/reprocess", data={"engine": ""})
    assert calls == [{"engine": None, "reprocess": True,
                      "trace": client.app.state.batch.note}]


def test_reprocess_with_an_engine_we_do_not_have_is_refused(setup, monkeypatch):
    _, client = setup
    monkeypatch.setattr("oknowledge.web.app.add_link",
                        lambda *args, **kwargs: pytest.fail("should not run"))
    assert client.post("/item/a1/reprocess",
                       data={"engine": "gpt5"}).status_code == 400


def test_reprocess_of_a_link_that_is_not_there_is_a_404(setup, monkeypatch):
    _, client = setup
    monkeypatch.setattr("oknowledge.web.app.add_link",
                        lambda *args, **kwargs: pytest.fail("should not run"))
    assert client.post("/item/zzz/reprocess").status_code == 404


def test_an_analysis_that_explodes_does_not_break_the_server(setup, monkeypatch):
    _, client = setup

    def boom(*args, **kwargs):
        raise RuntimeError("the engine died")

    monkeypatch.setattr("oknowledge.web.app.add_link", boom)
    assert client.post("/item/a1/reprocess", follow_redirects=False).status_code == 303
    assert client.get("/item/a1").status_code == 200


# --- settings ---------------------------------------------------------------

def test_settings_shows_the_chain_and_both_languages(setup):
    _, client = setup
    body = client.get("/settings").text
    assert "opencode" in body
    assert "Interface language" in body or "Idioma de la interfaz" in body


def test_the_two_language_pickers_offer_the_same_order(setup):
    """Two adjacent groups, both of them headed "language", had their options in
    opposite order. Clicking the first of each -- the only sensible thing to do
    -- set the summary to Spanish and the interface to English, and the page
    looked right afterwards because each group showed its own choice ticked.

    Rendered rather than read off the template: the order a browser lays out is
    the rendered one.
    """
    import re

    from oknowledge.i18n import LANGUAGES

    _, client = setup
    page = client.get("/settings").text

    def offered(field):
        return re.findall(rf'name="{field}"\s+value="([a-z]+)"', page)

    assert offered("language") == list(LANGUAGES)
    assert offered("ui_language") == offered("language")


def test_the_language_in_use_is_the_one_already_ticked(setup):
    """Otherwise the page is in Spanish with English ticked, and the next save
    -- of anything at all -- posts English back and switches the interface
    somebody never asked to switch."""
    cfg, _ = setup

    def ticked(body):
        return re.findall(r'name="ui_language" value="([a-z]+)"\s*checked', body)

    assert ticked(in_spanish(cfg).get("/settings").text) == ["es"]
    assert ticked(TestClient(create_app(cfg)).get("/settings").text) == ["en"]


def test_settings_warns_that_saving_rewrites_the_file(setup):
    """Comments are not the only thing lost: any key load() does not read goes
    too, and the file is the one we tell the user to hand-write."""
    _, client = setup
    body = client.get("/settings").text
    assert "comment" in body.lower()
    assert "does not read" in body
    assert "config.toml.bak" in body


def test_saving_settings_writes_both_languages_into_the_one_file(
        setup, config_path):
    """Two axes, two tables, one save. The summaries in English and the buttons
    in Spanish is a real combination somebody wants, and the form has to be
    able to say it."""
    _, client = setup

    client.post("/settings", data={
        "chain": ["ollama", "opencode"], "language": "en",
        "default_content": "summary", "ui_language": "es",
    })

    saved = tomllib.loads(config_path.read_text(encoding="utf-8"))
    assert saved["ai"]["chain"] == ["ollama", "opencode"]
    assert saved["ai"]["language"] == "en"
    assert saved["default_content"] == "summary"
    assert saved["web"]["language"] == "es"


def test_saving_settings_keeps_the_models(setup, config_path):
    _, client = setup
    client.post("/settings", data={"chain": ["ollama"], "ollama_model": "qwen3:8b"})
    saved = tomllib.loads(config_path.read_text(encoding="utf-8"))
    assert saved["ai"]["ollama"]["model"] == "qwen3:8b"


def test_an_empty_chain_keeps_the_one_that_works(setup, config_path):
    """config.load() refuses an empty chain: saving one would brick the app."""
    cfg, client = setup
    client.post("/settings", data={"language": "en"})
    saved = tomllib.loads(config_path.read_text(encoding="utf-8"))
    assert saved["ai"]["chain"] == list(cfg.chain)


def test_values_we_do_not_know_are_ignored(setup, config_path):
    cfg, client = setup
    client.post("/settings", data={
        "chain": ["gpt5"], "language": "klingon", "default_content": "half",
        "ui_language": "fr",
    })
    saved = tomllib.loads(config_path.read_text(encoding="utf-8"))
    assert saved["ai"]["chain"] == list(cfg.chain)
    assert saved["ai"]["language"] == cfg.language
    assert saved["default_content"] == cfg.default_content


def test_a_saved_config_can_be_read_back(setup, config_path):
    from oknowledge.config import load

    _, client = setup
    client.post("/settings", data={"chain": ["ollama", "api"], "language": "en",
                                   "default_content": "summary"})
    reloaded = load(config_path)
    assert reloaded.chain == ("ollama", "api")
    assert reloaded.default_content == "summary"


def test_the_settings_page_saves_the_mention_mode(setup, config_path):
    _, client = setup
    client.post("/settings", data={"mentions": "discussed"})
    saved = tomllib.loads(config_path.read_text(encoding="utf-8"))
    assert saved["ai"]["mentions"] == "discussed"


def test_a_mention_mode_that_is_not_one_leaves_what_was_there(setup, config_path):
    """Every value is checked in the route, because config.load() would refuse
    the file afterwards and the whole tool would stop reading its own config."""
    cfg, client = setup
    client.post("/settings", data={"mentions": "../../etc"})
    saved = tomllib.loads(config_path.read_text(encoding="utf-8"))
    assert saved["ai"]["mentions"] == cfg.mentions


# --- the origin check (ruling 6) --------------------------------------------

@pytest.mark.parametrize("path,data", WRITE_ROUTES)
def test_a_cross_site_post_is_refused_and_changes_nothing(
        setup, tmp_path, config_path, path, data):
    """Any page the user visits can POST here. None of them may be obeyed."""
    _, client = setup
    before = snapshot(tmp_path)

    response = client.post(path, data=data, headers={"Sec-Fetch-Site": "cross-site"},
                           follow_redirects=False)

    assert response.status_code == 403
    assert snapshot(tmp_path) == before
    assert not config_path.exists()


@pytest.mark.parametrize("path,data", WRITE_ROUTES)
def test_an_old_browser_with_a_foreign_origin_is_refused(setup, tmp_path, path, data):
    _, client = setup
    before = snapshot(tmp_path)
    response = client.post(path, data=data,
                           headers={"Origin": "https://evil.example"},
                           follow_redirects=False)
    assert response.status_code == 403
    assert snapshot(tmp_path) == before


def test_a_same_site_post_is_refused_too(setup, tmp_path):
    """Same site is not same origin: another port on localhost is another app."""
    _, client = setup
    before = snapshot(tmp_path)
    response = client.post("/item/a1/delete", headers={"Sec-Fetch-Site": "same-site"},
                           follow_redirects=False)
    assert response.status_code == 403
    assert snapshot(tmp_path) == before


def test_our_own_pages_can_still_post(setup):
    cfg, client = setup
    response = client.post("/item/a1/category", data={"category": "Redes"},
                           headers={"Sec-Fetch-Site": "same-origin",
                                    "Origin": "http://testserver"},
                           follow_redirects=False)
    assert response.status_code == 303
    assert find_note(cfg, "a1")[1].category == "Redes"


def test_a_post_with_no_browser_context_still_works(setup):
    """Sec-Fetch-Site: none is what the address bar sends; curl sends neither."""
    cfg, client = setup
    response = client.post("/item/a1/category", data={"category": "Redes"},
                           headers={"Sec-Fetch-Site": "none"}, follow_redirects=False)
    assert response.status_code == 303
    assert find_note(cfg, "a1")[1].category == "Redes"


def test_a_cross_site_get_is_still_served(setup):
    """Reading is not writing: an embedded page may be odd, but it is harmless."""
    _, client = setup
    assert client.get("/", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 200


# --- the two language axes (I1) ---------------------------------------------

def spanish_note(cfg):
    note = Note(id="c3", url="https://e.com/c3", title="Túneles", category="Redes",
                tags=["vpn"], type="article", source="e.com", saved="2026-10-03",
                summary="Resumen.", points=["Corre en el kernel"],
                body="El texto entero.")
    return write_note(cfg, note, "es")


def test_an_edit_keeps_the_note_in_the_language_the_ai_writes(tmp_path, config_path):
    """The UI language and `[ai] language` are two settings. The vault's
    `language` argument is the second one: it picks the note's headings."""
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault, language="es")       # the UI stays English (autouse)
    path = spanish_note(cfg)
    rebuild_indexes(cfg, "es")
    client = TestClient(create_app(cfg))

    client.post("/item/c3/category", data={"category": "Seguridad"})

    text = path.read_text(encoding="utf-8")
    assert "## Puntos clave" in text and "## Contenido original" in text
    assert "## Key points" not in text and "## Original content" not in text
    assert "Generado por oknowledge" in index_path(cfg, "Seguridad").read_text(
        encoding="utf-8")


def test_a_rename_keeps_the_note_in_the_language_the_ai_writes(tmp_path, config_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault, language="es")
    path = spanish_note(cfg)
    client = TestClient(create_app(cfg))

    client.post("/categories/rename", data={"old": "Redes", "new": "Seguridad"})

    assert "## Puntos clave" in path.read_text(encoding="utf-8")


def test_a_delete_keeps_the_indexes_in_the_language_the_ai_writes(tmp_path, config_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault, language="es")
    spanish_note(cfg)
    write_note(cfg, note("d4", "SSH", "Redes"), "es")
    rebuild_indexes(cfg, "es")
    client = TestClient(create_app(cfg))

    client.post("/item/c3/delete")

    assert "Generado por oknowledge" in index_path(cfg, "Redes").read_text(
        encoding="utf-8")


# --- reprocess replaces hand-typed content, so it asks first (I2) -----------

def test_reprocess_asks_before_it_replaces_the_note(setup):
    _, client = setup
    body = client.get("/item/a1").text
    form = body[body.index('/item/a1/reprocess'):]
    assert "data-ask=" in form[:400]
    assert "replaced" in form[:400]
    assert form.count("confirm(this.form.dataset.ask)") >= 1


# --- an edit and a running analysis cannot cross (m7) -----------------------

@pytest.mark.parametrize("path,data", [
    ("/item/a1/category", {"category": "Redes"}),
    ("/item/a1/tags", {"tags": "vpn"}),
    ("/item/a1/delete", {}),
])
def test_an_edit_waits_for_a_running_analysis(setup, path, data):
    """Otherwise a background reprocess writes its answer over the edit, or
    worse, recreates a note the user has just sent to the trash."""
    from oknowledge.queue import Queue

    cfg, client = setup
    before = find_note(cfg, "a1")[1]
    with Queue().lock("a1"):
        body = client.post(path, data=data).text

    assert "analysis is running" in body
    found = find_note(cfg, "a1")
    assert found is not None
    assert (found[1].category, found[1].tags) == (before.category, before.tags)


def test_an_edit_goes_through_once_the_analysis_is_over(setup):
    from oknowledge.queue import Queue

    cfg, client = setup
    with Queue().lock("a1"):
        pass
    client.post("/item/a1/category", data={"category": "Redes"})
    assert find_note(cfg, "a1")[1].category == "Redes"


def test_an_unlockable_state_tree_does_not_block_an_edit(setup, monkeypatch):
    """The queue is bookkeeping; the note is the artifact. Same call
    pipeline.add() makes when it cannot lock."""
    from oknowledge import queue as queue_module

    cfg, client = setup

    def refuse(*args, **kwargs):
        raise PermissionError(13, "state tree is read-only")

    monkeypatch.setattr(queue_module.Queue, "lock", refuse)
    client.post("/item/a1/category", data={"category": "Redes"})
    assert find_note(cfg, "a1")[1].category == "Redes"


# --- the refusal names the characters it refuses (m1) -----------------------

def test_the_refusal_names_every_character_it_refuses():
    """Read from the constant, so adding a character to the rule and not to the
    message is a failing test rather than a message that lies by omission."""
    from oknowledge.ai.base import UNSAFE_IN_A_NAME
    from oknowledge.web.app import NOTICES

    message = NOTICES["bad-category"]
    for char in UNSAFE_IN_A_NAME:
        assert char in message, f"the refusal does not name {char!r}"


# --- a write that cannot happen says so (m3) --------------------------------

@pytest.mark.skipif(os.geteuid() == 0, reason="a folder we cannot write does not bite as root")
@posix_only
def test_a_vault_that_cannot_be_written_says_so(setup):
    cfg, client = setup
    cfg.links_dir.chmod(0o500)
    try:
        body = client.post("/item/a1/category", data={"category": "Redes"}).text
    finally:
        cfg.links_dir.chmod(0o700)
    assert "could not be written" in body
    assert find_note(cfg, "a1")[1].category == "Networking"


def test_a_trash_folder_that_cannot_be_made_says_so(setup):
    cfg, client = setup
    (cfg.root / "trash").write_text("not a folder\n", encoding="utf-8")
    body = client.post("/item/a1/delete").text
    assert "could not be written" in body
    assert find_note(cfg, "a1") is not None


@pytest.mark.skipif(os.geteuid() == 0, reason="a folder we cannot write does not bite as root")
@posix_only
def test_settings_that_cannot_be_saved_say_so(setup, config_path):
    _, client = setup
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.parent.chmod(0o500)
    try:
        body = client.post("/settings", data={"chain": ["ollama"]}).text
    finally:
        config_path.parent.chmod(0o700)
    assert "could not be saved" in body
    assert not config_path.exists()


# --- the settings branches that had no test (m4) ----------------------------

def test_clearing_a_model_removes_only_that_key(setup, config_path):
    import dataclasses

    cfg, _ = setup
    with_model = dataclasses.replace(
        cfg, engines={"ollama": {"model": "qwen3:8b", "url": "http://x"}})
    client = TestClient(create_app(with_model))

    client.post("/settings", data={"chain": ["ollama"], "ollama_model": ""})

    saved = tomllib.loads(config_path.read_text(encoding="utf-8"))
    assert saved["ai"]["ollama"] == {"url": "http://x"}


def test_a_model_name_that_is_not_one_keeps_what_was_saved(setup, config_path):
    import dataclasses

    cfg, _ = setup
    with_model = dataclasses.replace(cfg, engines={"ollama": {"model": "qwen3:8b"}})
    client = TestClient(create_app(with_model))

    client.post("/settings", data={"chain": ["ollama"], "ollama_model": "qwen\x073:8b"})

    saved = tomllib.loads(config_path.read_text(encoding="utf-8"))
    assert saved["ai"]["ollama"]["model"] == "qwen3:8b"


def test_an_interface_language_we_do_not_have_leaves_the_saved_one_alone(
        setup, config_path):
    """The form is a list of radio buttons, so this only arrives from a posted
    form somebody built by hand -- and config.load() would refuse the file
    afterwards, which would stop the whole program reading its own config."""
    _, client = setup

    client.post("/settings", data={"chain": ["ollama"], "ui_language": "fr"})

    saved = tomllib.loads(config_path.read_text(encoding="utf-8"))
    assert saved["web"]["language"] == "en"
    assert load(config_path).ui_language == "en"


# --- counting and merging in words (m6, m10) --------------------------------

def test_moving_one_note_does_not_say_one_notes(setup):
    _, client = setup
    body = client.post("/categories/rename",
                       data={"old": "Networking", "new": "Redes"}).text
    assert "1 note moved" in body
    assert "1 notes" not in body


def test_a_merge_says_that_it_merged(setup):
    cfg, client = setup
    body = client.post("/categories/rename",
                       data={"old": "Networking", "new": "Cocina"}).text
    assert "merged" in body
    assert index_path(cfg, "Cocina").read_text(encoding="utf-8").count("[[") == 2


def test_a_plain_rename_does_not_claim_a_merge(setup):
    _, client = setup
    body = client.post("/categories/rename",
                       data={"old": "Networking", "new": "Redes"}).text
    assert "merged" not in body


# --- the cross-site test cannot quietly stop covering a route (m8) ----------

def test_the_cross_site_test_covers_every_write_route(setup):
    import re

    _, client = setup
    declared = {route.path for route in client.app.routes
                if "POST" in getattr(route, "methods", ())}
    assert declared, "no POST routes found: this test is not looking at the app"
    tested = [path for path, _ in WRITE_ROUTES]
    for route in sorted(declared):
        pattern = re.compile("^" + re.sub(r"\{[^}]+\}", "[^/]+", route) + "$")
        assert any(pattern.match(path) for path in tested), \
            f"no cross-site test for {route}"
    for path in tested:
        assert any(re.fullmatch(re.sub(r"\{[^}]+\}", "[^/]+", route), path)
                   for route in declared), f"{path} is not a route any more"


def test_a_note_whose_id_the_queue_cannot_name_is_still_editable(setup):
    """A hand-edited `id:` need not look like one of ours. The queue refuses to
    name a lock for it -- and no analysis can be running on it either, since
    the queue could not hold an entry for it, so the edit goes ahead."""
    cfg, client = setup
    odd = cfg.links_dir / "odd.md"
    odd.write_text(
        "---\nurl: https://e.com/odd\ntitle: Odd\ncategory: Networking\n"
        "tags: []\ntype: article\nsource: e.com\nsaved: '2026-10-03'\n"
        "id: has spaces\noknowledge: 1\n---\n\n# Odd\n\nResumen.\n",
        encoding="utf-8")

    response = client.post("/item/has spaces/category", data={"category": "Redes"},
                           follow_redirects=False)

    assert response.status_code == 303
    assert find_note(cfg, "has spaces")[1].category == "Redes"


@pytest.mark.parametrize("path,data", [
    ("/item/a1/category", {"category": "Redes"}),
    ("/item/a1/tags", {"tags": "vpn"}),
    ("/item/a1/delete", {}),
])
def test_the_lock_is_still_held_while_the_note_is_written(setup, monkeypatch, path, data):
    """Holding the lock is the fix; taking it and letting go before the work
    would only move the race, so assert it is still held at the end of it.
    flock belongs to the open file, so a second fd conflicts even in this
    process -- which is exactly the case that matters, since the background
    re-analysis is a thread of this same server."""
    from oknowledge import vault
    from oknowledge.queue import Locked, Queue

    _, client = setup
    reindexed = vault.rebuild_indexes
    held = []

    def watched(cfg, language, shelf=None):
        try:
            with Queue().lock("a1"):
                held.append(False)        # got it: nobody is holding it
        except Locked:
            held.append(True)
        return reindexed(cfg, language, shelf)

    monkeypatch.setattr(vault, "rebuild_indexes", watched)
    client.post(path, data=data)

    assert held, "the vault never got as far as rebuilding the indexes"
    assert all(held), "the link's queue lock was released before the work was done"


# --- the refusal states the rule it enforces (M1) ---------------------------

def test_every_notice_has_a_spanish_translation():
    from oknowledge.i18n import STRINGS
    from oknowledge.web.app import NOTICES

    missing = [key for key, text in NOTICES.items() if text not in STRINGS["es"]]
    assert missing == []


@pytest.mark.parametrize("language", ["en", "es"])
def test_the_refusal_states_the_rule_it_enforces(language):
    """The field arrives pre-filled with the value already saved, so a user
    whose AI-written category is "Misc." will click Save and be told why. The
    reason has to be the real one."""
    from oknowledge.ai.base import MAX_CATEGORY_LENGTH
    from oknowledge.i18n import translator
    from oknowledge.web.app import NOTICES

    message = translator(language)(NOTICES["bad-category"])
    if language == "es":
        assert message != NOTICES["bad-category"], "the Spanish is missing"
    for char in '/\\:*?"<>|':
        assert char in message, f"the refusal does not name {char!r}"
    assert str(MAX_CATEGORY_LENGTH) in message, "the length limit is not stated"
    assert "end" in message or "final" in message, "trailing dots are not stated"


def test_a_category_with_a_trailing_dot_is_refused_by_the_web(setup):
    cfg, client = setup
    body = client.post("/item/a1/category", data={"category": "Misc."}).text
    assert "cannot be used" in body
    assert find_note(cfg, "a1")[1].category == "Networking"


# --- a partial rename counts in words that agree (M2) -----------------------

def flaky_writes(monkeypatch, failing):
    """Make write_note fail for the notes whose id is in `failing`."""
    from oknowledge import vault

    real = vault.write_note

    def write(cfg, note, language, path=None):
        if note.id in failing:
            raise OSError(13, "Permission denied")
        return real(cfg, note, language, path=path)

    monkeypatch.setattr(vault, "write_note", write)


@pytest.mark.parametrize("moved,failed,fragment", [
    (1, 1, "1 note moved, 1 could not be written"),
    (1, 2, "1 note moved, 2 could not be written"),
    (2, 1, "2 notes moved, 1 could not be written"),
    (2, 2, "2 notes moved, 2 could not be written"),
])
def test_a_partial_rename_counts_in_words_that_agree(setup, monkeypatch, moved,
                                                     failed, fragment):
    cfg, client = setup
    ids = [f"n{i}" for i in range(moved + failed)]
    for name in ids:
        write_note(cfg, note(name, name.upper(), "Mixta"), "es")
    flaky_writes(monkeypatch, set(ids[moved:]))

    body = client.post("/categories/rename",
                       data={"old": "Mixta", "new": "Redes"}).text

    assert fragment in body
    assert "1 notes" not in body


def test_a_partial_rename_agrees_in_spanish(setup, monkeypatch):
    cfg, _ = setup
    client = in_spanish(cfg)
    write_note(cfg, note("n0", "Uno", "Mixta"), "es")
    write_note(cfg, note("n1", "Dos", "Mixta"), "es")
    flaky_writes(monkeypatch, {"n1"})

    body = client.post("/categories/rename",
                       data={"old": "Mixta", "new": "Redes"}).text

    assert "Se movió 1 nota" in body
    assert "1 no se pudo escribir" in body


# --- the reprocess confirmation is the reprocess button's (F2) --------------

def reprocess_form(body):
    start = body.index('action="/item/a1/reprocess"')
    return body[start:body.index("</form>", start)]


def test_reprocess_asks_on_its_own_button(setup):
    """Sliced to its own form: the delete form below it also confirms, and a
    slice that ran on into it would pass with this button unguarded."""
    _, client = setup
    form = reprocess_form(client.get("/item/a1").text)
    assert "data-ask=" in form
    assert "replaced" in form
    assert "confirm(this.form.dataset.ask)" in form


# --- a settings write has no halves left (was F3) ---------------------------

def test_a_settings_write_that_fails_does_not_switch_the_language_either(
        setup, config_path, monkeypatch):
    """The interface language used to go into a file of Omarchy's, so a save
    could land half: the config written, the language not, and a notice for
    exactly that. One file means one outcome -- and the page that comes back
    from a failed save is still in the language that is on disk.
    """
    _, client = setup

    def boom(*args, **kwargs):
        raise PermissionError(13, "the config folder is read-only")

    monkeypatch.setattr("oknowledge.web.app.save_config", boom)
    body = client.post("/settings",
                       data={"chain": ["ollama"], "ui_language": "es"}).text

    assert not config_path.exists()
    assert "could not be saved" in body
    assert "Ajustes" not in body                   # not switched to Spanish


# --- a change that landed with indexes that did not (F4) --------------------

def break_reindex(monkeypatch):
    from oknowledge import vault

    def boom(cfg, language, shelf=None):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(vault, "rebuild_indexes", boom)


def test_an_edit_whose_indexes_fail_does_not_claim_nothing_was_written(
        setup, monkeypatch):
    cfg, client = setup
    break_reindex(monkeypatch)

    body = client.post("/item/a1/category", data={"category": "Redes"}).text

    assert find_note(cfg, "a1")[1].category == "Redes"      # it did land
    assert "indexes" in body
    assert "could not be written" not in body


def test_a_delete_whose_indexes_fail_lands_somewhere_that_exists(setup, monkeypatch):
    cfg, client = setup
    break_reindex(monkeypatch)

    response = client.post("/item/a1/delete", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"].startswith("/?")
    landed = client.get(response.headers["location"])
    assert landed.status_code == 200
    assert "trash" in landed.text.lower() and "indexes" in landed.text
    assert find_note(cfg, "a1") is None
    assert list(trash_dir(cfg).glob("*.md"))


def test_a_rename_whose_indexes_fail_does_not_claim_nothing_was_written(
        setup, monkeypatch):
    cfg, client = setup
    break_reindex(monkeypatch)

    body = client.post("/categories/rename",
                       data={"old": "Networking", "new": "Redes"}).text

    assert find_note(cfg, "a1")[1].category == "Redes"
    assert "indexes" in body
    assert "could not be written" not in body


# --- the rename route holds each note's lock (F5) ---------------------------

def test_a_rename_from_the_web_skips_a_note_being_analysed(setup):
    from oknowledge.queue import Queue

    cfg, client = setup
    write_note(cfg, note("c3", "SSH", "Networking"), "es")
    with Queue().lock("a1"):
        body = client.post("/categories/rename",
                           data={"old": "Networking", "new": "Redes"}).text

    assert find_note(cfg, "a1")[1].category == "Networking"   # left alone
    assert find_note(cfg, "c3")[1].category == "Redes"
    assert "1 note moved, 1 could not be written" in body


# --- an unknown link leaves nothing behind (F6) -----------------------------

@pytest.mark.parametrize("path,data", [
    ("/item/zzz/category", {"category": "Redes"}),
    ("/item/zzz/tags", {"tags": "vpn"}),
    ("/item/zzz/delete", {}),
    ("/item/zzz/mentions/delete", {"name": "x"}),
])
def test_an_unknown_link_leaves_no_lock_behind(setup, tmp_path, path, data):
    """A lock file is never deleted, so creating one for a link that does not
    exist leaves litter in the state tree for every typo and stale page."""
    _, client = setup
    assert client.post(path, data=data).status_code == 404
    locks = tmp_path / "state" / "oknowledge" / "locks"
    # Two plain assertions, in this order: the folder is not made, and if some
    # other caller ever makes it, it still holds nothing. (Written as one
    # conditional expression this read as `assert True` on the happy path --
    # it did catch its regression, but only by accident of which came first.)
    assert not locks.exists()
    assert [p.name for p in locks.glob("*")] == []


# --- the coverage test watches every unsafe method (L3) ---------------------

def unsafe_routes(app):
    """Every (path, method) the origin check has to cover, from the app itself.

    Shaped by SAFE_METHODS and not by a list of verbs, because that is how the
    middleware decides: a PUT or a DELETE added later is covered without
    anyone remembering to cover it, and this is what keeps saying so.
    """
    from oknowledge.web.app import SAFE_METHODS

    return {(route.path, method) for route in app.routes
            for method in getattr(route, "methods", set()) - SAFE_METHODS}


def test_the_cross_site_test_covers_every_unsafe_method(setup):
    import re

    _, client = setup
    unsafe = unsafe_routes(client.app)
    assert unsafe, "no unsafe routes found: this test is not looking at the app"
    tested = [path for path, _ in WRITE_ROUTES]
    for route, method in sorted(unsafe):
        pattern = re.compile("^" + re.sub(r"\{[^}]+\}", "[^/]+", route) + "$")
        assert any(pattern.match(path) for path in tested), \
            f"no cross-site test for {method} {route}"


def test_the_coverage_check_is_not_blind_to_a_method_we_do_not_use_yet(setup):
    """Every unsafe route in the app is a POST today, so the check above would
    read the same if it only looked at POST. Give it a DELETE to find."""
    cfg, _ = setup
    app = create_app(cfg)

    @app.delete("/item/{link_id}/purge")
    def purge(link_id: str):
        return {"purged": link_id}

    assert ("/item/{link_id}/purge", "DELETE") in unsafe_routes(app)


def test_the_origin_check_covers_a_method_we_do_not_use_yet(setup):
    """The middleware checks the method against SAFE_METHODS rather than a
    list of the routes we happen to have, so this is the property that lets a
    future write route be safe before anyone thinks about it."""
    cfg, _ = setup
    app = create_app(cfg)

    @app.delete("/item/{link_id}/purge")
    def purge(link_id: str):
        return {"purged": link_id}

    client = TestClient(app)
    assert client.delete("/item/a1/purge",
                         headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert client.delete("/item/a1/purge").status_code == 200


# --- the config file the process was actually given -------------------------
# Started with `--config somewhere/else.toml`, the CLI reads that file and
# nothing else. A settings page that writes ~/.config/oknowledge/config.toml
# anyway would report "saved" and change nothing the tool reads, which is
# worse than refusing to save at all.

def write_config_file(path, vault):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'vault = "{vault}"\n[ai]\nlanguage = "es"\n', encoding="utf-8")
    return path


def elsewhere(tmp_path, monkeypatch):
    """A vault, a config file that is not the default one, and a decoy at the
    default location that no test may touch."""
    decoy = tmp_path / "default" / "config.toml"
    monkeypatch.setattr("oknowledge.web.app.CONFIG_PATH", decoy)
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    chosen = write_config_file(tmp_path / "elsewhere" / "oknowledge.toml", vault)
    return decoy, load(chosen), chosen


def test_settings_are_saved_to_the_config_the_process_was_given(tmp_path, monkeypatch):
    decoy, cfg, chosen = elsewhere(tmp_path, monkeypatch)
    client = TestClient(create_app(cfg))

    response = client.post("/settings", data={"chain": ["ollama"],
                                              "default_content": "summary"})

    assert response.status_code == 200
    assert not decoy.exists(), "the default config file was written instead"
    saved = tomllib.loads(chosen.read_text(encoding="utf-8"))
    assert saved["default_content"] == "summary"
    assert saved["ai"]["chain"] == ["ollama"]


def test_the_settings_page_names_the_config_the_process_was_given(tmp_path, monkeypatch):
    decoy, cfg, chosen = elsewhere(tmp_path, monkeypatch)
    client = TestClient(create_app(cfg))

    body = client.get("/settings").text

    assert str(chosen) in body
    assert str(decoy) not in body


def test_what_the_web_saves_is_what_the_cli_then_reads(tmp_path, monkeypatch):
    """The whole point of the two tests above, asserted end to end."""
    _, cfg, chosen = elsewhere(tmp_path, monkeypatch)
    client = TestClient(create_app(cfg))

    client.post("/settings", data={"chain": ["ollama", "opencode"],
                                   "language": "en", "default_content": "summary"})

    reloaded = load(chosen)
    assert reloaded.chain == ("ollama", "opencode")
    assert reloaded.language == "en"
    assert reloaded.default_content == "summary"
    assert reloaded.source == chosen


# --- a rename that moved nothing does not report a save (F2) ----------------
# `stale` was consulted first and `result.failed` only afterwards, so a vault
# that cannot be written at all reported "Saved, but the indexes could not be
# rebuilt" for zero notes moved. This is the Edited(notice, landed) lesson --
# say what landed, not what the first flag suggests -- carried into rename.

@pytest.mark.skipif(os.geteuid() == 0, reason="a read-only folder does not bite as root")
@posix_only
def test_a_rename_that_moved_nothing_does_not_say_it_saved(setup, monkeypatch):
    cfg, client = setup
    break_reindex(monkeypatch)
    cfg.links_dir.chmod(0o500)
    try:
        body = client.post("/categories/rename",
                           data={"old": "Networking", "new": "Redes"}).text
    finally:
        cfg.links_dir.chmod(0o700)

    assert find_note(cfg, "a1")[1].category == "Networking"   # nothing moved
    assert "could not be written" in body
    assert "Saved" not in body


@pytest.mark.skipif(os.geteuid() == 0, reason="a read-only folder does not bite as root")
def test_a_rename_that_moved_some_notes_still_reports_the_stale_indexes(
        setup, tmp_path, monkeypatch):
    """The other side of the same branch: when something did move, the user has
    to hear that it moved and that the indexes did not follow."""
    cfg, client = setup
    break_reindex(monkeypatch)

    body = client.post("/categories/rename",
                       data={"old": "Networking", "new": "Redes"}).text

    assert find_note(cfg, "a1")[1].category == "Redes"
    assert "indexes" in body


# --- reprocess reads the vault as it is now, not as the page remembers (F4) --

def test_reprocess_of_a_note_deleted_since_the_last_refresh_is_a_404(setup, monkeypatch):
    cfg, client = setup
    monkeypatch.setattr("oknowledge.web.app.add_link",
                        lambda *args, **kwargs: pytest.fail("the note is gone"))
    client.get("/item/a1")                      # the library is warm
    find_note(cfg, "a1")[0].unlink()            # deleted from Obsidian

    assert client.post("/item/a1/reprocess").status_code == 404


def test_reprocess_sees_a_note_that_appeared_since_the_last_refresh(setup, monkeypatch):
    """Refreshing has to be a refresh, not a cache reset that loses nothing."""
    cfg, client = setup
    calls = []
    monkeypatch.setattr("oknowledge.web.app.add_link",
                        lambda config, url, **kwargs: calls.append(url))
    client.get("/")
    write_note(cfg, note("c3", "Nextcloud", "Redes"), "es")

    assert client.post("/item/c3/reprocess", follow_redirects=False).status_code == 303
    assert calls == ["https://e.com/c3"]


def test_no_test_in_this_file_can_reach_the_real_config(tmp_path):
    """Asked of a test that uses no fixture of ours, like its state-tree twin:
    the pin is module-wide, and it is conftest's, not this file's."""
    from oknowledge.web import app as webapp

    assert webapp.CONFIG_PATH.is_relative_to(tmp_path)
    assert webapp.CONFIG_PATH != Path.home() / ".config" / "oknowledge" / "config.toml"


# --- deleting a mention ------------------------------------------------------

@pytest.fixture
def video(tmp_path, config_path, monkeypatch):
    """`setup`, with a1 a video that named two things: a real link and a search."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    write_note(cfg, note("a1", "Mi stack", "Networking", type="youtube",
                         mentions=[Mention(name="opencode", url="https://opencode.ai"),
                                   Mention(name="Railway", url=search_url("Railway"))]),
               "es")
    rebuild_indexes(cfg, "es")
    return cfg, TestClient(create_app(cfg))


def test_deleting_a_mention_leaves_the_rest(video):
    cfg, client = video
    client.post("/item/a1/mentions/delete", data={"name": "Railway"})

    assert [m.name for m in find_note(cfg, "a1")[1].mentions] == ["opencode"]


def test_deleting_the_last_one_leaves_an_empty_list_not_none(video):
    cfg, client = video
    for name in ("opencode", "Railway"):
        client.post("/item/a1/mentions/delete", data={"name": name})

    assert find_note(cfg, "a1")[1].mentions == []


def test_deleting_from_a_note_nobody_asked_leaves_none(setup):
    """None means nobody asked and [] means asked and nothing found. A crafted
    post must not flip one into the other: the Task 7 backfill would skip that
    video for good."""
    cfg, client = setup

    client.post("/item/a1/mentions/delete", data={"name": "x"})

    assert find_note(cfg, "a1")[1].mentions is None


# The one that can fail. Its vault-level twin, test_dropping_an_empty_name_is_a_no_op
# in test_vault_edit.py, is decorative on its own: it never sees a missing
# field. Keep both.
def test_a_delete_with_no_name_field_at_all_deletes_nothing(video):
    """The route defaults a missing name to "". If an absent name ever meant
    "all", a crafted post would wipe a whole list in silence."""
    cfg, client = video

    client.post("/item/a1/mentions/delete", data={})

    assert [m.name for m in find_note(cfg, "a1")[1].mentions] == ["opencode", "Railway"]


def test_deleting_a_mention_that_is_gone_is_not_an_error(video):
    """A double click, or a tab left open since yesterday."""
    _, client = video
    answer = client.post("/item/a1/mentions/delete", data={"name": "nada"},
                         follow_redirects=False)

    assert answer.status_code < 400


def test_deleting_a_mention_of_a_note_that_is_not_there_is_404(setup):
    _, client = setup
    answer = client.post("/item/nope/mentions/delete", data={"name": "x"},
                         follow_redirects=False)

    assert answer.status_code == 404


def test_deleting_a_mention_does_not_rebuild_the_indexes(video, monkeypatch):
    """No index mentions a mention. With 1227 notes, rebuilding them all on
    every click is real work for nothing."""
    _, client = video
    monkeypatch.setattr("oknowledge.vault.rebuild_indexes",
                        lambda *a, **kw: pytest.fail("rebuilt for nothing"))

    client.post("/item/a1/mentions/delete", data={"name": "Railway"})


# --- colecciones -------------------------------------------------------------

def collected(client, link_id):
    return client.get(f"/item/{link_id}").text


def test_adding_a_collection_to_several_notes_writes_them_all(setup):
    cfg, client = setup

    client.post("/collections/add", data={"name": "Casa nueva", "id": ["a1", "b2"]})

    assert find_note(cfg, "a1")[1].collections == ["Casa nueva"]
    assert find_note(cfg, "b2")[1].collections == ["Casa nueva"]


def test_the_form_the_library_draws_is_what_the_route_reads(setup):
    """Posted field by field out of the rendered HTML: a hidden input dropped
    from the template has to break a test, not a user's afternoon."""
    cfg, client = setup
    body = client.get("/?pick=1&category=Cocina").text
    action = re.search(r'<form id="pick"[^>]*action="([^"]+)"', body).group(1)
    fields = dict(re.findall(r'<input type="hidden" name="(\w+)" value="([^"]*)"', body))
    ids = re.findall(r'<input type="checkbox" form="pick" name="id" value="([^"]+)"', body)

    assert ids == ["b2"]                       # only the notes the filter shows
    client.post(action, data={**fields, "name": "Casa", "id": ids})

    assert find_note(cfg, "b2")[1].collections == ["Casa"]
    assert find_note(cfg, "a1")[1].collections == []


def test_a_collection_name_that_cleans_to_nothing_is_refused(setup, tmp_path):
    _, client = setup
    before = snapshot(tmp_path)

    response = client.post("/collections/add", data={"name": " .. ", "id": ["a1"]},
                           follow_redirects=False)

    assert "notice=bad-collection" in response.headers["location"]
    assert snapshot(tmp_path) == before


def test_one_note_that_is_gone_does_not_stop_the_others(setup):
    """Deleted from Obsidian between the page being drawn and the button being
    pressed. The other twenty-nine still belong in the project."""
    cfg, client = setup

    response = client.post("/collections/add",
                           data={"name": "Casa", "id": ["a1", "zzz"]},
                           follow_redirects=False)

    assert find_note(cfg, "a1")[1].collections == ["Casa"]
    assert "notice=collect-partial" in response.headers["location"]
    assert "n=1" in response.headers["location"] and "m=2" in response.headers["location"]


def test_adding_with_nothing_selected_says_so_and_writes_nothing(setup, tmp_path):
    _, client = setup
    before = snapshot(tmp_path)

    response = client.post("/collections/add", data={"name": "Casa"},
                           follow_redirects=False)

    assert "notice=nothing-picked" in response.headers["location"]
    assert snapshot(tmp_path) == before


def test_a_name_that_already_exists_keeps_the_spelling_it_has(setup):
    """Otherwise the user ends up with "Casa" and "casa" side by side, which
    is the mess this feature exists to undo."""
    cfg, client = setup
    client.post("/collections/add", data={"name": "Casa nueva", "id": ["a1"]})

    client.post("/collections/add", data={"name": "casa NUEVA", "id": ["b2"]})

    assert find_note(cfg, "b2")[1].collections == ["Casa nueva"]


def test_taking_notes_out_of_a_collection_leaves_the_other_one(setup):
    cfg, client = setup
    client.post("/collections/add", data={"name": "Casa", "id": ["a1", "b2"]})

    client.post("/collections/remove", data={"name": "Casa", "id": ["a1"]})

    assert find_note(cfg, "a1")[1].collections == []
    assert find_note(cfg, "b2")[1].collections == ["Casa"]


def test_the_note_page_adds_and_drops_one_collection(setup):
    cfg, client = setup

    client.post("/item/a1/collections", data={"add": "Casa"})
    client.post("/item/a1/collections", data={"add": "Trabajo"})
    client.post("/item/a1/collections", data={"drop": "Casa"})

    assert find_note(cfg, "a1")[1].collections == ["Trabajo"]


def test_the_user_lands_back_on_the_listing_they_picked_from(setup):
    _, client = setup

    response = client.post(
        "/collections/add",
        data={"name": "Casa", "id": ["a1"], "back": "library",
              "category": "Networking", "collection": "Vieja", "page": "3"},
        follow_redirects=False)

    where = response.headers["location"]
    assert where.startswith("/?")
    assert "category=Networking" in where and "collection=Vieja" in where
    assert "page=3" in where


def test_a_bulk_add_does_not_rebuild_the_indexes(setup, monkeypatch):
    """No index names a collection. Thirty notes joining a project must not
    rewrite the whole library thirty times."""
    cfg, client = setup
    monkeypatch.setattr("oknowledge.vault.rebuild_indexes",
                        lambda cfg, language, shelf=None:
                        pytest.fail("rebuilt the indexes"))

    client.post("/collections/add", data={"name": "Casa", "id": ["a1", "b2"]})

    assert find_note(cfg, "a1")[1].collections == ["Casa"]


def test_the_button_says_which_collection_to_leave(setup):
    """The box beside it is for joining one; the button is the one pressed,
    and it carries the collection the page is filtered by."""
    cfg, client = setup
    client.post("/collections/add", data={"name": "Casa", "id": ["a1"]})
    client.post("/collections/add", data={"name": "Trabajo", "id": ["a1"]})

    client.post("/collections/remove",
                data={"id": ["a1"], "leave": "Casa", "name": "Trabajo"})

    assert find_note(cfg, "a1")[1].collections == ["Trabajo"]


def test_the_remove_button_the_page_draws_takes_the_card_out(setup):
    cfg, client = setup
    client.post("/collections/add", data={"name": "Casa", "id": ["a1"]})
    body = client.get("/?pick=1&collection=Casa&when=2026-10").text
    button = re.search(r'formaction="([^"]+)" formnovalidate\s+name="leave" value="([^"]+)"',
                       body)
    fields = dict(re.findall(r'<input type="hidden" name="(\w+)" value="([^"]*)"', body))

    answer = client.post(button.group(1), follow_redirects=False,
                         data={**fields, "leave": button.group(2), "id": ["a1"]})

    assert find_note(cfg, "a1")[1].collections == []
    # Back to the listing it was pressed on -- the collection AND the month --
    # which the form has to carry, both of them.
    where = answer.headers["location"]
    assert "collection=Casa" in where and "when=2026-10" in where


def test_one_note_gets_a_sentence_and_two_get_a_count(setup):
    """"1 notas quedaron en la colección" is a sentence a program writes and
    a person never does."""
    _, client = setup

    one = client.post("/collections/add", data={"name": "Casa", "id": ["a1"]},
                      follow_redirects=False)
    assert "notice=collected-one" in one.headers["location"]

    two = client.post("/collections/add", data={"name": "Trabajo", "id": ["a1", "b2"]},
                      follow_redirects=False)
    assert "notice=collected&" in two.headers["location"]

    back = client.post("/collections/remove", data={"name": "Casa", "id": ["a1"]},
                       follow_redirects=False)
    assert "notice=uncollected-one" in back.headers["location"]

    both = client.post("/collections/remove", data={"name": "Trabajo", "id": ["a1", "b2"]},
                       follow_redirects=False)
    assert "notice=uncollected&" in both.headers["location"]


def test_the_note_page_draws_the_two_buttons_it_promises(setup):
    """Posted out of the rendered page, both ways round: the chip that leaves
    a collection and the box that joins one are the only way in or out for a
    single note."""
    cfg, client = setup
    body = client.get("/item/a1").text
    box = re.search(r'<form action="([^"]*/collections)" method="post" class="field">'
                    r'.*?<input id="field-collection" name="(\w+)"', body, re.S)
    assert box, "the note drew no box to join a collection with"

    client.post(box.group(1), data={box.group(2): "Casa"})

    chip = re.search(r'<form action="([^"]+)" method="post">\s*<button[^>]*'
                     r'name="(\w+)" value="([^"]*)"', client.get("/item/a1").text)
    assert chip, "the note drew no way out of the collection"
    assert chip.group(3) == "Casa"
    client.post(chip.group(1), data={chip.group(2): chip.group(3)})

    assert find_note(cfg, "a1")[1].collections == []


def test_picking_a_provider_saves_it(setup, config_path):
    _, client = setup
    client.post("/settings", data={"chain": ["api"], "api_provider": "groq"})
    saved = tomllib.loads(config_path.read_text(encoding="utf-8"))
    assert saved["ai"]["api"]["provider"] == "groq"


def test_a_provider_nobody_knows_does_not_replace_the_one_that_is_saved(setup,
                                                                       config_path):
    """The file may name a gateway of your own, by hand. This form must not be
    the thing that replaces it with a guess."""
    _, client = setup
    client.post("/settings", data={"chain": ["api"], "api_provider": "groq"})
    client.post("/settings", data={"chain": ["api"], "api_provider": "my-own-thing"})
    saved = tomllib.loads(config_path.read_text(encoding="utf-8"))
    assert saved["ai"]["api"]["provider"] == "groq"


# --- a safe method must not write (the GET that saved a card) ---------------

VAULT_WRITERS = ("write_note", "write_index", "rebuild_indexes", "update_note",
                 "delete_note", "download_cover", "save_card", "add_task")


def reachable_source(fn, seen=None):
    """A handler's source plus the source of the helpers it closes over.

    Every route of this app is a closure inside create_app(), so the
    helpers it can reach are its free variables -- which is how a GET
    reaches a writer without naming one itself.
    """
    import inspect

    seen = seen if seen is not None else set()
    if fn in seen or not callable(fn):
        return ""
    seen.add(fn)
    try:
        source = inspect.getsource(fn)
    except (OSError, TypeError):
        return ""
    for name, cell in zip(getattr(fn.__code__, "co_freevars", ()),
                          fn.__closure__ or ()):
        try:
            value = cell.cell_contents
        except ValueError:                       # a cell still being filled
            continue
        if inspect.isfunction(value):
            source += reachable_source(value, seen)
    return source


def test_no_safe_method_reaches_a_vault_writer(setup):
    """A GET that writes a note is a note anybody can make the browser
    write with an `<img src=...>`: the origin check looks only at the
    unsafe methods, by design, so a safe method must not write.

    This is the property, not a list of the routes we happen to have: the
    shortcut that saved a card from GET /ocio/buscar passed every other
    test in this file.
    """
    from oknowledge.web.app import SAFE_METHODS

    _, client = setup
    checked = 0
    for route in client.app.routes:
        methods = getattr(route, "methods", set())
        if not methods or methods - SAFE_METHODS:
            continue
        checked += 1
        source = reachable_source(route.endpoint)
        for writer in VAULT_WRITERS:
            assert f"{writer}(" not in source, \
                f"{route.path} can reach {writer}()"
    assert checked > 5, "no safe routes found: this test is not looking at the app"
