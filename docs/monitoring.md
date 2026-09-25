# Monitoring (Prometheus + Grafana)

- **Prometheus** collects numbers ("metrics") from the running system every 15 seconds and stores them for 7 days.
- **Grafana** draws them as a dashboard: http://localhost:3002, user `admin`, password `GRAFANA_ADMIN_PASSWORD` from `.env`.
  Open **Dashboards → AI Support → AI Support Platform**. It's loaded automatically (`infrastructure/grafana/`).

```
api    /metrics (port 8000) ─┐
worker :9808 ────────────────┼──► Prometheus :9090 ──► Grafana :3002
                             │      (infrastructure/prometheus/prometheus.yml)
```

## The metrics

Defined in `backend/app/core/metrics.py`.

| Metric | Type | Labels | Meaning |
|---|---|---|---|
| `http_requests_total` | counter | method, route, status | Every API request |
| `http_request_duration_seconds` | histogram | method, route | API response time |
| `ai_call_duration_seconds` | histogram | purpose | Time per model call (`TicketClassification`, `RagAnswer`, `agent_tools`, `embed`, `text`) |
| `ai_call_errors_total` | counter | purpose, error | Failed model calls (`AIUnavailableError`, `AIInvalidOutputError`) |
| `rag_answers_total` | counter | answerable | Knowledge-base answers vs "I don't know" |
| `tickets_created_total` | counter | – | New tickets |
| `ticket_escalations_total` | counter | source | Escalations by `person` / `ai_triage` / `ai_agent` / `sla` |
| `triage_decisions_total` | counter | outcome | AI triage `applied` / `not_applied` / `failed` |
| `celery_tasks_total` | counter | task, state | Jobs `succeeded` / `failed` / `retried` |
| `celery_task_duration_seconds` | histogram | task | Job run time |
| `celery_queue_length` | gauge | queue | Jobs waiting in Redis (read at each scrape) |

**Labels are kept small on purpose.** Routes are recorded as templates (`/api/v1/tickets/{ticket_id}`), never with real ids,
and unknown URLs (e.g. from scanners) are grouped as `unmatched`. Otherwise every ticket id would create a new series and
Prometheus would run out of memory.

## The dashboard (14 panels)

| Row | Panels |
|---|---|
| API | Requests/s by route · server error rate (5xx) · p95 response time by route |
| AI and RAG | p95 model-call time by purpose · AI errors · knowledge-base answers (answered vs "I don't know") |
| Tickets | Tickets created (1 h) · **escalation rate** (1 h) · escalations by source · triage outcomes |
| Background jobs | Queue length · failed jobs (1 h) · jobs finished by task and state · p95 job time by task |

## What to watch

| Signal | Likely meaning |
|---|---|
| Queue length keeps rising | Workers can't keep up (or are down): add a worker, or check Ollama speed |
| AI errors with `AIUnavailableError` | Ollama down or too slow (check `/health/ai`, raise `AI_TIMEOUT_SECONDS`) |
| Triage `not_applied` rising | Many low-confidence or injection-flagged tickets; check `ai_interactions.decision` |
| Escalation rate jumps | An outage or a wave of security reports, or an AI prompt change that escalates too much |
| High share of `answerable=false` | The knowledge base is missing articles customers ask about |
| p95 of `RagAnswer` or `agent_tools` very high | The model is overloaded (CPU): consider a GPU, a smaller model, or fewer parallel jobs |

## What is logged, and what isn't

Logs contain metadata only: model, latency, token counts, attempts, **kinds** of secrets removed. They never contain
prompts, customer messages, tokens or passwords. The full AI answers are kept in the database (`ai_interactions`), where
access is controlled, not in log files.

## Security note

`/metrics` has no login, like most Prometheus endpoints. In Docker it's only published on 127.0.0.1. On a real server,
block `/metrics` at the reverse proxy so only Prometheus (inside the private network) can reach it.
