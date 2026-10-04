"""The web routes that change the vault.

These are the only requests in the project that can destroy a user's work, so
most of this file is about what must NOT happen: a cross-site POST that
deletes a note, a category name that walks out of the vault, a browser left
hanging while an engine thinks, a settings save that wipes the shared
preference file other plugins write to.
"""

import json
import tomllib

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.vault import (
    find_note, index_path, rebuild_indexes, trash_dir, write_note,
)
from oknowledge.web.app import create_app

WRITE_ROUTES = [
    ("/item/a1/category", {"category": "Redes"}),
    ("/item/a1/tags", {"tags": "vpn"}),
    ("/item/a1/delete", {}),
    ("/item/a1/reprocess", {"engine": "ollama"}),
    ("/categories/rename", {"old": "Networking", "new": "Redes"}),
    ("/settings", {"chain": ["ollama"], "language": "en",
                   "default_content": "summary", "ui_language": "es"}),
]


def note(id, title, category, tags=("x",)):
    return Note(id=id, url=f"https://e.com/{id}", title=title, category=category,
                tags=list(tags), type="article", source="e.com", saved="2026-10-03",
                summary=f"Resumen de {title}.", points=[])


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


@pytest.fixture
def config_path(tmp_path, monkeypatch):
    """Nothing here may touch the real ~/.config/oknowledge/config.toml."""
    path = tmp_path / "config" / "config.toml"
    monkeypatch.setattr("oknowledge.web.app.CONFIG_PATH", path)
    return path


@pytest.fixture
def setup(tmp_path, config_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    write_note(cfg, note("a1", "WireGuard", "Networking"), "es")
    write_note(cfg, note("b2", "Masa madre", "Cocina"), "es")
    rebuild_indexes(cfg, "es")
    return cfg, TestClient(create_app(cfg))


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
    assert calls == [("https://e.com/a1", {"engine": "ollama", "reprocess": True})]


def test_reprocess_without_an_engine_lets_the_chain_decide(setup, monkeypatch):
    _, client = setup
    calls = []
    monkeypatch.setattr("oknowledge.web.app.add_link",
                        lambda cfg, url, **kwargs: calls.append(kwargs))
    client.post("/item/a1/reprocess", data={"engine": ""})
    assert calls == [{"engine": None, "reprocess": True}]


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


def test_settings_warns_that_saving_rewrites_the_file(setup):
    _, client = setup
    body = client.get("/settings").text
    assert "comment" in body.lower()
    assert "config.toml.bak" in body


def test_saving_settings_writes_the_config_and_the_shared_language(
        setup, tmp_path, config_path, monkeypatch):
    _, client = setup
    shared = tmp_path / "plugin-language.json"
    monkeypatch.setattr("oknowledge.i18n.SHARED_FILE", shared)

    client.post("/settings", data={
        "chain": ["ollama", "opencode"], "language": "en",
        "default_content": "summary", "ui_language": "es",
    })

    saved = tomllib.loads(config_path.read_text(encoding="utf-8"))
    assert saved["ai"]["chain"] == ["ollama", "opencode"]
    assert saved["ai"]["language"] == "en"
    assert saved["default_content"] == "summary"
    assert json.loads(shared.read_text(encoding="utf-8"))["language"] == "es"


def test_saving_settings_keeps_the_rest_of_the_shared_file(setup, tmp_path, monkeypatch):
    _, client = setup
    shared = tmp_path / "plugin-language.json"
    shared.write_text(json.dumps({"theme": "nord"}), encoding="utf-8")
    monkeypatch.setattr("oknowledge.i18n.SHARED_FILE", shared)

    client.post("/settings", data={"chain": ["ollama"], "ui_language": "es"})

    assert json.loads(shared.read_text(encoding="utf-8")) == {
        "theme": "nord", "language": "es"}


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
