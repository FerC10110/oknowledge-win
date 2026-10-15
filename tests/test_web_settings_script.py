"""What settings.js does over time (docs/2026-10-15-rediseno-modales-teclado-pendientes.md,
"Ajustes"), run in node over a fake page: the modal and the page /settings,
a server whose every answer the scenario gives (or never gives), and a clock
whose long timers run only when the scenario says so. Each scenario is a
fresh page; what it prints is checked."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.vault import rebuild_indexes, write_note
from oknowledge.web.app import create_app

# node is the one program these run, and nothing in it reaches the network:
# taken before conftest's guard swaps them for an alarm, and put back after it.
REAL = {name: getattr(subprocess, name) for name in ("run", "Popen")}

SETTINGS = (Path(__file__).resolve().parent.parent / "src" / "oknowledge" / "web" / "static"
            / "settings.js")
JSON = {"Accept": "application/json"}

PAGE = r"""
const fs = require("fs");
const SOURCE = fs.readFileSync(process.argv[2], "utf8");
const SETUP = JSON.parse(process.argv[3]);
const out = { reloads: 0, toasts: [], navigated: null, timers: [] };
const realTimeout = setTimeout;
const realClear = clearTimeout;
const settle = (ms) => new Promise((r) => realTimeout(r, ms || 20));

// --- the clock: a timer of a second or more waits for tick() -------------------
const later = [];
global.setTimeout = (fn, ms) => {
  if (!(ms >= 1000)) return realTimeout(fn, ms);
  out.timers.push(ms);
  const timer = { fn, gone: false };
  later.push(timer);
  return timer;
};
global.clearTimeout = (timer) => { if (timer && timer.fn) timer.gone = true; else realClear(timer); };
function tick() { later.splice(0).forEach((t) => { if (!t.gone) t.fn(); }); }

// --- elements -------------------------------------------------------------------
const body = { dataset: { saveFailed: "SAVE FAILED", close: "CLOSE" }, tagName: "BODY" };
function el(tag, props) {
  const on = {};
  const attrs = {};
  const classes = new Set();
  const e = Object.assign({
    tagName: tag, dataset: {}, hidden: false, value: "", isConnected: true,
    classList: { add: (c) => classes.add(c), remove: (c) => classes.delete(c),
                 contains: (c) => classes.has(c),
                 toggle(c, f) { const w = f === undefined ? !classes.has(c) : !!f;
                                if (w) classes.add(c); else classes.delete(c); return w; } },
    setAttribute(k, v) { attrs[k] = String(v); }, removeAttribute(k) { delete attrs[k]; },
    getAttribute(k) { return k in attrs ? attrs[k] : null; }, hasAttribute(k) { return k in attrs; },
    addEventListener(type, fn) { (on[type] = on[type] || []).push(fn); },
    fire(type, extra) {
      const event = Object.assign({ type, target: e, defaultPrevented: false, button: 0,
        preventDefault() { this.defaultPrevented = true; }, stopPropagation() {} }, extra || {});
      (on[type] || []).forEach((fn) => fn(event));
      return event;
    },
    focus() { document.activeElement = e; },
    blur() { if (document.activeElement === e) document.activeElement = body; },
    querySelector: () => null, querySelectorAll: () => [], closest: () => null,
    contains(x) { return x === e; }, appendChild() {}, replaceChildren() {},
  }, props || {});
  return e;
}

// A settings body as the server draws it, open on `tab`: the tabs, the
// Motores form, a rename form per category and the page's ✕.
let made = 0;
function makeRoot(tab) {
  const inside = new Set();
  const own = (e) => { inside.add(e); return e; };
  const root = el("DIV", { tab, n: ++made });
  const links = ["motores", "idioma", "importar", "categorias"].map((key) => {
    const a = own(el("A", { closest: (sel) => (sel === "a[data-settings-tab]" ? a : null) }));
    a.dataset.settingsTab = key;
    if (key === tab) a.classList.add("on");
    return a;
  });
  const form = own(el("FORM", { payload: { tab: "motores", opencode_model: "m1" } }));
  form.setAttribute("action", "/settings");
  const renames = (SETUP.categories || []).map((name) => {
    const box = own(el("INPUT", { value: name }));
    const old = own(el("INPUT", { value: name }));
    const f = own(el("FORM", { elements: { new: box, old } }));
    f.setAttribute("action", "/categories/rename");
    return f;
  });
  const pane = own(el("SECTION"));
  pane.dataset.merge = "Merge %1 into %2?";
  pane.querySelectorAll = (sel) => (sel.indexOf('input[name="old"]') >= 0
    ? renames.map((f) => f.elements.old) : sel === "form[data-settings-rename]" ? renames : []);
  const close = own(el("A", { closest: (sel) => (sel === "a[data-close]" ? close : null) }));
  close.setAttribute("href", "/");
  root.querySelectorAll = (sel) => (sel === "a[data-settings-tab]" ? links
    : sel === "form[data-settings]" ? [form] : []);
  root.querySelector = (sel) => (sel === "a[data-settings-tab].on" ? links.find((a) => a.classList.contains("on"))
    : sel === '[data-settings-pane="categorias"]' ? pane : null);
  root.contains = (x) => x === root || inside.has(x);
  root.replaceWith = (fresh) => { root.isConnected = false; if (root.onReplace) root.onReplace(fresh); };
  root.parts = { links, form, renames, close };
  return root;
}

// --- the modal --------------------------------------------------------------------
let drawn = null;           // the root in the modal
const modal = el("DIALOG", { open: false,
  // Like a browser's: the first control inside, or the dialog when empty.
  showModal() { this.open = true; document.activeElement = drawn ? drawn.parts.close : modal; },
  close() { if (!this.open) return; this.open = false; this.fire("close"); },
  replaceChildren() {
    if (drawn && drawn.contains(document.activeElement)) document.activeElement = body;
    if (drawn) drawn.isConnected = false;
    drawn = null;
  },
  querySelector: (sel) => (sel === "[data-settings-root]" ? drawn : null),
  contains(x) { return x === modal || !!(drawn && drawn.contains(x)); } });
modal.dataset.failed = "FAILED";
Object.defineProperty(modal, "innerHTML", { set(html) {
  if (drawn) drawn.isConnected = false;
  drawn = html.indexOf("ROOT:") === 0 ? makeRoot(html.slice(5)) : null;
  if (drawn) drawn.onReplace = (fresh) => { drawn = fresh; fresh.onReplace = drawn.onReplace; };
} });
function modalRoot() { return drawn; }

// --- the page ---------------------------------------------------------------------
let pageRoot = SETUP.page ? makeRoot(SETUP.tab || "motores") : null;
if (pageRoot) pageRoot.onReplace = (fresh) => { pageRoot = fresh; fresh.onReplace = pageRoot.onReplace; };
global.window = global;
global.document = {
  body, activeElement: body,
  getElementById: (id) => (id === "settings-modal" ? modal : null),
  querySelector: (sel) => (sel === ".settings-body[data-settings-root]" ? pageRoot : null),
  createElement(tag) {
    if (tag !== "template") return el(tag.toUpperCase());
    let fresh = null;
    return { set innerHTML(h) { fresh = h.indexOf("ROOT:") === 0 ? makeRoot(h.slice(5)) : null; },
             content: { querySelector: () => fresh } };
  },
};
global.location = {
  pathname: SETUP.page ? "/settings" : "/",
  get href() { return this.pathname; },
  set href(v) { out.navigated = v; },
  reload() { out.reloads += 1; },
};
global.history = { state: null, replaceState() {} };
global.confirm = () => true;
global.FormData = function (form) { return Object.assign({}, form && form.payload); };

// --- the server: every answer is the scenario's -------------------------------------
const fetches = [];
global.fetch = (url) => new Promise((resolve, reject) => {
  const tab = (url.match(/tab=([a-z]*)/) || [])[1] || "";
  fetches.push({ url, tab, serve: () => resolve({ ok: true, status: 200, text: () => Promise.resolve("ROOT:" + tab) }),
                 fail: () => resolve({ ok: false, status: 500, text: () => Promise.resolve("") }) });
});
function serveAll() { fetches.forEach((f) => { if (!f.done) { f.done = true; f.serve(); } }); }
const sends = [];
window.oknowledge = {
  toast(text) { out.toasts.push(text); },
  raiseToast() {},
  openModal(dialog) { if (dialog.open) return false; dialog.showModal(); return true; },
  send: (url, data) => new Promise((resolve, reject) => {
    sends.push({ url, data, answer: (b) => resolve(Object.assign({ ok: true, notice: "" }, b)),
                 refuse: (text) => reject(new Error(text)) });
  }),
};
const ok = window.oknowledge;
function rename(root, from, to) {
  const form = root.parts.renames.find((f) => f.elements.old.value === from);
  form.elements.new.value = to;
  form.elements.new.fire("change");
}
function clickClose(root) {
  return root.fire("click", { target: root.parts.close, metaKey: false, ctrlKey: false,
                              shiftKey: false, altKey: false });
}
eval(SOURCE);
"""


@pytest.fixture(autouse=True)
def node_may_run(no_network_and_no_subprocess, monkeypatch):
    for name, real in REAL.items():
        monkeypatch.setattr(subprocess, name, real)


def run(tmp_path, scenario, **setup):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    harness = tmp_path / "harness.js"
    harness.write_text(PAGE + "(async () => {\n" + scenario +
                       "\nconsole.log(JSON.stringify(out));\n})().catch((e) => { console.error(e.stack); process.exit(1); });\n",
                       encoding="utf-8")
    done = subprocess.run(["node", str(harness), str(SETTINGS), json.dumps(setup)],
                          capture_output=True, text=True, timeout=30, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


OPEN = """
ok.openSettings("categorias"); serveAll(); await settle();
const root = modalRoot();
"""


# --- the harness itself --------------------------------------------------------------

def test_the_modal_opens_on_the_tab_asked_for(tmp_path):
    out = run(tmp_path, OPEN + "out.tab = modalRoot().tab;", categories=["Redes"])
    assert out["tab"] == "categorias" and out["reloads"] == 0


# --- 4. a rename reloads on close exactly when something moved ------------------------

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr("oknowledge.web.app.CONFIG_PATH", tmp_path / "config" / "config.toml")
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    for id in ("b2", "c3"):
        write_note(cfg, Note(id=id, url=f"https://e.com/{id}", title=id, category="Cocina",
                             tags=[], type="article", source="e.com", saved="2026-10-03",
                             summary="s"), "es")
    rebuild_indexes(cfg, "es")
    return TestClient(create_app(cfg))


def test_a_rename_tells_a_script_how_many_it_moved(client):
    moved = client.post("/categories/rename", data={"old": "Cocina", "new": "Comida"},
                        headers=JSON).json()
    assert moved["ok"] and moved["moved"] == 2
    nothing = client.post("/categories/rename", data={"old": "Nadie", "new": "Otra"},
                          headers=JSON).json()
    assert nothing["ok"] and nothing["moved"] == 0


def test_a_rename_that_moved_nothing_does_not_reload_on_close(tmp_path):
    out = run(tmp_path, OPEN + """
rename(root, "Redes", "Nadie");
sends[0].answer({ moved: 0 }); await settle(); serveAll(); await settle();
modal.close(); await settle();
""", categories=["Redes"])
    assert out["reloads"] == 0


def test_a_rename_that_moved_notes_reloads_on_close(tmp_path):
    out = run(tmp_path, OPEN + """
rename(root, "Redes", "Otra");
sends[0].answer({ moved: 3 }); await settle(); serveAll(); await settle();
modal.close(); await settle();
""", categories=["Redes"])
    assert out["reloads"] == 1


def test_two_renames_out_at_a_close_reload_once_when_either_moved(tmp_path):
    out = run(tmp_path, OPEN + """
rename(root, "Redes", "Uno");
rename(root, "Cocina", "Dos");
modal.close(); await settle();
sends[1].answer({ moved: 0 }); await settle();
out.afterSecond = out.reloads;
sends[0].answer({ moved: 2 }); await settle(); serveAll(); await settle();
""", categories=["Redes", "Cocina"])
    assert out["afterSecond"] == 0 and out["reloads"] == 1


def test_two_renames_out_at_a_close_that_moved_nothing_do_not_reload(tmp_path):
    out = run(tmp_path, OPEN + """
rename(root, "Redes", "Uno");
rename(root, "Cocina", "Dos");
modal.close(); await settle();
sends[0].answer({ moved: 0 }); sends[1].refuse("NOPE"); await settle(); serveAll(); await settle();
""", categories=["Redes", "Cocina"])
    assert out["reloads"] == 0


# --- 5. a save that never answers fails after 15 s --------------------------------------

def test_a_save_that_never_answers_fails_visibly_and_lets_the_redraw_go(tmp_path):
    out = run(tmp_path, OPEN + """
root.parts.form.fire("change");                       // never answered
rename(root, "Redes", "Otra");
sends[1].answer({ moved: 1 }); await settle();
out.redrawsBefore = fetches.length;                   // the redraw waits for the save
tick(); await settle();
out.redrawsAfter = fetches.length;
root.parts.form.fire("change"); await settle();       // the same pane again is sent again
out.sent = sends.length;
""", categories=["Redes"])
    assert 15000 in out["timers"]
    assert out["redrawsBefore"] == 1 and out["redrawsAfter"] == 2
    assert out["toasts"][-1] == "SAVE FAILED"
    assert out["sent"] == 3


def test_a_save_that_answers_in_time_is_not_failed_later(tmp_path):
    out = run(tmp_path, OPEN + """
root.parts.form.fire("change");
sends[0].answer({ notice: "SAVED" }); await settle();
tick(); await settle();
""", categories=["Redes"])
    assert out["toasts"] == ["SAVED"]


# --- 6. a reopened modal shows the tab it was reopened on --------------------------------

@pytest.mark.parametrize("order", ["late first", "in order"])
def test_reopening_on_another_tab_shows_that_tab(tmp_path, order):
    serve = "fetches[1].serve(); await settle(); fetches[0].serve();" if order == "late first" \
        else "fetches[0].serve(); await settle(); fetches[1].serve();"
    out = run(tmp_path, f"""
ok.openSettings("idioma"); await settle();
modal.close(); await settle();
ok.openSettings("importar"); await settle();
{serve} await settle();
out.tab = modalRoot().tab;
""")
    assert out["tab"] == "importar"


# --- 8. the page's ✕ stays when the last save failed ------------------------------------

def test_the_pages_close_stays_and_says_so_when_the_last_save_failed(tmp_path):
    out = run(tmp_path, """
const root = pageRoot;
root.parts.form.fire("change");
sends[0].refuse("NOPE"); await settle();
const first = clickClose(root); await settle();
out.first = [first.defaultPrevented, out.navigated, out.toasts.slice()];
clickClose(root); await settle();
out.second = out.navigated;
""", page=True)
    assert out["first"] == [True, None, ["NOPE", "NOPE"]]
    assert out["second"] == "/"


def test_the_pages_close_goes_when_a_later_save_landed(tmp_path):
    out = run(tmp_path, """
const root = pageRoot;
root.parts.form.fire("change");
sends[0].refuse("NOPE"); await settle();
root.parts.form.payload.opencode_model = "m2";
root.parts.form.fire("change");
sends[1].answer({}); await settle();
clickClose(root); await settle();
""", page=True)
    assert out["navigated"] == "/"


def test_the_pages_close_stays_when_a_rename_failed(tmp_path):
    out = run(tmp_path, """
const root = pageRoot;
rename(root, "Redes", "Otra");
sends[0].refuse("NOPE"); await settle();
clickClose(root); await settle();
""", page=True, tab="categorias", categories=["Redes"])
    assert out["navigated"] is None and out["toasts"] == ["NOPE", "NOPE"]


# --- 9. reopened after Esc, the focus is the dialog's, not the page's ---------------------

def test_a_reopened_modal_keeps_the_focus_in_the_dialog(tmp_path):
    out = run(tmp_path, """
ok.openSettings("idioma"); serveAll(); await settle();
out.first = document.activeElement === modal;
modal.close(); document.activeElement = body; await settle();
ok.openSettings("motores"); await settle();
out.loading = document.activeElement === modal;
serveAll(); await settle();
out.loaded = document.activeElement === modal;
""")
    assert out["first"] and out["loading"] and out["loaded"]


def test_a_refused_modal_loads_nothing(tmp_path):
    out = run(tmp_path, """
ok.openModal = () => false;                           // the phone, over the detail
ok.openSettings("idioma"); await settle();
out.fetched = fetches.length;
""")
    assert out["fetched"] == 0
