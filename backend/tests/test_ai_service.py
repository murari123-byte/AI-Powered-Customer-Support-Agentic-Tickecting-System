from typing import Literal

import pytest
from pydantic import BaseModel, Field

from app.ai.errors import AIInvalidOutputError, AIUnavailableError
from app.ai.service import AIService
from tests.fakes import FakeLLMProvider, unavailable


class Sentiment(BaseModel):
    label: Literal["positive", "neutral", "negative"]
    confidence: float = Field(ge=0.0, le=1.0)


def make_service(*replies: str | Exception, retries: int = 1) -> tuple[AIService, FakeLLMProvider]:
    provider = FakeLLMProvider(replies)
    return AIService(provider, max_output_retries=retries), provider


def test_valid_json_is_returned_as_typed_object() -> None:
    service, provider = make_service('{"label": "negative", "confidence": 0.9}')

    result = service.generate_structured(system_prompt="s", user_prompt="u", output_model=Sentiment)

    assert result.data == Sentiment(label="negative", confidence=0.9)
    assert result.attempts == 1
    # The provider was asked to follow the model's JSON schema.
    assert provider.chat_calls[0]["json_schema"] == Sentiment.model_json_schema()


def test_invalid_output_is_retried_with_feedback() -> None:
    service, provider = make_service(
        '{"label": "furious", "confidence": 0.9}',  # label not allowed
        '{"label": "negative", "confidence": 0.8}',
    )

    result = service.generate_structured(system_prompt="s", user_prompt="u", output_model=Sentiment)

    assert result.data.label == "negative"
    assert result.attempts == 2
    retry_messages = provider.chat_calls[1]["messages"]
    # The retry shows the model its bad answer, then explains what was wrong.
    assert retry_messages[-2].role == "assistant"
    assert "furious" in retry_messages[-2].content
    assert retry_messages[-1].role == "user"
    assert "label" in retry_messages[-1].content


@pytest.mark.parametrize(
    "bad_output",
    [
        "not json at all",
        '{"label": "negative"}',  # missing field
        '{"label": "negative", "confidence": 7}',  # out of range
        "",
    ],
)
def test_gives_up_after_retries_and_keeps_raw_output(bad_output: str) -> None:
    service, provider = make_service(bad_output, bad_output, retries=1)

    with pytest.raises(AIInvalidOutputError) as exc_info:
        service.generate_structured(system_prompt="s", user_prompt="u", output_model=Sentiment)

    assert exc_info.value.attempts == 2
    assert exc_info.value.raw_output == bad_output
    assert len(provider.chat_calls) == 2


def test_zero_retries_means_one_attempt() -> None:
    service, provider = make_service("bad", retries=0)

    with pytest.raises(AIInvalidOutputError):
        service.generate_structured(system_prompt="s", user_prompt="u", output_model=Sentiment)

    assert len(provider.chat_calls) == 1


def test_unavailable_model_is_not_retried() -> None:
    service, provider = make_service(unavailable(), '{"label": "neutral", "confidence": 0.5}')

    with pytest.raises(AIUnavailableError):
        service.generate_structured(system_prompt="s", user_prompt="u", output_model=Sentiment)

    assert len(provider.chat_calls) == 1


def test_secrets_are_removed_before_reaching_the_model() -> None:
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.dBjftJeZ4CVPmB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    service, provider = make_service('{"label": "neutral", "confidence": 0.5}')

    service.generate_structured(
        system_prompt="You are a classifier.",
        user_prompt=f"I can't log in. My password is hunter2 and my token is {jwt}",
        output_model=Sentiment,
    )

    sent = provider.chat_calls[0]["messages"][1].content
    assert "hunter2" not in sent
    assert jwt not in sent
    assert "[REDACTED]" in sent
    assert "[REDACTED_JWT]" in sent
    assert "I can't log in." in sent


def test_generate_text_returns_raw_response_and_redacts() -> None:
    service, provider = make_service("Here is a summary.")

    response = service.generate_text(system_prompt="Summarise.", user_prompt="pwd=abc123 help")

    assert response.content == "Here is a summary."
    assert "abc123" not in provider.chat_calls[0]["messages"][1].content
    assert provider.chat_calls[0]["json_schema"] is None


def test_embed_redacts_and_keeps_order() -> None:
    service, provider = make_service()

    vectors = service.embed(["short", "password: hunter2"])

    assert len(vectors) == 2
    assert provider.embed_calls[0][0] == "short"
    assert "hunter2" not in provider.embed_calls[0][1]
