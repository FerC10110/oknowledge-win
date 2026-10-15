"""autosave.js's settle(): what a panel waits for before it is swapped
(Task 11 fix round 1). Run in node with a fake page: the fetches are held
and answered by the test, so the order of what lands is the test's."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "src" / "oknowledge" / "web" / "static" / "autosave.js"

HARNESS = r"""
const source = require("fs").readFileSync(process.argv[2], "utf8");
const listeners = { window: {}, document: {} };
function on(where) {
  return (type, fn) => { (listeners[where][type] = listeners[where][type] || []).push(fn); };
}
function makeField(value) {
  const handlers = {};
  return { value, name: "my_note", dataset: { autosave: "/item/x/mine/note" }, form: null,
           isConnected: true, hasAttribute: () => false,
           addEventListener: (t, f) => { handlers[t] = f; }, fire: (t) => handlers[t] && handlers[t](),
           dispatchEvent: () => true };
}
let fields = [makeField("a")];
const root = { querySelectorAll: (sel) => sel === "[data-autosave]" ? fields : [] };
global.window = global;
window.addEventListener = on("window");
global.document = { body: { dataset: { saveFailed: "No se pudo guardar" }, appendChild: () => null },
                    createElement: () => ({ setAttribute: () => null, remove: () => null }),
                    activeElement: null,
                    visibilityState: "visible", addEventListener: on("document"),
                    querySelector: () => null, querySelectorAll: (sel) => root.querySelectorAll(sel) };
global.FormData = class { constructor() { this.v = {}; } set(k, v) { this.v[k] = v; } };
global.CustomEvent = class { constructor(t) { this.type = t; } };
const held = [];
global.fetch = (url, opts) => new Promise((resolve) => held.push({ text: opts.body.v.my_note, resolve }));
function answer(ok) {
  const one = held.shift();
  one.resolve({ ok, status: ok ? 200 : 500,
                json: () => Promise.resolve(ok ? { ok: true, notice: "" } : { ok: false, error: "boom" }) });
  return one.text;
}
const tick = () => new Promise((r) => setTimeout(r, 0));
eval(source);
const out = {};
(async () => {
  const f = fields[0];
  // A pending debounced save is sent at once, and settle waits for it.
  f.value = "ab"; f.fire("input");
  let done = null;
  window.oknowledge.settle(root).then((e) => { done = e === null ? "ok" : "failed"; });
  await tick();
  out.sentAtOnce = held.map((h) => h.text);
  out.beforeAnswer = done;
  answer(true); await tick(); await tick();
  out.afterAnswer = done;
  // A save in flight and newer text behind it: settle waits for both.
  f.value = "abc"; f.fire("blur");
  f.value = "abcd";
  done = null;
  window.oknowledge.settle(root).then((e) => { done = e === null ? "ok" : "failed"; });
  await tick();
  const first = answer(true); await tick(); await tick();
  out.inFlight = [first, done];
  const second = answer(true); await tick(); await tick();
  out.behind = [second, done];
  // A failed save: settle says so, and the text stays in the field.
  f.value = "lost?";
  done = null;
  window.oknowledge.settle(root).then((e) => { done = e === null ? "ok" : e.message; });
  await tick();
  answer(false); await tick(); await tick(); await tick();
  out.failed = [done, f.value];
  // Nothing to save: settle answers at once.
  done = null;
  f.value = "fine"; window.oknowledge.settle(root).then((e) => { done = e; });
  await tick(); answer(true); await tick(); await tick();
  done = undefined;
  window.oknowledge.settle(root).then((e) => { done = e; });
  await tick();
  out.idle = done;
  // Many boxes bound, page listeners added once.
  fields = [makeField("x"), makeField("y"), makeField("z")];
  window.oknowledge.bind(root);
  out.pagehide = (listeners.window.pagehide || []).length;
  out.visibility = (listeners.document.visibilitychange || []).length;
  console.log(JSON.stringify(out));
})();
"""


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    harness = tmp_path_factory.mktemp("settle") / "harness.js"
    harness.write_text(HARNESS, encoding="utf-8")
    done = subprocess.run([node, str(harness), str(SCRIPT)], capture_output=True, text=True,
                          timeout=30, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_settle_sends_a_pending_save_now_and_waits_for_it(run):
    assert run["sentAtOnce"] == ["ab"]
    assert run["beforeAnswer"] is None and run["afterAnswer"] == "ok"


def test_settle_waits_for_the_newest_text_behind_a_save_in_flight(run):
    assert run["inFlight"] == ["abc", None]
    assert run["behind"] == ["abcd", "ok"]


def test_a_failed_save_is_told_and_the_text_stays(run):
    assert run["failed"] == ["boom", "lost?"]


def test_nothing_to_save_settles_at_once(run):
    assert run["idle"] is None


def test_the_page_listeners_are_added_once(run):
    assert run["pagehide"] == 1 and run["visibility"] == 1


# Final review I-2: the text goes back to the last saved value while a save is
# in flight. The newest text must still be sent once that save lands, and the
# indicator must settle on "saved".
BACK_HARNESS = r"""
const source = require("fs").readFileSync(process.argv[2], "utf8");
const handlers = {};
const indicator = { textContent: "", dataset: { saving: "Guardando…", saved: "Guardado" } };
const field = { value: "A", name: "my_note", dataset: { autosave: "/item/x/mine/note", indicator: "#ind" },
                form: null, isConnected: true, hasAttribute: () => false,
                addEventListener: (t, f) => { handlers[t] = f; }, dispatchEvent: () => true };
const root = { querySelectorAll: (sel) => sel === "[data-autosave]" ? [field] : [] };
global.window = global;
window.addEventListener = () => null;
global.document = { body: { dataset: {}, appendChild: () => null },
                    createElement: () => ({ setAttribute: () => null, remove: () => null }),
                    activeElement: null, visibilityState: "visible", addEventListener: () => null,
                    querySelector: (sel) => sel === "#ind" ? indicator : null,
                    querySelectorAll: (sel) => root.querySelectorAll(sel) };
global.FormData = class { constructor() { this.v = {}; } set(k, v) { this.v[k] = v; } };
global.CustomEvent = class { constructor(t) { this.type = t; } };
const held = [];
const landed = [];
global.fetch = (url, opts) => new Promise((resolve) => held.push({ text: opts.body.v.my_note, resolve }));
function answer() {
  const one = held.shift();
  landed.push(one.text);
  one.resolve({ ok: true, status: 200, json: () => Promise.resolve({ ok: true, notice: "" }) });
}
const tick = () => new Promise((r) => setTimeout(r, 0));
eval(source);
(async () => {
  const out = {};
  field.value = "AB"; handlers.blur();            // "AB" goes out
  await tick();
  field.value = "A"; handlers.blur();             // back to what the server had
  await tick();
  answer(); await tick(); await tick(); await tick();
  out.followUp = held.map((h) => h.text);
  while (held.length) { answer(); await tick(); await tick(); await tick(); }
  out.landed = landed;
  out.indicator = indicator.textContent;
  console.log(JSON.stringify(out));
})();
"""


@pytest.fixture(scope="module")
def back(tmp_path_factory):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    harness = tmp_path_factory.mktemp("back") / "harness.js"
    harness.write_text(BACK_HARNESS, encoding="utf-8")
    done = subprocess.run([node, str(harness), str(SCRIPT)], capture_output=True, text=True,
                          timeout=30, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_text_back_to_the_saved_value_during_a_save_is_sent_after_it(back):
    assert back["followUp"] == ["A"]
    assert back["landed"] == ["AB", "A"]
    assert back["indicator"] == "Guardado"
