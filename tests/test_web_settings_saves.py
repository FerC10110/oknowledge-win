"""Settings saves itself, one pane at a time (spec §3.1): a field that does
not arrive keeps its value, every write answers JSON to a script, and the
interface language asks for a reload."""

import pytest
from fastapi.testclient import TestClient

from oknowledge.ai.fake import FakeEngine
from oknowledge.config import Config, load
from oknowledge.model import Note
from oknowledge.vault import rebuild_indexes, write_note
from oknowledge.web import app as module
from oknowledge.web.app import create_app

JSON = {"Accept": "application/json"}


@pytest.fixture(autouse=True)
def state_tree(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr("oknowledge.web.app.CONFIG_PATH", tmp_path / "config" / "config.toml")


@pytest.fixture
def client(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    for id in ("a1", "b2"):
        write_note(cfg, Note(id=id, url=f"https://e.com/{id}", title=id, category="Networking",
                             tags=[], type="article", source="e.com", saved="2026-10-03",
                             summary="s"), "es")
    rebuild_indexes(cfg, "es")
    return TestClient(create_app(cfg))


def saved(tmp_path):
    return load(tmp_path / "config" / "config.toml")


def listed(names):
    def build(name, cfg):
        found = FakeEngine([])
        found.models = lambda: list(names)
        return found
    return build


# --- one pane at a time ---------------------------------------------------------

def test_a_pane_saves_only_its_own_fields(client, tmp_path):
    client.post("/settings", data={"chain": ["opencode"], "opencode_model": "a/one",
                                   "tab": "motores"})
    client.post("/settings", data={"language": "en", "ui_language": "en",
                                   "default_content": "summary", "mentions": "all",
                                   "batch": "7", "tab": "idioma"})
    cfg = saved(tmp_path)
    assert cfg.engines["opencode"]["model"] == "a/one"
    assert cfg.chain == ("opencode",)
    assert (cfg.default_content, cfg.mentions, cfg.batch) == ("summary", "all", 7)


def test_an_empty_model_box_still_clears_it(client, tmp_path):
    client.post("/settings", data={"opencode_model": "a/one", "tab": "motores"})
    client.post("/settings", data={"opencode_model": "", "tab": "motores"})
    assert "model" not in saved(tmp_path).engines.get("opencode", {})


def test_a_pane_answers_a_script_with_nothing_to_say(client):
    answer = client.post("/settings", data={"default_content": "summary", "tab": "idioma"},
                         headers=JSON)
    assert answer.json() == {"ok": True, "notice": ""}


def test_changing_the_interface_language_asks_for_a_reload(client):
    first = client.post("/settings", data={"ui_language": "es", "tab": "idioma"}, headers=JSON)
    assert first.json() == {"ok": True, "notice": "", "reload": True}
    again = client.post("/settings", data={"ui_language": "es", "tab": "idioma"}, headers=JSON)
    assert "reload" not in again.json()


def test_a_form_goes_back_to_its_pane(client):
    answer = client.post("/settings", data={"ui_language": "es", "tab": "idioma"},
                         follow_redirects=False)
    assert answer.headers["location"] == "/settings?tab=idioma&notice=saved"


@pytest.mark.parametrize("tab", ["", "nope"])
def test_without_a_known_tab_it_goes_to_the_page(client, tab):
    answer = client.post("/settings", data={"batch": "3", "tab": tab}, follow_redirects=False)
    assert answer.headers["location"] == "/settings?notice=saved"


def test_a_config_that_cannot_be_written_is_a_500_to_a_script(client, monkeypatch):
    def boom(*args, **kwargs):
        raise OSError(13, "Permission denied")
    monkeypatch.setattr("oknowledge.web.app.save_config", boom)
    answer = client.post("/settings", data={"batch": "3", "tab": "idioma"}, headers=JSON)
    assert answer.status_code == 500
    assert "could not be saved" in answer.json()["error"]


def test_a_shared_language_that_cannot_be_written_is_said(client, monkeypatch):
    def boom(language):
        raise PermissionError(13, "read-only")
    monkeypatch.setattr("oknowledge.web.app.set_ui_language", boom)
    body = client.post("/settings", data={"ui_language": "es", "tab": "idioma"},
                       headers=JSON).json()
    assert body["ok"] is True and "interface language" in body["notice"]


# --- the action buttons -----------------------------------------------------------

def test_finding_models_answers_a_script_and_a_form_goes_to_engines(client, monkeypatch):
    monkeypatch.setattr(module, "build_engine", listed(["a/one", "b/two"]))
    body = client.post("/settings/models/opencode", headers=JSON).json()
    assert body == {"ok": True, "notice": "2 models found. They are in the list beside each box."}
    location = client.post("/settings/models/opencode", follow_redirects=False).headers["location"]
    assert location == "/settings?tab=motores&notice=models-found&n=2"


def test_making_the_env_answers_a_script(client):
    first = client.post("/settings/env", data={"provider": "groq"}, headers=JSON)
    assert first.status_code == 200 and first.json()["ok"] is True
    again = client.post("/settings/env", data={"provider": "groq"}, headers=JSON)
    assert again.status_code == 409


def test_an_env_that_cannot_be_made_is_a_500(client, monkeypatch):
    monkeypatch.setattr("oknowledge.web.app.env.create", lambda *a, **k: False)
    assert client.post("/settings/env", data={"provider": "groq"}, headers=JSON).status_code == 500


def test_renaming_answers_a_script_and_a_form_goes_to_categories(client):
    body = client.post("/categories/rename", data={"old": "Networking", "new": "Redes"},
                       headers=JSON).json()
    assert body == {"ok": True, "notice": "2 notes moved."}
    location = client.post("/categories/rename", data={"old": "Redes", "new": "Seguridad"},
                           follow_redirects=False).headers["location"]
    assert location == "/settings?tab=categorias&notice=renamed&n=2&m=0"


def test_a_refused_rename_is_a_400_to_a_script(client):
    answer = client.post("/categories/rename", data={"old": "Networking", "new": "a/b"},
                         headers=JSON)
    assert answer.status_code == 400 and "cannot be used" in answer.json()["error"]


# --- final fix pass: the page's ✕ waits for the saves, in node ----------------------------

CLOSE_HARNESS = r"""
const source = require("fs").readFileSync(process.argv[2], "utf8");
const on = {};
const listen = (name) => (type, fn) => { on[name + ":" + type] = fn; };
const form = { addEventListener: listen("form"), getAttribute: () => "/settings/motores",
               querySelector: () => null };
const link = { href: "http://x/", getAttribute: () => "/" };
const root = {
  addEventListener: listen("root"),
  querySelector: () => null,
  querySelectorAll: (sel) => (sel === "form[data-settings]" ? [form] : []),
};
global.window = global;
global.location = { href: "/settings", pathname: "/settings" };
global.history = { replaceState() {} };
global.FormData = function () { return { model: "nuevo" }; };
global.document = {
  body: { dataset: {} }, activeElement: null,
  getElementById: () => null,
  querySelector: (sel) => (sel === ".settings-body[data-settings-root]" ? root : null),
};
let answer = null;
window.oknowledge = { toast() {}, send: () => new Promise((r) => { answer = r; }) };
eval(source);
const out = {};
(async () => {
  on["form:change"]();                                 // the blur of the click saves
  const event = { button: 0, metaKey: false, ctrlKey: false, shiftKey: false, altKey: false,
                  target: { closest: (sel) => (sel === "a[data-close]" ? link : null) },
                  defaultPrevented: false, preventDefault() { this.defaultPrevented = true; } };
  on["root:click"](event);
  await new Promise((r) => setTimeout(r, 10));
  out.whileSaving = [event.defaultPrevented, location.href];
  answer({ notice: "" });
  await new Promise((r) => setTimeout(r, 10));
  out.saved = location.href;
  console.log(JSON.stringify(out));
  process.exit(0);
})();
"""


@pytest.fixture(scope="module")
def closing(tmp_path_factory):
    import json
    import shutil
    import subprocess
    from pathlib import Path
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = (Path(__file__).resolve().parent.parent / "src" / "oknowledge" / "web" / "static"
              / "settings.js")
    harness = tmp_path_factory.mktemp("closing") / "harness.js"
    harness.write_text(CLOSE_HARNESS, encoding="utf-8")
    done = subprocess.run([node, str(harness), str(script)], capture_output=True, text=True,
                          timeout=30, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_the_pages_close_waits_for_a_save_still_out(closing):
    assert closing["whileSaving"] == [True, "/settings"]
    assert closing["saved"] == "/"
