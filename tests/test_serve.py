"""`oknowledge serve`: start the web, and stop it when nobody is using it.

The part that matters is what the idle timer must NOT do: stop the server while
a request, or the background re-analysis it started, is still running. Every
timer test drives an injected clock; nothing here sleeps.
"""

import asyncio
import dataclasses
import io
import signal

import pytest
from fastapi.testclient import TestClient

from oknowledge.cli import main
from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.vault import rebuild_indexes, write_note
from oknowledge.web import runner
from oknowledge.web.runner import IdleTimer, TrackActivity, announce, build_app, watch

FAR = 10_000_000.0


@pytest.fixture(autouse=True)
def state(tmp_path, monkeypatch):
    # Anything that reaches the queue (a re-analysis) must stay inside tmp_path.
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


# --- the timer ---------------------------------------------------------------

def test_a_fresh_timer_is_not_expired():
    timer = IdleTimer(seconds=900, now=lambda: 1000.0)
    assert timer.expired(1000.0) is False


def test_it_expires_after_the_idle_window():
    timer = IdleTimer(seconds=900, now=lambda: 1000.0)
    assert timer.expired(1899.0) is False
    assert timer.expired(1901.0) is True


def test_every_request_pushes_the_deadline_back():
    timer = IdleTimer(seconds=900, now=lambda: 1000.0)
    timer.touch(1800.0)
    assert timer.expired(1901.0) is False
    assert timer.expired(2701.0) is True


def test_zero_seconds_means_never_shut_down():
    timer = IdleTimer(seconds=0, now=lambda: 1000.0)
    assert timer.expired(10_000_000.0) is False


def test_work_in_flight_is_never_idle_however_long_it_takes():
    timer = IdleTimer(seconds=900, now=lambda: 1000.0)
    timer.begin()
    assert timer.expired(1000.0 + 900 * 1000) is False


def test_the_countdown_starts_when_the_work_finishes_not_when_it_began():
    timer = IdleTimer(seconds=900, now=lambda: 1000.0)
    timer.begin()
    timer.end(when=5000.0)                       # a four-thousand-second job
    assert timer.expired(5000.0 + 899) is False
    assert timer.expired(5000.0 + 901) is True


def test_one_finished_request_does_not_hide_one_still_running():
    timer = IdleTimer(seconds=900, now=lambda: 1000.0)
    timer.begin()
    timer.begin()
    timer.end(when=1100.0)
    assert timer.expired(FAR) is False
    timer.end(when=1200.0)
    assert timer.expired(FAR) is True


def test_an_unbalanced_end_cannot_make_the_count_negative():
    timer = IdleTimer(seconds=900, now=lambda: 1000.0)
    timer.end()
    timer.begin()
    assert timer.expired(FAR) is False


# --- the middleware ----------------------------------------------------------

def call(app, scope_type="http"):
    async def go():
        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            pass

        await app({"type": scope_type, "method": "GET", "path": "/"}, receive, send)

    asyncio.run(go())


def test_a_request_counts_as_work_until_the_whole_call_returns():
    timer = IdleTimer(seconds=900, now=Clock())
    seen = []

    async def inner(scope, receive, send):
        seen.append(timer.expired(FAR))          # while the handler runs
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})
        seen.append(timer.expired(FAR))          # after the response, as a background task would

    call(TrackActivity(inner, timer))
    assert seen == [False, False]
    assert timer.expired(FAR) is True


def test_the_clock_restarts_when_a_request_finishes():
    clock = Clock(1000.0)
    timer = IdleTimer(seconds=900, now=clock)

    async def inner(scope, receive, send):
        clock.t = 5000.0                          # the request took a long time

    call(TrackActivity(inner, timer))
    assert timer.last == 5000.0


def test_a_handler_that_raises_does_not_leave_the_server_counted_busy():
    timer = IdleTimer(seconds=900, now=Clock())

    async def inner(scope, receive, send):
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        call(TrackActivity(inner, timer))
    assert timer.active == 0
    assert timer.expired(FAR) is True


def test_the_lifespan_is_not_a_request():
    timer = IdleTimer(seconds=900, now=Clock())
    seen = []

    async def inner(scope, receive, send):
        seen.append(timer.active)

    call(TrackActivity(inner, timer), scope_type="lifespan")
    assert seen == [0]


# --- the real app: a re-analysis outlives its request -----------------------

def make_note(id, title):
    return Note(id=id, url=f"https://e.com/{id}", title=title, category="Redes",
                tags=["x"], type="article", source="e.com", saved="2026-10-03",
                summary=f"Resumen de {title}.", points=[])


@pytest.fixture
def vault_cfg(tmp_path):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault, port=9123)
    write_note(cfg, make_note("a1", "WireGuard"), "es")
    rebuild_indexes(cfg, "es")
    return cfg


def test_the_server_stays_up_while_a_reanalysis_runs_in_the_background(vault_cfg, monkeypatch):
    timer = IdleTimer(seconds=900, now=Clock())
    during = []

    def slow_analysis(cfg, url, **kwargs):
        during.append(timer.expired(FAR))        # the response has already gone
        during.append(timer.active)

    monkeypatch.setattr("oknowledge.web.app.add_link", slow_analysis)
    client = TestClient(build_app(vault_cfg, timer))

    response = client.post("/item/a1/reprocess", follow_redirects=False)

    assert response.status_code == 303
    assert during == [False, 1]
    assert timer.expired(FAR) is True            # and once it is done, it can stop


def test_the_real_app_is_wrapped_by_the_activity_tracker(vault_cfg):
    timer = IdleTimer(seconds=900, now=Clock(1000.0))
    client = TestClient(build_app(vault_cfg, timer))
    timer.touch(0.0)
    assert client.get("/").status_code == 200
    assert timer.last > 0.0


# --- the watchdog ------------------------------------------------------------

class FakeServer:
    should_exit = False


def test_the_watchdog_stops_the_server_once_the_timer_expires():
    clock = Clock(1000.0)
    timer = IdleTimer(seconds=900, now=clock)
    server = FakeServer()
    naps = []

    def sleep(seconds):
        naps.append(seconds)
        assert len(naps) <= 10, "the watchdog never stopped the server"
        clock.t += 400.0

    watch(server, timer, interval=5.0, sleep=sleep)

    assert server.should_exit is True
    assert len(naps) == 3                        # 400, 800, 1200 seconds idle


def test_the_watchdog_leaves_a_busy_server_alone_and_stops_it_after():
    clock = Clock(1000.0)
    timer = IdleTimer(seconds=900, now=clock)
    server = FakeServer()
    timer.begin()
    naps = []

    def sleep(seconds):
        naps.append(seconds)
        assert server.should_exit is False, "stopped while work was running"
        assert len(naps) <= 5, "it should have stopped by now"
        clock.t += 5000.0                        # hours pass with the work still running
        if len(naps) == 4:
            timer.end()                          # the work finishes, at the current time

    watch(server, timer, interval=5.0, sleep=sleep)

    assert server.should_exit is True
    assert len(naps) == 5                        # a full idle window after the work, not before


def test_a_server_told_to_exit_ends_the_watchdog_without_waiting():
    server = FakeServer()
    server.should_exit = True
    watch(server, IdleTimer(seconds=900), sleep=lambda s: pytest.fail("it slept"))


# --- serve() itself ----------------------------------------------------------

class StubServer:
    """Stands in for uvicorn.Server: no socket is opened."""
    instances = []

    def __init__(self, config):
        self.config = config
        self.should_exit = False
        self.started = True
        StubServer.instances.append(self)

    def run(self):
        StubServer.behaviour(self)


class RecordedThread:
    """Stands in for runner.Thread: remembers what it was asked to run."""
    made = []

    # The signature mirrors threading.Thread's, keyword arguments and all:
    # `kwargs` is the dict the thread passes on, not this call's leftovers.
    def __init__(self, target=None, args=(), kwargs=None, daemon=None, **rest):
        self.target, self.args, self.daemon = target, args, daemon
        self.kwargs = dict(kwargs or {})
        RecordedThread.made.append(self)

    def start(self):
        self.started = True


@pytest.fixture
def stub_uvicorn(monkeypatch):
    StubServer.instances = []
    StubServer.behaviour = staticmethod(lambda server: None)
    RecordedThread.made = []
    monkeypatch.setattr(runner.uvicorn, "Server", StubServer)
    # The runner's own reference, not the stdlib module: TestClient and anyio
    # start threads of their own.
    monkeypatch.setattr(runner, "Thread", RecordedThread)
    return StubServer


def watchdogs():
    return [t for t in RecordedThread.made if t.target is runner.watch]


def test_serve_listens_on_localhost_only_at_the_configured_port(vault_cfg, stub_uvicorn):
    runner.serve(vault_cfg, open_browser=False)
    config = stub_uvicorn.instances[0].config
    assert (config.host, config.port) == ("127.0.0.1", 9123)


def test_serve_starts_a_watchdog_on_the_server_with_the_configured_window(vault_cfg, stub_uvicorn):
    cfg = Config(vault=vault_cfg.vault, port=9123, idle_timeout=321)
    runner.serve(cfg)
    (dog,) = watchdogs()
    server, timer = dog.args
    assert server is stub_uvicorn.instances[0]
    assert timer.seconds == 321
    assert dog.daemon is True and dog.started is True


def test_the_timer_the_watchdog_reads_is_the_one_the_app_feeds(vault_cfg, stub_uvicorn):
    # A timeout asked for: the default is never, which starts no watchdog.
    runner.serve(dataclasses.replace(vault_cfg, idle_timeout=900))
    (dog,) = watchdogs()
    app = stub_uvicorn.instances[0].config.app
    layer = app.middleware_stack if app.middleware_stack else app.build_middleware_stack()
    while layer is not None and not isinstance(layer, TrackActivity):
        layer = getattr(layer, "app", None)
    assert layer is not None and layer.timer is dog.args[1]


def test_never_shutting_down_starts_no_watchdog(vault_cfg, stub_uvicorn):
    runner.serve(Config(vault=vault_cfg.vault, port=9123, idle_timeout=0))
    assert watchdogs() == []


def test_a_watchdog_that_fails_is_logged_and_leaves_the_server_up(caplog):
    class Broken(IdleTimer):
        def expired(self, when=None):
            raise RuntimeError("clock exploded")

    server = FakeServer()
    watch(server, Broken(seconds=900), sleep=lambda s: None)
    assert server.should_exit is False
    assert "clock exploded" in caplog.text


# --- telling the user where it is, and opening it ---------------------------

class Booting:
    """A server that comes up after a few polls, or is told to stop first."""

    def __init__(self, up_after=None, stop_after=None):
        self.started, self.should_exit = False, False
        self.up_after, self.stop_after, self.polls = up_after, stop_after, 0

    def sleep(self, seconds):
        self.polls += 1
        if self.up_after is not None and self.polls >= self.up_after:
            self.started = True
        if self.stop_after is not None and self.polls >= self.stop_after:
            self.should_exit = True


def run_announce(server, open_browser):
    opened, out = [], io.StringIO()
    announce(server, "http://127.0.0.1:9123/", open_browser, opener=opened.append,
             sleep=server.sleep, out=out)
    return opened, out.getvalue()


def test_the_url_is_printed_once_the_server_is_up():
    opened, out = run_announce(Booting(up_after=3), open_browser=False)
    assert "http://127.0.0.1:9123/" in out
    assert opened == []


def test_the_browser_opens_only_after_the_server_is_up():
    server = Booting(up_after=3)
    opened = []
    announce(server, "u", True, opener=lambda url: opened.append((url, server.started)),
             sleep=server.sleep, out=io.StringIO())
    assert opened == [("u", True)]


def test_a_server_that_never_came_up_gets_neither_a_url_nor_a_browser():
    """A taken port: should_exit is set by serve()'s finally, started never is."""
    opened, out = run_announce(Booting(stop_after=2), open_browser=True)
    assert opened == [] and out == ""


def test_serve_announces_through_a_helper_thread_that_cannot_hold_the_process(vault_cfg, stub_uvicorn):
    runner.serve(vault_cfg, open_browser=True)
    (helper,) = [t for t in RecordedThread.made if t.target is runner.announce]
    server, url, flag = helper.args
    assert (server, url, flag) == (stub_uvicorn.instances[0], "http://127.0.0.1:9123/", True)
    assert helper.daemon is True


def test_when_serve_returns_the_helper_threads_are_told_to_stop(vault_cfg, stub_uvicorn):
    """A taken port never sets should_exit itself; the announce thread would
    poll forever (and a watchdog would outlive the server in-process)."""
    def refuse(server):
        server.started = False
        raise SystemExit(1)

    stub_uvicorn.behaviour = staticmethod(refuse)
    with pytest.raises(runner.PortUnavailable):
        runner.serve(vault_cfg)
    assert stub_uvicorn.instances[0].should_exit is True


def test_ctrl_c_ends_serve_quietly(vault_cfg, stub_uvicorn):
    def interrupt(server):
        raise KeyboardInterrupt

    stub_uvicorn.behaviour = staticmethod(interrupt)
    runner.serve(vault_cfg)                      # no exception


def test_sigterm_during_the_run_stops_it_like_ctrl_c(vault_cfg, stub_uvicorn):
    reached = []

    def terminate(server):
        signal.raise_signal(signal.SIGTERM)
        reached.append("still running")          # must be unreachable

    stub_uvicorn.behaviour = staticmethod(terminate)
    runner.serve(vault_cfg)
    assert reached == []


def test_sigterm_handler_is_put_back_afterwards(vault_cfg, stub_uvicorn):
    def mine(signum, frame):
        pass

    original = signal.signal(signal.SIGTERM, mine)
    try:
        runner.serve(vault_cfg)
        assert signal.getsignal(signal.SIGTERM) is mine
    finally:
        signal.signal(signal.SIGTERM, original)


def test_a_port_that_is_taken_is_reported_not_swallowed(vault_cfg, stub_uvicorn):
    def refuse(server):
        server.started = False
        raise SystemExit(1)                      # what uvicorn does when it cannot bind

    stub_uvicorn.behaviour = staticmethod(refuse)
    with pytest.raises(runner.PortUnavailable, match=r"9123.*web\.port"):
        runner.serve(vault_cfg)


# --- the command -------------------------------------------------------------

def test_serve_passes_the_port_and_the_browser_flag(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    (vault / "oknowledge" / "links").mkdir(parents=True)
    cfg = Config(vault=vault, port=9123)
    monkeypatch.setattr("oknowledge.cli.load_config", lambda path=None: cfg)

    seen = {}
    monkeypatch.setattr("oknowledge.cli.serve",
                        lambda config, open_browser: seen.update(port=config.port,
                                                                 open=open_browser))
    assert main(["serve", "--open"]) == 0
    assert seen == {"port": 9123, "open": True}


def test_serve_without_open_does_not_open_the_browser(tmp_path, monkeypatch):
    cfg = Config(vault=tmp_path / "vault")
    monkeypatch.setattr("oknowledge.cli.load_config", lambda path=None: cfg)
    seen = {}
    monkeypatch.setattr("oknowledge.cli.serve",
                        lambda config, open_browser: seen.update(open=open_browser))
    main(["serve"])
    assert seen == {"open": False}


def test_the_command_reaches_the_runner(tmp_path, monkeypatch):
    cfg = Config(vault=tmp_path / "vault")
    monkeypatch.setattr("oknowledge.cli.load_config", lambda path=None: cfg)
    seen = []
    monkeypatch.setattr(runner, "serve", lambda config, open_browser: seen.append(open_browser))
    assert main(["serve"]) == 0
    assert seen == [False]


def test_a_taken_port_is_exit_2_with_a_hint(tmp_path, monkeypatch, capsys):
    cfg = Config(vault=tmp_path / "vault", port=9123)
    monkeypatch.setattr("oknowledge.cli.load_config", lambda path=None: cfg)

    def taken(config, open_browser):
        raise runner.PortUnavailable("could not listen on 127.0.0.1:9123. Set another web.port.")

    monkeypatch.setattr(runner, "serve", taken)
    assert main(["serve"]) == 2
    err = capsys.readouterr().err
    assert err == "oknowledge: could not listen on 127.0.0.1:9123. Set another web.port.\n"


def test_a_bad_config_is_exit_2_and_never_starts_a_server(tmp_path, monkeypatch, capsys):
    bad = tmp_path / "config.toml"
    bad.write_text("vault = [", encoding="utf-8")
    monkeypatch.setattr(runner, "serve", lambda *a: pytest.fail("a server was started"))
    assert main(["--config", str(bad), "serve"]) == 2
    assert "Traceback" not in capsys.readouterr().err


# --- which interface it listens on, and the address you can type -------------

def test_serve_listens_where_the_config_says(vault_cfg, stub_uvicorn):
    runner.serve(dataclasses.replace(vault_cfg, host="0.0.0.0"), open_browser=False)
    assert stub_uvicorn.instances[0].config.host == "0.0.0.0"


def test_every_interface_is_not_an_address_you_can_visit():
    # Printing http://0.0.0.0:8787/ and opening a browser tab on it is a dead
    # end: it means "every interface", not a place.
    assert runner.visitable("0.0.0.0") == "127.0.0.1"
    assert runner.visitable("::") == "127.0.0.1"
    assert runner.visitable("192.168.1.9") == "192.168.1.9"


def test_listening_only_here_says_nothing_about_the_network():
    for host in ("127.0.0.1", "localhost", "::1"):
        assert runner.shared_note(host, 8787) == "", host


def test_listening_on_every_interface_names_the_address_and_the_risk():
    said = runner.shared_note("0.0.0.0", 8787, finder=lambda: "192.168.100.178")
    assert "http://192.168.100.178:8787/" in said
    # The point of the line: who else can reach it, and what they can do.
    assert "Anyone" in said and "change" in said


def test_a_machine_with_no_address_is_warned_without_half_a_url():
    said = runner.shared_note("0.0.0.0", 8787, finder=lambda: "")
    assert "Anyone" in said
    # Not "at http://:8787/", which is a URL with the address missing.
    assert "http://" not in said


def test_a_host_that_is_already_an_address_is_the_one_named():
    # The finder answers something else on purpose: a config that names one
    # interface must not be advertised at another. (Passing no finder let this
    # pass by luck on a machine whose own address was the one in the test.)
    said = runner.shared_note("10.1.1.1", 8787, finder=lambda: "192.168.1.254")
    assert "http://10.1.1.1:8787/" in said
    assert "192.168.1.254" not in said


def test_the_address_of_this_machine_is_found_without_sending_anything():
    found = runner.lan_address()
    assert found == "" or found.count(".") == 3


def test_a_probe_that_is_not_an_address_is_not_a_crash():
    assert runner.lan_address(probe="not an address at all") == ""


def test_what_the_server_prints_is_where_to_go_and_who_else_can_get_there(
        vault_cfg, stub_uvicorn):
    runner.serve(dataclasses.replace(vault_cfg, host="0.0.0.0"), open_browser=False)
    (helper,) = [t for t in RecordedThread.made if t.target is runner.announce]
    _, url, _ = helper.args
    # The URL is for the browser on this machine; the warning is the half that
    # is about the phone, and about everybody else on that wifi.
    assert url == f"http://127.0.0.1:{vault_cfg.port}/"
    assert "Anyone on it" in helper.kwargs["also"]


def test_listening_only_here_prints_no_second_line(vault_cfg, stub_uvicorn):
    runner.serve(vault_cfg, open_browser=False)
    (helper,) = [t for t in RecordedThread.made if t.target is runner.announce]
    assert helper.kwargs["also"] == ""


def test_the_second_line_comes_after_the_url_and_only_when_there_is_one():
    out = io.StringIO()
    server = Booting(up_after=1)
    announce(server, "http://127.0.0.1:9123/", False, opener=lambda url: None,
             sleep=server.sleep, out=out, also="oknowledge: and from the wifi")
    assert out.getvalue().splitlines() == [
        "oknowledge: the library is at http://127.0.0.1:9123/",
        "oknowledge: and from the wifi"]
