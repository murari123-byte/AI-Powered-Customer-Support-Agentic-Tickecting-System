# Changelog

Newest first.

## [1.0.0] - 2026-09-25: Final review

### Changed
- Documentation audit: README (results, stack, roadmap), setup (fresh-machine guide, costs), api (every endpoint), testing,
  architecture, troubleshooting, migrations; new `final-checklist.md`; interview guide rewritten (50+ questions).
- `.env.example`: added `RATE_LIMIT_ENABLED`.
- Test counts corrected everywhere: 251 backend + 11 frontend.

### Fixed
- Grafana "AI errors" panel: the legend showed ":" when there were no errors (the `or vector(0)` fallback has no labels).
  Now one line per error type, plus an "all errors" total that shows 0 instead of "No data". Dashboard version 3.

## [0.13.0] - 2026-09-25: Security review, CI, deployment guide

### Added
- **Rate limiting** (`app/core/rate_limit.py`, Redis fixed window): login 10/min, register 5/hour per IP; 429 + `Retry-After`;
  allows requests if Redis is down. `RATE_LIMIT_ENABLED`. Tests: `test_rate_limit.py` (3).
- **Content-Security-Policy** in the frontend nginx config (API origin filled in at container start).
- **GitHub Actions CI** (`.github/workflows/ci.yml`): ruff, migrations on an empty DB + `alembic check`, pytest, pip-audit;
  frontend lint, tests, build, npm audit; both Docker images build. Not run on GitHub yet (no repository).
- `ruff` security (`S`) and bug (`B`) rules; `pip-audit` in dev requirements.
- Docs: `security.md`, `deployment.md` (AWS options with rough, not live-checked, prices).

### Fixed
- Knowledge upload read the whole file before checking its size. Now read in 1 MB pieces; 413 at the limit.
- Upload route was `async def` with blocking DB calls. Now a normal `def`.

## [0.12.0] - 2026-09-25: Full Docker setup + monitoring

### Added
- `docker-compose.yml`: 9 services (postgres, redis, ollama, migrate, api, worker, frontend, prometheus, grafana). Only
  127.0.0.1 ports; Ollama not published; `migrate` runs `alembic upgrade head` before the api starts.
- `backend/Dockerfile` (non-root), `frontend/Dockerfile` (build, then nginx with SPA fallback).
- **Prometheus metrics** (`app/core/metrics.py`, `app/api/metrics.py`): requests by route template, latency, AI calls and
  latency, RAG answers, tickets created, escalations by source, Celery tasks, queue length. Worker metrics on port 9808.
- **Grafana** dashboard (14 panels) provisioned automatically. `GRAFANA_ADMIN_PASSWORD` required.
- `FRONTEND_PORT` (default 8080).
- Tests: `test_metrics.py` (4).
- Docs: `docker.md` rewritten, `monitoring.md`.

## [0.11.0] - 2026-09-25: Frontend

### Added
- Pages: login, register, ticket list, new ticket, ticket detail (conversation, notes, status, assignment, escalation,
  history, AI panel with triage result, suggested reply and agent run), knowledge base, admin (users, teams), 404.
- `api/client.ts`: access token in memory, one shared refresh on 401, AI timeout.
- Tests: Vitest + Testing Library (11). Docs: `frontend.md`.

### Fixed
- The reply box could be cleared while a reply was still sending. It is now locked while sending.

## [0.10.0] - 2026-09-25: AI agent with tool calling

### Added
- `app/services/agent_tools.py`: 6 tools (`search_knowledge_base`, `get_ticket_history`, `get_customer_details`, `assign_ticket`, `update_status`,
  `escalate_ticket`); the draft reply is the model's final plain-text answer, saved for staff;
  argument validation, no id arguments, runs with the starter's rights, each write once, read-only mode for injection-looking tickets.
- `app/services/agent_service.py`: prompt versions agent-v1/v2/v3, at most 6 turns and 8 tool calls; every step saved in `ai_interactions`.
- `POST /api/v1/tickets/{id}/agent` (staff, 202) and Celery task `agent.run`.
- Ollama provider: tool calling support.
- **Agent evaluation** `evals/run_agent.py`, 15 scenarios: v3 12/15 fully right; 0 forbidden changes in 37 runs.
- Tests: `test_agent.py`.

### Fixed
- Read-only mode was always on, because the guard matched the agent's own "Priority:" line. Now only customer text is checked.
- A v3 prompt example leaked a held-out scenario. Replaced; 4 new held-out scenarios added.

## [0.9.0] - 2026-09-25: RAG knowledge base

### Added
- **Migration `0004`**: `knowledge_documents`, `knowledge_chunks` (`embedding vector(768)`), HNSW cosine index.
- `app/services/document_processing.py`: extract (.md/.txt/.pdf, content-checked), clean, chunk (800 chars, 150 overlap).
- `app/services/knowledge_service.py`: create, process (embed with `search_document:` prefix + title), search (cosine,
  top-k, similarity cut-off, READY only), list, delete.
- `app/ai/rag.py`: `rag-v1` prompt, `RagAnswer` schema, anti-hallucination checks (no sources → no LLM call; answer must be
  answerable, cited, and cite only real sources).
- Endpoints: `POST/GET /api/v1/knowledge`, `DELETE /api/v1/knowledge/{id}`, `POST /api/v1/knowledge/search`,
  `POST /api/v1/knowledge/ask`, `POST /api/v1/tickets/{id}/suggest-reply` (saved in `ai_interactions`, never sent).
- Celery task `knowledge.process_document`; CLI `load-knowledge <folder>`.
- `knowledge-base/`: 8 sample help-centre articles.
- **RAG evaluation** `evals/run_rag.py` + 28 questions: retrieval 100%, correct answers 86.4%, correct refusals 83.3%,
  hallucination 1/6.
- Tests: `test_document_processing.py` (13), `test_rag.py` (24), +3 in `test_eval_metrics.py`; 222 pass.
- Docs: `rag.md` rewritten; api, database, migrations, celery, setup, testing, troubleshooting, interview prep, README.

### Changed
- `tests/fakes.py`: word-hash fake embeddings (768 dims) so search can be tested without a model.
- `app/api/errors.py`: AI errors → 503 with a fixed, safe message.
- Document titles come from the first `# heading` (falls back to the file name).

### Fixed (found while building)
- A bad chunk (e.g. wrong vector size) failed only at `commit()`, outside the error handling, which would have left the document
  stuck in PROCESSING. Now flushed inside the `try` and marked FAILED (caught by a test).
- The autogenerated migration used pgvector's type without importing it (would have crashed).

### Dependencies
`pgvector==0.5.0`, `pypdf==6.19.0`, `python-multipart==0.0.32`.

### Environment variables added
`RAG_CHUNK_SIZE` (800), `RAG_CHUNK_OVERLAP` (150), `RAG_TOP_K` (4), `RAG_MIN_SIMILARITY` (0.55), `KNOWLEDGE_MAX_UPLOAD_MB` (5).

### Migrations
| Revision | Change | Apply | Undo |
|---|---|---|---|
| `0004` | Knowledge base tables + HNSW index | `alembic upgrade head` | `alembic downgrade 0003` (knowledge base lost) |

## [0.8.0] - 2026-09-25: AI ticket classification + evaluation

### Added
- `app/ai/classifier.py`: prompt versions `classify-v1` and `classify-v2`, the `TicketClassification` answer
  shape (category, priority, confidence, reasoning), ticket text wrapped in `<ticket>` tags.
- `app/services/triage_service.py`: rules that decide what to do with the answer (injection guard, people
  first, confidence ≥ 0.7, route by category, escalate SECURITY/CRITICAL), saving every call.
- `app/ai/injection.py`: code-level prompt-injection guard.
- **Migration `0003`**: `ai_interactions` table.
- Celery task `tickets.triage` (retries if Ollama is down) and `app/workers/queue.py` (tickets are still
  created when Redis is down).
- `GET /api/v1/tickets/{id}/ai` (staff): the AI's answers and what the code did.
- `python -m app.cli seed-teams`: creates the 5 teams triage routes to.
- **Evaluation**: `evals/run_classification.py`, 64-ticket main set and 16-ticket held-out set, reports in
  `evals/results/`. Results: category accuracy 81.2% → 93.8% (main), 87.5% → 93.8% (held-out).
- Tests: `test_triage.py` (17), `test_injection.py` (12), `test_eval_metrics.py` (7); 182 pass.
- Docs: classification, injection guard and evaluation sections in `ai.md`; updated api, database, migrations,
  celery, setup, testing, troubleshooting, interview prep, README.

### Changed
- `tests/conftest.py`: the `api` fixture turns AI triage off, so tests never queue real jobs.
- `POST /api/v1/tickets` queues AI triage after saving the ticket.

### Fixed (found while building)
- Tests were putting real jobs on the development Redis queue (fixed with the fixture above; stray job purged).
- Evaluation script: p95 formula was wrong, and empty groups showed "0%" instead of "n/a".

### Environment variables added
`AI_TRIAGE_ENABLED` (default `true`), `AI_CONFIDENCE_THRESHOLD` (default `0.7`).

### Migrations
| Revision | Change | Apply | Undo |
|---|---|---|---|
| `0003` | `ai_interactions` table | `alembic upgrade head` | `alembic downgrade 0002` (saved AI answers are lost) |

## [0.7.0] - 2026-09-25: Background jobs (Celery + Redis)

### Added
- `app/workers/celery_app.py` (Celery app, JSON only, late acks, beat schedule) and `app/workers/tasks.py`
  (`tickets.check_sla`, retries on database errors).
- `app/services/sla_service.py`: escalates OPEN tickets waiting longer than 1h / 4h / 24h / 72h
  (CRITICAL / HIGH / MEDIUM / LOW). Safe to run repeatedly.
- **Migration `0002`**: `raised_by_id` / `changed_by_id` nullable (NULL = done by the system); its downgrade
  stops with a clear message if system-made rows exist.
- `/health/ready` now also checks Redis.
- Tests: `test_sla.py` (11) + 1 Redis readiness test; 146 pass. A real worker + beat run was verified.
- Docs: new `celery.md`; updated migrations, database, api, setup, testing, troubleshooting, interview prep, architecture, README.

### Changed
- `ticket_service`: status changes and escalations accept `by=None` (system); new public `record_escalation()`.
- `HistoryOut.changed_by` may be `null`.

### Dependencies
`celery[redis]==5.6.3` (brings `redis 6.4.0`, `kombu 5.6.2`, `billiard 4.3.0`, `vine 5.1.0`).

### Environment variables added
`REDIS_HOST` (default `localhost`), `SLA_CHECK_INTERVAL_SECONDS` (default 300). `REDIS_PORT` is now also read by the backend.

### Migrations
| Revision | Change | Apply | Undo |
|---|---|---|---|
| `0002` | System actions allowed in ticket history | `alembic upgrade head` | `alembic downgrade 0001` (blocked if system rows exist) |

## [0.6.0] - 2026-09-25: Simplified the backend

Goal: code a junior developer can fully understand and explain, keeping every feature and technology.

### Changed
- **Roles:** 14 fine-grained permissions → **one role per user** (`users.role`), checked with
  `require_roles(...)`. New `app/core/roles.py` (`Role`, `STAFF`, `MANAGERS`); removed `permissions.py`.
- **Who sees tickets:** customer = own; agent = their teams + assigned to them; manager/admin = all.
- **Refresh tokens:** no "families" or reuse detection. Each token works once (one `DELETE … RETURNING`),
  logout deletes it. Removed the `revoked_at` and `family_id` columns.
- **Tickets:** removed the `ticket_assignments` history table and row locks. History = status changes.
  Endpoint `/assignment` renamed to `/assign`. Teams now return their members inline
  (`POST /teams/{id}/members` replaces `PUT …/members/{user_id}`).
- **Users:** dropped the `roles`/`user_roles` tables and `last_login_at`/`updated_at`; removed
  `GET /admin/users/{id}`.
- **Security helpers:** removed the JWT `iss`/`type`/`jti` claims and `JWT_ISSUER`, the dummy-hash timing
  protection and password rehash.
- **Migrations:** 4 migrations → **one clean `0001_initial_schema`** (8 tables + pgvector). Both databases were
  rolled back to empty first; nothing real was lost.
- **Tests:** rewritten for the simpler design: 134 tests. Mutation-checked: 7 key protections removed one at a time, each caught.
- **Docs:** rewritten shorter. `tickets.md` merged into `architecture.md`; new `testing.md`.

### Removed environment variables
`JWT_ISSUER`

### Migrations
| Revision | Change | Apply | Undo |
|---|---|---|---|
| `0001` | Whole initial schema | `alembic upgrade head` | `alembic downgrade base` (deletes all data) |

## [0.5.0]: Teams and tickets
Teams, tickets, messages (with internal notes), status rules, assignment and escalation.

## [0.4.0]: Authentication
Register, login, logout, JWT access tokens, refresh tokens in httpOnly cookies, Argon2 passwords, roles, create-admin CLI.
Added `pyjwt 2.15.0`, `argon2-cffi 25.1.0`, `email-validator 2.3.0`.

## [0.3.0]: Database
Docker Compose with PostgreSQL 17 + pgvector (port 5433) and Redis 7 (port 6380), SQLAlchemy, Alembic, `/health/ready`.
Added `sqlalchemy 2.1.1`, `psycopg[binary] 3.3.6`, `alembic 1.20.0`.

## [0.2.0]: AI service layer
`AIService` over a local Ollama server: JSON output validated with Pydantic (with one retry), secrets removed
before sending, `/health/ai`. Ollama 0.34.4 with `qwen2.5:7b` and `nomic-embed-text`, stored inside the project.
Added `httpx2 2.13.1`.

## [0.1.0]: Foundation
FastAPI backend with `/health`, React + TypeScript frontend (Vite, React Router, Axios), shared `.env`.
Added `fastapi 0.141.1`, `uvicorn 0.54.0`, `pydantic-settings 2.15.0`, `pytest 9.1.1`.
