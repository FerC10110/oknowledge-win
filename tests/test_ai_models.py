"""Each engine listing its own models, with one promise: never raise, never
hang. An engine that cannot say gives back nothing, and the box stays
typable."""

import httpx
import pytest

from oknowledge.ai.api import ApiEngine
from oknowledge.ai.base import MODEL_LIMIT, clean_models
from oknowledge.ai.ollama import OllamaEngine
from oknowledge.ai.opencode import OpenCodeEngine, parse_opencode_models

# httpx refuses raise_for_status() on a response that was never requested, so
# every fake reply below carries one.
GET = httpx.Request("GET", "https://e.test/x")


# --- the shared cleaning ------------------------------------------------------

def test_a_listing_that_is_garbage_lists_nothing():
    assert parse_opencode_models("\x00\x01 no soy una lista") == []


def test_a_listing_of_ten_thousand_lines_is_cut():
    assert len(parse_opencode_models(
        "".join(f"m{n}\n" for n in range(10_000)))) == MODEL_LIMIT


def test_the_names_keep_the_order_they_came_in_and_lose_the_repeats():
    assert parse_opencode_models("b\na\nb\n") == ["b", "a"]


def test_a_name_long_enough_to_break_a_page_is_not_a_name():
    assert clean_models(["x" * 400, "fine"]) == ["fine"]


def test_a_listing_with_blank_lines_and_spaces_is_still_a_listing():
    assert parse_opencode_models("\n  opencode/ling-3.1  \n\nollama/qwen2.5:7b\n") == [
        "opencode/ling-3.1", "ollama/qwen2.5:7b"]


def test_what_is_not_a_string_is_not_a_model():
    assert clean_models(["ok", None, 7, {"name": "x"}]) == ["ok"]


# --- opencode -----------------------------------------------------------------

def test_opencode_lists_what_it_printed(monkeypatch):
    seen = {}

    def fake_run(argv, **kw):
        seen.update(argv=argv, timeout=kw.get("timeout"))
        return type("P", (), {"returncode": 0, "stdout": "a/one\nb/two\n", "stderr": ""})()

    monkeypatch.setattr("oknowledge.ai.opencode.subprocess.run", fake_run)
    assert OpenCodeEngine(model="m").models() == ["a/one", "b/two"]
    assert seen["argv"][1] == "models"
    assert seen["timeout"] == 5          # not the 300 a completion gets


def test_opencode_that_is_not_installed_lists_nothing(monkeypatch):
    monkeypatch.setattr("oknowledge.ai.opencode.subprocess.run",
                        lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("no")))
    assert OpenCodeEngine(model="m").models() == []


def test_opencode_that_takes_too_long_lists_nothing(monkeypatch):
    import subprocess

    monkeypatch.setattr("oknowledge.ai.opencode.subprocess.run",
                        lambda *a, **k: (_ for _ in ()).throw(
                            subprocess.TimeoutExpired("opencode", 5)))
    assert OpenCodeEngine(model="m").models() == []


def test_opencode_that_fails_lists_nothing(monkeypatch):
    monkeypatch.setattr("oknowledge.ai.opencode.subprocess.run",
                        lambda *a, **k: type("P", (), {
                            "returncode": 1, "stdout": "a/one\n", "stderr": "boom"})())
    assert OpenCodeEngine(model="m").models() == []


def test_opencode_that_explodes_in_a_way_nobody_expected_lists_nothing(monkeypatch):
    monkeypatch.setattr("oknowledge.ai.opencode.subprocess.run",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("?!")))
    assert OpenCodeEngine(model="m").models() == []


# --- ollama -------------------------------------------------------------------

def test_a_server_that_is_not_there_lists_nothing_and_does_not_raise(monkeypatch):
    """The state of this machine while this was written: ollama installed and
    its service inactive."""
    monkeypatch.setattr("oknowledge.ai.ollama.httpx.get",
                        lambda *a, **k: (_ for _ in ()).throw(
                            httpx.ConnectError("refused")))
    assert OllamaEngine(model="m", url="http://127.0.0.1:1").models() == []


def test_ollama_lists_the_models_it_has_pulled(monkeypatch):
    body = {"models": [{"name": "qwen2.5:7b"}, {"name": "llama3:8b"}]}
    monkeypatch.setattr("oknowledge.ai.ollama.httpx.get",
                        lambda url, **kw: httpx.Response(200, json=body, request=GET))
    assert OllamaEngine(model="m").models() == ["qwen2.5:7b", "llama3:8b"]


def test_ollama_asks_the_tags_endpoint_and_does_not_wait_long(monkeypatch):
    seen = {}

    def fake_get(url, **kw):
        seen.update(url=url, timeout=kw.get("timeout"))
        return httpx.Response(200, json={"models": []}, request=GET)

    monkeypatch.setattr("oknowledge.ai.ollama.httpx.get", fake_get)
    OllamaEngine(model="m", url="http://localhost:11434/").models()
    assert seen["url"] == "http://localhost:11434/api/tags"
    assert seen["timeout"] == 2.0


def test_ollama_never_starts_the_server_to_answer_this(monkeypatch):
    """Listing is a question, not a request to work: starting a server to
    answer it would turn opening Settings into a 15-second wait."""
    monkeypatch.setattr("oknowledge.ai.ollama.ensure_running",
                        lambda *a, **k: pytest.fail("listing started the server"))
    monkeypatch.setattr("oknowledge.ai.ollama.httpx.get",
                        lambda *a, **k: httpx.Response(200, json={"models": []}, request=GET))
    assert OllamaEngine(model="m").models() == []


def test_a_reply_that_is_not_the_shape_promised_lists_nothing(monkeypatch):
    monkeypatch.setattr("oknowledge.ai.ollama.httpx.get",
                        lambda *a, **k: httpx.Response(200, json={"models": "none"}, request=GET))
    assert OllamaEngine(model="m").models() == []


def test_a_server_that_answers_an_error_lists_nothing(monkeypatch):
    """The body of a 500 can be perfectly good JSON -- a proxy's error page,
    a gateway's own answer -- and still not be this server's model list."""
    monkeypatch.setattr("oknowledge.ai.ollama.httpx.get",
                        lambda *a, **k: httpx.Response(
                            500, json={"models": [{"name": "ghost"}]}, request=GET))
    assert OllamaEngine(model="m").models() == []


# --- api ----------------------------------------------------------------------

def test_the_api_lists_what_the_provider_offers(monkeypatch):
    seen = {}

    def fake_get(url, **kw):
        seen.update(url=url, headers=kw.get("headers"), timeout=kw.get("timeout"))
        return httpx.Response(200, json={"data": [{"id": "claude-sonnet-5"}]}, request=GET)

    monkeypatch.setattr("oknowledge.ai.api.httpx.get", fake_get)
    engine = ApiEngine(provider="anthropic", model="m", key="sk-test")
    assert engine.models() == ["claude-sonnet-5"]
    assert seen["url"] == "https://api.anthropic.com/v1/models"
    assert seen["headers"]["x-api-key"] == "sk-test"
    assert seen["timeout"] == 5


def test_the_api_with_no_key_lists_nothing_without_asking(monkeypatch):
    monkeypatch.setattr("oknowledge.ai.api.httpx.get",
                        lambda *a, **k: pytest.fail("asked without a key"))
    assert ApiEngine(provider="anthropic", model="m").models() == []


def test_a_provider_that_refuses_lists_nothing(monkeypatch):
    monkeypatch.setattr("oknowledge.ai.api.httpx.get",
                        lambda *a, **k: httpx.Response(401, json={"error": "bad key"}, request=GET))
    assert ApiEngine(provider="openai", model="m", key="sk-x").models() == []


def test_a_gateway_of_your_own_is_asked_where_it_lives(monkeypatch):
    seen = {}
    monkeypatch.setattr("oknowledge.ai.api.httpx.get",
                        lambda url, **kw: seen.update(url=url)
                        or httpx.Response(200, json={"data": []}, request=GET))
    ApiEngine(provider="openai", model="m", key="k",
              base_url="https://gw.example.com/proxy/v1/chat/completions").models()
    assert seen["url"] == "https://gw.example.com/v1/models"


def test_the_openai_key_travels_as_a_bearer(monkeypatch):
    seen = {}
    monkeypatch.setattr("oknowledge.ai.api.httpx.get",
                        lambda url, **kw: seen.update(headers=kw.get("headers"))
                        or httpx.Response(200, json={"data": []}, request=GET))
    ApiEngine(provider="openai", model="m", key="sk-x").models()
    assert seen["headers"]["Authorization"] == "Bearer sk-x"
