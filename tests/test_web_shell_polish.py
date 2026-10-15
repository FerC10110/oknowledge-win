"""shell.js races and leftovers from docs/2026-10-14-rediseno-ocio-ideas-pendientes.md,
run in node over test_web_layer_history's fake page (a desktop unless said)."""

import pytest

from test_web_layer_history import node_may_run, run  # noqa: F401  (the fixture is used)

# A filter or sort link as the page draws it: in the sidebar's group for
# `param` (data-apart, data-param), or in the list head's sort menu.
LINKS = r"""
const sidebar = { id: "sidebar" };
function navLink(href, where) {
  const attrs = { href, "data-nav": "" };
  const group = where && where.param ? { dataset: { param: where.param } } : null;
  return {
    attrs, dataset: { nav: "" }, href: new URL(href, ORIGIN).href,
    hasAttribute: (k) => k in attrs, getAttribute: (k) => (k in attrs ? attrs[k] : null),
    matches: () => false,
    closest(sel) {
      if (sel.indexOf("a[data-nav]") >= 0) return this;
      if (/sidebar|chip-row/.test(sel)) return group ? sidebar : null;
      if (sel === "[data-apart]") return group;
      if (sel === ".sort") return where && where.sort ? {} : null;
      return null;
    },
  };
}
const fetched = (path) => asked.filter((u) => new URL(u, ORIGIN).pathname === path)
  .map((u) => { const x = new URL(u, ORIGIN); return x.pathname + x.search; });
"""

OCIO = dict(mode="ocio", action="/ocio", source="/ocio/lista", wide=True)


def ocio(tmp_path, scenario, url):
    return run(tmp_path, LINKS + scenario, entries=[{"url": url, "state": None}], **OCIO)


# --- Ocio: a sort while searching keeps the search ------------------------------------------

def test_a_sort_while_searching_keeps_the_field_and_q(tmp_path):
    out = ocio(tmp_path, """
field.value = "dune";
click(navLink("/ocio?q=dune&orden=titulo", { sort: true })); await settle();
out.field = field.value;
out.lists = fetched("/ocio/lista");
out.url = where().url;
""", "/ocio?q=dune")
    assert out["field"] == "dune"
    assert out["lists"] == ["/ocio/lista?q=dune&orden=titulo"]
    assert out["url"] == "/ocio?q=dune&orden=titulo"


def test_a_sort_takes_the_words_typed_since_the_list_was_drawn(tmp_path):
    out = ocio(tmp_path, """
field.value = "alien"; field.dispatchEvent({ type: "input" });
click(navLink("/ocio?q=dune&orden=anio", { sort: true })); await settle(300);
out.lists = fetched("/ocio/lista");
out.url = where().url;
""", "/ocio?q=dune")
    # One list, the sorted one with the newest words: the pending search was folded in.
    assert out["lists"] == ["/ocio/lista?q=alien&orden=anio"]
    assert out["url"] == "/ocio?q=alien&orden=anio"


def test_a_sort_with_an_empty_field_drops_q(tmp_path):
    out = ocio(tmp_path, """
field.value = "";
click(navLink("/ocio?q=dune&orden=titulo", { sort: true })); await settle();
out.url = where().url;
""", "/ocio?q=dune")
    assert out["url"] == "/ocio?orden=titulo"


def test_a_sidebar_filter_still_clears_the_search(tmp_path):
    out = ocio(tmp_path, """
field.value = "dune";
click(navLink("/ocio?tipo=book", { param: "tipo" })); await settle();
out.field = field.value;
out.url = where().url;
""", "/ocio?q=dune")
    assert out["field"] == "" and out["url"] == "/ocio?tipo=book"


# --- Ocio: ESTADO right after TIPO keeps the TIPO -------------------------------------------

def test_a_state_clicked_before_the_kind_s_list_lands_keeps_the_kind(tmp_path):
    out = ocio(tmp_path, """
// Both links as the page drew them before either click: the state's knows no kind.
const book = navLink("/ocio?tipo=book", { param: "tipo" });
const pending = navLink("/ocio?estado=pending", { param: "estado" });
click(book); click(pending); await settle();
out.lists = fetched("/ocio/lista");
out.url = where().url;
""", "/ocio")
    assert out["lists"][-1] == "/ocio/lista?tipo=book&estado=pending"
    assert out["url"] == "/ocio?tipo=book&estado=pending"


def test_a_kind_after_a_state_keeps_the_state_and_drops_the_old_kind(tmp_path):
    out = ocio(tmp_path, """
click(navLink("/ocio?estado=done", { param: "estado" }));
click(navLink("/ocio?tipo=movie&estado=pending", { param: "tipo" })); await settle();
out.url = where().url;
""", "/ocio?tipo=book&estado=pending&q=x&hasta=120")
    assert out["url"] == "/ocio?tipo=movie&estado=done"


def test_all_in_a_group_takes_its_parameter_off(tmp_path):
    out = ocio(tmp_path, """
click(navLink("/ocio?estado=done", { param: "tipo" })); await settle();
out.url = where().url;
""", "/ocio?tipo=book&estado=done")
    assert out["url"] == "/ocio?estado=done"


# --- the field's hidden inputs follow the list ----------------------------------------------

HIDDEN = r"""
const hidden = {};
function hiddenInput(name, value) {
  return { name, value, type: "hidden", remove() { delete hidden[name]; } };
}
form.querySelector = (sel) => {
  const m = sel.match(/name="([^"]+)"/);
  return m && hidden[m[1]] || null;
};
form.appendChild = (input) => { hidden[input.name] = input; };
document.createElement = (tag) => {
  const made = el("", { tagName: tag.toUpperCase() });
  Object.defineProperty(made, "name", { get() { return this.attrs.name; }, set(v) { this.attrs.name = v; } });
  return made;
};
const values = () => Object.fromEntries(Object.entries(hidden).map(([k, v]) => [k, v.value]));
"""


def test_the_hidden_inputs_follow_a_filter_chosen_in_place(tmp_path):
    out = ocio(tmp_path, HIDDEN + """
hidden.estado = hiddenInput("estado", "pending");
click(navLink("/ocio?tipo=book&orden=titulo", { param: "tipo" })); await settle();
out.hidden = values();
""", "/ocio?estado=pending&orden=titulo")
    assert out["hidden"] == {"tipo": "book", "estado": "pending", "orden": "titulo"}


def test_the_ideas_hidden_inputs_follow_a_state_chosen_in_place(tmp_path):
    out = run(tmp_path, LINKS + HIDDEN + """
hidden.estado = hiddenInput("estado", "doing");
hidden.vista = hiddenInput("vista", "lista");
click(navLink("/ideas?estado=done", { param: "estado" })); await settle();
out.hidden = values();
""", entries=[{"url": "/ideas?estado=doing&vista=lista", "state": None}], mode="ideas",
              action="/ideas", source="/ideas/lista", wide=True)
    assert out["hidden"] == {"estado": "done", "vista": "lista"}


# --- /ideas: an idea opened comes back to the list as it is now ------------------------------

def hit_scenario(event_js):
    return LINKS + r"""
const hit = { attrs: { href: "/ideas/i1?back=%2Fideas%3Festado%3Ddoing" },
  get href() { return new URL(this.attrs.href, ORIGIN).href; },
  getAttribute(k) { return this.attrs[k] || null; }, setAttribute(k, v) { this.attrs[k] = v; },
  hasAttribute: (k) => false, dataset: {}, matches: () => false,
  closest(sel) { return sel.indexOf("a.hit") >= 0 ? this : null; } };
""" + event_js + """
out.href = hit.attrs.href;
"""


IDEAS = dict(mode="ideas", action="/ideas", source="/ideas/lista", wide=True)


@pytest.mark.parametrize("event", ["click", "mousedown", "auxclick"])
def test_an_idea_opened_carries_the_list_s_url_now(tmp_path, event):
    """Its href was drawn with the list as the server saw it: no hasta for
    an idea that came with "more", and the old estado after a filter in place."""
    out = run(tmp_path, hit_scenario(f"""
fireDoc("{event}", {{ type: "{event}", target: hit, button: 0, preventDefault() {{}} }});
"""), entries=[{"url": "/ideas?estado=done&hasta=120", "state": None}], **IDEAS)
    assert out["href"] == "/ideas/i1?back=%2Fideas%3Festado%3Ddone%26hasta%3D120"


def test_an_idea_opened_from_the_plain_list_has_no_back(tmp_path):
    out = run(tmp_path, hit_scenario("""
fireDoc("click", { type: "click", target: hit, button: 0, preventDefault() {} });
"""), entries=[{"url": "/ideas", "state": None}], **IDEAS)
    assert out["href"] == "/ideas/i1"


# --- the panel: the pick is drawn when its panel comes, after a slow save ---------------------

SLOW_SAVE = r"""
let release = null;
let dirtyNow = false;
ok.dirty = () => dirtyNow;
ok.settle = () => new Promise((resolve) => { release = resolve; });
const lit = [];
const li = (id) => ({ id: "card-" + id, classList: { add: () => lit.push(id), remove() {} } });
const lis = { "card-o1": li("o1"), "card-o2": li("o2") };
const realById = document.getElementById;
document.getElementById = (id) => lis[id] || realById(id);
"""


def test_a_pick_behind_a_slow_save_is_lit_when_the_save_lands(tmp_path):
    out = ocio(tmp_path, SLOW_SAVE + """
dirtyNow = true;
click(link({ href: "/ocio?sel=o2", "data-sel": "o2" })); await settle();
out.before = lit.slice();
out.current = items.dataset.current;
dirtyNow = false; release(null); await settle();
out.after = lit.slice();
out.panel = panelHtml;
""", "/ocio?sel=o1")
    assert out["before"] == [] and out["current"] == "o2"
    assert out["after"] == ["o2"] and out["panel"] == "PANEL:o2"


def test_a_pick_with_nothing_to_save_is_lit_at_once(tmp_path):
    out = ocio(tmp_path, SLOW_SAVE + """
ok.settle = () => Promise.resolve(null);
click(link({ href: "/ocio?sel=o2", "data-sel": "o2" }));
out.before = lit.slice();
""", "/ocio?sel=o1")
    assert out["before"] == ["o2"]


# --- the panel reloaded under the caret (a rewrite ended) -------------------------------------

CARET = r"""
function box(value, start, end) {
  return { id: "card-note", inPanel: true, value, selectionStart: start, selectionEnd: end,
           focused: false, range: null,
           focus() { this.focused = true; document.activeElement = this; },
           setSelectionRange(a, b) { this.range = [a, b]; } };
}
"""


@pytest.mark.parametrize("fresh, expected", [("hola mundo", [3, 5]), ("otro texto", [0, 0])])
def test_a_reloaded_panel_keeps_the_caret_where_it_was(tmp_path, fresh, expected):
    """The same text: the caret (and the selection) where it was. Text that
    changed under it: the start, where an old offset cannot land mid-word."""
    out = ocio(tmp_path, CARET + f"""
const old = box("hola mundo", 3, 5);
document.activeElement = old;
byId["card-note"] = box("{fresh}", 0, 0);
ok.list.reload("o1"); await settle();
out.focused = byId["card-note"].focused;
out.range = byId["card-note"].range;
""", "/ocio?sel=o1")
    assert out["focused"] and out["range"] == expected


def test_a_sort_with_a_link_to_save_in_the_field_drops_the_old_q(tmp_path):
    """Review M-5: the field holds a link, not a search: the list sorted is
    the whole one, as the field shows no words to search for."""
    out = ocio(tmp_path, """
field.value = "https://www.imdb.com/title/tt0088247/";
click(navLink("/ocio?q=dune&orden=titulo", { sort: true })); await settle();
out.url = where().url;
out.field = field.value;
""", "/ocio?q=dune")
    assert out["url"] == "/ocio?orden=titulo"
    assert out["field"] == "https://www.imdb.com/title/tt0088247/"
