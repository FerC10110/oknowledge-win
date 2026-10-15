"""Processing the links the import left unanalysed, in batches, from the web.

An imported chat leaves a thousand notes saved and none analysed, because
each analysis is a model call. The Procesar button runs a batch of them and
the page draws how far it got. Nothing here makes a real model call: the
worker that would is replaced, and what is tested is the route around it.
"""

import pytest
from fastapi.testclient import TestClient

from oknowledge.config import Config
from oknowledge.queue import Queue
from oknowledge.vault import rebuild_indexes
from oknowledge.web import app as module
from oknowledge.web.app import create_app


@pytest.fixture(autouse=True)
def state_tree(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr("oknowledge.web.app.CONFIG_PATH",
                        tmp_path / "config" / "config.toml")


@pytest.fixture
def setup(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault, batch=2)
    rebuild_indexes(cfg, "es")
    return cfg, TestClient(create_app(cfg))


@pytest.fixture
def started(monkeypatch):
    """What the route handed the worker, without a model call behind it."""
    calls = []
    monkeypatch.setattr(module, "run_batch",
                        lambda cfg, held, limit: calls.append((cfg, held, limit)))
    return calls


def owe(count):
    """`count` links the queue still owes, the way an import leaves them."""
    q = Queue()
    for n in range(count):
        q.enqueue(f"id{n}", f"https://e{n}.com/x", "full")
        q.set_status(f"id{n}", "partial")


# --- Starting a batch ---------------------------------------------------------

def test_the_button_starts_a_batch_and_sends_you_to_watch_it(setup, started):
    cfg, client = setup
    owe(5)

    answer = client.post("/retry", follow_redirects=False)

    assert answer.status_code == 303
    assert answer.headers["location"].startswith("/retry")
    assert len(started) == 1


def test_the_batch_is_the_size_the_settings_say(setup, started):
    """The whole point of the field: 10 links tonight, not 1180."""
    cfg, client = setup                       # batch=2
    owe(5)

    client.post("/retry", follow_redirects=False)

    assert started[0][2] == 2


def test_the_bar_s_total_is_never_more_than_what_is_owed(setup, started):
    """A bar whose total is 50 when 3 links are left can only ever look stuck."""
    cfg, client = setup                       # batch=2
    owe(1)

    client.post("/retry", follow_redirects=False)

    assert client.app.state.batch.snapshot().total == 1


def test_a_batch_with_nothing_left_to_do_is_not_started(setup, started):
    cfg, client = setup

    answer = client.post("/retry", follow_redirects=False)

    assert "notice=nothing-owed" in answer.headers["location"]
    assert started == []
    assert not client.app.state.batch.snapshot().running


def test_a_second_click_while_a_batch_runs_is_refused(setup, started):
    """Two runs would reach for the same links and pay twice for each."""
    cfg, client = setup
    owe(5)
    client.post("/retry", follow_redirects=False)

    answer = client.post("/retry", follow_redirects=False)

    assert "notice=batch-running" in answer.headers["location"]
    assert len(started) == 1                  # the second one never ran


def test_a_batch_can_be_started_again_once_the_last_one_ended(setup, started):
    cfg, client = setup
    owe(5)
    client.post("/retry", follow_redirects=False)
    client.app.state.batch.finish()           # the worker would do this

    client.post("/retry", follow_redirects=False)

    assert len(started) == 2


def test_the_batch_runs_after_the_answer_is_sent(setup, monkeypatch):
    """Fifty model calls is an hour. A browser does not wait an hour."""
    log = []

    class Recorder:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            async def watched(message):
                if (message["type"] == "http.response.body"
                        and not message.get("more_body")):
                    log.append("response sent")
                await send(message)

            await self.app(scope, receive, watched)

    monkeypatch.setattr(module, "run_batch",
                        lambda cfg, held, limit: log.append("batch ran"))
    cfg, _ = setup
    owe(3)
    client = TestClient(Recorder(create_app(cfg)))

    client.post("/retry", follow_redirects=False)

    assert log == ["response sent", "batch ran"]


# --- Watching it --------------------------------------------------------------

def test_the_page_draws_a_bar_while_the_batch_runs(setup, started):
    cfg, client = setup
    owe(5)
    client.post("/retry", follow_redirects=False)
    client.app.state.batch.step(_ok())

    body = client.get("/retry").text

    assert '<progress value="1" max="2">' in body


def test_the_running_page_comes_back_on_its_own(setup, started):
    """Without this the bar only moves when the user thinks to reload, which
    is the same as having no bar."""
    cfg, client = setup
    owe(5)
    client.post("/retry", follow_redirects=False)

    body = client.get("/retry?notice=batch-started").text

    assert '<meta http-equiv="refresh" content="10; url=/retry">' in body


def test_the_running_page_does_not_bring_its_notice_back_every_time(setup, started):
    """It comes back every ten seconds. Reloading this URL would reload the
    notice with it -- "Analysing. You can close it." forever."""
    cfg, client = setup
    owe(5)
    client.post("/retry", follow_redirects=False)

    body = client.get("/retry?notice=batch-started").text

    assert "url=/retry" in body               # the clean path, not this one
    assert "notice=batch-started" not in body


def test_the_finished_page_stays_still(setup, started):
    """A page that keeps reloading after the run is over looks broken, and on
    this page every reload is a queue listing."""
    cfg, client = setup
    owe(5)
    client.post("/retry", follow_redirects=False)
    client.app.state.batch.finish()

    body = client.get("/retry").text

    assert 'http-equiv="refresh"' not in body
    assert "<progress" not in body


def test_the_page_says_how_many_links_are_still_waiting(setup):
    cfg, client = setup
    owe(7)

    body = client.get("/retry").text

    assert "Waiting to be analysed: 7" in body


def test_the_page_says_what_went_wrong_when_a_batch_broke(setup, started):
    cfg, client = setup
    owe(5)
    client.post("/retry", follow_redirects=False)
    client.app.state.batch.finish("OSError: no space left on device")

    body = client.get("/retry").text

    assert "no space left on device" in body


def test_the_page_is_readable_before_any_batch_has_run(setup):
    cfg, client = setup

    answer = client.get("/retry")

    assert answer.status_code == 200


# --- The settings page --------------------------------------------------------

def test_settings_offers_the_batch_size_and_the_button(setup):
    cfg, client = setup
    owe(3)

    body = client.get("/settings").text

    assert 'name="batch"' in body
    assert 'action="/retry"' in body
    assert "Analyse 2 links" in body


@pytest.mark.parametrize("where", ["/settings", "/retry"])
def test_the_button_promises_only_the_links_that_are_there(setup, where):
    """Offering to analyse 2 when 1 is left is a button that cannot keep its
    word -- and "Analyse 1 links" is the other half of the same mistake."""
    cfg, client = setup                       # batch=2
    owe(1)

    body = client.get(where).text

    assert "Analyse 1 link<" in body


def test_settings_offers_no_button_when_there_is_nothing_to_analyse(setup):
    """A button that can only answer "nothing to do" is a button that lies
    about there being something to do."""
    cfg, client = setup

    body = client.get("/settings").text

    assert 'action="/retry"' not in body
    assert "Every link has been analysed" in body


def test_settings_says_how_many_links_are_waiting(setup):
    cfg, client = setup
    owe(4)

    body = client.get("/settings").text

    assert "Links waiting for analysis: 4" in body


def test_saving_the_batch_size_keeps_it(setup):
    cfg, client = setup

    client.post("/settings", data=form(batch="25"), follow_redirects=False)

    assert client.app.state.settings["cfg"].batch == 25


def test_a_batch_size_that_is_not_one_leaves_the_saved_one_alone(setup):
    """The form is the only way in, so a refused value must not take the rest
    of the settings down with it -- nor save a config load() would refuse."""
    cfg, client = setup

    answer = client.post("/settings", data=form(batch="0", language="en"),
                         follow_redirects=False)

    assert "notice=saved" in answer.headers["location"]
    live = client.app.state.settings["cfg"]
    assert live.batch == 2                    # what it was
    assert live.language == "en"              # the rest of the form still took


@pytest.mark.parametrize("bad", ["", " ", "0", "-1", "2.5", "abc", "1e3", "0x10"])
def test_a_batch_size_the_config_would_refuse_leaves_the_saved_one_alone(setup, bad):
    """Not clamped to something near it: a number the user did not type is no
    better a guess than the one already saved, and a 0 written to the file
    would make config.load() refuse it and stop the whole tool."""
    cfg, client = setup

    client.post("/settings", data=form(batch=bad), follow_redirects=False)

    assert client.app.state.settings["cfg"].batch == 2


def test_a_batch_size_typed_with_a_stray_space_still_counts(setup):
    """A number with a space around it is a number. Silently keeping the old
    value would look like the field does not work."""
    cfg, client = setup

    client.post("/settings", data=form(batch=" 25 "), follow_redirects=False)

    assert client.app.state.settings["cfg"].batch == 25


def test_the_saved_batch_size_survives_a_reload_of_the_config(setup, tmp_path):
    """Saved to the file, not only to the running server: the CLI reads it too."""
    from oknowledge.config import load

    cfg, client = setup
    client.post("/settings", data=form(batch="25"), follow_redirects=False)

    assert load(tmp_path / "config" / "config.toml").batch == 25


# --- Helpers ------------------------------------------------------------------

def form(**over):
    """A full settings form, since every field it leaves out is a field cleared."""
    data = {"chain": ["opencode"], "language": "es", "default_content": "full",
            "mentions": "tools", "ui_language": "es", "batch": "2"}
    data.update(over)
    return data


def _ok():
    from oknowledge.pipeline import Result
    return Result(id="id0", url="https://e0.com/x", path=None, status="ok")


def test_a_notice_added_to_a_path_that_already_has_a_query_is_a_second_field():
    """A second "?" instead would make the notice part of the value before it,
    and the user would land on a category called `Redes?notice=queued`."""
    from oknowledge.web.app import see_other

    answer = see_other("/?category=Redes", notice="queued")

    assert answer.headers["location"] == "/?category=Redes&notice=queued"


# --- Where reprocessing sends you back ---------------------------------------

@pytest.fixture
def cards(tmp_path):
    """A library with one analysed note and one the import left unanalysed."""
    from oknowledge.model import Note
    from oknowledge.vault import write_note

    def note(id, status):
        return Note(id=id, url=f"https://e.com/{id}", title=f"T{id}",
                    category="Redes", tags=["x"], type="article", source="e.com",
                    saved="2026-10-03", summary="", points=[], status=status)

    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault)
    q = Queue()
    for link, status in (("done", "ok"), ("waiting", "partial")):
        write_note(cfg, note(link, status), "es")
        # An import leaves an entry for every link it writes, so a note with a
        # queue entry is the state these pages are actually looked at in.
        q.enqueue(link, f"https://e.com/{link}", "full")
        q.set_status(link, status)
    rebuild_indexes(cfg, "es")
    return cfg, TestClient(create_app(cfg))


def test_the_card_button_comes_back_to_the_view_it_was_clicked_on(cards, monkeypatch):
    """Analysing from a card and landing on the note page is the trip the
    button exists to avoid -- and on page 4 of a category it is worse."""
    monkeypatch.setattr(module, "reanalyze", lambda cfg, url, engine, **kw: None)
    cfg, client = cards

    answer = client.post("/item/waiting/reprocess",
                         data={"back": "library", "category": "Redes", "page": "2"},
                         follow_redirects=False)

    assert answer.headers["location"] == "/?category=Redes&page=2&notice=queued"


def test_the_note_page_button_still_comes_back_to_the_note(cards, monkeypatch):
    monkeypatch.setattr(module, "reanalyze", lambda cfg, url, engine, **kw: None)
    cfg, client = cards

    answer = client.post("/item/waiting/reprocess", data={"engine": ""},
                         follow_redirects=False)

    assert answer.headers["location"] == "/item/waiting?notice=queued"


@pytest.mark.parametrize("sent, expected", [
    # A destination is rebuilt from what the library route understands, never
    # echoed, so a hand-made form cannot land the user anywhere but here.
    ({"back": "library", "category": "//evil.com"}, "/?category=%2F%2Fevil.com&notice=queued"),
    ({"back": "library", "page": "../../etc"}, "/?notice=queued"),
    ({"back": "library", "page": "-1"}, "/?notice=queued"),
    ({"back": "library", "page": "1"}, "/?notice=queued"),
    ({"back": "/evil", "category": "Redes"}, "/item/waiting?notice=queued"),
    ({"back": "https://evil.com"}, "/item/waiting?notice=queued"),
])
def test_a_hand_made_return_cannot_leave_this_app(cards, monkeypatch, sent, expected):
    monkeypatch.setattr(module, "reanalyze", lambda cfg, url, engine, **kw: None)
    cfg, client = cards

    answer = client.post("/item/waiting/reprocess", data=sent, follow_redirects=False)

    assert answer.headers["location"] == expected


# --- A search to come back to, and the nav ------------------------------------

def test_a_search_with_nothing_to_search_for_is_not_a_destination(cards, monkeypatch):
    """/search with no terms redirects to the library, so sending the user
    there would bounce them somewhere they never were."""
    monkeypatch.setattr(module, "reanalyze", lambda cfg, url, engine, **kw: None)
    cfg, client = cards

    answer = client.post("/item/waiting/reprocess",
                         data={"back": "search", "q": "  "}, follow_redirects=False)

    assert answer.headers["location"] == "/item/waiting?notice=queued"


@pytest.mark.parametrize("path", ["/settings", "/settings/panel?tab=importar"])
def test_activity_is_reached_from_settings(setup, path):
    """It left the sidebar (spec §7): Settings → Import links it."""
    cfg, client = setup

    assert 'href="/retry"' in client.get(path).text


def test_the_nav_says_how_far_a_running_batch_has_got(setup, started):
    """The run is behind whatever page the user is reading."""
    cfg, client = setup
    owe(5)
    client.post("/retry", follow_redirects=False)
    client.app.state.batch.step(_ok())

    body = client.get("/categories").text

    assert '<b class="mono">1/2</b>' in body


def test_the_nav_counts_nothing_when_no_batch_is_running(setup):
    cfg, client = setup

    body = client.get("/categories").text

    assert '<b class="mono">0/0</b>' not in body


# --- Clicking without losing the page -----------------------------------------

def test_a_link_being_worked_on_says_so(cards, monkeypatch):
    """What the spinning card polls. The queue and never the vault: every card
    the user clicked asks this every few seconds. Working is the lock the task
    holds; the `pending` the click writes is not work by itself."""
    seen = {}

    def reanalyze(cfg, url, engine, **kw):
        with Queue().lock("waiting"):
            seen["during"] = client.get("/item/waiting/state").json()

    monkeypatch.setattr(module, "reanalyze", reanalyze)
    cfg, client = cards

    client.post("/item/waiting/reprocess", data={"back": "library"},
                follow_redirects=False)

    assert seen["during"] == {"working": True, "status": "pending"}


def test_a_reprocess_whose_task_died_is_not_working(cards, monkeypatch):
    """The task ended without finishing (an OSError, a restart): the entry is
    left pending with nobody holding it, and a card polling it must stop."""
    monkeypatch.setattr(module, "reanalyze", lambda cfg, url, engine, **kw: None)
    cfg, client = cards

    client.post("/item/waiting/reprocess", data={"back": "library"},
                follow_redirects=False)

    assert client.get("/item/waiting/state").json() == {"working": False,
                                                        "status": "pending"}


def test_a_link_nobody_is_working_on_says_so(cards):
    cfg, client = cards

    assert client.get("/item/waiting/state").json() == {"working": False,
                                                        "status": "partial"}


def test_a_link_with_no_entry_at_all_is_not_working(cards):
    """A note whose queue entry was deleted. The card stops spinning rather
    than spinning for ever over something nobody will ever finish."""
    cfg, client = cards

    assert client.get("/item/nosuchlink/state").json()["working"] is False


@pytest.mark.parametrize("bad", ["not an id", "ZZZZ!", "a" * 400, "....."])
def test_the_state_of_a_link_whose_id_is_nonsense_is_an_answer_not_a_crash(cards, bad):
    """The id reaches the queue straight from a URL. A malformed one names no
    entry, which is an answer; it must not reach the filesystem as a path.

    "." and ".." are not in the list because they never arrive: the router
    resolves them away and the request is a 404 before any of this runs.
    """
    cfg, client = cards

    answer = client.get(f"/item/{bad}/state")

    assert answer.status_code == 200
    assert answer.json() == {"working": False, "status": "unknown"}


def test_the_click_marks_the_link_pending_before_it_answers(cards, monkeypatch):
    """Not when the background task gets round to it: between the two the card
    would poll, be told nobody is working, and stop spinning at once.

    It is also what the note page has always claimed -- "the note stays pending
    until it finishes" -- made true at the moment it says it.
    """
    from oknowledge.queue import Queue

    seen = {}
    monkeypatch.setattr(module, "reanalyze",
                        lambda cfg, url, engine, **kw: seen.update(
                            status=Queue().get("waiting").status))

    cfg, client = cards

    client.post("/item/waiting/reprocess", follow_redirects=False)

    assert seen["status"] == "pending"


def test_a_click_without_the_script_still_gets_its_page(cards, monkeypatch):
    """The same route serves both: with JavaScript off the form posts plainly
    and the browser has to be sent somewhere."""
    monkeypatch.setattr(module, "reanalyze", lambda cfg, url, engine, **kw: None)
    cfg, client = cards

    answer = client.post("/item/waiting/reprocess", data={"back": "library"},
                         follow_redirects=False)

    assert answer.status_code == 303
    assert answer.headers["location"] == "/?notice=queued"


def test_the_quiet_answer_still_queues_the_work(cards, monkeypatch):
    """A 204 that did nothing would be the quietest bug in the program."""
    seen = []
    monkeypatch.setattr(module, "reanalyze",
                        lambda cfg, url, engine, **kw: seen.append(url))
    cfg, client = cards

    client.post("/item/waiting/reprocess", headers={"X-Requested-With": "redo"},
                follow_redirects=False)

    assert seen == ["https://e.com/waiting"]


def test_a_link_someone_holds_the_lock_on_is_working_whatever_the_queue_says(cards):
    """The two halves answer different moments, and this is the one that holds
    while the model runs: the entry only turns `pending` if the queue could be
    written, and a read-only state tree must not stop a card from spinning
    over work that is really happening.
    """
    cfg, client = cards
    assert Queue().get("waiting").status == "partial"      # not pending

    with Queue().lock("waiting"):
        answer = client.get("/item/waiting/state").json()

    assert answer == {"working": True, "status": "partial"}


def test_the_lock_being_let_go_ends_the_spin(cards):
    """The other side of the same test: a lock nobody holds is not work."""
    cfg, client = cards

    with Queue().lock("waiting"):
        pass

    assert client.get("/item/waiting/state").json()["working"] is False


# --- What the run is doing, line by line -------------------------------------

def step(n, name="extract", state="ok"):
    from oknowledge.trace import Step
    return Step(link=f"link{n}", name=name, state=state, seconds=1.5,
                detail=f"detail {n}")


def test_the_lines_are_capped_and_the_newest_is_first():
    """A run of 1164 links is some six thousand lines, and the page sends
    every one of them it holds on every refresh."""
    from oknowledge.web.batch import Batch

    held = Batch()
    held.start(500)
    for n in range(500):
        held.note(step(n))

    lines = held.snapshot().lines
    assert len(lines) == 200
    assert lines[0].link == "link499"
    assert lines[-1].link == "link300"


def test_work_outside_a_batch_is_still_work_you_can_watch():
    """The list is what this process has been doing, not what one run did.
    A link re-analysed from its card is a model call like any other, and the
    page that shows model calls has to show it."""
    from oknowledge.web.batch import Batch

    held = Batch()
    held.start(1)
    held.note(step(1))
    held.finish()
    held.note(step(2))          # the card's own button, long after the batch
    assert [line.link for line in held.snapshot().lines] == ["link2", "link1"]


def test_the_worker_hands_the_tracer_to_retry(setup, monkeypatch):
    cfg, _ = setup
    from oknowledge.web import batch as batch_module

    seen = {}
    monkeypatch.setattr(batch_module, "retry",
                        lambda cfg, **kw: seen.update(kw) or [])
    held = batch_module.Batch()
    held.start(1)
    batch_module.run(cfg, held, 1)
    assert seen["trace"] == held.note


def test_the_card_s_retry_button_is_watched_too(cards, monkeypatch):
    """The whole complaint: the ↻ on a card is a model call the page knew
    nothing about."""
    cfg, client = cards
    seen = {}
    monkeypatch.setattr(module, "reanalyze",
                        lambda cfg, url, engine, trace=None: seen.update(trace=trace))

    client.post("/item/waiting/reprocess")

    assert seen["trace"] == client.app.state.batch.note


def test_re_analysing_one_link_hands_the_tracer_to_the_pipeline(monkeypatch):
    seen = {}
    monkeypatch.setattr(module, "add_link",
                        lambda cfg, url, **kw: seen.update(kw))
    module.reanalyze("cfg", "https://e.com/x", None, trace="the-tracer")
    assert seen["trace"] == "the-tracer"


def test_the_page_draws_what_the_run_is_doing(setup, started):
    cfg, client = setup
    owe(3)
    client.post("/retry")
    app_batch = client.app.state.batch
    app_batch.note(step(1, name="analyze", state="fail"))

    body = client.get("/retry").text
    assert "Analyse with the model" in body
    assert "detail 1" in body
    assert "1.5" in body


def test_a_step_with_nothing_to_say_says_nothing(setup, started):
    """`opencode · ` reads as a line that lost half of itself."""
    from oknowledge.trace import Step

    cfg, client = setup
    owe(3)
    client.post("/retry")
    client.app.state.batch.note(Step(link="a", name="analyze", state="start",
                                     seconds=0.0, engine="opencode"))

    body = client.get("/retry").text
    assert "opencode" in body
    assert "opencode ·" not in body
    assert "opencode &#183;" not in body


def test_the_checkbox_is_off_unless_asked(setup, started):
    cfg, client = setup
    owe(3)
    body = client.get("/retry").text
    assert 'name="debug"' in body
    assert "checked" not in body


def test_the_page_says_the_traces_hold_the_page_text(setup, started):
    """The box says what it keeps, because what it keeps is your content."""
    cfg, client = setup
    owe(3)
    assert "full text of each page" in client.get("/retry").text


def test_the_box_unticked_traces_nothing(setup, started):
    cfg, client = setup
    owe(3)
    client.post("/retry")
    assert started[0][0].trace_to == ""


def test_the_box_ticked_traces_this_batch_and_no_other(setup, started):
    cfg, client = setup
    owe(3)
    client.post("/retry", data={"debug": "on"})
    assert started[0][0].trace_to != ""
    # The server's own config is untouched: a box ticked once must not leave
    # every later run writing the full text of every page to disk.
    assert client.app.state.settings["cfg"].trace_to == ""


# --- a batch started from Settings (delivery 3, spec §3.1) ------------------------

JSON = {"Accept": "application/json"}


def test_a_script_starting_a_batch_is_told_how_many(setup, started):
    cfg, client = setup                       # batch=2
    owe(3)
    assert client.post("/retry", headers=JSON).json() == {"ok": True, "notice": "Analysing 2 links"}


def test_a_script_starting_one_is_told_in_the_singular(setup, started):
    cfg, client = setup
    owe(1)
    assert client.post("/retry", headers=JSON).json()["notice"] == "Analysing 1 link"


def test_a_second_batch_is_a_409_to_a_script(setup, started):
    cfg, client = setup
    owe(3)
    client.post("/retry", follow_redirects=False)
    assert client.post("/retry", headers=JSON).status_code == 409
    assert len(started) == 1
