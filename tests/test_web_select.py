"""Multi-selection (spec §5): a checkbox outside the link on each item that
can be ticked, and one bar per section with that section's actions."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.ideas import new_idea
from oknowledge.model import Note
from oknowledge.vault import note_path, rebuild_indexes, write_note
from oknowledge.web.app import create_app

WEB = Path(__file__).resolve().parent.parent / "src" / "oknowledge" / "web"
SELECT = WEB / "static" / "select.js"
CARD = "c00000000001"


@pytest.fixture
def client(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    for id, category in (("a1", "Redes"), ("b2", "Cocina")):
        write_note(cfg, Note(id=id, url=f"https://e.com/{id}", title=f"T {id}", category=category,
                             tags=[], type="article", source="e.com", saved="2026-10-03",
                             summary="s"), "es")
    card = Note(id=CARD, url="https://www.imdb.com/title/tt1", title="Dune", category="Películas",
                tags=[], type="movie", source="imdb.com", saved="2026-10-02", summary="s",
                engine="")
    write_note(cfg, card, "es", path=note_path(cfg, card, shelf=cfg.ocio))
    idea = new_idea("Una idea.", "VPN", "2026-10-13", "2026-10-13T00:00:00.000001+00:00")
    write_note(cfg, idea, "es", path=note_path(cfg, idea, shelf=cfg.ideas))
    for shelf in (cfg.links, cfg.ocio, cfg.ideas):
        rebuild_indexes(cfg, "es", shelf=shelf)
    client = TestClient(create_app(cfg))
    client.idea = idea.id
    return client


def bar(body):
    return re.search(r'<form id="bulk".*?</form>', body, re.S).group(0)


def between(text, start, end):
    head = text.index(start)
    return text[head:text.index(end, head)]


# --- checkboxes ----------------------------------------------------------------------

@pytest.mark.parametrize("path, id, title", [("/", "a1", "T a1"), ("/?vista=lista", "a1", "T a1"),
                                             ("/ocio", CARD, "Dune"), ("/ideas", "idea", "VPN"),
                                             ("/ideas?vista=lista", "idea", "VPN")])
def test_each_item_has_its_checkbox_outside_the_link(client, path, id, title):
    id = client.idea if id == "idea" else id
    body = client.get(path).text
    item = re.search(rf'<li class="item[^"]*" id="(?:card|idea)-{id}".*?</li>', body, re.S).group(0)
    check = (f'<label class="check js-only"><input type="checkbox" name="ids" value="{id}" '
             f'form="bulk" aria-label="Select {title}"></label>')
    assert check in item
    assert item.index(check) < item.index('<a class="hit"')


def test_an_item_being_analysed_has_no_checkbox():
    text = (WEB / "templates" / "shelf-items.html").read_text(encoding="utf-8")
    assert 'class="check' not in between(text, "{% macro pending", "{%- endmacro %}")


def test_settings_and_the_idea_screen_have_no_bar(client):
    for path in ("/settings", f"/ideas/{client.idea}", "/retry"):
        assert 'id="bulk"' not in client.get(path).text, path


# --- the bar -------------------------------------------------------------------------------

def test_the_library_bar_moves_to_a_category_stars_and_deletes(client):
    found = bar(client.get("/").text)
    assert 'class="bulk js-only"' in found and " hidden" in found
    assert 'data-one="1 selected" data-many="%1 selected"' in found
    assert 'formaction="/bulk/category" name="category" value="Redes"' in found
    assert 'formaction="/bulk/category" name="category" value="Cocina"' in found
    assert 'name="new_category"' in found
    assert 'formaction="/bulk/mark" name="mark" value="⭐"' in found
    assert 'formaction="/bulk/delete"' in found and "data-clear" in found
    # The hidden first button: Enter in "New category" moves.
    assert found.index('class="default-submit"') < found.index('name="new_category"')


def test_the_ocio_bar_changes_the_kind_and_has_no_star(client):
    found = bar(client.get("/ocio").text)
    for kind in ("movie", "series", "anime", "book"):
        assert f'formaction="/bulk/kind" name="kind" value="{kind}"' in found
    assert "/bulk/mark" not in found and "/bulk/category" not in found
    assert 'formaction="/bulk/delete"' in found


def test_the_ideas_bar_changes_the_state_and_has_no_star(client):
    found = bar(client.get("/ideas").text)
    for state in ("pending", "doing", "done", "dropped"):
        assert f'formaction="/bulk/state" name="state" value="{state}"' in found
    assert "/bulk/mark" not in found and "/bulk/kind" not in found
    assert 'formaction="/bulk/delete"' in found


@pytest.mark.parametrize("path", ["/", "/ocio", "/ideas"])
def test_select_js_comes_after_shell_js(client, path):
    body = client.get(path).text
    assert (body.index('<script src="/static/shell.js" defer></script>')
            < body.index('<script src="/static/select.js" defer></script>'))


# --- select.js: its behaviour is in node, below (batch G) ---------------------------------


# --- fix round 1 -------------------------------------------------------------------------

@pytest.mark.parametrize("name, macro", [("shelf-items.html", "{% macro item"),
                                         ("posters.html", "{% macro poster")])
def test_a_note_being_reanalysed_has_no_checkbox(name, macro):
    text = between((WEB / "templates" / name).read_text(encoding="utf-8"), macro, "{%- endmacro %}")
    guarded = re.search(r"\{%- if note\.id not in busy %\}\s*<label class=\"check js-only\">.*?</label>"
                        r"\s*\{%- endif %\}", text, re.S)
    assert guarded, name


def test_the_list_leaves_room_for_the_bar_while_picking():
    css = (WEB / "static" / "app.css").read_text(encoding="utf-8")
    assert re.search(r"#list\.picking \.list-body \{ padding-bottom: \d+px; \}", css)


# --- final fix pass: one bulk send at a time, in node --------------------------------------

SENDING_HARNESS = r"""
const source = require("fs").readFileSync(process.argv[2], "utf8");
const out = { sends: [], toasts: [], undos: [] };
const listeners = {};
const on = (name) => (type, fn) => { (listeners[name + ":" + type] = listeners[name + ":" + type] || []).push(fn); };
const button = (formaction) => ({ disabled: false, getAttribute: (a) => (a === "formaction" ? formaction : null) });
const del = button("/bulk/delete"), star = button("/bulk/mark"), clr = button(null);
const boxes = ["a1", "b2"].map((value) => ({ value, checked: false, matches: () => true, closest: () => null }));
const bar = {
  hidden: true, dataset: { one: "1", many: "%1" }, elements: { back: { value: "" } },
  addEventListener: on("bar"), getAttribute: () => "/bulk/category",
  querySelector: (sel) => (sel === "[data-count]" ? { textContent: "" }
                           : sel === 'button[formaction="/bulk/delete"]' ? del : null),
  querySelectorAll: (sel) => [del, star, clr],
  classList: { toggle() {}, add() {}, remove() {} },
};
const list = { addEventListener: on("list"), querySelectorAll: () => boxes, querySelector: () => null,
               classList: { toggle() {}, contains: () => false } };
global.window = global;
global.location = { pathname: "/", search: "" };
global.FormData = function () { this.delete = () => {}; this.append = () => {}; };
global.document = { getElementById: (id) => ({ bulk: bar, list: list }[id] || null) };
let answer = null;
window.oknowledge = {
  keys: {}, closeMenus() {}, toast: (t) => out.toasts.push(t),
  offerUndo: (t, token) => out.undos.push(token),
  send: (url) => { out.sends.push(url); return new Promise((r) => { answer = r; }); },
  list: { current: () => "", shown: () => [], reload: () => Promise.resolve(), pick() {}, empty() {} },
};
eval(source);
const ok = window.oknowledge;
const tick = (id) => listeners["list:change"].forEach((fn) => fn({ target: boxes.find((b) => b.value === id) && Object.assign(boxes.find((b) => b.value === id), { checked: true }) }));
const press = (key, repeat) => ok.keys[key]({ key, repeat: !!repeat });
const click = (submitter) => listeners["bar:submit"].forEach((fn) => fn({ preventDefault() {}, submitter }));
(async () => {
  tick("a1"); tick("b2");
  out.repeat = press("Backspace", true);
  out.afterRepeat = out.sends.length;
  press("Backspace");
  out.disabled = [del.disabled, star.disabled, clr.disabled];
  press("Backspace"); press("Delete"); click(del); click(star);
  out.whileSending = out.sends.slice();
  answer({ notice: "Borradas", undo: "tok" });
  await new Promise((r) => setTimeout(r, 10));
  out.enabled = [del.disabled, star.disabled, clr.disabled];
  out.after = out.undos.slice();
  console.log(JSON.stringify(out));
  process.exit(0);
})();
"""


@pytest.fixture(scope="module")
def sending(tmp_path_factory):
    import json
    import shutil
    import subprocess
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    harness = tmp_path_factory.mktemp("sending") / "harness.js"
    harness.write_text(SENDING_HARNESS, encoding="utf-8")
    done = subprocess.run([node, str(harness), str(SELECT)], capture_output=True, text=True,
                          timeout=30, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_a_held_backspace_does_not_delete(sending):
    assert sending["afterRepeat"] == 0


def test_a_bulk_send_is_one_at_a_time(sending):
    assert sending["whileSending"] == ["/bulk/delete"]
    assert sending["after"] == ["tok"]


def test_the_bar_is_disabled_while_sending_and_back_after(sending):
    assert sending["disabled"] == [True, True, True]
    assert sending["enabled"] == [False, False, False]


# --- delivery 4: the phone's selection mode, in node --------------------------------------

MODE_HARNESS = r"""
const source = require("fs").readFileSync(process.argv[2], "utf8");
const out = {};
const listeners = {};
const on = (name) => (type, fn) => { (listeners[name + ":" + type] = listeners[name + ":" + type] || []).push(fn); };
const classes = new Set();
const classList = {
  toggle(c, force) { const want = force === undefined ? !classes.has(c) : !!force; if (want) classes.add(c); else classes.delete(c); return want; },
  contains: (c) => classes.has(c), add: (c) => classes.add(c), remove: (c) => classes.delete(c),
};
const button = { dataset: { on: "Cancelar" }, textContent: "Seleccionar", attrs: {},
                 setAttribute(k, v) { this.attrs[k] = v; },
                 closest: (sel) => (sel === "[data-select-mode]" ? button : null) };
function item(id) {
  const li = { classList: { toggle() {} }, querySelector: () => box };
  const box = { value: id, checked: false, matches: () => true, closest: () => li };
  const hit = { closest: (sel) => (sel === "a.hit" ? hit : sel === "li.item" ? li : null) };
  return { box, li, hit };
}
const a = item("a1"), b = item("b2");
const pending = { closest: (sel) => (sel === "a.hit" ? pending : sel === "li.item" ? { querySelector: () => null } : null) };
const bar = { hidden: true, dataset: { one: "1", many: "%1" }, elements: { back: { value: "" } },
              addEventListener: on("bar"), getAttribute: () => "/bulk/category",
              querySelector: (sel) => (sel === "[data-count]" ? { textContent: "" } : null),
              querySelectorAll: () => [], classList: { toggle() {} } };
const list = { addEventListener: on("list"), querySelectorAll: () => [a.box, b.box],
               querySelector: (sel) => (sel === "[data-select-mode]" ? button : null), classList };
global.window = global;
global.location = { pathname: "/", search: "" };
global.document = { getElementById: (id) => ({ bulk: bar, list: list }[id] || null) };
window.oknowledge = { keys: {}, closeMenus() {}, toast() {}, list: { current: () => "", shown: () => [] } };
eval(source);
const ok = window.oknowledge;
function tap(target) {
  const event = { target, defaultPrevented: false, stopped: false,
                  preventDefault() { this.defaultPrevented = true; }, stopPropagation() { this.stopped = true; } };
  (listeners["list:click"] || []).forEach((fn) => fn(event));
  return event;
}
const told = (reason) => listeners["list:oknowledge:list"].forEach((fn) => fn({ detail: { reason } }));
out.drawn = [button.textContent, button.attrs["aria-pressed"]];
out.off = tap(a.hit).defaultPrevented;                       // not selecting: shell.js opens it
tap(button);
out.on = [classes.has("selecting"), button.textContent, button.attrs["aria-pressed"]];
const ticked = tap(a.hit);
out.tapTicks = [ticked.defaultPrevented, ticked.stopped, a.box.checked, bar.hidden];
tap(a.hit);
out.tapAgainUnticks = [a.box.checked, bar.hidden];
const busy = tap(pending);
out.pendingIgnored = [busy.defaultPrevented, a.box.checked, b.box.checked];
tap(b.hit);
ok.keys.Escape();
out.escLeaves = [classes.has("selecting"), b.box.checked, button.textContent, bar.hidden];
tap(button);
out.escEmpty = [ok.keys.Escape() !== false, classes.has("selecting")];
tap(button); tap(a.hit);
told("filter");
out.filterLeaves = [classes.has("selecting"), a.box.checked];
tap(button);
button.textContent = "Seleccionar";                          // the server drew the head again
told("refresh");
out.refreshKeeps = [classes.has("selecting"), button.textContent];
tap(button);
out.cancel = [classes.has("selecting"), button.textContent, button.attrs["aria-pressed"]];
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def mode(tmp_path_factory):
    import json
    import shutil
    import subprocess
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    harness = tmp_path_factory.mktemp("mode") / "harness.js"
    harness.write_text(MODE_HARNESS, encoding="utf-8")
    done = subprocess.run([node, str(harness), str(SELECT)], capture_output=True, text=True,
                          timeout=30, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_the_button_is_drawn_off(mode):
    assert mode["drawn"] == ["Seleccionar", "false"]


def test_seleccionar_turns_the_mode_on(mode):
    assert mode["off"] is False
    assert mode["on"] == [True, "Cancelar", "true"]


def test_a_tap_in_the_mode_ticks_and_never_opens(mode):
    """Review Focus 4: prevented and stopped before shell.js sees it."""
    assert mode["tapTicks"] == [True, True, True, False]
    assert mode["tapAgainUnticks"] == [False, True]
    assert mode["pendingIgnored"] == [True, False, False]


def test_every_way_out_leaves_the_mode_and_clears(mode):
    assert mode["escLeaves"] == [False, False, "Seleccionar", True]
    assert mode["escEmpty"] == [True, False]
    assert mode["filterLeaves"] == [False, False]
    assert mode["cancel"] == [False, "Seleccionar", "false"]


def test_a_refresh_keeps_the_mode_and_redraws_the_new_button(mode):
    assert mode["refreshKeeps"] == [True, "Cancelar"]


# --- fix round 1: the mode does not outlive the phone ----------------------------

MEDIA_PREFIX = r"""
const media = { matches: true, fns: [], addEventListener(type, fn) { if (type === "change") this.fns.push(fn); } };
global.matchMedia = (query) => { media.query = query; return media; };
"""

MEDIA_SUFFIX = r"""
const wide = {};
tap(button); tap(a.hit);
media.matches = false;
media.fns.forEach((fn) => fn({ matches: false }));
wide.left = [media.query, classes.has("selecting"), a.box.checked, bar.hidden, button.textContent];
wide.tapOpens = tap(b.hit).defaultPrevented;
media.matches = true;
media.fns.forEach((fn) => fn({ matches: true }));
wide.backNarrow = classes.has("selecting");
console.log(JSON.stringify(wide));
"""


@pytest.fixture(scope="module")
def widened(tmp_path_factory):
    import json
    import shutil
    import subprocess
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    harness = tmp_path_factory.mktemp("media") / "harness.js"
    harness.write_text(MEDIA_PREFIX + MODE_HARNESS + MEDIA_SUFFIX, encoding="utf-8")
    done = subprocess.run([node, str(harness), str(SELECT)], capture_output=True, text=True,
                          timeout=30, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_growing_past_the_phone_leaves_the_mode(widened):
    """A tablet turned past 60rem: Cancelar is not drawn there, so the mode goes."""
    assert widened["left"] == ["(max-width: 60rem)", False, False, True, "Seleccionar"]
    assert widened["tapOpens"] is False
    assert widened["backNarrow"] is False


# --- phone follow-ups: a long press also enters the mode, in node ---------------------

TIMER_PREFIX = r"""
let clock = 0;
const timers = [];
global.setTimeout = (fn, ms) => { timers.push({ fn, at: clock + (ms || 0) }); return timers.length; };
global.clearTimeout = (id) => { if (timers[id - 1]) timers[id - 1].fn = null; };
function advance(ms) {
  clock += ms;
  timers.forEach((t) => { if (t.fn && t.at <= clock) { const fn = t.fn; t.fn = null; fn(); } });
}
"""

LONG_SUFFIX = r"""
const long = {};
function press(type, target, x, y, extra) {
  const event = Object.assign({ type, target, clientX: x, clientY: y, pointerId: 1, isPrimary: true,
                                button: 0, pointerType: "touch", defaultPrevented: false, stopped: false,
                                preventDefault() { this.defaultPrevented = true; },
                                stopPropagation() { this.stopped = true; } }, extra || {});
  (listeners["list:" + type] || []).forEach((fn) => fn(event));
  return event;
}
// A tap held less than the press: nothing.
press("pointerdown", a.hit, 100, 100); advance(300); press("pointerup", a.hit, 100, 100);
long.shortTap = [classes.has("selecting"), tap(a.hit).defaultPrevented];
long.bareMenu = press("contextmenu", a.hit, 100, 100).defaultPrevented;
// Held, wobbling a few px: the mode, the item ticked.
press("pointerdown", a.hit, 100, 100); advance(300); press("pointermove", a.hit, 106, 104); advance(250);
long.held = [classes.has("selecting"), a.box.checked, button.textContent, button.attrs["aria-pressed"], bar.hidden];
long.menu = press("contextmenu", a.hit, 106, 104).defaultPrevented;
press("pointerup", a.hit, 106, 104);
const swallowed = tap(a.hit);
long.clickSwallowed = [swallowed.defaultPrevented, swallowed.stopped, a.box.checked, classes.has("selecting")];
const other = tap(b.hit);
long.nextTapTicks = [other.defaultPrevented, b.box.checked, a.box.checked];
// In the mode a long press adds nothing: its click is a tap like any other.
press("pointerdown", b.hit, 50, 50); advance(700); press("pointerup", b.hit, 50, 50);
const again = tap(b.hit);
long.inMode = [again.defaultPrevented, b.box.checked, a.box.checked, classes.has("selecting")];
ok.keys.Escape();
// A scroll: the finger moved past 10 px.
press("pointerdown", a.hit, 100, 100); advance(200); press("pointermove", a.hit, 100, 125); advance(600);
press("pointerup", a.hit, 100, 125);
long.scroll = [classes.has("selecting"), a.box.checked];
// The browser took the gesture.
press("pointerdown", a.hit, 100, 100); advance(200); press("pointercancel", a.hit, 100, 100); advance(600);
long.cancelled = [classes.has("selecting"), a.box.checked];
// Released before the time: gone, even if the timer would have run.
press("pointerdown", a.hit, 100, 100); advance(100); press("pointerup", a.hit, 100, 100); advance(600);
long.released = classes.has("selecting");
// One being analysed has no box: ignored.
press("pointerdown", pending, 100, 100); advance(700);
long.pending = [classes.has("selecting"), press("contextmenu", pending, 100, 100).defaultPrevented];
press("pointerup", pending, 100, 100);
long.pendingTap = tap(pending).defaultPrevented;
// A mouse's right button is not a press.
press("pointerdown", a.hit, 100, 100, { button: 2, pointerType: "mouse" }); advance(700);
long.rightButton = classes.has("selecting");
press("pointerup", a.hit, 100, 100, { button: 2, pointerType: "mouse" });
// The desktop: nothing at all.
media.matches = false;
press("pointerdown", a.hit, 100, 100); advance(700);
long.desktop = [classes.has("selecting"), a.box.checked, press("contextmenu", a.hit, 100, 100).defaultPrevented];
press("pointerup", a.hit, 100, 100);
long.desktopTap = tap(a.hit).defaultPrevented;
console.log(JSON.stringify(long));
"""


@pytest.fixture(scope="module")
def long_press(tmp_path_factory):
    import json
    import shutil
    import subprocess
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    harness = tmp_path_factory.mktemp("long") / "harness.js"
    harness.write_text(MEDIA_PREFIX + TIMER_PREFIX + MODE_HARNESS + LONG_SUFFIX, encoding="utf-8")
    done = subprocess.run([node, str(harness), str(SELECT)], capture_output=True, text=True,
                          timeout=30, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_a_short_tap_is_not_a_long_press(long_press):
    assert long_press["shortTap"] == [False, False]
    assert long_press["bareMenu"] is False
    assert long_press["released"] is False


def test_a_long_press_enters_the_mode_and_ticks_the_item(long_press):
    assert long_press["held"] == [True, True, "Cancelar", "true", False]
    assert long_press["menu"] is True


def test_the_click_after_a_long_press_is_swallowed_once(long_press):
    """It must neither open the item (shell.js) nor untick it (the mode's tap)."""
    assert long_press["clickSwallowed"] == [True, True, True, True]
    assert long_press["nextTapTicks"] == [True, True, True]


def test_a_long_press_in_the_mode_adds_nothing(long_press):
    assert long_press["inMode"] == [True, False, True, True]


def test_a_scroll_or_a_cancel_is_not_a_long_press(long_press):
    assert long_press["scroll"] == [False, False]
    assert long_press["cancelled"] == [False, False]
    assert long_press["rightButton"] is False


def test_a_long_press_ignores_one_being_analysed(long_press):
    assert long_press["pending"] == [False, False]
    assert long_press["pendingTap"] is False


def test_the_desktop_has_no_long_press(long_press):
    assert long_press["desktop"] == [False, False, False]
    assert long_press["desktopTap"] is False


# --- fix round 1: Android's menu comes before the 500 ms ------------------------------

EARLY_SUFFIX = r"""
const early = {};
function send(type, target, extra) {
  const event = Object.assign({ type, target, clientX: 100, clientY: 100, pointerId: 1, isPrimary: true,
                                button: 0, pointerType: "touch", defaultPrevented: false,
                                preventDefault() { this.defaultPrevented = true; },
                                stopPropagation() {} }, extra || {});
  (listeners["list:" + type] || []).forEach((fn) => fn(event));
  return event;
}
send("pointerdown", a.hit); advance(400);
const menu = send("contextmenu", a.hit);
early.menu = [menu.defaultPrevented, classes.has("selecting"), a.box.checked];
send("pointercancel", a.hit); advance(600);
early.afterCancel = [classes.has("selecting"), a.box.checked];
ok.keys.Escape();
media.matches = false;
send("pointerdown", a.hit); advance(100);
early.desktop = [send("contextmenu", a.hit).defaultPrevented, classes.has("selecting")];
send("pointerup", a.hit);
console.log(JSON.stringify(early));
"""


@pytest.fixture(scope="module")
def early_menu(tmp_path_factory):
    import json
    import shutil
    import subprocess
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    harness = tmp_path_factory.mktemp("early") / "harness.js"
    harness.write_text(MEDIA_PREFIX + TIMER_PREFIX + MODE_HARNESS + EARLY_SUFFIX, encoding="utf-8")
    done = subprocess.run([node, str(harness), str(SELECT)], capture_output=True, text=True,
                          timeout=30, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_a_menu_before_the_500_ms_fires_the_press(early_menu):
    """Android sends contextmenu about when our timer runs, then pointercancel."""
    assert early_menu["menu"] == [True, True, True]
    assert early_menu["afterCancel"] == [True, True]


def test_the_desktop_menu_is_left_alone(early_menu):
    assert early_menu["desktop"] == [False, False]


# --- polish: a desktop selection that shrinks onto the phone ----------------------------

SHRUNK_SUFFIX = r"""
const shrunk = {};
media.matches = false;                               // the desktop
listeners["list:change"].forEach((fn) => fn({ target: Object.assign(a.box, { checked: true }) }));
shrunk.desk = [classes.has("selecting"), bar.hidden];
media.matches = true;                                // the window made narrow
media.fns.forEach((fn) => fn({ matches: true }));
shrunk.phone = [classes.has("selecting"), a.box.checked, bar.hidden, button.textContent,
                button.attrs["aria-pressed"]];
const shrunkTap = tap(b.hit);
shrunk.tapTicks = [shrunkTap.defaultPrevented, b.box.checked];
ok.keys.Escape();
media.matches = false; media.fns.forEach((fn) => fn({ matches: false }));
media.matches = true; media.fns.forEach((fn) => fn({ matches: true }));
shrunk.emptyStaysOff = classes.has("selecting");
console.log(JSON.stringify(shrunk));
"""


@pytest.fixture(scope="module")
def shrunk(tmp_path_factory):
    import json
    import shutil
    import subprocess
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    harness = tmp_path_factory.mktemp("shrunk") / "harness.js"
    harness.write_text(MEDIA_PREFIX + MODE_HARNESS + SHRUNK_SUFFIX, encoding="utf-8")
    done = subprocess.run([node, str(harness), str(SELECT)], capture_output=True, text=True,
                          timeout=30, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_a_selection_that_shrinks_onto_the_phone_enters_the_mode(shrunk):
    """The boxes would be hidden and a tap would open the layer: the mode
    shows them, with Cancelar, and a tap ticks."""
    assert shrunk["desk"] == [False, False]
    assert shrunk["phone"] == [True, True, False, "Cancelar", "true"]
    assert shrunk["tapTicks"] == [True, True]


def test_shrinking_with_nothing_ticked_enters_no_mode(shrunk):
    assert shrunk["emptyStaysOff"] is False


# --- delivery 6, batch C: what a bulk action leaves behind, in node -------------------------

LEFTOVERS_HARNESS = r"""
const source = require("fs").readFileSync(process.argv[2], "utf8");
const out = { reloads: [], picks: [], empties: 0 };
const listeners = {};
const on = (name) => (type, fn) => { (listeners[name + ":" + type] = listeners[name + ":" + type] || []).push(fn); };
const button = (formaction) => ({ disabled: false, getAttribute: (a) => (a === "formaction" ? formaction : null) });
const move = button("/bulk/category");
const boxes = ["a1", "b2", "c3"].map((value) => ({ value, checked: false, matches: () => true, closest: () => null }));
const bar = {
  hidden: true, dataset: { one: "1", many: "%1" }, elements: { back: { value: "" } },
  addEventListener: on("bar"), getAttribute: () => "/bulk/category",
  querySelector: (sel) => (sel === "[data-count]" ? { textContent: "" } : null),
  querySelectorAll: () => [move],
  classList: { toggle() {}, add() {}, remove() {} },
};
const list = { addEventListener: on("list"), querySelectorAll: () => boxes, querySelector: () => null,
               classList: { toggle() {}, contains: () => false } };
global.window = global;
global.location = { pathname: "/", search: "" };
global.FormData = function () { this.delete = () => {}; this.append = () => {}; };
global.document = { getElementById: (id) => ({ bulk: bar, list: list }[id] || null) };
let answer = null, current = "a1", shown = ["a1", "b2", "c3"];
window.oknowledge = {
  keys: {}, closeMenus() {}, toast() {}, offerUndo() {},
  send: () => new Promise((r) => { answer = r; }),
  list: {
    current: () => current,
    shown: () => shown.map((id) => ({ id: "card-" + id })),
    reload: (...args) => { out.reloads.push(args); shown = ["b2", "c3"]; return Promise.resolve(); },
    pick: (id) => out.picks.push(id),
    empty: () => { out.empties += 1; },
  },
};
eval(source);
const ok = window.oknowledge;
const tick = (id) => listeners["list:change"].forEach((fn) => fn({ target: Object.assign(boxes.find((b) => b.value === id), { checked: true }) }));
const click = () => listeners["bar:submit"].forEach((fn) => fn({ preventDefault() {}, submitter: move }));
(async () => {
  tick("a1");                       // the open one: a1, which the move takes out of the list
  click();
  current = "c3";
  ok.keys.x();                      // ticked with x while the move travels
  out.whileSending = boxes.map((b) => b.checked);
  answer({ notice: "1 moved" });
  await new Promise((r) => setTimeout(r, 10));
  out.after = boxes.map((b) => b.checked);
  out.barHidden = bar.hidden;
  console.log(JSON.stringify(out));
  process.exit(0);
})();
"""


@pytest.fixture(scope="module")
def leftovers(tmp_path_factory):
    import json
    import shutil
    import subprocess
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    harness = tmp_path_factory.mktemp("leftovers") / "harness.js"
    harness.write_text(LEFTOVERS_HARNESS, encoding="utf-8")
    done = subprocess.run([node, str(harness), str(SELECT)], capture_output=True, text=True,
                          timeout=30, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_a_box_ticked_while_a_bulk_action_travels_is_kept(leftovers):
    assert leftovers["whileSending"] == [True, False, True]
    assert leftovers["after"] == [False, False, True]
    assert leftovers["barHidden"] is False


def test_moving_the_open_note_out_of_the_list_asks_for_the_panel_once(leftovers):
    # The list is told to leave the panel to select.js, which picks the next one.
    assert leftovers["reloads"] == [["", True]]
    assert leftovers["picks"] == ["b2"]


# --- review I1: a shrink's mode leaves without the ticks it did not make -------------------

ROUND_TRIP_SUFFIX = r"""
const trip = {};
media.matches = false;
listeners["list:change"].forEach((fn) => fn({ target: Object.assign(a.box, { checked: true }) }));
media.matches = true; media.fns.forEach((fn) => fn({ matches: true }));
trip.narrow = [classes.has("selecting"), a.box.checked];
media.matches = false; media.fns.forEach((fn) => fn({ matches: false }));
trip.wideAgain = [classes.has("selecting"), a.box.checked, bar.hidden, button.textContent];
ok.keys.Escape();
// A mode turned on by hand on the phone still clears when the screen grows.
media.matches = true; media.fns.forEach((fn) => fn({ matches: true }));
tap(button); tap(a.hit);
media.matches = false; media.fns.forEach((fn) => fn({ matches: false }));
trip.handMode = [classes.has("selecting"), a.box.checked];
console.log(JSON.stringify(trip));
"""


@pytest.fixture(scope="module")
def round_trip(tmp_path_factory):
    import json
    import shutil
    import subprocess
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    harness = tmp_path_factory.mktemp("trip") / "harness.js"
    harness.write_text(MEDIA_PREFIX + MODE_HARNESS + ROUND_TRIP_SUFFIX, encoding="utf-8")
    done = subprocess.run([node, str(harness), str(SELECT)], capture_output=True, text=True,
                          timeout=30, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_a_desktop_selection_survives_a_narrow_and_back_resize(round_trip):
    assert round_trip["narrow"] == [True, True]
    assert round_trip["wideAgain"] == [False, True, False, "Seleccionar"]


def test_a_mode_entered_on_the_phone_still_clears_when_the_screen_grows(round_trip):
    assert round_trip["handMode"] == [False, False]


# --- batch G: select.js over app.js, in node ----------------------------------------------
# One harness for what the bar does: app.js is the real one (its toast, its
# send, its Deshacer), the server and shell.js's list are fakes that write
# down what they were asked. Each scenario is a fresh page.

APP = WEB / "static" / "app.js"

BULK_HARNESS = r"""
const fs = require("fs");
const APP = fs.readFileSync(process.argv[2], "utf8");
const SELECT = fs.readFileSync(process.argv[3], "utf8");
const out = { fetched: [], toasts: [], reloads: [], picks: [], empties: 0, cleared: 0 };
const settle = (ms) => new Promise((r) => setTimeout(r, ms || 15));
const listeners = {};
const on = (name) => (type, fn) => { (listeners[name + ":" + type] = listeners[name + ":" + type] || []).push(fn); };

// --- the toast: what it says, and its button --------------------------------
let undoButton = null;
const toastEl = {
  hidden: true, classList: { add() {}, remove() {} },
  replaceChildren(...kids) { undoButton = null; if (kids.length) out.toasts.push(kids[0].textContent); },
  appendChild(kid) { undoButton = kid; }, querySelector: () => null,
};
const element = () => { const fns = {}; return { textContent: "", className: "",
  addEventListener(type, fn) { fns[type] = fn; }, click() { fns.click(); } }; };

// --- the bar and the list ------------------------------------------------------
const button = (formaction) => ({ disabled: false, getAttribute: (a) => (a === "formaction" ? formaction : null) });
const buttons = { move: button("/bulk/category"), star: button("/bulk/mark"), del: button("/bulk/delete") };
let count = "";
const bar = {
  hidden: true, dataset: { one: "1", many: "%1" },
  elements: { back: { value: "" }, new_category: { value: "typed" } },
  addEventListener: on("bar"), getAttribute: () => "/bulk/category",
  querySelector: (sel) => (sel === "[data-count]" ? { set textContent(v) { count = v; } }
                           : sel === 'button[formaction="/bulk/delete"]' ? buttons.del : null),
  querySelectorAll: () => Object.values(buttons),
  classList: { toggle() {} },
};
let ids = ["a1", "b2", "c3"];
const box = (value) => ({ value, checked: false, matches: () => true, closest: () => null });
let boxes = ids.map(box);
const classes = new Set();
const list = { addEventListener: on("list"), querySelectorAll: () => boxes, querySelector: () => null,
               classList: { toggle(c, f) { if (f) classes.add(c); else classes.delete(c); }, contains: (c) => classes.has(c) } };
global.window = global;
global.addEventListener = () => {};
global.location = { href: "http://t/", pathname: "/", search: "", reload() { out.pageReloaded = true; } };
global.FormData = function () { this.ids = []; this.delete = () => {}; this.append = (k, v) => { if (k === "ids") this.ids.push(v); }; };
global.document = {
  body: { dataset: { undo: "Deshacer", saveFailed: "No se pudo guardar" }, tagName: "BODY", appendChild() {} },
  addEventListener() {},
  getElementById: (id) => ({ toast: toastEl, bulk: bar, list }[id] || null),
  createElement: element,
  querySelector: () => null,
  querySelectorAll: () => [],
};
document.activeElement = document.body;

// --- the server --------------------------------------------------------------------
let answers = {};          // path -> body; a bulk not listed answers {ok, notice: "hecho"}
global.fetch = (url, opts) => {
  out.fetched.push([url, (opts && opts.body && opts.body.ids) || []]);
  const body = answers[url] || { ok: true, notice: "hecho" };
  return Promise.resolve({ ok: body.ok !== false, status: body.ok === false ? 404 : 200, json: () => Promise.resolve(body) });
};

// --- shell.js's list -------------------------------------------------------------------
let current = "", shownIds = ids.slice(), afterReload = null;
const fakeList = {
  current: () => current,
  shown: () => shownIds.map((id) => ({ id: "card-" + id })),
  reload: (...args) => { out.reloads.push(args); if (afterReload) shownIds = afterReload; return Promise.resolve(); },
  pick: (id) => out.picks.push(id),
  empty: () => { out.empties += 1; },
};

eval(APP);
const ok = window.oknowledge;
ok.list = fakeList;
eval(SELECT);
const tick = (id) => listeners["list:change"].forEach((fn) => fn({ target: Object.assign(boxes.find((b) => b.value === id), { checked: true }) }));
const send = (which) => listeners["bar:submit"].forEach((fn) => fn({ preventDefault() {}, submitter: buttons[which] }));
const told = (reason) => listeners["list:oknowledge:list"].forEach((fn) => fn({ detail: { reason } }));
const ticked = () => boxes.filter((b) => b.checked).map((b) => b.value);
"""

BULK_SCENARIOS = {
    # The ticked ids go out, and the bar says what came back and clears.
    "move": """
current = "c3";
tick("a1"); tick("b2");
out.count = count; out.shown = !bar.hidden;
send("move"); await settle();
out.ticked = ticked(); out.hidden = bar.hidden; out.typed = bar.elements.new_category.value;
""",
    # A delete offers app.js's Deshacer; taken, the list reloads onto the
    # first note back.
    "undo": """
current = "a1";
answers["/bulk/delete"] = { ok: true, notice: "1 borrada", undo: "tok" };
answers["/undo/tok"] = { ok: true, notice: "Restaurada", restored: ["b2"] };
tick("b2");
send("del"); await settle();
out.offered = !!undoButton;
undoButton.click(); await settle();
""",
    # A refresh keeps what is still on screen; a new filter clears.
    "follows": """
tick("a1"); tick("c3");
boxes = ["a1", "b2"].map(box);
told("refresh");
out.kept = ticked();
told("filter");
out.afterFilter = ticked(); out.hidden = bar.hidden;
""",
    # The keys: x ticks the pick and again unticks it; Backspace and Delete
    # send the delete; Esc clears and is not taken when there is nothing.
    "keys": """
current = "b2";
ok.keys.x(); out.x = ticked();
ok.keys.x(); out.xAgain = ticked();
current = "zz"; out.noBox = ok.keys.x();
out.escIdle = ok.keys.Escape();
current = "a1"; ok.keys.x();
out.esc = String(ok.keys.Escape()); out.afterEsc = ticked();
out.backIdle = ok.keys.Backspace({});
ok.keys.x(); ok.keys.Delete({}); await settle();
""",
    # The open note ticked and changed but still listed: the list leaves the
    # panel alone and the same note is picked again.
    "repick": """
current = "a1";
tick("a1");
send("star"); await settle();
""",
    # Every listed note deleted with the open one among them: the panel empties.
    "emptied": """
current = "b2";
afterReload = [];
tick("a1"); tick("b2"); tick("c3");
send("del"); await settle();
""",
}


@pytest.fixture(scope="module")
def bulk(tmp_path_factory):
    import json
    import shutil
    import subprocess
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    folder = tmp_path_factory.mktemp("bulk")
    found = {}
    for name, scenario in BULK_SCENARIOS.items():
        harness = folder / f"{name}.js"
        harness.write_text(BULK_HARNESS + "(async () => {\n" + scenario +
                           "\nconsole.log(JSON.stringify(out));\nprocess.exit(0);\n})()"
                           ".catch((e) => { console.error(e.stack); process.exit(1); });\n",
                           encoding="utf-8")
        done = subprocess.run([node, str(harness), str(APP), str(SELECT)], capture_output=True,
                              text=True, timeout=30, check=False)
        assert done.returncode == 0, done.stderr
        found[name] = json.loads(done.stdout.strip().splitlines()[-1])
    return found


def test_the_bar_sends_the_ticked_ids_and_clears(bulk):
    move = bulk["move"]
    assert move["count"] == "2" and move["shown"] is True
    assert move["fetched"] == [["/bulk/category", ["a1", "b2"]]]
    assert move["toasts"] == ["hecho"]
    assert move["ticked"] == [] and move["hidden"] is True and move["typed"] == ""
    # The open one was not ticked: the list reloads and keeps it.
    assert move["reloads"] == [[""]] and move["picks"] == []


def test_a_bulk_delete_s_undo_reloads_the_list_onto_the_first_one_back(bulk):
    undo = bulk["undo"]
    assert undo["offered"] is True
    assert undo["fetched"] == [["/bulk/delete", ["b2"]], ["/undo/tok", []]]
    assert undo["toasts"] == ["1 borrada", "Restaurada"]
    assert undo["reloads"] == [["a1"], ["b2"]]
    assert "pageReloaded" not in undo


def test_a_refresh_keeps_the_ticks_still_listed_and_a_filter_clears_them(bulk):
    assert bulk["follows"]["kept"] == ["a1"]
    assert bulk["follows"]["afterFilter"] == [] and bulk["follows"]["hidden"] is True


def test_the_selection_keys(bulk):
    keys = bulk["keys"]
    assert keys["x"] == ["b2"] and keys["xAgain"] == []
    assert keys["noBox"] is False and keys["escIdle"] is False
    assert keys["esc"] == "undefined" and keys["afterEsc"] == []
    assert keys["backIdle"] is False
    assert keys["fetched"] == [["/bulk/delete", ["a1"]]]


def test_a_change_to_the_open_note_picks_it_again_once_the_list_is_back(bulk):
    repick = bulk["repick"]
    assert repick["fetched"] == [["/bulk/mark", ["a1"]]]
    assert repick["reloads"] == [["", True]]
    assert repick["picks"] == ["a1"] and repick["empties"] == 0


def test_deleting_every_listed_note_empties_the_panel(bulk):
    emptied = bulk["emptied"]
    assert emptied["reloads"] == [[""]]
    assert emptied["empties"] == 1
