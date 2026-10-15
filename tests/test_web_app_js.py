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
global.addEventListener = () => {};
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
global.addEventListener = () => {};
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
global.addEventListener = () => {};
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


# --- delivery 4: layers (docs/2026-10-15-rediseno-celular-design.md §6.3, §8) --------------

LAYERS_HARNESS = r"""
const source = require("fs").readFileSync(process.argv[2], "utf8");
const out = {};
const win = {};
const handlers = {};
global.window = global;
global.addEventListener = (type, fn) => { (win[type] = win[type] || []).push(fn); };
// A history of same-document entries: back() pops one and fires popstate later.
const entries = [{ state: null, url: "/" }];
let at = 0;
global.location = { get href() { return "http://x" + entries[at].url; }, pathname: "/",
                    reload() { out.reloaded = true; } };
global.history = {
  get state() { return entries[at].state; },
  pushState(state, _, url) { entries.splice(at + 1); entries.push({ state, url: url.replace("http://x", "") }); at++; },
  replaceState(state, _, url) { entries[at] = { state, url: url.replace("http://x", "") }; },
  back() {
    if (at === 0) { out.leftSite = true; return; }
    at--;
    setTimeout(() => (win.popstate || []).forEach((fn) => fn({ state: entries[at].state })), 0);
  },
};
let narrow = true;
global.matchMedia = () => ({ get matches() { return narrow; } });
const modalOn = {};
const modal = {
  id: "settings-modal", open: false,
  showModal() { this.open = true; },
  close() { if (!this.open) return; this.open = false; (modalOn.close || []).forEach((fn) => fn()); },
  addEventListener: (type, fn) => { (modalOn[type] = modalOn[type] || []).push(fn); },
};
global.document = {
  body: { dataset: {}, tagName: "BODY" },
  addEventListener: (type, fn) => { (handlers[type] = handlers[type] || []).push(fn); },
  getElementById: (id) => (id === "settings-modal" ? modal : null),
  querySelector: () => null,
  querySelectorAll: () => [],
};
document.activeElement = document.body;
eval(source);
const ok = window.oknowledge;
const tick = () => new Promise((r) => setTimeout(r, 5));
function press(key) {
  const event = { key, defaultPrevented: false, isComposing: false, metaKey: false, ctrlKey: false,
                  altKey: false, preventDefault() { this.defaultPrevented = true; } };
  (handlers.keydown || []).forEach((fn) => fn(event));
}
(async () => {
  out.phone = ok.phone();
  // 1. A panel layer: its own entry; back closes it and the URL is the list's.
  const closed = [];
  out.opened = ok.layers.open("panel", (how) => closed.push(how), "/?sel=a1");
  out.urlOpen = entries[at].url;
  out.second = ok.layers.open("settings", () => closed.push("settings"));   // one at a time
  history.back();
  await tick();
  out.afterBack = [closed.slice(), ok.layers.top(), entries[at].url];
  // 2. Ajustes on the phone: ✕ (the dialog's close) goes back once.
  ok.openModal(modal);
  out.settingsPushed = [modal.open, ok.layers.top(), entries.length, at];
  modal.close();
  await ok.layers.settled();
  await tick();
  out.closeWentBack = [ok.layers.top(), at, out.leftSite === true];
  // ... and the browser's back closes the dialog.
  ok.openModal(modal);
  history.back();
  await tick();
  out.backClosedModal = [modal.open, ok.layers.top(), at];
  // 3. A layer the page started with (a reload with sel=): closed in place.
  const adopted = [];
  ok.layers.adopt("panel", (how) => adopted.push(how));
  const where = at;
  await ok.layers.close();
  out.adoptedClose = [adopted, at === where, out.leftSite === true];
  // ... unless the entry is ours (a forward, a reload of our entry): then back.
  ok.layers.open("panel", (how) => closed.push("p:" + how), "/?sel=b2");
  history.back(); await tick();
  history.state;                                   // the list's entry again
  at++;                                            // forward, by hand
  ok.layers.adopt("panel", (how) => closed.push("fwd:" + how));
  await ok.layers.close();
  await tick();
  out.adoptedOwnEntry = [closed[closed.length - 1], at];
  // 4. Esc: a field being typed in is blurred first; the next Esc closes.
  ok.layers.open("panel", (how) => closed.push("esc:" + how), "/?sel=a1");
  document.activeElement = { tagName: "INPUT", type: "text", isContentEditable: false, closest: () => null,
                             blur() { out.blurred = true; document.activeElement = document.body; } };
  press("Escape");
  await tick();
  out.escInField = [out.blurred === true, ok.layers.top()];
  press("Escape");
  await tick();
  out.escClosesLayer = [ok.layers.top(), closed[closed.length - 1]];
  // 4b. Fix round 1: Ajustes is refused over a panel layer, and a second
  // close() before the first back() lands goes back only once.
  ok.layers.open("panel", (how) => closed.push("twice:" + how), "/?sel=c3");
  const pushedAt = at, count = entries.length;
  out.refusedOverPanel = [ok.openModal(modal), modal.open, entries.length === count, ok.layers.top()];
  const first = ok.layers.close(), again = ok.layers.close();
  await first; await again; await tick();
  out.closeTwice = [at === pushedAt - 1, out.leftSite === true, ok.layers.top(),
                    closed.filter((c) => c.startsWith("twice:"))];
  // 5. A desktop: Ajustes makes no entry.
  narrow = false;
  const length = entries.length;
  ok.openModal(modal);
  out.desktop = [modal.open, entries.length === length, ok.layers.top()];
  console.log(JSON.stringify(out));
  process.exit(0);
})();
"""


@pytest.fixture(scope="module")
def layers(tmp_path_factory):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    harness = tmp_path_factory.mktemp("layers") / "harness.js"
    harness.write_text(LAYERS_HARNESS, encoding="utf-8")
    done = subprocess.run([node, str(harness), str(APP)], capture_output=True, text=True,
                          timeout=30, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_the_phone_is_one_breakpoint(layers):
    assert layers["phone"] is True
    assert 'matchMedia("(max-width: 60rem)")' in APP.read_text(encoding="utf-8")


def test_a_layer_has_its_entry_and_back_closes_it(layers):
    assert layers["opened"] is True and layers["urlOpen"] == "/?sel=a1"
    assert layers["afterBack"] == [["back"], "", "/"]


def test_one_layer_at_a_time(layers):
    assert layers["second"] is False


def test_settings_on_the_phone_is_a_layer_closed_by_x_or_back(layers):
    """Review Focus 3: ✕ goes back exactly once, and never off the site."""
    assert layers["settingsPushed"] == [True, "settings", 2, 1]
    assert layers["closeWentBack"] == ["", 0, False]
    assert layers["backClosedModal"] == [False, "", 0]


def test_a_layer_the_page_started_with_closes_in_place(layers):
    assert layers["adoptedClose"] == [["close"], True, False]


def test_a_layer_on_its_own_entry_goes_back_even_when_adopted(layers):
    assert layers["adoptedOwnEntry"] == ["fwd:back", 0]


def test_esc_blurs_a_field_before_it_closes_the_layer(layers):
    assert layers["escInField"] == [True, "panel"]
    assert layers["escClosesLayer"] == ["", "esc:back"]


def test_a_desktop_makes_no_history_for_settings(layers):
    assert layers["desktop"] == [True, True, ""]


def test_ajustes_is_refused_over_a_panel_layer(layers):
    assert layers["refusedOverPanel"] == [False, False, True, "panel"]


def test_closing_twice_goes_back_only_once(layers):
    assert layers["closeTwice"] == [True, False, "", ["twice:back"]]


# A reload on a layer's entry (pull to refresh), and a page back from the bfcache.
RELOAD_HARNESS = r"""
const source = require("fs").readFileSync(process.argv[2], "utf8");
const c = JSON.parse(process.argv[3]);   // {adopt, state, url, mode}
const out = {};
const win = {}, handlers = {};
global.window = global;
global.addEventListener = (type, fn) => { (win[type] = win[type] || []).push(fn); };
const entries = [{ state: null, url: "/ocio" }, { state: null, url: "/" },
                 { state: c.state, url: c.url }];
let at = 2;
let popOnBack = true;
global.location = { get href() { return "http://x" + entries[at].url; }, pathname: "/", reload() {} };
global.history = {
  get length() { return entries.length; },
  get state() { return entries[at].state; },
  pushState(state, _, url) { entries.splice(at + 1); entries.push({ state, url: url.replace("http://x", "") }); at++; },
  replaceState(state, _, url) { entries[at] = { state, url: url.replace("http://x", "") }; },
  back() { at--; if (popOnBack) setTimeout(() => (win.popstate || []).forEach((fn) => fn({})), 0); },
};
global.matchMedia = () => ({ matches: true });
global.document = {
  body: { dataset: {}, tagName: "BODY" },
  addEventListener: (type, fn) => { (handlers[type] = handlers[type] || []).push(fn); },
  getElementById: () => null, querySelector: () => null, querySelectorAll: () => [],
};
document.activeElement = document.body;
eval(source);
const ok = window.oknowledge;
if (c.adopt) ok.layers.adopt(c.adopt, () => {});   // a deferred script, before DOMContentLoaded
(handlers.DOMContentLoaded || []).forEach((fn) => fn());
const tick = () => new Promise((r) => setTimeout(r, 10));
(async () => {
  await tick();
  out.at = at;
  out.state = entries[at].state;
  out.url = entries[at].url;
  out.top = ok.layers.top();
  if (c.mode === "bfcache") {
    // A layer is open; its back() becomes a navigation away (no popstate),
    // and the page comes back from the bfcache on the entry before.
    const how = [];
    ok.layers.open("panel", (h) => how.push(h), "/?sel=q9");
    popOnBack = false;
    let firstDone = false;
    ok.layers.close().then(() => { firstDone = true; });
    (win.pageshow || []).forEach((fn) => fn({ persisted: true }));
    await tick();
    const where = at;
    await Promise.race([ok.layers.close(), tick()]); // in place: the entry is not its own any more
    out.bfcache = [firstDone, how, at === where, ok.layers.top()];
  }
  console.log(JSON.stringify(out));
})();
"""

RELOAD_CASES = {
    # Ajustes reloaded: drawn without it, the entry before is the same URL -> one back.
    "settings": {"adopt": "", "url": "/", "state": {"layer": "settings", "base": "http://x/"}},
    # A detail at another ?sel= than the entry before, nobody adopts: no back, state cleared.
    "other": {"adopt": "", "url": "/?sel=l11", "state": {"layer": "panel", "base": "http://x/?sel=p1"}},
    # The detail adopted while the page loads keeps its entry.
    "adopted": {"adopt": "panel", "url": "/?sel=a1", "state": {"layer": "panel", "base": "http://x/"}},
    "bfcache": {"adopt": "", "url": "/", "state": None, "mode": "bfcache"},
}


@pytest.fixture(scope="module")
def reloads(tmp_path_factory):
    """Every case, run before the per-test guard against programs (as `layers`)."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    harness = tmp_path_factory.mktemp("reload") / "harness.js"
    harness.write_text(RELOAD_HARNESS, encoding="utf-8")
    found = {}
    for case, spec in RELOAD_CASES.items():
        done = subprocess.run([node, str(harness), str(APP), json.dumps(spec)], capture_output=True,
                              text=True, timeout=30, check=False)
        assert done.returncode == 0, done.stderr
        found[case] = json.loads(done.stdout.strip().splitlines()[-1])
    return found


def test_a_reload_on_an_entry_nobody_adopts_drops_it(reloads):
    """Fix round 1: Ajustes reloaded is not drawn again, so its entry goes."""
    assert reloads["settings"]["at"] == 1 and reloads["settings"]["top"] == ""


def test_a_reload_on_a_detail_elsewhere_keeps_its_place_and_forgets_the_layer(reloads):
    """Fix round 2: going back would put another URL over the same screen."""
    other = reloads["other"]
    assert [other["at"], other["state"], other["url"], other["top"]] == [2, None, "/?sel=l11", ""]


def test_a_reload_on_an_adopted_layer_keeps_its_entry(reloads):
    adopted = reloads["adopted"]
    assert [adopted["at"], adopted["top"], adopted["state"]["layer"]] == [2, "panel", "panel"]


def test_a_layer_entry_names_the_one_it_was_pushed_from():
    assert "{ layer: name, base: location.href }" in APP.read_text(encoding="utf-8")


def test_a_page_back_from_the_bfcache_forgets_a_back_under_way(reloads):
    assert reloads["bfcache"]["bfcache"] == [True, ["close"], True, ""]


def test_settings_loads_nothing_when_ajustes_is_refused():
    text = (STATIC / "settings.js").read_text(encoding="utf-8")
    opening = between(text, "ok.openSettings = function", "ok.bindSettings")
    # Emptied before it opens (polish D9: the dialog takes the focus), and
    # nothing fetched when refused (test_web_settings_script.py runs it).
    gate = "if (!ok.openModal(modal)) return;"
    assert "if (!modal.open) {" in opening and gate in opening
    assert opening.index("modal.replaceChildren()") < opening.index(gate) < opening.index("fetch(")
