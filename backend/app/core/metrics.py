"""Prometheus metrics: numbers about the running system, for dashboards and alerts.

Prometheus "scrapes" (reads) them every few seconds from:
- the API:    GET /metrics on port 8000
- the worker: port 9808 (started in app/workers/celery_app.py)

Three kinds of metric are used:
- Counter:   only goes up (e.g. tickets created). Dashboards show its rate per second/minute.
- Histogram: counts values in buckets (e.g. request times), so dashboards can show p95 latency.
- Gauge:     goes up and down (e.g. jobs waiting in the queue).

Labels (the {…} parts) must have FEW possible values: route templates like /api/v1/tickets/{ticket_id},
never real ids, or Prometheus would store millions of series.
"""

import time
from collections.abc import Iterator
from contextlib import contextmanager

from prometheus_client import Counter, Histogram

# ---------- API ----------
HTTP_REQUESTS = Counter("http_requests_total", "HTTP requests handled", ["method", "route", "status"])
HTTP_LATENCY = Histogram(
    "http_request_duration_seconds",
    "Time to handle an HTTP request",
    ["method", "route"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60),
)

# ---------- AI ----------
AI_CALL_LATENCY = Histogram(
    "ai_call_duration_seconds",
    "Time for one call to the model",
    ["purpose"],
    buckets=(0.1, 0.5, 1, 2, 5, 10, 20, 30, 60, 120),
)
AI_CALL_ERRORS = Counter("ai_call_errors_total", "Model calls that failed", ["purpose", "error"])
RAG_ANSWERS = Counter("rag_answers_total", "Knowledge-base answers", ["answerable"])

# ---------- Tickets ----------
TICKETS_CREATED = Counter("tickets_created_total", "Tickets created")
TRIAGE_DECISIONS = Counter("triage_decisions_total", "AI triage results", ["outcome"])  # applied / not_applied / failed
ESCALATIONS = Counter(
    "ticket_escalations_total", "Tickets escalated", ["source"]
)  # person / ai_triage / ai_agent / sla

# ---------- Background jobs ----------
CELERY_TASKS = Counter(
    "celery_tasks_total", "Background jobs finished", ["task", "state"]
)  # succeeded / failed / retried
CELERY_TASK_LATENCY = Histogram(
    "celery_task_duration_seconds",
    "Time a background job took",
    ["task"],
    buckets=(0.1, 0.5, 1, 5, 10, 30, 60, 120, 300, 600),
)


@contextmanager
def time_ai_call(purpose: str) -> Iterator[None]:
    """Time a model call, and count it as an error if it raises."""
    started = time.perf_counter()
    try:
        yield
    except Exception as exc:
        AI_CALL_ERRORS.labels(purpose=purpose, error=exc.__class__.__name__).inc()
        raise
    finally:
        AI_CALL_LATENCY.labels(purpose=purpose).observe(time.perf_counter() - started)


# Create the known label values at 0, so dashboards show "0" instead of "No data" before the first event.
for _source in ("person", "ai_triage", "ai_agent", "sla"):
    ESCALATIONS.labels(source=_source)
for _outcome in ("applied", "not_applied", "failed"):
    TRIAGE_DECISIONS.labels(outcome=_outcome)
for _answerable in ("true", "false"):
    RAG_ANSWERS.labels(answerable=_answerable)
