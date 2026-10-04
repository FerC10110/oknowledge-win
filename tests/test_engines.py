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
    with pytest.raises(EngineError, match="opencode is not installed"):
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
    with pytest.raises(EngineError, match="ollama.*model 'qwen2.5:7b' not found"):
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
    assert seen["headers"]["x-api-key"] == "sk-secret"
    assert "anthropic" in seen["url"]
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
                        seen.update(headers=headers) or Response(
                            {"choices": [{"message": {"content": GOOD}}]}))
    out = ApiEngine(provider="openai", model="m", key_env="MY_KEY").complete("hola")
    assert out == GOOD
    assert seen["headers"]["Authorization"] == "Bearer sk-secret"


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


def test_ensure_running_without_ollama_installed_is_an_engine_error(monkeypatch):
    from oknowledge.ai.ollama import ensure_running

    def down(url, timeout=None):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr("httpx.get", down)
    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.setattr("subprocess.Popen", lambda *a, **k: pytest.fail("must not spawn"))
    with pytest.raises(EngineError, match="ollama is not installed"):
        ensure_running("http://localhost:11434")
