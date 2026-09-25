from collections.abc import Sequence
from typing import Any, Protocol

from app.ai.types import ChatMessage, LLMResponse, ProviderHealth


class LLMProvider(Protocol):
    """What every model backend must offer. Ollama is the default implementation.

    To add another backend (for example an OpenAI-compatible API), write a class with these
    methods and select it in app/ai/dependencies.py. Nothing else in the app changes.

    Providers only move text in and out. Validation, retries and redaction live in AIService,
    so they behave the same whichever provider is used.
    """

    name: str
    chat_model: str
    embed_model: str

    def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        json_schema: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        """Send a conversation and return the model's reply.

        When `tools` is given (function definitions with JSON-schema parameters), the model may
        answer with `tool_calls` instead of text. The provider only reports them; it never runs them.

        When `json_schema` is given, the provider asks the model to reply with JSON that
        matches it. The caller still validates the result, because models can ignore it.
        Raises AIUnavailableError when the model cannot be reached.
        """
        ...

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one embedding vector per input text, in the same order."""
        ...

    def health(self) -> ProviderHealth:
        """Check the provider is reachable and the configured models exist."""
        ...
