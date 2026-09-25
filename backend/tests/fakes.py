"""Test doubles for the AI layer. No network, no real model, fully predictable."""

import hashlib
import math
import re
from collections.abc import Sequence
from typing import Any

from app.ai.errors import AIUnavailableError
from app.ai.types import ChatMessage, LLMResponse, ProviderHealth


class FakeLLMProvider:
    """Plays back scripted replies and records every call it receives.

    Each item in `replies` is a string (the model's text), a list of ToolCall (the model asking
    for tools), or an exception instance (raised instead), consumed in order.
    """

    name = "fake"
    chat_model = "fake-chat"
    embed_model = "fake-embed"

    def __init__(
        self,
        replies: Sequence[str | Exception] = (),
        *,
        health: ProviderHealth | None = None,
        embedding_size: int = 768,
    ) -> None:
        self._replies = list(replies)
        self._health = health or ProviderHealth(reachable=True, models={self.chat_model: True, self.embed_model: True})
        self._embedding_size = embedding_size
        self.chat_calls: list[dict[str, Any]] = []
        self.embed_calls: list[list[str]] = []

    def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        json_schema: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        self.chat_calls.append({"messages": list(messages), "json_schema": json_schema, "tools": tools})
        if not self._replies:
            raise AssertionError("FakeLLMProvider ran out of scripted replies")
        reply = self._replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, list):
            return LLMResponse(content="", tool_calls=reply, model=self.chat_model, latency_ms=1)
        return LLMResponse(content=reply, model=self.chat_model, prompt_tokens=10, completion_tokens=5, latency_ms=1)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.embed_calls.append(list(texts))
        return [fake_embedding(text, self._embedding_size) for text in texts]

    def health(self) -> ProviderHealth:
        return self._health


def unavailable() -> AIUnavailableError:
    return AIUnavailableError("fake: model server down")


_STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "to",
    "of",
    "in",
    "is",
    "it",
    "my",
    "i",
    "for",
    "on",
    "can",
    "how",
    "do",
    "you",
}


def fake_embedding(text: str, size: int = 768) -> list[float]:
    """A stand-in for a real embedding: texts that share words get similar vectors.

    Each word is hashed to one of `size` positions; the vector is then scaled to length 1 so
    cosine similarity works as with real embeddings. Stable across runs (md5, not hash()).
    """
    text = re.sub(r"^search_(query|document): ", "", text)
    vector = [0.0] * size
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        if word not in _STOPWORDS:
            vector[int(hashlib.md5(word.encode(), usedforsecurity=False).hexdigest(), 16) % size] += 1.0
    length = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / length for v in vector]
