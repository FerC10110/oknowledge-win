"""idea.js's poll of /actions/state (spec 2.2), run in node over a fake idea
screen: the polls are held and answered by the test, in the order it says,
and the 3 s interval is fired by hand."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "src" / "oknowledge" / "web" / "static" / "idea.js"

# node is the one program these run: taken before conftest's guard swaps
# them for an alarm, and put back after it (as test_web_layer_history does).
_REAL = {name: getattr(subprocess, name) for name in ("run", "Popen")}

HARNESS = r"""
const source = require("fs").readFileSync(process.argv[2], "utf8");
const SETUP = JSON.parse(process.argv[3]);
const tick = () => new Promise((r) => setTimeout(r, 0));
const settle = async () => { for (let i = 0; i < 6; i++) await tick(); };
let every = null;
global.setInterval = (fn) => { every = fn; return 1; };
global.clearInterval = () => { every = null; };
const docOn = {};
function el(id, dataset) {
  return { id, dataset: dataset || {}, hidden: false, classList: { toggle() {}, remove() {}, contains: () => false },
           replaceWith() {}, closest: () => null, matches: () => false };
}
const root = el("idea", { id: "i1" });
const bar = el("idea-ai", { running: SETUP.running, doneAs: "Listo: %1", failedAs: "Falló: %1",
                            nameImprove: "Mejoras", nameExpand: "Ampliación" });
const byId = { idea: root, "idea-ai": bar };
global.window = global;
global.location = { href: "http://t/ideas/i1" };
global.history = { state: null, replaceState() {} };
global.document = {
  getElementById: (id) => byId[id] || null,
  querySelectorAll: () => [],
  addEventListener: (type, fn) => { (docOn[type] = docOn[type] || []).push(fn); },
  adoptNode: (n) => n,
};
global.DOMParser = class { parseFromString() { return { getElementById: () => null }; } };
const polls = [];
global.fetch = (url) => {
  if (url.indexOf("/actions/state") >= 0) {
    return new Promise((resolve) => polls.push((state) => resolve({
      ok: true, status: 200, json: () => Promise.resolve(state) })));
  }
  return Promise.resolve({ ok: true, status: 200, text: () => Promise.resolve("") });
};
const toasts = [];
window.oknowledge = { toast: (t) => toasts.push(t), bind() {},
  post: () => Promise.resolve({ ok: true }) };
function run(action) {
  const form = { dataset: { runs: action }, matches: (s) => s === "form[data-json]", closest: () => null,
                 hasAttribute: () => false, classList: { contains: () => false } };
  (docOn.submit || []).forEach((fn) => fn({ target: form, preventDefault() {} }));
}
eval(source);
const out = {};
"""


@pytest.fixture
def idea(tmp_path, no_network_and_no_subprocess, monkeypatch):
    for name, real in _REAL.items():
        monkeypatch.setattr(subprocess, name, real)

    def go(scenario, running=""):
        node = shutil.which("node")
        if node is None:
            pytest.skip("node is not installed")
        harness = tmp_path / "harness.js"
        harness.write_text(HARNESS + "(async () => {\n" + scenario +
                           "\nconsole.log(JSON.stringify(out));\n})().catch((e) => { console.error(e.stack); process.exit(1); });\n",
                           encoding="utf-8")
        done = subprocess.run([node, str(harness), str(SCRIPT), json.dumps({"running": running})],
                              capture_output=True, text=True, timeout=30, check=False)
        assert done.returncode == 0, done.stderr
        return json.loads(done.stdout.strip().splitlines()[-1])
    return go


def test_an_answer_slower_than_the_interval_still_counts(idea):
    """A server slower than 3 s: the poll that left first answers after the
    next one left. It is the newest answer there is, and says "Listo"."""
    out = idea("""
every(); every();                         // two polls out, neither answered
polls[0]({ running: [], failed: [], title: "" }); await settle();
out.first = toasts.slice();
polls[1]({ running: [], failed: [], title: "" }); await settle();
out.both = toasts.slice();
out.polling = every !== null;
""", running="improve")
    assert out["first"] == ["Listo: Mejoras"]
    assert out["both"] == ["Listo: Mejoras"]          # said once
    assert out["polling"] is False


def test_an_older_answer_after_a_newer_one_is_dropped(idea):
    out = idea("""
every(); every();
polls[1]({ running: ["improve"], failed: [], title: "" }); await settle();
polls[0]({ running: [], failed: [], title: "" }); await settle();
out.toasts = toasts;
""", running="improve")
    assert out["toasts"] == []


def test_a_poll_that_left_before_an_action_started_does_not_end_it(idea):
    out = idea("""
every();                                  // left knowing only "improve"
run("expand"); await settle();
polls[0]({ running: ["improve"], failed: [], title: "" }); await settle();
out.early = toasts.slice();
every();
polls[1]({ running: [], failed: ["expand"], title: "" }); await settle();
out.late = toasts.slice();
""", running="improve")
    assert out["early"] == []
    assert out["late"] == ["Listo: Mejoras", "Falló: Ampliación"]


def test_a_refresh_that_fails_after_a_write_rejects_nothing(idea):
    """A tag added, then the screen cannot be read again (offline): refresh()
    ends in its own catch, so the "+ tag" focus after it never sees a
    rejection, and none goes unhandled (pendientes, batch G)."""
    out = idea("""
const unhandled = [];
process.on("unhandledRejection", (e) => unhandled.push(String(e)));
const focused = [];
byId["tag-add"] = { focus() { focused.push(1); } };
global.fetch = () => Promise.reject(new TypeError("Failed to fetch"));
const form = { dataset: {}, matches: (s) => s === "form[data-json]", closest: () => null,
               hasAttribute: () => false, classList: { contains: (c) => c === "tag-new" } };
(docOn.submit || []).forEach((fn) => fn({ target: form, preventDefault() {} }));
await settle(); await new Promise((r) => setTimeout(r, 20));
out.unhandled = unhandled; out.focused = focused.length;
""")
    assert out["unhandled"] == []
    assert out["focused"] == 1
