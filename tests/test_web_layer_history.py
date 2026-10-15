"""The phone's layers and the browser's history (docs/2026-10-15-rediseno-celular-design.md
§6.3, §8), run in node over a fake page: app.js and shell.js together, a
session history that pushes, replaces and goes back and forward the way a
browser does (popstate comes later, never inside back()), and the 60rem
media query. Each scenario is a fresh page; what it prints is checked."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

# node is the one program these run, and nothing in it reaches the network:
# taken before conftest's guard swaps them for an alarm, and put back after it.
REAL = {name: getattr(subprocess, name) for name in ("run", "Popen")}

STATIC = Path(__file__).resolve().parent.parent / "src" / "oknowledge" / "web" / "static"

BROWSER = r"""
const fs = require("fs");
const APP = fs.readFileSync(process.argv[2], "utf8");
const SHELL = fs.readFileSync(process.argv[3], "utf8");
const SETUP = JSON.parse(process.argv[4]);
const ORIGIN = "http://t";
const out = {};
const settle = (ms) => new Promise((r) => setTimeout(r, ms || 30));

// --- the session history ----------------------------------------------------
const copy = (s) => (s === undefined || s === null ? null : JSON.parse(JSON.stringify(s)));
const rel = (url) => { const u = new URL(url, ORIGIN + entries[at].url); return u.pathname + u.search; };
const entries = SETUP.entries.map((e) => ({ url: e.url, state: copy(e.state) }));
let at = SETUP.at || 0;
const winOn = {};
global.window = global;
global.addEventListener = (type, fn) => { (winOn[type] = winOn[type] || []).push(fn); };
const fireWin = (type, event) => (winOn[type] || []).forEach((fn) => fn(event));
global.location = {
  get href() { return ORIGIN + entries[at].url; },
  set href(v) { out.navigated = rel(v); },
  get pathname() { return new URL(this.href).pathname; },
  get search() { return new URL(this.href).search; },
  reload() { out.reloaded = true; },
};
function travel(by) {
  setTimeout(() => {
    if (at + by < 0 || at + by >= entries.length) return;
    at += by;
    fireWin("popstate", { state: copy(entries[at].state) });
  }, 1);
}
global.history = {
  get state() { return copy(entries[at].state); },
  get length() { return entries.length; },
  pushState(state, _, url) { const to = rel(url); entries.splice(at + 1); entries.push({ url: to, state: copy(state) }); at += 1; },
  replaceState(state, _, url) { entries[at] = { url: url === undefined ? entries[at].url : rel(url), state: copy(state) }; },
  back() { travel(-1); },
  forward() { travel(1); },
};
const where = () => ({ url: entries[at].url, layer: (entries[at].state || {}).layer || "",
                       base: (entries[at].state || {}).base || "", at, length: entries.length });

// --- the 60rem query --------------------------------------------------------
const media = { matches: !SETUP.wide, fns: [],
  addEventListener(type, fn) { if (type === "change") this.fns.push(fn); }, addListener(fn) { this.fns.push(fn); } };
global.matchMedia = () => media;
function resize(phone) { media.matches = phone; media.fns.forEach((fn) => fn({ matches: phone })); }

// --- the page ---------------------------------------------------------------
function el(id, extra) {
  const attrs = {};
  const on = {};
  const classes = new Set();
  return Object.assign({
    id, attrs, dataset: {}, children: [], value: "", scrollTop: 0, tagName: "DIV",
    classList: { add: (c) => classes.add(c), remove: (c) => classes.delete(c), contains: (c) => classes.has(c),
                 toggle(c, f) { const w = f === undefined ? !classes.has(c) : !!f; if (w) classes.add(c); else classes.delete(c); return w; } },
    setAttribute(k, v) { attrs[k] = String(v); }, removeAttribute(k) { delete attrs[k]; },
    hasAttribute(k) { return k in attrs; }, getAttribute(k) { return k in attrs ? attrs[k] : null; },
    addEventListener(type, fn) { (on[type] = on[type] || []).push(fn); },
    dispatchEvent(event) { (on[event.type] || []).forEach((fn) => fn(event)); return true; },
    querySelector() { return null; }, querySelectorAll() { return []; },
    contains(x) { return x === this; }, closest() { return null; }, matches() { return false; },
    scrollIntoView() {}, focus() {}, replaceChildren() {}, appendChild() {}, remove() {},
  }, extra || {});
}

function link(attrs, inPanel) {
  const dataset = {};
  Object.keys(attrs).forEach((k) => { if (k.indexOf("data-") === 0) dataset[k.slice(5)] = attrs[k]; });
  const a = {
    attrs, dataset, inPanel: !!inPanel, href: new URL(attrs.href || "/", ORIGIN).href,
    hasAttribute: (k) => k in attrs, getAttribute: (k) => (k in attrs ? attrs[k] : null),
    matches: () => false,
    closest(sel) {
      return sel.split(",").some((one) => {
        const m = one.trim().match(/^a(?:\.[\w-]+)?\[([\w-]+)\]$/);
        return m && m[1] in attrs;
      }) ? a : null;
    },
  };
  return a;
}

const body = el("body", { tagName: "BODY" });
const items = el("items");
items.dataset.current = SETUP.current || "";
const list = el("list");
list.dataset.source = SETUP.source || "/lista";
let listHtml = "";
Object.defineProperty(list, "innerHTML", { get: () => listHtml, set: (h) => { listHtml = h; out.lists = (out.lists || 0) + 1; } });

const panel = el("panel");
panel.dataset.empty = "EMPTY";
let panelHtml = SETUP.panel || "";
const back = el("back");
back.setAttribute("href", "/back-the-server-drew");
Object.defineProperty(panel, "innerHTML", { get: () => panelHtml, set: (h) => { panelHtml = h; } });
panel.replaceChildren = function () { panelHtml = "EMPTY"; };
panel.contains = (x) => x === panel || !!(x && x.inPanel) || x === back;
panel.querySelector = (sel) => {
  const m = panelHtml.match(/^PANEL:(.*)$/);
  if (sel === "[data-panel]") return m ? { dataset: { panel: m[1] } } : panelHtml === "CATALOG" ? { dataset: { panel: "" } } : null;
  if (sel === '[data-panel=""]') return panelHtml === "CATALOG" ? { dataset: { panel: "" } } : null;
  if (sel === "a[data-back]") return panelHtml ? back : null;
  return null;
};
panel.querySelectorAll = () => [];
if (SETUP.open) panel.setAttribute("data-open", "");

const form = el("unified");
form.dataset.mode = SETUP.mode || "library";
form.setAttribute("action", SETUP.action || "/");
const field = el("field-q", { tagName: "INPUT", type: "text" });

const dialog = el("settings-modal", { open: false,
  showModal() { this.open = true; },
  close() { if (!this.open) return; this.open = false; this.dispatchEvent({ type: "close", target: this }); } });

const byId = { list, panel, unified: form, "field-q": field, items, "list-body": el("list-body"),
               "settings-modal": dialog };
const docOn = {};
global.document = {
  body, activeElement: body,
  getElementById: (id) => byId[id] || null,
  querySelector: (sel) => (sel === "dialog[open]" ? (dialog.open ? dialog : null) : null),
  querySelectorAll: () => [],
  createElement: (tag) => el("", { tagName: tag.toUpperCase() }),
  addEventListener(type, fn) { (docOn[type] = docOn[type] || []).push(fn); },
};
const fireDoc = (type, event) => (docOn[type] || []).forEach((fn) => fn(event));
global.CSS = { escape: (s) => s };

// --- the server ---------------------------------------------------------------
const asked = [];
const gone = new Set(SETUP.gone || []);
global.fetch = (url) => {
  asked.push(url);
  const path = new URL(url, ORIGIN).pathname;
  let status = 200;
  let text = "LIST";
  if (path.indexOf("/panel/") === 0) {
    const id = decodeURIComponent(path.slice(7));
    status = gone.has(id) ? 404 : 200;
    text = "PANEL:" + id;
  } else if (path === "/ocio/candidatos") {
    text = "CATALOG";
  }
  return Promise.resolve({ ok: status < 400, status, text: () => Promise.resolve(text),
                           json: () => Promise.resolve({ ok: true }) });
};

// --- acts -------------------------------------------------------------------
function click(target) {
  const event = { type: "click", target, button: 0, defaultPrevented: false,
                  preventDefault() { this.defaultPrevented = true; } };
  fireDoc("click", event);
  return event;
}
function key(name) {
  const event = { key: name, defaultPrevented: false, isComposing: false,
                  preventDefault() { this.defaultPrevented = true; } };
  fireDoc("keydown", event);
}
const tap = (id) => click(link({ href: "/?sel=" + id, "data-sel": id }));
const isOpen = () => panel.hasAttribute("data-open");
const page = () => Object.assign(where(), { open: isOpen(), top: ok.layers.top(), settings: dialog.open,
                                            panel: panelHtml });

window.oknowledge = { keys: {}, openSettings() { ok.openModal(dialog); } };
eval(APP);
eval(SHELL);
const ok = window.oknowledge;
fireDoc("DOMContentLoaded", {});
"""


@pytest.fixture(autouse=True)
def node_may_run(no_network_and_no_subprocess, monkeypatch):
    for name, real in REAL.items():
        monkeypatch.setattr(subprocess, name, real)


def run(tmp_path, scenario, **setup):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    setup.setdefault("entries", [{"url": "/", "state": None}])
    harness = tmp_path / "harness.js"
    harness.write_text(BROWSER + "(async () => {\n" + scenario +
                       "\nconsole.log(JSON.stringify(out));\n})().catch((e) => { console.error(e.stack); process.exit(1); });\n",
                       encoding="utf-8")
    done = subprocess.run([node, str(harness), str(STATIC / "app.js"), str(STATIC / "shell.js"),
                           json.dumps(setup)], capture_output=True, text=True, timeout=30, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


# --- the harness itself: a tap opens the layer and back shuts it ---------------------

def test_a_tap_pushes_the_layer_and_back_shuts_it(tmp_path):
    out = run(tmp_path, """
tap("a1"); await settle();
out.opened = page();
history.back(); await settle();
out.back = page();
""")
    assert out["opened"]["url"] == "/?sel=a1" and out["opened"]["layer"] == "panel"
    assert out["opened"]["open"] and out["opened"]["top"] == "panel"
    assert out["opened"]["panel"] == "PANEL:a1"
    assert out["back"]["url"] == "/" and not out["back"]["open"] and out["back"]["top"] == ""


# --- 1. forward onto Ajustes after a back and a reload ----------------------------------

SETTINGS_AHEAD = [{"url": "/", "state": None},
                  {"url": "/", "state": {"layer": "settings", "base": "http://t/"}}]


def test_forward_onto_ajustes_after_a_reload_opens_it_again(tmp_path):
    """The page was reloaded on the list with Ajustes' entry ahead: forward
    lands there with nothing open. It opens Ajustes, and back shuts it."""
    out = run(tmp_path, """
history.forward(); await settle();
out.forward = page();
history.back(); await settle();
out.back = page();
history.forward(); await settle();
out.again = page();
""", entries=SETTINGS_AHEAD, at=0)
    assert out["forward"]["settings"] and out["forward"]["top"] == "settings"
    assert out["forward"]["at"] == 1
    assert not out["back"]["settings"] and out["back"]["top"] == "" and out["back"]["at"] == 0
    assert out["again"]["settings"] and out["again"]["top"] == "settings"


def test_on_a_desktop_forward_onto_ajustes_opens_nothing(tmp_path):
    out = run(tmp_path, """
history.forward(); await settle();
out.forward = page();
""", entries=SETTINGS_AHEAD, at=0, wide=True)
    assert not out["forward"]["settings"] and out["forward"]["top"] == ""


# --- 2. the panel emptied under the open layer ------------------------------------------

def test_an_emptied_panel_leaves_a_forward_that_reopens_the_note(tmp_path):
    out = run(tmp_path, """
tap("a1"); await settle();
ok.list.empty(); await settle();
out.emptied = page();
history.forward(); await settle();
out.forward = page();
""")
    assert out["emptied"]["url"] == "/" and out["emptied"]["at"] == 0
    assert not out["emptied"]["open"]
    assert out["forward"]["url"] == "/?sel=a1" and out["forward"]["layer"] == "panel"
    assert out["forward"]["open"] and out["forward"]["panel"] == "PANEL:a1"


def test_forward_onto_a_note_that_is_gone_goes_back_to_the_list(tmp_path):
    """A 404 emptied the layer: forward tries the note, finds it gone, and
    shuts the layer again by back -- never a page load, never a dead entry."""
    out = run(tmp_path, """
tap("a1"); await settle();
gone.add("a1");
ok.list.empty(); await settle();
history.forward(); await settle(80);
out.forward = page();
out.navigated = out.navigated || "";
""")
    assert out["forward"]["at"] == 0 and out["forward"]["url"] == "/"
    assert not out["forward"]["open"] and out["forward"]["top"] == ""
    assert out["navigated"] == ""


# --- 3. forward onto the layer after a new filter ---------------------------------------

def test_forward_onto_the_layer_keeps_the_filter_chosen_since(tmp_path):
    out = run(tmp_path, """
tap("a1"); await settle();
out.opened = page();
history.back(); await settle();
click(link({ href: "/?cat=b", "data-nav": "" })); await settle();
out.filtered = page();
history.forward(); await settle();
out.forward = page();
history.back(); await settle();
out.back = page();
""", entries=[{"url": "/?cat=a", "state": None}])
    assert out["opened"]["url"] == "/?cat=a&sel=a1"
    assert out["filtered"]["url"] == "/?cat=b"
    assert out["forward"]["url"] == "/?cat=b&sel=a1" and out["forward"]["open"]
    assert out["forward"]["base"] == "http://t/?cat=b"
    assert out["back"]["url"] == "/?cat=b" and not out["back"]["open"]


# --- 4. a tag in the layer --------------------------------------------------------------

def test_after_a_tag_in_the_layer_forward_reopens_the_note_over_the_new_list(tmp_path):
    """The layer's entry cannot leave the history: forward onto it is the
    note that was being read, over the list the tag filtered."""
    out = run(tmp_path, """
tap("a1"); await settle();
click(link({ href: "/?tag=x", "data-nav": "" }, true)); await settle();
out.tagged = page();
history.forward(); await settle();
out.forward = page();
history.back(); await settle();
out.back = page();
""")
    assert out["tagged"]["url"] == "/?tag=x" and out["tagged"]["at"] == 0
    assert not out["tagged"]["open"]
    assert out["forward"]["url"] == "/?tag=x&sel=a1" and out["forward"]["open"]
    assert out["forward"]["panel"] == "PANEL:a1"
    assert out["back"]["url"] == "/?tag=x" and not out["back"]["open"]


# --- 5. a layer the screen outgrows -----------------------------------------------------

def test_a_layer_outgrown_past_60rem_lets_its_entry_go(tmp_path):
    """A tablet turned: the desktop has no layer, so Esc there must not go
    back (it would drop sel from the URL)."""
    out = run(tmp_path, """
tap("a1"); await settle();
resize(false); await settle();
out.wide = page();
key("Escape"); await settle();
out.esc = page();
""")
    assert out["wide"]["top"] == "" and out["wide"]["layer"] == ""
    assert out["wide"]["url"] == "/?sel=a1" and out["wide"]["at"] == 1
    assert out["esc"]["url"] == "/?sel=a1" and out["esc"]["at"] == 1


def test_ajustes_outgrown_stays_open_as_the_desktop_modal_and_its_entry_goes(tmp_path):
    out = run(tmp_path, """
ok.openSettings(); await settle();
out.opened = page();
resize(false); await settle();
out.wide = page();
dialog.close(); await settle();
out.closed = page();
""")
    assert out["opened"]["top"] == "settings" and out["opened"]["at"] == 1
    assert out["wide"]["settings"] and out["wide"]["top"] == ""
    assert out["wide"]["at"] == 0 and out["wide"]["url"] == "/"
    assert not out["closed"]["settings"] and out["closed"]["at"] == 0


# --- 6. the catalogs' way back ----------------------------------------------------------

def test_the_catalogs_way_back_keeps_the_list_s_filters(tmp_path):
    out = run(tmp_path, """
field.value = "dune";
const submit = { type: "submit", submitter: { id: "catalog-search" }, defaultPrevented: false,
                 preventDefault() { this.defaultPrevented = true; } };
form.dispatchEvent(submit); await settle();
out.searched = page();
out.href = back.getAttribute("href");
""", entries=[{"url": "/ocio?q=dune&estado=pending&orden=titulo", "state": None}],
        mode="ocio", action="/ocio", source="/ocio/lista")
    assert out["searched"]["url"] == "/ocio?q=dune&estado=pending&orden=titulo&buscar=dune&catalogo=movie"
    assert out["searched"]["open"] and out["searched"]["panel"] == "CATALOG"
    assert out["href"] == "/ocio?q=dune&estado=pending&orden=titulo"


# --- review M1: Ajustes widened and narrowed again ----------------------------------------

def test_ajustes_back_on_the_phone_after_a_rotation_gets_its_entry_again(tmp_path):
    """Back must close it, never leave the app."""
    out = run(tmp_path, """
ok.openSettings(); await settle();
resize(false); await settle();
resize(true); await settle();
out.narrow = page();
history.back(); await settle();
out.back = page();
""")
    assert out["narrow"]["settings"] and out["narrow"]["top"] == "settings"
    assert out["narrow"]["at"] == 1 and out["narrow"]["layer"] == "settings"
    assert not out["back"]["settings"] and out["back"]["at"] == 0 and out["back"]["top"] == ""


# --- polish D7: only a click that started on the backdrop closes the modal ------------------

def test_a_drag_released_on_the_backdrop_leaves_the_modal_open(tmp_path):
    out = run(tmp_path, """
dialog.matches = (sel) => sel === "dialog.modal[open]" && dialog.open;
ok.openSettings(); await settle();
fireDoc("pointerdown", { target: field });          // a text drag starts in a box...
fireDoc("pointerup", { target: dialog });
click(dialog);                                       // ...and ends on the backdrop
out.dragged = dialog.open;
fireDoc("pointerdown", { target: dialog });          // a click on the backdrop itself
fireDoc("pointerup", { target: dialog });
click(dialog);
out.clicked = dialog.open;
""", wide=True)
    assert out["dragged"] is True and out["clicked"] is False



def test_a_drag_from_the_backdrop_into_the_dialog_leaves_it_open(tmp_path):
    """Review M5: both the press and the release must be on the backdrop."""
    out = run(tmp_path, """
dialog.matches = (sel) => sel === "dialog.modal[open]" && dialog.open;
ok.openSettings(); await settle();
fireDoc("pointerdown", { target: dialog });
fireDoc("pointerup", { target: field });
click(dialog);
out.open = dialog.open;
""", wide=True)
    assert out["open"] is True


# --- the sidebar a list's answer brings (batch G) -----------------------------------------

SIDEBAR_SWAP = """
// A small tree: a box of named children, enough for what sideFilters() does.
function box(names) {
  const b = { kids: [] };
  const kid = (name) => ({ name, parent: b,
    remove() { const k = this.parent.kids; k.splice(k.indexOf(this), 1); },
    replaceWith(x) { if (x.parent) x.remove(); const k = this.parent.kids; k.splice(k.indexOf(this), 1, x); x.parent = this.parent; } });
  names.forEach((n) => b.kids.push(kid(n)));
  const match = (k, sel) => ({ "nav.sections": "sections", "nav.group": "group", ".foot": "foot" })[sel] === k.name.split(":")[0];
  b.querySelector = (sel) => b.kids.find((k) => match(k, sel)) || null;
  b.querySelectorAll = (sel) => b.kids.filter((k) => match(k, sel));
  b.insertBefore = (frag, ref) => {
    const moving = frag.kids.splice(0);
    moving.forEach((k) => { k.parent = b; });
    b.kids.splice(ref ? b.kids.indexOf(ref) : b.kids.length, 0, ...moving);
  };
  return b;
}
const sidebar = box(["logo", "sections:old", "group:old1", "group:old2", "foot"]);
let fresh = { content: box(FRESH), remove() { fresh = null; } };
list.querySelector = (sel) => (sel === "template#side-filters" ? fresh : null);
const before = document.querySelector;
document.querySelector = (sel) => (sel === ".sidebar" ? sidebar : before(sel));
ok.list.reload(); await settle();
out.side = sidebar.kids.map((k) => k.name);
"""


def test_a_list_s_answer_swaps_the_sections_counts_and_the_groups_in_place(tmp_path):
    """After a bulk action the list reloads: the sections (their counts) are
    replaced where they are, and the groups land before the foot -- never a
    second row of sections there."""
    out = run(tmp_path, 'const FRESH = ["sections:new", "group:new1", "group:new2"];' + SIDEBAR_SWAP)
    assert out["side"] == ["logo", "sections:new", "group:new1", "group:new2", "foot"]


def test_a_list_s_answer_without_sections_keeps_the_sidebar_s_own(tmp_path):
    out = run(tmp_path, 'const FRESH = ["group:new1"];' + SIDEBAR_SWAP)
    assert out["side"] == ["logo", "sections:old", "group:new1", "foot"]


# --- a reload that leaves the panel to its caller (batch G) --------------------------------

def test_a_reload_that_leaves_the_panel_asks_for_no_panel(tmp_path):
    """select.js reloads with leavePanel after a change to the open note,
    and picks the panel itself once the list is back: the list must not ask
    for the server's pick on its own first. A plain reload still does."""
    scenario = """
panelHtml = "PANEL:a1";
const before = asked.length;
ok.list.reload("", LEAVE); await settle();
out.panels = asked.slice(before).filter((u) => u.indexOf("/panel/") === 0);
out.panel = panelHtml;
"""
    left = run(tmp_path, "const LEAVE = true;" + scenario, wide=True, current="b2")
    assert left["panels"] == [] and left["panel"] == "PANEL:a1"
    plain = run(tmp_path, "const LEAVE = false;" + scenario, wide=True, current="b2")
    assert [u.split("?")[0] for u in plain["panels"]] == ["/panel/b2"]


# --- the list's reloads, on the desktop (batch G: these read shell.js's source before) -----

def test_a_search_carries_the_pick(tmp_path):
    """The search asks with the sel it was typed under, so a search with no
    matches leaves the note in the panel and clearing it comes back to it."""
    out = run(tmp_path, """
field.value = "vpn";
field.dispatchEvent({ type: "input" }); await settle(320);
out.lists = asked.filter((u) => u.indexOf("/lista") === 0);
""", entries=[{"url": "/?sel=a1", "state": None}], wide=True, panel="PANEL:a1", current="a1")
    assert len(out["lists"]) == 1
    assert "q=vpn" in out["lists"][0] and "sel=a1" in out["lists"][0]


def test_a_list_with_no_matches_does_not_empty_the_panel(tmp_path):
    out = run(tmp_path, """
ok.list.reload(); await settle();
out.panels = asked.filter((u) => u.indexOf("/panel/") === 0);
out.panel = panelHtml;
""", entries=[{"url": "/?q=zz&sel=a1", "state": None}], wide=True, panel="PANEL:a1", current="")
    assert out["panels"] == [] and out["panel"] == "PANEL:a1"


def test_a_list_reload_leaves_an_open_catalog_search_alone(tmp_path):
    out = run(tmp_path, """
ok.list.reload(); await settle();
out.panels = asked.filter((u) => u.indexOf("/panel/") === 0);
out.panel = panelHtml;
""", entries=[{"url": "/ocio?buscar=dune", "state": None}], wide=True, panel="CATALOG",
        current="c1", source="/ocio/lista", mode="ocio", action="/ocio")
    assert out["panels"] == [] and out["panel"] == "CATALOG"


def test_a_list_that_lands_after_another_pick_keeps_the_pick(tmp_path):
    """A list asked under sel=a1 that lands after the user picked b2 puts
    neither a1 back in the URL nor its panel."""
    out = run(tmp_path, """
const real = global.fetch;
let held = null;
global.fetch = (url) => (url.indexOf("/lista") === 0 && !held
  ? new Promise((r) => { held = () => r(real(url)); }) : real(url));
field.value = "vpn";
field.dispatchEvent({ type: "input" }); await settle(320);
tap("b2"); await settle();
held(); await settle();
out.where = where().url;
out.panel = panelHtml;
out.panels = asked.filter((u) => u.indexOf("/panel/") === 0).map((u) => u.split("?")[0]);
""", entries=[{"url": "/?sel=a1", "state": None}], wide=True, panel="PANEL:a1", current="a1")
    assert "sel=b2" in out["where"] and "q=vpn" in out["where"]
    assert out["panel"] == "PANEL:b2"
    assert out["panels"] == ["/panel/b2"]


# --- the tab bar follows the list shown (batch G: read in the source before) ---------------

TABS = """
const classOf = (on) => { const c = new Set(on ? ["on"] : []);
  return { toggle(n, f) { if (f) c.add(n); else c.delete(n); }, contains: (n) => c.has(n) }; };
const tabs = ["/", "/ocio", "/ideas", "/?mark=%E2%AD%90"].map((h, i) =>
  ({ href: ORIGIN + h, name: h, classList: classOf(i === LIT) }));
const all = document.querySelectorAll;
document.querySelectorAll = (sel) => (sel === ".tabbar a" ? tabs : all(sel));
ok.list.reload(); await settle();
out.lit = tabs.filter((t) => t.classList.contains("on")).map((t) => t.name);
"""


@pytest.mark.parametrize("url, source, lit", [
    ("/?vista=lista&mark=%E2%AD%90", "/lista", ["/?mark=%E2%AD%90"]),     # ★ carries vista: still Favoritos
    ("/?mark=%E2%AD%90&q=wire", "/lista", ["/"]),                         # a search is not Favoritos
    ("/?mark=%E2%AD%90&q=%20", "/lista", ["/?mark=%E2%AD%90"]),           # blanks are no search
    ("/?cat=Redes", "/lista", ["/"]),
    ("/ocio?tipo=book", "/ocio/lista", ["/ocio"]),
])
def test_the_tab_lit_is_read_from_the_list_s_path_and_mark(tmp_path, url, source, lit):
    out = run(tmp_path, "const LIT = 1;" + TABS, entries=[{"url": url, "state": None}],
              source=source)
    assert out["lit"] == lit
