"""AIService: the only door between the application and a language model.

What it guarantees, whichever provider is behind it:
1. Every message is redacted before it leaves the process (no passwords, tokens, JWTs).
2. Structured answers are validated with Pydantic. Callers get typed objects, never raw text.
3. Invalid output is retried a limited number of times, then raises AIInvalidOutputError.
4. Only metadata is logged (model, latency, token counts, attempts), never prompt text.
"""

import logging
from collections.abc import Sequence

from pydantic import BaseModel, ValidationError

from app.ai.errors import AIError, AIInvalidOutputError
from app.ai.providers.base import LLMProvider
from app.ai.redaction import redact
from app.ai.types import ChatMessage, LLMResponse, ProviderHealth, StructuredResult
from app.core.metrics import time_ai_call

logger = logging.getLogger("app.ai")

# Sent back to the model when its JSON fails validation.
_RETRY_INSTRUCTION = (
    "Your previous reply did not match the required JSON schema. Problems: {problems}. "
    "Reply again with ONLY a JSON object that matches the schema. No other text."
)


def _describe_errors(error: ValidationError) -> str:
    """Short, value-free summary of validation errors, e.g. "category: Input should be ..."."""
    parts = []
    for item in error.errors()[:5]:
        location = ".".join(str(part) for part in item["loc"]) or "(root)"
        parts.append(f"{location}: {item['msg']}")
    return "; ".join(parts)


class AIService:
    def __init__(self, provider: LLMProvider, *, max_output_retries: int = 1) -> None:
        self._provider = provider
        self._max_output_retries = max_output_retries

    @property
    def provider_name(self) -> str:
        return self._provider.name

    @property
    def chat_model(self) -> str:
        return self._provider.chat_model

    @property
    def embed_model(self) -> str:
        return self._provider.embed_model

    def generate_text(self, *, system_prompt: str, user_prompt: str) -> LLMResponse:
        """Free-text answer. Use generate_structured() whenever the app acts on the result."""
        messages = self._build_messages(system_prompt, user_prompt)
        with time_ai_call("text"):
            response = self._provider.chat(messages)
        self._log_call("text", response, attempts=1)
        return response

    def generate_structured[T: BaseModel](
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        output_model: type[T],
    ) -> StructuredResult[T]:
        """Ask for JSON matching `output_model` and return it as a validated object.

        Raises:
            AIUnavailableError: the model could not be reached (not retried here; the
                caller decides, for example a background job retries later).
            AIInvalidOutputError: every attempt returned invalid output.
        """
        schema = output_model.model_json_schema()
        messages = self._build_messages(system_prompt, user_prompt)
        total_attempts = 1 + self._max_output_retries
        last_output = ""
        last_problems = ""

        for attempt in range(1, total_attempts + 1):
            with time_ai_call(output_model.__name__):
                response = self._provider.chat(messages, json_schema=schema)
            last_output = response.content
            try:
                data = output_model.model_validate_json(response.content)
            except ValidationError as error:
                last_problems = _describe_errors(error)
                logger.warning(
                    "ai.invalid_output",
                    extra={"model": response.model, "attempt": attempt, "schema": output_model.__name__},
                )
                # Show the model its own answer and what was wrong, then ask again.
                messages = [
                    *messages,
                    ChatMessage(role="assistant", content=response.content),
                    ChatMessage(role="user", content=_RETRY_INSTRUCTION.format(problems=last_problems)),
                ]
                continue

            self._log_call(output_model.__name__, response, attempts=attempt)
            return StructuredResult(data=data, response=response, attempts=attempt)

        raise AIInvalidOutputError(
            f"Model output failed {output_model.__name__} validation after "
            f"{total_attempts} attempt(s): {last_problems}",
            raw_output=last_output,
            attempts=total_attempts,
        )

    def chat_with_tools(self, messages: Sequence[ChatMessage], tools: list[dict]) -> LLMResponse:
        """One turn of a tool-using conversation. The reply has either text or tool_calls.

        Every message is redacted, including tool results, so secrets in the database (or typed by
        a customer) never reach the model. Running the tools is the caller's job, never the model's.
        """
        cleaned = [message.model_copy(update={"content": redact(message.content).text}) for message in messages]
        with time_ai_call("agent_tools"):
            response = self._provider.chat(cleaned, tools=tools)
        self._log_call("tools", response, attempts=1)
        return response

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed texts (redacted first). Returns one vector per text, in order."""
        cleaned = [redact(text).text for text in texts]
        with time_ai_call("embed"):
            vectors = self._provider.embed(cleaned)
        if len(vectors) != len(cleaned):
            raise AIError("Provider returned the wrong number of embeddings")
        return vectors

    def health(self) -> ProviderHealth:
        return self._provider.health()

    @staticmethod
    def _build_messages(system_prompt: str, user_prompt: str) -> list[ChatMessage]:
        found: list[str] = []
        messages = []
        for role, content in (("system", system_prompt), ("user", user_prompt)):
            result = redact(content)
            found.extend(result.found)
            messages.append(ChatMessage(role=role, content=result.text))
        if found:
            # Log which kinds were removed (never the values) so we can spot patterns.
            logger.info("ai.redacted", extra={"kinds": sorted(set(found))})
        return messages

    @staticmethod
    def _log_call(purpose: str, response: LLMResponse, *, attempts: int) -> None:
        logger.info(
            "ai.call",
            extra={
                "purpose": purpose,
                "model": response.model,
                "latency_ms": response.latency_ms,
                "prompt_tokens": response.prompt_tokens,
                "completion_tokens": response.completion_tokens,
                "attempts": attempts,
            },
        )
