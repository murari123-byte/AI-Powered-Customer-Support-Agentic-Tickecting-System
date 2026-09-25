"""Talks to the REAL Ollama server. Skipped unless RUN_LIVE_AI_TESTS=1.

Run:  RUN_LIVE_AI_TESTS=1 .venv/bin/pytest -m live_ai -v
Needs: scripts/ollama.sh serve, and both models pulled (see docs/setup.md).
"""

import os
from typing import Literal

import pytest
from pydantic import BaseModel, Field

from app.ai.dependencies import build_provider
from app.ai.service import AIService
from app.core.config import Settings

pytestmark = [
    pytest.mark.live_ai,
    pytest.mark.skipif(os.environ.get("RUN_LIVE_AI_TESTS") != "1", reason="set RUN_LIVE_AI_TESTS=1"),
]


class Mood(BaseModel):
    mood: Literal["happy", "neutral", "angry"]
    confidence: float = Field(ge=0.0, le=1.0)


@pytest.fixture(scope="module")
def service() -> AIService:
    settings = Settings()
    return AIService(build_provider(settings), max_output_retries=settings.ai_max_output_retries)


def test_models_are_available(service: AIService) -> None:
    health = service.health()
    assert health.ok, health.detail


def test_structured_output_from_real_model(service: AIService) -> None:
    result = service.generate_structured(
        system_prompt="Classify the customer's mood. Reply with JSON only.",
        user_prompt="This is the third time my order is late. I am furious!",
        output_model=Mood,
    )

    assert result.data.mood == "angry"
    assert 0.0 <= result.data.confidence <= 1.0


def test_real_embeddings(service: AIService) -> None:
    vectors = service.embed(["refund policy", "how do I reset my password"])

    assert len(vectors) == 2
    assert len(vectors[0]) == 768  # nomic-embed-text dimension
    assert vectors[0] != vectors[1]
