"""Ollama provider: talks to a local Ollama server over its REST API.

API reference: https://github.com/ollama/ollama/blob/main/docs/api.md
Endpoints used: POST /api/chat, POST /api/embed, GET /api/tags.
"""

import time
from collections.abc import Sequence
from typing import Any

import httpx2

from app.ai.errors import AIError, AIUnavailableError
from app.ai.types import ChatMessage, LLMResponse, ProviderHealth, ToolCall


def _with_default_tag(model: str) -> str:
    """Ollama lists "nomic-embed-text" as "nomic-embed-text:latest"."""
    return model if ":" in model else f"{model}:latest"


def _to_ollama(message: ChatMessage) -> dict[str, Any]:
    """Our ChatMessage -> the JSON shape Ollama's /api/chat expects."""
    data: dict[str, Any] = {"role": message.role, "content": message.content}
    if message.tool_calls:
        data["tool_calls"] = [{"function": {"name": c.name, "arguments": c.arguments}} for c in message.tool_calls]
    if message.tool_name:
        data["tool_name"] = message.tool_name
    return data


class OllamaProvider:
    name = "ollama"

    def __init__(
        self,
        *,
        base_url: str,
        chat_model: str,
        embed_model: str,
        timeout_seconds: float,
        num_ctx: int,
        temperature: float,
        http_client: httpx2.Client | None = None,
    ) -> None:
        self.chat_model = chat_model
        self.embed_model = embed_model
        self._num_ctx = num_ctx
        self._temperature = temperature
        # Tests pass a client with a fake transport, so no real server is needed.
        self._http = http_client or httpx2.Client(base_url=base_url, timeout=timeout_seconds)

    def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        json_schema: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self.chat_model,
            "messages": [_to_ollama(message) for message in messages],
            "stream": False,
            "options": {"temperature": self._temperature, "num_ctx": self._num_ctx},
        }
        if json_schema is not None:
            # Ollama constrains generation to this JSON schema ("structured outputs").
            payload["format"] = json_schema
        if tools:
            payload["tools"] = tools

        started = time.perf_counter()
        body = self._post("/api/chat", payload, model=self.chat_model)
        latency_ms = int((time.perf_counter() - started) * 1000)

        try:
            content = body["message"]["content"]
            raw_calls = body["message"].get("tool_calls") or []
            tool_calls = [
                ToolCall(name=call["function"]["name"], arguments=call["function"].get("arguments") or {})
                for call in raw_calls
            ]
        except (KeyError, TypeError) as exc:
            raise AIError("Ollama chat response has no message content") from exc

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            model=body.get("model", self.chat_model),
            prompt_tokens=body.get("prompt_eval_count"),
            completion_tokens=body.get("eval_count"),
            latency_ms=latency_ms,
        )

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        body = self._post("/api/embed", {"model": self.embed_model, "input": list(texts)}, model=self.embed_model)
        embeddings = body.get("embeddings")
        if not isinstance(embeddings, list) or len(embeddings) != len(texts):
            raise AIError("Ollama returned the wrong number of embeddings")
        return embeddings

    def health(self) -> ProviderHealth:
        wanted = [self.chat_model, self.embed_model]
        try:
            response = self._http.get("/api/tags")
            response.raise_for_status()
            installed = {m.get("name") for m in response.json().get("models", [])}
        except (httpx2.HTTPError, ValueError) as exc:
            return ProviderHealth(
                reachable=False,
                models={model: False for model in wanted},
                detail=f"Cannot reach Ollama: {exc.__class__.__name__}",
            )

        models = {model: _with_default_tag(model) in installed for model in wanted}
        missing = [model for model, present in models.items() if not present]
        detail = f"Model not downloaded: {', '.join(missing)}" if missing else None
        return ProviderHealth(reachable=True, models=models, detail=detail)

    def _post(self, path: str, payload: dict[str, Any], *, model: str) -> dict[str, Any]:
        """POST to Ollama and turn every transport problem into one of our AI errors."""
        try:
            response = self._http.post(path, json=payload)
        except httpx2.TimeoutException as exc:
            raise AIUnavailableError("Ollama did not answer in time") from exc
        except httpx2.TransportError as exc:
            raise AIUnavailableError("Cannot connect to Ollama. Is it running?") from exc

        if response.status_code == 404:
            # Ollama answers 404 when the model has not been pulled.
            raise AIUnavailableError(f"Model '{model}' is not available in Ollama. Run: scripts/ollama.sh pull {model}")
        if response.status_code >= 500:
            raise AIUnavailableError(f"Ollama server error ({response.status_code})")
        if response.status_code >= 400:
            raise AIError(f"Ollama rejected the request ({response.status_code}): {response.text[:200]}")

        try:
            return response.json()
        except ValueError as exc:
            raise AIError("Ollama returned a response that is not JSON") from exc
