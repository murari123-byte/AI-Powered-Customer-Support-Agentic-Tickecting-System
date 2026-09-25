import logging
from functools import lru_cache
from typing import Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.ai.dependencies import get_ai_service
from app.ai.service import AIService
from app.core.config import Settings, get_settings
from app.db.session import get_engine

logger = logging.getLogger("app.health")

router = APIRouter(tags=["health"])

CheckStatus = Literal["ok", "unavailable"]


@lru_cache
def get_redis() -> Redis:
    """Redis client for health checks. Short timeout so a dead Redis fails fast."""
    return Redis.from_url(get_settings().redis_url, socket_connect_timeout=2, socket_timeout=2)


class ReadinessResponse(BaseModel):
    status: CheckStatus
    checks: dict[str, CheckStatus]


class HealthResponse(BaseModel):
    status: str
    app: str
    version: str
    environment: str


class AIHealthResponse(BaseModel):
    status: str  # "ok" or "unavailable"
    provider: str
    chat_model: str
    embed_model: str
    models: dict[str, bool]
    detail: str | None = None


@router.get("/health", response_model=HealthResponse)
def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    """Liveness check: returns 200 whenever the API process is up.

    It deliberately checks nothing else. If it depended on the database, a short database
    outage would make Docker restart healthy API containers for no reason.
    """
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
    )


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse, "description": "A dependency is down"}},
)
def readiness(
    response: Response, engine: Engine = Depends(get_engine), redis: Redis = Depends(get_redis)
) -> ReadinessResponse:
    """Readiness check: can the API serve real requests? Checks the database and Redis."""
    checks: dict[str, CheckStatus] = {}
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except SQLAlchemyError as exc:
        # Log the error type only: the full message can contain the host and username.
        logger.warning("health.database_unavailable", extra={"error": exc.__class__.__name__})
        checks["database"] = "unavailable"

    try:
        redis.ping()
        checks["redis"] = "ok"
    except RedisError as exc:
        logger.warning("health.redis_unavailable", extra={"error": exc.__class__.__name__})
        checks["redis"] = "unavailable"

    ready = all(value == "ok" for value in checks.values())
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(status="ok" if ready else "unavailable", checks=checks)


@router.get(
    "/health/ai",
    response_model=AIHealthResponse,
    responses={503: {"model": AIHealthResponse, "description": "Model server down or model missing"}},
)
def ai_health(response: Response, ai: AIService = Depends(get_ai_service)) -> AIHealthResponse:
    """Is the model server reachable, and are the configured models downloaded?

    Kept separate from /health on purpose: the API still works (tickets can be created and
    routed to humans) when the AI is down, so AI trouble must not mark the whole API unhealthy.
    """
    result = ai.health()
    if not result.ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return AIHealthResponse(
        status="ok" if result.ok else "unavailable",
        provider=ai.provider_name,
        chat_model=ai.chat_model,
        embed_model=ai.embed_model,
        models=result.models,
        detail=result.detail,
    )
