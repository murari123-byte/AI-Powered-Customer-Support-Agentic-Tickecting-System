"""Celery: runs work in the background, outside web requests.

    FastAPI / beat ──puts a job──► Redis (queue) ──worker takes it──► runs the task

Start a worker (plus the beat scheduler, for development) from backend/:

    .venv/bin/celery -A app.workers.celery_app worker --beat --pool=threads --loglevel=info

--pool=threads: all jobs run in ONE process, so the metrics below (kept in memory) are complete.
The jobs mostly wait for Ollama or the database, so threads are enough.
"""

import time

from celery import Celery
from celery.signals import task_failure, task_postrun, task_prerun, task_retry, task_success, worker_init
from prometheus_client import start_http_server

from app.core.config import get_settings
from app.core.metrics import CELERY_TASK_LATENCY, CELERY_TASKS

settings = get_settings()

celery = Celery("support", broker=settings.redis_url, include=["app.workers.tasks"])

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],  # never accept pickled data from the queue
    timezone="UTC",
    # Only mark a job done AFTER it finishes, so a crashed worker's job is picked up again.
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # We don't read task return values, so no result storage is needed.
    task_ignore_result=True,
    beat_schedule={
        "sla-check": {
            "task": "tickets.check_sla",
            "schedule": float(settings.sla_check_interval_seconds),
        },
    },
)


# ---------- Metrics (Prometheus reads them from port 9808 of the worker) ----------

WORKER_METRICS_PORT = 9808
_started_at: dict[str, float] = {}


@worker_init.connect
def _start_metrics_server(**_) -> None:
    start_http_server(WORKER_METRICS_PORT)


@task_prerun.connect
def _task_started(task_id: str, **_) -> None:
    _started_at[task_id] = time.perf_counter()


@task_postrun.connect
def _task_finished(task_id: str, task, **_) -> None:
    started = _started_at.pop(task_id, None)
    if started is not None:
        CELERY_TASK_LATENCY.labels(task=task.name).observe(time.perf_counter() - started)


@task_success.connect
def _task_succeeded(sender, **_) -> None:
    CELERY_TASKS.labels(task=sender.name, state="succeeded").inc()


@task_failure.connect
def _task_failed(sender, **_) -> None:
    CELERY_TASKS.labels(task=sender.name, state="failed").inc()


@task_retry.connect
def _task_retried(sender, **_) -> None:
    CELERY_TASKS.labels(task=sender.name, state="retried").inc()
