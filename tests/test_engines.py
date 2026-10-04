import json
import subprocess

import httpx
import pytest

from oknowledge.ai import AllEnginesFailed, analyze_with_chain, build_engine
from oknowledge.ai.api import ApiEngine
from oknowledge.ai.base import EngineError
from oknowledge.ai.ollama import OllamaEngine
from oknowledge.ai.opencode import OpenCodeEngine
from oknowledge.config import Config

GOOD = json.dumps({
    "title": "T", "summary": "S", "points": ["p"], "category": "Redes", "tags": ["vpn"],
})
META = {"url": "https://e.com/x", "title": "T"}


def make_config(tmp_path, chain):
    vault = tmp_path / "vault"
    vault.mkdir(exist_ok=True)
    return Config(vault=vault, chain=tuple(chain), engines={"fake": {}})


def test_opencode_runs_in_an_empty_directory_and_without_plugins(monkeypatch):
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        seen["cwd"] = kwargs["cwd"]
        assert kwargs["stdin"] is subprocess.DEVNULL
        assert "stderr" not in kwargs or kwargs["stderr"] != subprocess.STDOUT
        seen["cwd_was_empty"] = not list(__import__("pathlib").Path(kwargs["cwd"]).iterdir())
        return type("P", (), {"returncode": 0, "stdout": GOOD, "stderr": ""})()

    monkeypatch.setattr("subprocess.run", fake_run)
    out = OpenCodeEngine(model="opencode/x-free").complete("hola")

    assert out == GOOD
    assert seen["argv"][:5] == ["opencode", "run", "--pure", "-m", "opencode/x-free"]
    assert seen["argv"][5] == "hola"
    assert seen["cwd_was_empty"]


def test_opencode_failing_is_an_engine_error(monkeypatch):
    monkeypatch.setattr(
        "subprocess.run",
        lambda argv, **kw: type("P", (), {"returncode": 1, "stdout": "", "stderr": "nope"})(),
    )
    with pytest.raises(EngineError, match="nope"):
        OpenCodeEngine(model="m").complete("hola")


def test_opencode_not_installed_is_an_engine_error(monkeypatch):
    def missing(argv, **kw):
        raise FileNotFoundError(2, "No such file or directory", "opencode")

    monkeypatch.setattr("subprocess.run", missing)
    with pytest.raises(EngineError, match="opencode is not installed.*'opencode'"):
        OpenCodeEngine(model="m").complete("hola")


def test_opencode_has_a_timeout_and_reports_it(monkeypatch):
    seen = {}

    def hang(argv, **kw):
        seen["timeout"] = kw["timeout"]
        raise subprocess.TimeoutExpired(argv, kw["timeout"])

    monkeypatch.setattr("subprocess.run", hang)
    with pytest.raises(EngineError, match="timed out after 7s"):
        OpenCodeEngine(model="m", timeout=7).complete("hola")
    assert seen["timeout"] == 7


def test_opencode_empty_output_is_an_engine_error(monkeypatch):
    monkeypatch.setattr(
        "subprocess.run",
        lambda argv, **kw: type("P", (), {"returncode": 0, "stdout": " \n", "stderr": ""})(),
    )
    with pytest.raises(EngineError, match="empty"):
        OpenCodeEngine(model="m").complete("hola")


class Response:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status_code = status
        self.request = httpx.Request("POST", "http://x")

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload

    @property
    def text(self):
        return json.dumps(self.payload)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}", request=self.request,
                response=httpx.Response(self.status_code, request=self.request),
            )


def ollama(**kw):
    return OllamaEngine(model="qwen2.5:7b", url="http://localhost:11434",
                        ensure=lambda: None, **kw)


def test_ollama_asks_for_json_and_reads_the_message(monkeypatch):
    seen = {}

    def fake_post(url, json=None, timeout=None):
        seen["url"] = url
        seen["body"] = json
        seen["timeout"] = timeout
        return Response({"message": {"content": GOOD}})

    monkeypatch.setattr("httpx.post", fake_post)
    out = ollama().complete("hola")

    assert out == GOOD
    assert seen["url"] == "http://localhost:11434/api/chat"
    assert seen["body"]["format"] == "json"
    assert seen["body"]["stream"] is False
    assert seen["body"]["messages"][0]["content"] == "hola"
    assert seen["timeout"]


def test_ollama_connection_refused_names_the_engine(monkeypatch):
    def refused(url, json=None, timeout=None):
        raise httpx.ConnectError("All connection attempts failed")

    monkeypatch.setattr("httpx.post", refused)
    with pytest.raises(EngineError, match="ollama.*connection attempts failed"):
        ollama().complete("hola")


def test_ollama_model_not_found_surfaces_the_server_message(monkeypatch):
    monkeypatch.setattr(
        "httpx.post",
        lambda url, json=None, timeout=None: Response(
            {"error": "model 'qwen2.5:7b' not found"}, status=404),
    )
    with pytest.raises(EngineError, match="ollama.*model 'qwen2.5:7b' not found.*ollama pull qwen2.5:7b"):
        ollama().complete("hola")


def test_ollama_read_timeout_is_an_engine_error(monkeypatch):
    def hang(url, json=None, timeout=None):
        raise httpx.ReadTimeout("slow")

    monkeypatch.setattr("httpx.post", hang)
    with pytest.raises(EngineError, match="ollama.*timed out"):
        ollama(timeout=3).complete("hola")


def test_ollama_reply_without_text_is_an_engine_error(monkeypatch):
    monkeypatch.setattr(
        "httpx.post", lambda url, json=None, timeout=None: Response({"message": {}}))
    with pytest.raises(EngineError, match="ollama.*unexpected"):
        ollama().complete("hola")


def test_ollama_ensure_failure_propagates(monkeypatch):
    def down():
        raise EngineError("ollama is not installed")

    monkeypatch.setattr("httpx.post", lambda *a, **k: pytest.fail("must not post"))
    with pytest.raises(EngineError, match="not installed"):
        OllamaEngine(model="m", ensure=down).complete("hola")


def test_the_api_engine_sends_the_key_from_the_environment(monkeypatch):
    seen = {}
    monkeypatch.setenv("MY_KEY", "sk-secret")
    monkeypatch.setattr("httpx.post", lambda url, headers=None, json=None, timeout=None:
                        seen.update(url=url, headers=headers, body=json, timeout=timeout)
                        or Response({"content": [{"text": GOOD}]}))

    out = ApiEngine(provider="anthropic", model="claude-sonnet-5", key_env="MY_KEY").complete("hola")

    assert out == GOOD
    assert seen["url"] == "https://api.anthropic.com/v1/messages"
    assert seen["headers"] == {"x-api-key": "sk-secret", "anthropic-version": "2023-06-01"}
    assert seen["body"] == {
        "model": "claude-sonnet-5", "max_tokens": 2000,
        "messages": [{"role": "user", "content": "hola"}],
    }
    assert seen["timeout"]


def test_the_api_engine_without_a_key_says_so(monkeypatch):
    monkeypatch.delenv("MY_KEY", raising=False)
    monkeypatch.setattr("httpx.post", lambda *a, **k: pytest.fail("must not post"))
    with pytest.raises(EngineError, match="MY_KEY"):
        ApiEngine(provider="anthropic", model="m", key_env="MY_KEY").complete("hola")


def test_the_api_engine_never_echoes_the_key_in_errors(monkeypatch):
    monkeypatch.setenv("MY_KEY", "sk-secret")
    monkeypatch.setattr(
        "httpx.post",
        lambda url, headers=None, json=None, timeout=None: Response({"error": "bad"}, status=401),
    )
    with pytest.raises(EngineError) as error:
        ApiEngine(provider="anthropic", model="m", key_env="MY_KEY").complete("hola")
    assert "sk-secret" not in str(error.value)
    assert "anthropic" in str(error.value)


def test_the_api_engine_reply_without_text_is_an_engine_error(monkeypatch):
    monkeypatch.setenv("MY_KEY", "sk-secret")
    monkeypatch.setattr(
        "httpx.post",
        lambda url, headers=None, json=None, timeout=None: Response({"content": []}),
    )
    with pytest.raises(EngineError, match="unexpected"):
        ApiEngine(provider="anthropic", model="m", key_env="MY_KEY").complete("hola")


def test_the_api_engine_speaks_the_openai_shape(monkeypatch):
    seen = {}
    monkeypatch.setenv("MY_KEY", "sk-secret")
    monkeypatch.setattr("httpx.post", lambda url, headers=None, json=None, timeout=None:
                        seen.update(url=url, headers=headers, body=json) or Response(
                            {"choices": [{"message": {"content": GOOD}}]}))
    out = ApiEngine(provider="openai", model="gpt-x", key_env="MY_KEY").complete("hola")
    assert out == GOOD
    assert seen["url"] == "https://api.openai.com/v1/chat/completions"
    assert seen["headers"] == {"Authorization": "Bearer sk-secret"}
    assert seen["body"] == {"model": "gpt-x", "messages": [{"role": "user", "content": "hola"}]}


def test_the_api_engine_surfaces_the_servers_error_without_the_key(monkeypatch):
    monkeypatch.setenv("MY_KEY", "sk-secret")
    monkeypatch.setattr(
        "httpx.post",
        lambda url, headers=None, json=None, timeout=None: Response(
            {"error": {"type": "authentication_error", "message": "invalid x-api-key sk-secret"}},
            status=401),
    )
    with pytest.raises(EngineError) as error:
        ApiEngine(provider="anthropic", model="m", key_env="MY_KEY").complete("hola")
    assert "invalid x-api-key" in str(error.value)
    assert "sk-secret" not in str(error.value)


def test_opencode_answer_is_stdout_only_without_the_terminal_chrome(monkeypatch):
    chrome = "\x1b[0m\n> build · ling-3.1-flash-free\n\x1b[0m"
    monkeypatch.setattr(
        "subprocess.run",
        lambda argv, **kw: type("P", (), {"returncode": 0, "stdout": GOOD, "stderr": chrome})(),
    )
    out = OpenCodeEngine(model="m").complete("hola")
    assert out == GOOD
    assert "\x1b" not in out and "build" not in out


def test_opencode_permission_error_is_an_engine_error(monkeypatch):
    def denied(argv, **kw):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr("subprocess.run", denied)
    with pytest.raises(EngineError, match="opencode could not be run.*Permission denied"):
        OpenCodeEngine(model="m").complete("hola")


def test_opencode_argument_too_long_is_an_engine_error(monkeypatch):
    def too_long(argv, **kw):
        raise OSError(7, "Argument list too long")

    monkeypatch.setattr("subprocess.run", too_long)
    with pytest.raises(EngineError, match="Argument list too long"):
        OpenCodeEngine(model="m").complete("x")


def test_an_unknown_engine_in_the_chain_falls_through(tmp_path, monkeypatch):
    from oknowledge.ai.fake import FakeEngine

    real = build_engine
    monkeypatch.setattr(
        "oknowledge.ai.build_engine",
        lambda name, cfg: FakeEngine([GOOD]) if name == "ollama" else real(name, cfg),
    )
    analysis, used = analyze_with_chain(make_config(tmp_path, ["gpt5", "ollama"]), "t", META, [])
    assert used == "ollama"


def test_an_unknown_engine_alone_fails_naming_it(tmp_path):
    with pytest.raises(AllEnginesFailed, match="gpt5"):
        analyze_with_chain(make_config(tmp_path, ["gpt5"]), "t", META, [])


def test_the_chain_falls_through_to_the_next_engine(tmp_path, monkeypatch):
    from oknowledge.ai.fake import FakeEngine

    broken = FakeEngine([EngineError("sin cuota")])
    working = FakeEngine([GOOD])
    engines = {"opencode": broken, "ollama": working}
    monkeypatch.setattr("oknowledge.ai.build_engine", lambda name, cfg: engines[name])

    cfg = make_config(tmp_path, ["opencode", "ollama"])
    analysis, used = analyze_with_chain(cfg, "texto", META, [])

    assert used == "ollama"
    assert analysis.category == "Redes"


def test_the_chain_falls_through_when_the_reply_is_unusable(tmp_path, monkeypatch):
    from oknowledge.ai.fake import FakeEngine

    engines = {"opencode": FakeEngine(["no json", "still no json"]),
               "ollama": FakeEngine([GOOD])}
    monkeypatch.setattr("oknowledge.ai.build_engine", lambda name, cfg: engines[name])
    _, used = analyze_with_chain(make_config(tmp_path, ["opencode", "ollama"]), "t", META, [])
    assert used == "ollama"


def test_an_engine_missing_from_the_chain_is_never_used(tmp_path, monkeypatch):
    from oknowledge.ai.fake import FakeEngine

    built = []
    monkeypatch.setattr(
        "oknowledge.ai.build_engine",
        lambda name, cfg: built.append(name) or FakeEngine([EngineError("down")]),
    )
    cfg = make_config(tmp_path, ["opencode"])
    with pytest.raises(AllEnginesFailed):
        analyze_with_chain(cfg, "texto", META, [])
    assert built == ["opencode"]


def test_the_first_engine_that_works_stops_the_chain(tmp_path, monkeypatch):
    from oknowledge.ai.fake import FakeEngine

    built = []
    monkeypatch.setattr(
        "oknowledge.ai.build_engine",
        lambda name, cfg: built.append(name) or FakeEngine([GOOD]),
    )
    _, used = analyze_with_chain(make_config(tmp_path, ["ollama", "opencode"]), "t", META, [])
    assert used == "ollama" and built == ["ollama"]


def test_when_every_engine_fails_the_error_names_them_all(tmp_path, monkeypatch):
    from oknowledge.ai.fake import FakeEngine

    monkeypatch.setattr(
        "oknowledge.ai.build_engine",
        lambda name, cfg: FakeEngine([EngineError(f"{name} caído")]),
    )
    cfg = make_config(tmp_path, ["opencode", "ollama"])
    with pytest.raises(AllEnginesFailed) as error:
        analyze_with_chain(cfg, "texto", META, [])
    assert "opencode" in str(error.value) and "ollama" in str(error.value)


def test_an_empty_chain_is_not_reported_as_engines_failing(tmp_path):
    cfg = make_config(tmp_path, [])
    with pytest.raises(AllEnginesFailed, match="no engine"):
        analyze_with_chain(cfg, "texto", META, [])


def test_forcing_an_engine_ignores_the_chain(tmp_path, monkeypatch):
    from oknowledge.ai.fake import FakeEngine

    calls = []
    monkeypatch.setattr(
        "oknowledge.ai.build_engine",
        lambda name, cfg: calls.append(name) or FakeEngine([GOOD]),
    )
    cfg = make_config(tmp_path, ["opencode", "ollama"])
    analyze_with_chain(cfg, "texto", META, [], engine="ollama")
    assert calls == ["ollama"]


def test_build_engine_refuses_a_name_it_does_not_know(tmp_path):
    with pytest.raises(EngineError, match="gpt5"):
        build_engine("gpt5", make_config(tmp_path, ["opencode"]))


def test_build_engine_reads_each_engines_settings(tmp_path):
    cfg = Config(vault=tmp_path, chain=("opencode",), engines={
        "opencode": {"model": "opencode/other-free"},
        "ollama": {"model": "llama3", "url": "http://h:1/"},
        "api": {"provider": "openai", "model": "gpt", "key_env": "K"},
    })
    assert build_engine("opencode", cfg).model == "opencode/other-free"
    assert (build_engine("ollama", cfg).model, build_engine("ollama", cfg).url) == (
        "llama3", "http://h:1")
    api = build_engine("api", cfg)
    assert (api.provider, api.key_env) == ("openai", "K")


class Host:
    """Fakes everything ensure_running touches: probe, systemctl, which, Popen, clock."""

    def __init__(self, monkeypatch, up_after=None, user_unit=False, system_unit=False,
                 start_rc=0, ollama_bin=True):
        self.calls = []
        self.spawned = []
        self.up = up_after == 0
        self.up_after = up_after
        self.probes = 0
        self.user_unit, self.system_unit, self.start_rc = user_unit, system_unit, start_rc

        def get(url, timeout=None):
            self.probes += 1
            if self.up_after is not None and self.probes > self.up_after:
                self.up = True
            if not self.up:
                raise httpx.ConnectError("refused")
            return Response({})

        def run(argv, **kw):
            self.calls.append(argv)
            assert argv[0] == "systemctl", f"unexpected command {argv}"
            user = "--user" in argv
            verb = argv[2] if user else argv[1]
            stdout, rc = "", 0
            if verb == "list-unit-files":
                present = self.user_unit if user else self.system_unit
                stdout = "ollama.service disabled disabled\n" if present else \
                    "0 unit files listed.\n"
            elif verb == "start":
                rc = self.start_rc
            return type("P", (), {"returncode": rc, "stdout": stdout, "stderr": "denied"})()

        monkeypatch.setattr("httpx.get", get)
        monkeypatch.setattr("subprocess.run", run)
        monkeypatch.setattr("shutil.which", lambda n: "/usr/bin/ollama" if ollama_bin else None)
        monkeypatch.setattr("subprocess.Popen",
                            lambda argv, **kw: self.spawned.append((argv, kw)))
        monkeypatch.setattr("time.sleep", lambda s: None)

    def started(self):
        return [c for c in self.calls if "start" in c or "enable" in c]


def test_ensure_running_starts_nothing_when_ollama_is_up(monkeypatch):
    from oknowledge.ai.ollama import ensure_running

    host = Host(monkeypatch, up_after=0, user_unit=True, system_unit=True)
    ensure_running("http://localhost:11434")
    assert host.calls == [] and host.spawned == []


def test_ensure_running_starts_the_user_unit_when_there_is_one(monkeypatch):
    from oknowledge.ai.ollama import ensure_running

    host = Host(monkeypatch, up_after=2, user_unit=True, system_unit=True)
    ensure_running("http://localhost:11434")
    assert host.started() == [["systemctl", "--user", "start", "ollama.service"]]
    assert host.spawned == []


def test_a_system_unit_is_reported_never_started_or_escalated(monkeypatch):
    from oknowledge.ai.ollama import ensure_running

    host = Host(monkeypatch, system_unit=True)
    with pytest.raises(EngineError) as error:
        ensure_running("http://localhost:11434")
    message = str(error.value)
    assert "sudo systemctl start ollama" in message
    assert "sudo systemctl enable --now ollama" in message
    assert host.spawned == []
    assert host.started() == []
    assert not any("sudo" in part for call in host.calls for part in call)


def test_ensure_running_spawns_detached_when_there_is_no_unit_at_all(monkeypatch):
    from oknowledge.ai.ollama import ensure_running

    host = Host(monkeypatch, up_after=2)
    ensure_running("http://localhost:11434")
    assert host.started() == []
    (argv, kw), = host.spawned
    assert argv == ["ollama", "serve"] and kw["start_new_session"] is True


def test_ensure_running_gives_up_with_a_how_to_when_it_never_answers(monkeypatch):
    from oknowledge.ai.ollama import ensure_running

    Host(monkeypatch, up_after=None, user_unit=True)
    with pytest.raises(EngineError, match="could not be started.*systemctl --user start ollama"):
        ensure_running("http://localhost:11434", timeout=0.01)


def test_a_user_unit_that_fails_to_start_never_gets_a_competing_spawn(monkeypatch):
    from oknowledge.ai.ollama import ensure_running

    host = Host(monkeypatch, user_unit=True, start_rc=1)
    with pytest.raises(EngineError, match="via systemd.*denied"):
        ensure_running("http://localhost:11434")
    assert host.spawned == []


def test_ensure_running_without_unit_or_binary_is_an_engine_error(monkeypatch):
    from oknowledge.ai.ollama import ensure_running

    host = Host(monkeypatch, ollama_bin=False)
    with pytest.raises(EngineError, match="ollama is not installed"):
        ensure_running("http://localhost:11434")
    assert host.spawned == []


def test_without_systemctl_a_missing_unit_means_the_detached_spawn(monkeypatch):
    from oknowledge.ai.ollama import ensure_running

    host = Host(monkeypatch, up_after=2)

    def no_systemctl(argv, **kw):
        host.calls.append(argv)
        raise FileNotFoundError(2, "No such file or directory", "systemctl")

    monkeypatch.setattr("subprocess.run", no_systemctl)
    ensure_running("http://localhost:11434")
    assert [argv for argv, _ in host.spawned] == [["ollama", "serve"]]


def test_a_remote_ollama_url_never_starts_a_local_server(monkeypatch):
    from oknowledge.ai.ollama import ensure_running

    host = Host(monkeypatch, up_after=None)
    with pytest.raises(EngineError, match="remote.*nothing was started"):
        ensure_running("http://gpu-box:11434")
    assert host.calls == [] and host.spawned == []


def test_a_failing_spawn_is_an_engine_error(monkeypatch):
    from oknowledge.ai.ollama import ensure_running

    Host(monkeypatch)

    def denied(argv, **kw):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr("subprocess.Popen", denied)
    with pytest.raises(EngineError, match="could not be started.*Permission denied"):
        ensure_running("http://localhost:11434")
