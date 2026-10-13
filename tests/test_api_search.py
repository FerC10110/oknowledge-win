"""The API engine searches only with Anthropic's own web search tool."""

import pytest

from oknowledge.ai.api import SEARCH_TOOL, ApiEngine
from oknowledge.ai.base import NO_SEARCH, EngineError

KEY = "sk-test-0123456789"


class Reply:
    def __init__(self, data, status=200):
        self._data = data
        self.status_code = status

    def json(self):
        return self._data


@pytest.fixture
def posted(monkeypatch):
    seen = {"reply": Reply({"content": [{"type": "text", "text": "hola"}]})}

    def post(url, headers=None, json=None, timeout=None):
        seen["body"] = json
        return seen["reply"]

    monkeypatch.setattr("httpx.post", post)
    return seen


def anthropic():
    return ApiEngine(provider="anthropic", model="claude-x", key=KEY)


def test_only_the_anthropic_protocol_searches():
    assert anthropic().searches is True
    assert ApiEngine(provider="groq", model="m", key=KEY).searches is False


def test_search_asks_for_the_web_search_tool(posted):
    posted["reply"] = Reply({"content": [
        {"type": "server_tool_use", "name": "web_search"},
        {"type": "web_search_tool_result", "content": []},
        {"type": "text", "text": "Encontré "},
        {"type": "text", "text": "dos."}]})
    assert anthropic().search("busca") == "Encontré dos."
    assert posted["body"]["tools"] == [SEARCH_TOOL]
    assert SEARCH_TOOL["type"] == "web_search_20250305"


def test_complete_never_sends_the_tool(posted):
    anthropic().complete("hola")
    assert "tools" not in posted["body"]


def test_api_search_without_a_search_result_is_an_error(posted):
    posted["reply"] = Reply({"content": [{"type": "text", "text": "de memoria"}]})
    with pytest.raises(EngineError) as raised:
        anthropic().search("busca")
    assert str(raised.value) == NO_SEARCH


def test_a_provider_that_cannot_search_says_so_without_calling(posted):
    with pytest.raises(EngineError, match="groq cannot search the web"):
        ApiEngine(provider="groq", model="m", key=KEY).search("busca")
    assert "body" not in posted


def test_the_key_never_reaches_a_search_error(posted):
    posted["reply"] = Reply({"error": {"message": f"bad key {KEY}"}}, status=401)
    with pytest.raises(EngineError) as raised:
        anthropic().search("busca")
    assert KEY not in str(raised.value)
