"""`oknowledge serve`: start the web, and stop it when nobody is using it.

The part that matters is what the idle timer must NOT do: stop the server while
a request, or the background re-analysis it started, is still running. Every
timer test drives an injected clock; nothing here sleeps.
"""

import asyncio
import signal

import pytest
from fastapi.testclient import TestClient

from oknowledge.cli import main
from oknowledge.config import Config
from oknowledge.model import Note
from oknowledge.vault import rebuild_indexes, write_note
from oknowledge.web import runner
from oknowledge.web.runner import IdleTimer, TrackActivity, build_app, watch

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
        self.behaviour = lambda server: None
        StubServer.instances.append(self)

    def run(self):
        StubServer.behaviour(self)


@pytest.fixture
def stub_uvicorn(monkeypatch):
    StubServer.instances = []
    StubServer.behaviour = staticmethod(lambda server: None)
    monkeypatch.setattr(runner.uvicorn, "Server", StubServer)
    monkeypatch.setattr(runner.threading, "Thread",
                        lambda **kw: type("T", (), {"start": lambda self: None})())
    return StubServer


def test_serve_listens_on_localhost_only_at_the_configured_port(vault_cfg, stub_uvicorn):
    runner.serve(vault_cfg, open_browser=False)
    config = stub_uvicorn.instances[0].config
    assert (config.host, config.port) == ("127.0.0.1", 9123)


def test_serve_opens_the_browser_only_when_asked(vault_cfg, stub_uvicorn, monkeypatch):
    opened = []

    class FakeTimer:
        def __init__(self, delay, function, args):
            self.args = args
            self.daemon = False

        def start(self):
            opened.append(self.args)

    monkeypatch.setattr(runner.threading, "Timer", FakeTimer)
    runner.serve(vault_cfg, open_browser=False)
    assert opened == []
    runner.serve(vault_cfg, open_browser=True)
    assert opened == [["http://127.0.0.1:9123/"]]


def test_ctrl_c_ends_serve_quietly(vault_cfg, stub_uvicorn):
    def interrupt(server):
        raise KeyboardInterrupt

    stub_uvicorn.behaviour = staticmethod(interrupt)
    runner.serve(vault_cfg)                      # no exception


def test_sigterm_ends_serve_quietly_and_the_old_handler_comes_back(vault_cfg, stub_uvicorn):
    def terminate(server):
        signal.raise_signal(signal.SIGTERM)

    stub_uvicorn.behaviour = staticmethod(terminate)
    before = signal.getsignal(signal.SIGTERM)
    runner.serve(vault_cfg)
    assert signal.getsignal(signal.SIGTERM) is before


def test_a_port_that_is_taken_is_reported_not_swallowed(vault_cfg, stub_uvicorn):
    def refuse(server):
        server.started = False
        raise SystemExit(1)                      # what uvicorn does when it cannot bind

    stub_uvicorn.behaviour = staticmethod(refuse)
    with pytest.raises(runner.PortUnavailable):
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
        raise runner.PortUnavailable("could not listen on 127.0.0.1:9123")

    monkeypatch.setattr(runner, "serve", taken)
    assert main(["serve"]) == 2
    err = capsys.readouterr().err
    assert "9123" in err and "web.port" in err and "Traceback" not in err


def test_a_bad_config_is_exit_2_and_never_starts_a_server(tmp_path, monkeypatch, capsys):
    bad = tmp_path / "config.toml"
    bad.write_text("vault = [", encoding="utf-8")
    monkeypatch.setattr(runner, "serve", lambda *a: pytest.fail("a server was started"))
    assert main(["--config", str(bad), "serve"]) == 2
    assert "Traceback" not in capsys.readouterr().err
