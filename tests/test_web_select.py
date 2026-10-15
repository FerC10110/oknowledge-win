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


# --- select.js -------------------------------------------------------------------------------

def test_select_follows_the_list():
    text = SELECT.read_text(encoding="utf-8")
    listening = between(text, '"oknowledge:list"', "});")
    assert '"filter"' in listening


def test_select_registers_its_keys():
    text = SELECT.read_text(encoding="utf-8")
    for key in ("keys.x", "keys.Backspace", "keys.Delete", "keys.Escape"):
        assert key in text, key


def test_select_sends_the_ticked_ids_and_offers_undo():
    text = SELECT.read_text(encoding="utf-8")
    sending = between(text, "function submit", "function pickAfter")
    assert 'data.delete("ids")' in sending and 'data.append("ids"' in sending
    assert "ok.offerUndo(body.notice, body.undo" in sending and "ok.list.reload(" in sending


# --- fix round 1 -------------------------------------------------------------------------

@pytest.mark.parametrize("name, macro", [("shelf-items.html", "{% macro item"),
                                         ("posters.html", "{% macro poster")])
def test_a_note_being_reanalysed_has_no_checkbox(name, macro):
    text = between((WEB / "templates" / name).read_text(encoding="utf-8"), macro, "{%- endmacro %}")
    guarded = re.search(r"\{%- if note\.id not in busy %\}\s*<label class=\"check js-only\">.*?</label>"
                        r"\s*\{%- endif %\}", text, re.S)
    assert guarded, name


def test_a_bulk_change_reloads_the_pick_when_it_was_ticked():
    text = SELECT.read_text(encoding="utf-8")
    sending = between(text, "function submit", "function pickAfter")
    assert "var mine = picked.indexOf(cur) >= 0;" in sending
    # Once the list is back: the same pick redrawn, or the next one if it left.
    assert "var next = listed(cur) ? cur : after;" in sending


def test_the_list_leaves_room_for_the_bar_while_picking():
    css = (WEB / "static" / "app.css").read_text(encoding="utf-8")
    assert re.search(r"#list\.picking \.list-body \{ padding-bottom: \d+px; \}", css)


# --- fix round 2 -------------------------------------------------------------------------

def test_the_panel_empties_when_no_pick_is_left():
    shell = (WEB / "static" / "shell.js").read_text(encoding="utf-8")
    assert "empty: emptyPanel" in between(shell, "ok.list = {", "};")
    text = SELECT.read_text(encoding="utf-8")
    sending = between(text, "function submit", "function pickAfter")
    # Moved out, or deleted, with nothing left to pick: the panel empties.
    assert "if (next) ok.list.pick(next); else ok.list.empty();" in sending
    assert "if (mine && !after) ok.list.empty();" in sending


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
