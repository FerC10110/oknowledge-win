"""Start the web on demand and stop it when nobody is using it.

There is no daemon: the server exists while you are using it.

"Nobody is using it" is a stricter claim than "no request arrived lately". A
re-analysis runs as a background task of this same process, holds the link's
queue lock, and can take minutes; the browser that asked for it went away the
moment the 303 came back. So idleness is measured from the last request that
*finished*, and the clock does not run at all while any request, or the
background work attached to one, is still going.
"""

from __future__ import annotations

import signal
import threading
import time
import webbrowser

import uvicorn

from ..config import Config, PortUnavailable
from .app import create_app

# How often the watchdog looks at the timer. Shutdown can be this late.
CHECK_EVERY = 5.0


class IdleTimer:
    """Idle for `seconds` since the last thing finished. 0 means never shut down.

    begin()/end() bracket a unit of work. While any is open the timer is never
    expired, and end() restarts the countdown, so a long job is followed by a
    full idle window rather than by an immediate shutdown. Called from the
    event loop and from the watchdog thread, hence the lock.
    """

    def __init__(self, seconds: int, now=time.monotonic):
        self.seconds = seconds
        self._now = now
        self._lock = threading.Lock()
        self._active = 0
        self.last = now()

    @property
    def active(self) -> int:
        with self._lock:
            return self._active

    def touch(self, when: float | None = None) -> None:
        with self._lock:
            self.last = self._now() if when is None else when

    def begin(self) -> None:
        with self._lock:
            self._active += 1

    def end(self, when: float | None = None) -> None:
        with self._lock:
            self._active = max(0, self._active - 1)
            self.last = self._now() if when is None else when

    def expired(self, when: float | None = None) -> bool:
        if self.seconds <= 0:
            return False
        with self._lock:
            if self._active:
                return False
            moment = self._now() if when is None else when
            return (moment - self.last) > self.seconds


class TrackActivity:
    """Pure ASGI, so that "the request is over" means the whole ASGI call.

    Starlette runs a route's background tasks inside the response call, after
    the body has been sent, so awaiting the inner app is what keeps a
    re-analysis counted as work. (A BaseHTTPMiddleware would also see the
    response leave early, and would only touch the clock when a request
    started.) The decrement is in a finally: a handler that raises, or a
    client that disconnects, must not leave the server counted busy forever.
    """

    def __init__(self, app, timer: IdleTimer):
        self.app = app
        self.timer = timer

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        self.timer.begin()
        try:
            await self.app(scope, receive, send)
        finally:
            self.timer.end()


def build_app(cfg: Config, timer: IdleTimer):
    app = create_app(cfg)
    app.add_middleware(TrackActivity, timer=timer)
    return app


def watch(server, timer: IdleTimer, interval: float = CHECK_EVERY, sleep=time.sleep) -> None:
    """Ask the server to stop once the timer says so."""
    # A plain thread rather than an asyncio task: it needs no hook into the
    # app's lifecycle, which modern FastAPI no longer offers through on_event.
    while not server.should_exit:
        sleep(interval)
        if timer.expired():
            server.should_exit = True


def _terminate_like_ctrl_c(signum, frame):
    raise KeyboardInterrupt


def serve(cfg: Config, open_browser: bool = False) -> None:
    timer = IdleTimer(cfg.idle_timeout)
    server = uvicorn.Server(uvicorn.Config(
        build_app(cfg, timer), host="127.0.0.1", port=cfg.port, log_level="warning",
    ))

    threading.Thread(target=watch, args=(server, timer), daemon=True).start()

    if open_browser:
        opener = threading.Timer(0.8, webbrowser.open, [f"http://127.0.0.1:{cfg.port}/"])
        opener.daemon = True
        opener.start()

    # uvicorn finishes its graceful shutdown and then re-raises the signal it
    # caught; with the default handlers that is a traceback for Ctrl-C and an
    # abrupt kill for SIGTERM. Both mean "stop", so both end the same way.
    previous = None
    if threading.current_thread() is threading.main_thread():
        previous = signal.signal(signal.SIGTERM, _terminate_like_ctrl_c)
    interrupted = False
    try:
        server.run()
    except KeyboardInterrupt:
        interrupted = True
    except SystemExit:
        pass            # uvicorn's way of saying it could not bind; checked below
    finally:
        server.should_exit = True          # lets the watchdog thread end
        if previous is not None:
            signal.signal(signal.SIGTERM, previous)
    if not server.started and not interrupted:
        raise PortUnavailable(f"could not listen on 127.0.0.1:{cfg.port}; "
                              "is another copy already running?")
