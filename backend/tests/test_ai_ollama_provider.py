"""OllamaProvider tests against a fake HTTP transport: checks what we send and how we
handle every kind of answer, without a running Ollama server."""

import json
from collections.abc import Callable

import httpx2
import pytest

from app.ai.errors import AIError, AIUnavailableError
from app.ai.providers.ollama import OllamaProvider
from app.ai.types import ChatMessage

Handler = Callable[[httpx2.Request], httpx2.Response]


def make_provider(handler: Handler) -> OllamaProvider:
    client = httpx2.Client(base_url="http://ollama.test", transport=httpx2.MockTransport(handler))
    return OllamaProvider(
        base_url="http://ollama.test",
        chat_model="qwen2.5:7b",
        embed_model="nomic-embed-text",
        timeout_seconds=5,
        num_ctx=8192,
        temperature=0.1,
        http_client=client,
    )


MESSAGES = [ChatMessage(role="system", content="sys"), ChatMessage(role="user", content="hi")]


def test_chat_sends_expected_payload_and_parses_reply() -> None:
    seen: dict = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx2.Response(
            200,
            json={
                "model": "qwen2.5:7b",
                "message": {"role": "assistant", "content": '{"ok": true}'},
                "prompt_eval_count": 42,
                "eval_count": 7,
            },
        )

    schema = {"type": "object"}
    response = make_provider(handler).chat(MESSAGES, json_schema=schema)

    assert seen["path"] == "/api/chat"
    assert seen["body"]["model"] == "qwen2.5:7b"
    assert seen["body"]["stream"] is False
    assert seen["body"]["format"] == schema
    assert seen["body"]["options"] == {"temperature": 0.1, "num_ctx": 8192}
    assert seen["body"]["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
    ]
    assert response.content == '{"ok": true}'
    assert response.prompt_tokens == 42
    assert response.completion_tokens == 7
    assert response.latency_ms >= 0


def test_chat_without_schema_sends_no_format() -> None:
    seen: dict = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["body"] = json.loads(request.content)
        return httpx2.Response(200, json={"message": {"content": "text"}})

    make_provider(handler).chat(MESSAGES)

    assert "format" not in seen["body"]


def test_connection_refused_is_unavailable() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("refused", request=request)

    with pytest.raises(AIUnavailableError, match="Is it running"):
        make_provider(handler).chat(MESSAGES)


def test_timeout_is_unavailable() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("slow", request=request)

    with pytest.raises(AIUnavailableError, match="in time"):
        make_provider(handler).chat(MESSAGES)


def test_missing_model_tells_you_how_to_pull_it() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(404, json={"error": "model 'qwen2.5:7b' not found"})

    with pytest.raises(AIUnavailableError, match="scripts/ollama.sh pull qwen2.5:7b"):
        make_provider(handler).chat(MESSAGES)


def test_server_error_is_unavailable() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(500, json={"error": "out of memory"})

    with pytest.raises(AIUnavailableError, match="500"):
        make_provider(handler).chat(MESSAGES)


def test_bad_request_is_a_plain_ai_error() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(400, json={"error": "invalid format"})

    with pytest.raises(AIError) as exc_info:
        make_provider(handler).chat(MESSAGES)
    assert not isinstance(exc_info.value, AIUnavailableError)


def test_malformed_chat_body_is_an_ai_error() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={"unexpected": True})

    with pytest.raises(AIError, match="no message content"):
        make_provider(handler).chat(MESSAGES)


def test_embed_returns_vectors_in_order() -> None:
    seen: dict = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx2.Response(200, json={"embeddings": [[0.1, 0.2], [0.3, 0.4]]})

    vectors = make_provider(handler).embed(["a", "b"])

    assert seen["path"] == "/api/embed"
    assert seen["body"] == {"model": "nomic-embed-text", "input": ["a", "b"]}
    assert vectors == [[0.1, 0.2], [0.3, 0.4]]


def test_embed_with_no_texts_makes_no_request() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise AssertionError("should not be called")

    assert make_provider(handler).embed([]) == []


def test_embed_count_mismatch_is_an_error() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={"embeddings": [[0.1]]})

    with pytest.raises(AIError, match="wrong number"):
        make_provider(handler).embed(["a", "b"])


def test_health_ok_when_both_models_installed() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={"models": [{"name": "qwen2.5:7b"}, {"name": "nomic-embed-text:latest"}]})

    health = make_provider(handler).health()

    assert health.ok
    assert health.models == {"qwen2.5:7b": True, "nomic-embed-text": True}


def test_health_reports_missing_model() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={"models": [{"name": "qwen2.5:7b"}]})

    health = make_provider(handler).health()

    assert health.reachable
    assert not health.ok
    assert health.models["nomic-embed-text"] is False
    assert "nomic-embed-text" in (health.detail or "")


def test_health_when_server_down() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("refused", request=request)

    health = make_provider(handler).health()

    assert not health.reachable
    assert not health.ok
