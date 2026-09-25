from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import metrics
from app.api.errors import register_error_handlers
from app.api.routes import admin_users, auth, health, knowledge, teams, tickets
from app.core.config import get_settings

API_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    """Build the FastAPI app. A factory function makes it easy to create fresh apps in tests."""
    settings = get_settings()

    app = FastAPI(title=settings.app_name, version=settings.app_version)

    # Only the listed frontend origins may call the API from a browser.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Count and time every request for Prometheus (see app/api/metrics.py).
    app.middleware("http")(metrics.record_request_metrics)
    metrics.register_queue_collector()

    # Health checks stay at the root (infrastructure uses them); business API is versioned.
    app.include_router(health.router)
    app.include_router(metrics.router)
    app.include_router(auth.router, prefix=API_PREFIX)
    app.include_router(admin_users.router, prefix=API_PREFIX)
    app.include_router(teams.router, prefix=API_PREFIX)
    app.include_router(tickets.router, prefix=API_PREFIX)
    app.include_router(knowledge.router, prefix=API_PREFIX)
    register_error_handlers(app)
    return app


app = create_app()
