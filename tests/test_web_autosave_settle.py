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


# --- polish (docs/2026-10-14-rediseno-ocio-ideas-pendientes.md, "Panel y autoguardado") ---
# A clock the test moves: the timers autosave.js sets wait for advance().
# node is the one program these run: taken before conftest's guard swaps
# them for an alarm, and put back after it (as test_web_layer_history does).
_REAL = {name: getattr(subprocess, name) for name in ("run", "Popen")}

CLOCK_HARNESS = r"""
const source = require("fs").readFileSync(process.argv[2], "utf8");
const realTimeout = setTimeout;
let now = 0;
let timers = [];
global.setTimeout = (fn, ms) => { const t = { fn, at: now + (ms || 0) }; timers.push(t); return t; };
global.clearTimeout = (t) => { timers = timers.filter((x) => x !== t); };
async function advance(ms) {
  now += ms;
  for (;;) {
    const due = timers.filter((t) => t.at <= now).sort((a, b) => a.at - b.at)[0];
    if (!due) break;
    timers = timers.filter((t) => t !== due);
    due.fn();
    await tick();
  }
}
const tick = () => new Promise((r) => realTimeout(r, 0));
const listeners = { window: {}, document: {} };
function on(where) {
  return (type, fn) => { (listeners[where][type] = listeners[where][type] || []).push(fn); };
}
const handlers = {};
const field = { value: "", name: "my_note", dataset: { autosave: "/item/x/mine/note" }, form: null,
                isConnected: true, hasAttribute: () => false,
                addEventListener: (t, f) => { handlers[t] = f; }, dispatchEvent: () => true };
const root = { querySelectorAll: (sel) => sel === "[data-autosave]" ? [field] : [] };
global.window = global;
window.addEventListener = on("window");
global.document = { body: { dataset: { saveFailed: "No se pudo guardar" }, appendChild: () => null },
                    createElement: () => ({ setAttribute: () => null, remove: () => null }),
                    activeElement: null, visibilityState: "visible", addEventListener: on("document"),
                    querySelector: () => null, querySelectorAll: (sel) => root.querySelectorAll(sel) };
global.FormData = class { constructor() { this.v = {}; } set(k, v) { this.v[k] = v; } };
global.CustomEvent = class { constructor(t) { this.type = t; } };
const held = [];
const sent = [];
global.fetch = (url, opts) => new Promise((resolve, reject) => {
  sent.push({ text: opts.body.v.my_note, keepalive: opts.keepalive, rev: opts.body.v.rev,
             page: opts.body.v.page });
  held.push({ resolve, reject });
  if (opts.signal) opts.signal.addEventListener("abort", () => reject(new Error("aborted")));
});
function answer(ok, extra) {
  held.shift().resolve({ ok, status: ok ? 200 : 500,
    json: () => Promise.resolve(ok ? Object.assign({ ok: true, notice: "" }, extra || {})
                                   : { ok: false, error: "boom" }) });
}
const toasts = [];
window.oknowledge = { toast: (t) => toasts.push(t) };
function visibility(state) {
  document.visibilityState = state;
  (listeners.document.visibilitychange || []).forEach((fn) => fn());
}
eval(source);
const out = {};
"""


@pytest.fixture
def clock(tmp_path, no_network_and_no_subprocess, monkeypatch):
    for name, real in _REAL.items():
        monkeypatch.setattr(subprocess, name, real)
    return lambda scenario: run_clock(tmp_path, scenario)


def run_clock(tmp_path, scenario):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    harness = tmp_path / "harness.js"
    harness.write_text(CLOCK_HARNESS + "(async () => {\n" + scenario +
                       "\nconsole.log(JSON.stringify(out));\n})().catch((e) => { console.error(e.stack); process.exit(1); });\n",
                       encoding="utf-8")
    done = subprocess.run([node, str(harness), str(SCRIPT)], capture_output=True, text=True,
                          timeout=30, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_a_save_that_never_answers_fails_after_fifteen_seconds(clock):
    out = clock("""
field.value = "ab";
let told = "waiting";
window.oknowledge.settle(root).then((e) => { told = e ? e.message : null; });
await tick();
await advance(14999);
out.before = told;
await advance(1); await tick(); await tick();
out.after = told;
out.toasts = toasts.slice();
out.text = field.value;
// The panel change is not stuck: the next one tries again.
window.oknowledge.settle(root);
await tick();
out.sent = sent.map((s) => s.text);
""")
    assert out["before"] == "waiting"
    assert out["after"] == "No se pudo guardar" and out["toasts"] == ["No se pudo guardar"]
    assert out["text"] == "ab" and out["sent"] == ["ab", "ab"]


def test_a_save_that_answers_in_time_is_not_timed_out(clock):
    out = clock("""
field.value = "ab";
let told = "waiting";
window.oknowledge.settle(root).then((e) => { told = e; });
await tick();
await advance(14000);
answer(true); await tick(); await tick(); await tick();
await advance(5000);
out.told = told;
out.toasts = toasts;
""")
    assert out["told"] is None and out["toasts"] == []


@pytest.mark.parametrize("size, keepalive", [(1000, True), (70000, False)])
def test_leaving_with_a_big_text_does_not_use_keepalive(clock, size, keepalive):
    """keepalive bodies are capped at 64 KB: a bigger one would fail at once
    with a false error. It goes as a normal request instead."""
    out = clock(f"""
field.value = "x".repeat({size});
visibility("hidden");
await tick();
out.keepalive = sent.map((s) => s.keepalive);
out.toasts = toasts;
""")
    assert out["keepalive"] == [keepalive] and out["toasts"] == []


def test_a_failed_leave_is_sent_again_when_the_page_comes_back(clock):
    out = clock("""
field.value = "abc";
visibility("hidden");
await tick();
answer(false); await tick(); await tick(); await tick();
out.afterFail = sent.length;
visibility("visible");
await tick();
out.sent = sent.map((s) => s.text);
""")
    assert out["afterFail"] == 1 and out["sent"] == ["abc", "abc"]


def test_coming_back_with_nothing_unsaved_sends_nothing(clock):
    out = clock("""
field.value = "abc";
visibility("hidden");
await tick();
answer(true); await tick(); await tick(); await tick();
visibility("visible");
await tick();
out.sent = sent.length;
""")
    assert out["sent"] == 1


def test_a_failed_save_is_not_sent_again_at_once_by_the_settle_that_waited(clock):
    """A settle asked while the save was out waits for that one only: it is
    told the failure after fifteen seconds, not thirty."""
    out = clock("""
field.value = "ab"; handlers.blur();
await tick();
let told = "waiting";
window.oknowledge.settle(root).then((e) => { told = e ? e.message : null; });
await tick();
await advance(15000); await tick(); await tick();
out.told = told;
out.sent = sent.map((s) => s.text);
""")
    assert out["told"] == "No se pudo guardar" and out["sent"] == ["ab"]


def test_text_typed_while_a_save_failed_is_sent_a_second_later(clock):
    out = clock("""
field.value = "ab"; handlers.blur();
await tick();
field.value = "abc"; handlers.blur();          // out while "ab" is: it waits for it
await tick();
answer(false); await tick(); await tick(); await tick();
out.atOnce = sent.map((s) => s.text);
await advance(1000); await tick();
out.later = sent.map((s) => s.text);
""")
    assert out["atOnce"] == ["ab"] and out["later"] == ["ab", "abc"]


# --- the model's title and a focused title box (polish, Ideas) -------------------------------

def test_the_model_s_title_lands_in_an_empty_box_that_has_the_focus(clock):
    out = clock("""
document.activeElement = field;
out.empty = field.oknowledgeSettle("VPN familiar");
out.value = field.value;
""")
    assert out["empty"] is True and out["value"] == "VPN familiar"


def test_the_model_s_title_waits_while_somebody_types_in_the_box(clock):
    out = clock("""
document.activeElement = field;
field.value = "Mi tí";
out.typing = field.oknowledgeSettle("VPN familiar");
out.value = field.value;
""")
    assert out["typing"] is False and out["value"] == "Mi tí"


def test_a_box_with_text_saved_and_the_focus_keeps_it(clock):
    """Text that is the box's own, saved or not: the focus means it may be
    edited next, and the model does not take it."""
    out = clock("""
field.value = "Mío"; handlers.blur(); await tick();
answer(true); await tick(); await tick(); await tick();
document.activeElement = field;
out.kept = field.oknowledgeSettle("VPN familiar");
out.value = field.value;
""")
    assert out["kept"] is False and out["value"] == "Mío"


# --- review I-1, M-1, M-2 ------------------------------------------------------------------------

def test_every_save_of_a_field_carries_a_rising_revision(clock):
    """The server writes a field's text only if its rev is newer than the last
    one written, so a save that ran late cannot land over a newer one. The
    leave() path (keepalive, in parallel with one in flight) carries it too."""
    out = clock("""
field.value = "a"; handlers.blur(); await tick();
field.value = "ab"; visibility("hidden"); await tick();   // leave(): out beside "a"
answer(true); answer(true); await tick(); await tick(); await tick();
field.value = "abc"; handlers.blur(); await tick();
out.revs = sent.map((s) => s.rev);
out.texts = sent.map((s) => s.text);
""")
    revs = [float(r) for r in out["revs"]]
    assert out["texts"] == ["a", "ab", "abc"]
    assert revs == sorted(revs) and len(set(revs)) == 3 and revs[0] > 1e12   # the clock's ms


def test_a_stale_answer_is_not_taken_as_this_text_saved(clock):
    out = clock("""
field.value = "A"; handlers.blur(); await tick();
answer(true, { stale: true }); await tick(); await tick(); await tick();
window.oknowledge.settle(root); await tick();
out.texts = sent.map((s) => s.text);
""")
    assert out["texts"] == ["A", "A"]


def test_after_a_timeout_going_back_to_the_old_text_still_sends_it(clock):
    """Review M-1: the save that timed out may have landed late; what the
    server holds is unknown, so the old text is not "already saved"."""
    out = clock("""
field.value = "x"; handlers.blur(); await tick();
answer(true); await tick(); await tick(); await tick();
field.value = "xy"; handlers.blur(); await tick();
await advance(15000); await tick(); await tick();
field.value = "x";
window.oknowledge.settle(root); await tick();
out.texts = sent.map((s) => s.text);
""")
    assert out["texts"] == ["x", "xy", "x"]


def test_a_form_post_has_no_save_timeout(clock):
    """Review M-2: idea.js's posts (an AI action's start, + Add, a tag) are
    not autosaves: no 15 s limit and no "could not be saved"."""
    out = clock("""
let settled = "waiting";
window.oknowledge.post({ action: "/item/x/actions/improve" }).then(() => { settled = "ok"; },
                                                                (e) => { settled = e.message; });
await tick();
await advance(60000); await tick();
out.before = settled;
answer(true); await tick(); await tick();
out.after = settled;
out.toasts = toasts;
""")
    assert out["before"] == "waiting" and out["after"] == "ok" and out["toasts"] == []


# --- batch G: what test_web_idea_scripts.py read in autosave.js's source, run instead -------

def test_a_field_saves_a_second_after_the_last_key_and_at_once_on_blur(clock):
    out = clock("""
field.value = "a"; handlers.input(); await advance(600);
field.value = "ab"; handlers.input(); await advance(999); await tick();
out.waiting = sent.length;
await advance(1); await tick();
out.second = sent.map((s) => s.text);
answer(true); await tick(); await tick(); await tick();
field.value = "abc"; handlers.blur(); await tick();
out.blur = sent.map((s) => s.text);
""")
    assert out["waiting"] == 0 and out["second"] == ["ab"]
    assert out["blur"] == ["ab", "abc"]


def test_a_save_asks_for_json(clock):
    out = clock("""
const real = global.fetch;
global.fetch = (url, opts) => { out.accept = opts.headers && opts.headers.Accept; out.url = url; return real(url, opts); };
field.value = "a"; handlers.blur(); await tick();
""")
    assert out["accept"] == "application/json" and out["url"] == "/item/x/mine/note"


def test_one_save_out_at_a_time_and_then_the_newest_text_not_the_reply(clock):
    out = clock("""
field.value = "a"; handlers.blur(); await tick();
field.value = "ab"; handlers.blur(); await tick();
field.value = "abc"; handlers.blur(); await tick();
out.whileOut = sent.map((s) => s.text);
answer(true); await tick(); await tick(); await tick();
out.after = sent.map((s) => s.text);
out.field = field.value;                         // the answer to "a" does not write "a" back
""")
    assert out["whileOut"] == ["a"]
    assert out["after"] == ["a", "abc"] and out["field"] == "abc"


def test_an_empty_box_marked_skip_empty_is_not_sent(clock):
    out = clock("""
field.hasAttribute = (name) => name === "data-skip-empty";
field.value = "   "; handlers.blur(); await tick();
visibility("hidden"); await tick();
out.empty = sent.length;
field.value = "Título"; handlers.blur(); await tick();
out.named = sent.map((s) => s.text);
""")
    assert out["empty"] == 0 and out["named"] == ["Título"]


def test_a_landed_save_toasts_only_what_the_server_warns(clock):
    out = clock("""
field.value = "a"; handlers.blur(); await tick();
answer(true); await tick(); await tick(); await tick();
out.quiet = toasts.slice();
field.value = "ab"; handlers.blur(); await tick();
answer(true, { notice: "Saved, but the indexes are behind." }); await tick(); await tick(); await tick();
out.warned = toasts.slice();
""")
    assert out["quiet"] == [] and out["warned"] == ["Saved, but the indexes are behind."]


def test_leaving_does_not_send_again_what_is_already_on_its_way(clock):
    out = clock("""
field.value = "a"; handlers.blur(); await tick();
visibility("hidden"); await tick();
out.sent = sent.map((s) => s.text);
""")
    assert out["sent"] == ["a"]


def test_what_needs_javascript_off_is_hidden_by_it(clock):
    out = clock("""
const nojs = [{ hidden: false }, { hidden: false }];
window.oknowledge.bind({ querySelectorAll: (sel) => (sel === "[data-nojs]" ? nojs : []) });
out.hidden = nojs.map((el) => el.hidden);
""")
    assert out["hidden"] == [True, True]


# --- final review I-1: revs are ordered within one page; stale is not "saved" ---------------

def test_every_save_of_a_page_carries_the_same_page_id(clock):
    """The server orders revs only among one page's saves: each page sends
    its own random id with them, the leave() path too."""
    out = clock("""
field.value = "a"; handlers.blur(); await tick();
field.value = "ab"; visibility("hidden"); await tick();
out.pages = sent.map((s) => s.page);
""")
    assert len(out["pages"]) == 2 and out["pages"][0] and out["pages"][0] == out["pages"][1]
    assert len(out["pages"][0]) >= 8


def test_a_stale_answer_this_page_did_not_cause_is_a_failure(clock):
    """Nothing newer went from this page: the text was not written, and the
    panel must not be told it was."""
    out = clock("""
field.value = "A"; handlers.blur(); await tick();
let told = "waiting";
window.oknowledge.settle(root).then((e) => { told = e ? e.message : null; });
answer(true, { stale: true }); await tick(); await tick(); await tick();
out.told = told;
out.toasts = toasts;
""")
    assert out["told"] == "No se pudo guardar" and out["toasts"] == ["No se pudo guardar"]


def test_a_stale_answer_behind_this_page_s_newer_save_is_superseded(clock):
    """A box swapped away and the new one of the same field: the old box's
    late save is stale because the page's newer one landed. That is not an
    error, and the old text is not sent again over the newer one."""
    out = clock("""
const field2 = Object.assign({}, field, { value: "", dataset: { autosave: "/item/x/mine/note" } });
const h2 = {};
field2.addEventListener = (t, f) => { h2[t] = f; };
window.oknowledge.bind({ querySelectorAll: (sel) => sel === "[data-autosave]" ? [field2] : [] });
field.value = "old"; handlers.blur(); await tick();
field2.value = "new"; h2.blur(); await tick();
out.revs = sent.map((s) => Number(s.rev));
held.push(held.shift());                    // the second is answered first
answer(true); await tick(); await tick();
answer(true, { stale: true }); await tick(); await tick(); await tick();
let told = "waiting";
window.oknowledge.settle({ querySelectorAll: () => [], contains: (f) => f === field }).then((e) => { told = e ? e.message : null; });
await tick(); await tick();
out.told = told;
out.toasts = toasts;
out.sent = sent.map((s) => s.text);
""")
    assert out["revs"][1] > out["revs"][0]
    assert out["told"] is None and out["toasts"] == [] and out["sent"] == ["old", "new"]
