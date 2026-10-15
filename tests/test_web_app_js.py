"""app.js (spec §1-§4): the one toast, the menus, the two modals and the keys,
on every page. The key rules run in node over a fake page (Review Focus 3:
nothing typed into a field or a modal ever moves the list or the page)."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.model import Note
from oknowledge.vault import note_path, rebuild_indexes, write_note
from oknowledge.web.app import create_app

STATIC = Path(__file__).resolve().parent.parent / "src" / "oknowledge" / "web" / "static"
APP = STATIC / "app.js"


@pytest.fixture
def client(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    write_note(cfg, Note(id="a1", url="https://e.com/a1", title="A", category="Redes", tags=[],
                         type="article", source="e.com", saved="2026-10-03", summary="s"), "es")
    idea = new_idea("Una idea.", "Idea", "2026-10-13", "2026-10-13T00:00:00.000001+00:00")
    write_note(cfg, idea, "es", path=note_path(cfg, idea, shelf=cfg.ideas))
    for shelf in (cfg.links, cfg.ideas):
        rebuild_indexes(cfg, "es", shelf=shelf)
    client = TestClient(create_app(cfg))
    client.idea = idea.id
    return client


def between(text, start, end):
    head = text.index(start)
    return text[head:text.index(end, head)]


# --- the page -------------------------------------------------------------------

@pytest.mark.parametrize("path", ["/", "/ocio", "/ideas", "/settings", "/retry", "/import", "idea"])
def test_every_page_loads_app_js_before_the_others(client, path):
    body = client.get(f"/ideas/{client.idea}" if path == "idea" else path).text
    first = body.index('<script src="/static/app.js" defer></script>')
    for name in re.findall(r'<script src="/static/([a-z]+)\.js" defer></script>', body):
        if name != "app":
            assert first < body.index(f'<script src="/static/{name}.js" defer></script>'), name


def test_the_keys_help_is_on_every_page_with_its_eleven_rows(client):
    body = client.get("/").text
    found = re.search(r'<dialog id="keys-help" class="modal keys".*?</dialog>', body, re.S).group(0)
    assert found.count("<dt>") == 11
    for text in ("Keyboard shortcuts", "Search or paste a link", "Library · Leisure · Ideas",
                 "Open the original link", "Close / deselect"):
        assert text in found
    assert '<kbd class="mono">1</kbd><kbd class="mono">2</kbd><kbd class="mono">3</kbd>' in found
    assert '<kbd class="mono">esc</kbd>' in found


def test_the_body_carries_the_undo_word(client):
    assert 'data-undo="Undo"' in client.get("/").text


@pytest.mark.parametrize("path", ["/", "/ocio", "/ideas"])
def test_the_unified_field_answers_to_the_slash(client, path):
    assert re.search(r'<input type="text" name="q" id="field-q"[^>]*data-slash', client.get(path).text)


def test_on_an_idea_the_slash_goes_to_the_links_search(client):
    assert re.search(r'id="links-q"[^>]*data-slash', client.get(f"/ideas/{client.idea}").text)


# --- the source --------------------------------------------------------------------

def test_the_toast_is_one_element_timed_here():
    text = APP.read_text(encoding="utf-8")
    body = between(text, "function toast", "function send")
    assert "replaceChildren" in body and "5000" in body and "2200" in body
    assert 'getElementById("toast")' in text


def test_the_server_toast_is_taken_over_and_its_undo_sent_as_json():
    text = APP.read_text(encoding="utf-8")
    assert "form.toast-undo" in text and '"/undo/"' in text
    assert 'Accept: "application/json"' in text


def test_menus_close_each_other_and_modals_open_with_show_modal():
    text = APP.read_text(encoding="utf-8")
    assert '"toggle"' in text and "details.menu" in text
    assert "showModal" in text and "[data-modal]" in text and '"keys-help"' in text


def test_shell_and_autosave_no_longer_draw_their_own_toast():
    for name in ("shell.js", "autosave.js"):
        assert 'className = "notice toast"' not in (STATIC / name).read_text(encoding="utf-8"), name
    shell = (STATIC / "shell.js").read_text(encoding="utf-8")
    assert 'addEventListener("toggle"' not in shell
    autosave = (STATIC / "autosave.js").read_text(encoding="utf-8")
    assert not re.search(r"^\s*window\.oknowledge = \{", autosave, re.M)   # never replaced
    assert "window.oknowledge || (window.oknowledge = {})" in autosave


# --- the key rules, in node ------------------------------------------------------------

HARNESS = r"""
const source = require("fs").readFileSync(process.argv[2], "utf8");
const handlers = {};
const out = {};
let dialog = null;
const field = (type) => ({ tagName: "INPUT", type, isContentEditable: false, closest: () => null,
                           blur() { out.blurred = (out.blurred || 0) + 1; } });
global.window = global;
global.location = { href: "/", pathname: "/", reload() {} };
global.document = {
  body: { dataset: {}, tagName: "BODY" },
  addEventListener: (type, fn) => { (handlers[type] = handlers[type] || []).push(fn); },
  getElementById: () => null,
  querySelector: (sel) => (sel === "dialog[open]" ? dialog : null),
  querySelectorAll: () => [],
};
document.activeElement = document.body;
eval(source);
const calls = [];
window.oknowledge.keys.j = () => { calls.push("j"); };
window.oknowledge.keys.Escape = () => { calls.push("esc"); };
function press(key, extra) {
  const event = Object.assign({ key, defaultPrevented: false, isComposing: false, metaKey: false,
    ctrlKey: false, altKey: false, shiftKey: false,
    preventDefault() { this.defaultPrevented = true; } }, extra || {});
  (handlers.keydown || []).forEach((fn) => fn(event));
  return event;
}
press("j"); out.plain = calls.slice();
press("j", { ctrlKey: true }); press("j", { metaKey: true }); press("j", { altKey: true });
out.modifiers = calls.slice();
document.activeElement = field("text");
press("j"); press("1"); out.inField = [calls.slice(), location.href];
press("Escape"); out.escInField = [out.blurred, calls.slice()];
document.activeElement = field("checkbox");
press("j"); out.onCheckbox = calls.slice();
dialog = { id: "settings-modal", close() {} };
document.activeElement = field("text");
press("j"); press("1"); press("x");
document.activeElement = document.body;
press("j"); press("2"); out.inModal = [calls.slice(), location.href];
dialog = { id: "keys-help", close() { out.helpClosed = true; } };
press("?");
dialog = null;
document.activeElement = document.body;
press("Escape"); out.escClears = calls.slice();
press("3"); out.section = location.href;
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def keys(tmp_path_factory):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    harness = tmp_path_factory.mktemp("keys") / "harness.js"
    harness.write_text(HARNESS, encoding="utf-8")
    done = subprocess.run([node, str(harness), str(APP)], capture_output=True, text=True,
                          timeout=30, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_a_key_the_screen_registered_runs(keys):
    assert keys["plain"] == ["j"]


def test_cmd_ctrl_or_alt_mean_nothing(keys):
    assert keys["modifiers"] == ["j"]


def test_in_a_field_keys_are_text_and_esc_only_blurs(keys):
    assert keys["inField"] == [["j"], "/"]
    assert keys["escInField"] == [1, ["j"]]


def test_a_checkbox_is_not_a_field(keys):
    assert keys["onCheckbox"] == ["j", "j"]


def test_with_a_modal_open_no_key_reaches_the_page(keys):
    assert keys["inModal"] == [["j", "j"], "/"]
    assert keys["helpClosed"] is True


def test_esc_with_nothing_else_to_do_clears_the_selection(keys):
    assert keys["escClears"] == ["j", "j", "esc"]


def test_the_number_keys_go_to_the_sections(keys):
    assert keys["section"] == "/ideas"


# --- a failed Deshacer, in node -----------------------------------------------------------

UNDO_HARNESS = r"""
const source = require("fs").readFileSync(process.argv[2], "utf8");
const out = { toasts: [], uncaught: [] };
process.on("unhandledRejection", (e) => { out.uncaught.push(String(e && e.message)); });
const toastEl = {
  hidden: true, classList: { add() {}, remove() {} },
  replaceChildren(...kids) { if (kids.length) out.toasts.push(kids[0].textContent); },
  appendChild() {}, querySelector: () => null,
};
global.window = global;
global.location = { href: "/", pathname: "/", reload() { out.reloaded = true; } };
global.FormData = function () {};
global.document = {
  body: { dataset: { saveFailed: "No se pudo guardar" }, tagName: "BODY", appendChild() {} },
  addEventListener() {},
  getElementById: (id) => (id === "toast" ? toastEl : null),
  createElement: () => ({ textContent: "", className: "", addEventListener() {} }),
  querySelector: () => null,
  querySelectorAll: () => [],
};
eval(source);
const ok = window.oknowledge;
(async () => {
  global.fetch = () => Promise.reject(new TypeError("Failed to fetch"));
  await ok.send("/x").catch((e) => { out.sendError = [e.message, e.status === undefined]; });
  await ok.undo("t1");
  out.offline = out.toasts.slice();
  global.fetch = () => Promise.resolve({ ok: true, status: 200,
    json: () => Promise.resolve({ ok: true, notice: "Restaurado", restored: ["a1"] }) });
  ok.undo("t2", () => { throw new Error("a screen bug"); });   // not awaited: its error is the page's
  await new Promise((r) => setTimeout(r, 20));
  out.screenBug = out.toasts.slice(out.offline.length);
  console.log(JSON.stringify(out));
  process.exit(0);
})();
"""


@pytest.fixture(scope="module")
def failed_undo(tmp_path_factory):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    harness = tmp_path_factory.mktemp("undo") / "harness.js"
    harness.write_text(UNDO_HARNESS, encoding="utf-8")
    done = subprocess.run([node, str(harness), str(APP)], capture_output=True, text=True,
                          timeout=30, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_no_network_is_the_pages_own_words_not_the_browsers(failed_undo):
    assert failed_undo["sendError"] == ["No se pudo guardar", True]
    assert failed_undo["offline"] == ["No se pudo guardar"]


def test_a_screen_error_after_the_undo_is_not_toasted(failed_undo):
    assert failed_undo["screenBug"] == ["Restaurado"]
    assert failed_undo["uncaught"] == ["a screen bug"]


def test_the_keys_help_opens_on_its_grid_and_not_on_the_close_button(client):
    # Handoff 09: opened with "?", no focus ring sits on the ✕ (Task 12).
    body = client.get("/").text
    found = re.search(r'<dialog id="keys-help".*?</dialog>', body, re.S).group(0)
    assert '<dl class="keys-grid" tabindex="-1" autofocus>' in found


# --- final fix pass: the toast above a modal, in node ------------------------------------

TOP_HARNESS = r"""
const source = require("fs").readFileSync(process.argv[2], "utf8");
const log = [];
const handlers = {};
let open = false;
const holder = (name) => ({ name, appendChild(kid) {
  open = false;                                      // a popover moved is hidden
  kid.parentNode = this; log.push("into " + name); } });
const body = Object.assign(holder("body"), { dataset: {}, tagName: "BODY" });
const dialog = Object.assign(holder("dialog"), { open: false,
  showModal() { this.open = true; log.push("modal"); }, close() { this.open = false; },
  contains(kid) { return kid.parentNode === this; } });
const toastEl = {
  hidden: true, popover: null, parentNode: body, classList: { add() {}, remove() {} },
  replaceChildren() {}, appendChild() {}, querySelector: () => null,
  showPopover() { if (open) throw new Error("already open"); open = true; log.push("show"); },
  hidePopover() { if (!open) throw new Error("not open"); open = false; log.push("hide"); },
  matches: (sel) => sel === ":popover-open" && open,
};
global.window = global;
global.location = { href: "/", pathname: "/", reload() {} };
global.document = {
  body,
  addEventListener: (type, fn) => { (handlers[type] = handlers[type] || []).push(fn); },
  getElementById: (id) => (id === "toast" ? toastEl : null),
  createElement: () => ({ textContent: "", className: "", addEventListener() {} }),
  querySelector: (sel) => (sel === "dialog[open]" && dialog.open ? dialog : null),
  querySelectorAll: () => [],
};
eval(source);
const ok = window.oknowledge;
const out = {};
ok.toast("uno");
out.first = [toastEl.popover, log.slice()];
ok.toast("dos");
out.second = log.slice();
log.length = 0;
ok.openModal(dialog);
out.modal = [log.slice(), toastEl.parentNode.name];
log.length = 0;
ok.toast("desde el modal");
out.inModal = [log.slice(), toastEl.parentNode.name];
log.length = 0;
dialog.close();
(handlers.close || []).forEach((fn) => fn({ target: dialog }));
out.closed = [log.slice(), toastEl.parentNode.name];
console.log(JSON.stringify(out));
process.exit(0);
"""


@pytest.fixture(scope="module")
def top(tmp_path_factory):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    harness = tmp_path_factory.mktemp("top") / "harness.js"
    harness.write_text(TOP_HARNESS, encoding="utf-8")
    done = subprocess.run([node, str(harness), str(APP)], capture_output=True, text=True,
                          timeout=30, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_the_toast_is_shown_in_the_top_layer(top):
    assert top["first"] == ["manual", ["show"]]


def test_a_new_toast_goes_on_top_again(top):
    assert top["second"] == ["show", "hide", "show"]


def test_a_modal_opened_under_a_toast_does_not_cover_it(top):
    # Inside the modal: drawn above its backdrop and not inert under it.
    assert top["modal"] == [["modal", "into dialog", "show"], "dialog"]


def test_a_toast_said_from_the_modal_is_inside_it(top):
    assert top["inModal"] == [["hide", "show"], "dialog"]


def test_the_toast_goes_back_to_the_page_when_the_modal_closes(top):
    assert top["closed"] == [["into body", "show"], "body"]


def test_without_javascript_the_toast_is_no_popover(client):
    # A [popover] the server drew would stay hidden with no script to show it.
    toast = re.search(r'<div id="toast"[^>]*>', client.get("/").text).group(0)
    assert "popover" not in toast


def test_the_settings_modal_puts_the_toast_back_after_drawing_its_content():
    # modal.innerHTML / replaceChildren take out a toast that sits inside it.
    text = (STATIC / "settings.js").read_text(encoding="utf-8")
    opening = between(text, "ok.openSettings = function", "ok.bindSettings")
    assert opening.count("raiseToast();") >= 1
    assert "raiseToast();" in between(text, "function failed", "ok.openSettings")
    loaded = between(opening, "modal.innerHTML = html;", ".catch")
    assert "raiseToast();" in loaded
