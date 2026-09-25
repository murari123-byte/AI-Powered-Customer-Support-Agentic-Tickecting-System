from functools import lru_cache

from app.ai.providers.base import LLMProvider
from app.ai.providers.ollama import OllamaProvider
from app.ai.service import AIService
from app.core.config import Settings, get_settings


def build_provider(settings: Settings) -> LLMProvider:
    if settings.ai_provider == "ollama":
        return OllamaProvider(
            base_url=settings.ollama_base_url,
            chat_model=settings.ollama_chat_model,
            embed_model=settings.ollama_embed_model,
            timeout_seconds=settings.ai_timeout_seconds,
            num_ctx=settings.ollama_num_ctx,
            temperature=settings.ai_temperature,
        )
    # Unreachable while Settings.ai_provider only allows "ollama"; kept for new providers.
    raise ValueError(f"Unknown AI provider: {settings.ai_provider}")


@lru_cache
def get_ai_service() -> AIService:
    """FastAPI dependency. One shared service (and HTTP connection pool) per process.

    Tests replace it with app.dependency_overrides[get_ai_service] = lambda: fake_service.
    """
    settings = get_settings()
    return AIService(build_provider(settings), max_output_retries=settings.ai_max_output_retries)
