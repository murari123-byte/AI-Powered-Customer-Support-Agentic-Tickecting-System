# Background jobs (Celery + Redis)

## Why

Some work shouldn't happen inside a web request:
- **Slow work**: an AI call on a CPU can take 30+ seconds. The user shouldn't wait, and the API shouldn't freeze.
- **Timed work**: "every 5 minutes, check for overdue tickets". No user request starts it.

**Celery** runs this work in a separate **worker** process. **Redis** is the queue in between.
**Beat** is Celery's timer: it puts scheduled jobs on the queue.

```
beat (timer) ─┐
              ├─ puts a job ──► Redis (queue) ──► worker takes it ──► runs the task ──► PostgreSQL
FastAPI ──────┘   (from step 7: "classify this ticket")
```

## Jobs

| Job | Started by | What it does |
|---|---|---|
| `tickets.check_sla` | beat, every `SLA_CHECK_INTERVAL_SECONDS` (300) | Escalates OPEN tickets that waited too long |
| `tickets.triage` | the API, right after a ticket is created | Asks the AI for category/priority and applies it if confident ([ai.md](ai.md#ticket-classification)). Retries 3× if Ollama is down |
| `agent.run` | the API (`POST /tickets/{id}/agent`) | Runs the AI agent on a ticket with the starter's rights ([agentic-workflow.md](agentic-workflow.md)). Time limit 10 min, 2 retries |
| `knowledge.process_document` | the API, after an admin uploads a document | Splits it into chunks, embeds them, marks it READY (or FAILED). Retries 3× if Ollama is down |

## The SLA check

A ticket must not stay **OPEN** (nobody working on it) longer than its priority allows:

| Priority | Max wait in OPEN |
|---|---|
| CRITICAL | 1 hour |
| HIGH | 4 hours |
| MEDIUM | 24 hours |
| LOW | 72 hours |

If it does, the system **escalates** it with the reason "SLA breached: … waited more than Nh in OPEN".
The escalation's `raised_by` is empty, which means "done by the system" (migration 0002).

- The clock starts when the ticket last became OPEN (a reopened ticket starts again).
- **Safe to run many times**: an escalated ticket isn't OPEN any more, so it's never escalated twice.
- Code: the rule is in `app/services/sla_service.py` (tested without Celery). The task in `app/workers/tasks.py` only opens a database session and calls it.

## Run it

Redis must be running (`docker compose up -d`). In `backend/`, in a new terminal:

```bash
.venv/bin/celery -A app.workers.celery_app worker --beat --loglevel=info
```

`--beat` runs the timer inside the worker, which is handy for development. In production you'd run
**one** separate beat process (`celery -A app.workers.celery_app beat`) and as many workers as needed.
Two beats would schedule every job twice.

Good output:

```
Connected to redis://localhost:6380/0
celery@… ready.
Scheduler: Sending due task sla-check (tickets.check_sla)
Task tickets.check_sla[…] succeeded in 0.1s: []
```

To try it quickly, run with `SLA_CHECK_INTERVAL_SECONDS=15` in front of the command.

## Settings in `celery_app.py`

| Setting | Why |
|---|---|
| `task_serializer="json"`, `accept_content=["json"]` | Never accept pickled Python objects from the queue (a security risk) |
| `task_acks_late=True` | A job is marked done only **after** it finishes. If a worker crashes mid-job, another worker runs it again |
| `worker_prefetch_multiplier=1` | A worker takes one job at a time (AI jobs are slow; don't hoard them) |
| `task_ignore_result=True` | We don't read task return values, so no result storage is needed |
| Retries on `OperationalError` | If the database is briefly down, retry after 30 s, 60 s, 120 s |

## Verified

A real worker + beat (interval 15 s) with a ticket that had waited 30 h in OPEN: beat sent the job,
the worker ran it, and the ticket became ESCALATED with `raised_by` = system, all within about 15 seconds.
