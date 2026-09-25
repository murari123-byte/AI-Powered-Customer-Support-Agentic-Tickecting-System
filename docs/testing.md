# Testing

| Suite | Command | Result (25 Sept 2026) |
|---|---|---|
| Backend | `cd backend && .venv/bin/pytest` | **251 passed, 3 skipped** |
| Frontend | `cd frontend && npm test` | **11 passed** |
| Lint | `ruff check . && ruff format --check .` · `npm run lint` | clean |
| Dependencies | `pip-audit` · `npm audit --omit=dev` | 0 known vulnerabilities |
| AI quality | `python -m evals.run_classification` / `run_rag` / `run_agent` | see ai.md, rag.md, agentic-workflow.md |

All of these also run in CI on every push ([CI](#ci)).

## Backend

```bash
cd backend
.venv/bin/pytest -v                                    # everything (needs: docker compose up -d)
.venv/bin/pytest -m "not db"                           # only tests that need no database
RUN_LIVE_AI_TESTS=1 .venv/bin/pytest -m live_ai -v     # talk to the real Ollama model
```

Expected: **251 passed, 3 skipped** (the 3 live AI tests are skipped unless you turn them on).
If Docker isn't running, the database tests are **skipped with a message**, not failed.

## What is tested

| File | What it checks |
|---|---|
| `test_health.py`, `test_health_ready.py`, `test_health_ai.py` | Health checks; CORS; database or Redis down → 503; AI down → 503 but the API stays up |
| `test_migrations.py` | Migrations apply, undo and re-apply; models match migrations |
| `test_security.py` | Argon2 hashing; tokens: expired, forged, `alg: none`, garbage all rejected |
| `test_auth_api.py` | Register, login, cookie flags, refresh (each token works once), logout, disabled users |
| `test_users_admin.py` | Who can list/change users; role changes work immediately; admins can't lock themselves out; create-admin CLI |
| `test_ticket_workflow.py` | Status rules as pure logic: who may make which move; reopen window |
| `test_tickets.py` | Teams; creating tickets; **who sees which tickets**; internal notes hidden; auto status moves; assignment rules; escalation; history |
| `test_sla.py` | SLA rule per priority, only OPEN tickets, never escalated twice, system shown in history; the Celery task is registered, scheduled, and runs the check |
| `test_triage.py` | AI triage with a **fake LLM**: the prompt wraps customer text safely; an injection attempt is never acted on, even if the model obeys it; confident answers are applied and routed; low confidence changes nothing; SECURITY/CRITICAL escalate; the AI never overrides a person; invalid/unavailable answers are recorded; tickets are still created when Redis is down; staff-only `/ai` endpoint |
| `test_document_processing.py` | Text/Markdown/real PDF extraction; fake PDFs, .exe, null bytes, non-UTF-8 rejected; cleaning; chunk size, overlap, no cut words, huge paragraphs |
| `test_rag.py` | Upload → process → READY with 768-dim chunks; AI down keeps PROCESSING (retry); bad data → FAILED; search order, cut-off, READY-only; **the anti-hallucination rules** (no sources = no LLM call, uncited or made-up citations rejected); API upload/ask/search/suggest-reply permissions; 503 without leaking details |
| `test_agent.py` | The agent loop with a **scripted fake LLM**: tool results go back to the model; unknown tools, invalid/extra arguments, `status=RESOLVED` refused with nothing changed; write tools once; **starter's rights** (an agent's run can't reassign); normal ticket rules; read-only mode for injection tickets (write tools not even offered); turn and tool-call limits; no email/ids in customer details; secrets redacted in tool results; API 202/403/409 |
| `test_injection.py` | The injection guard: 6 attacks caught, 6 normal sentences not flagged |
| `test_eval_metrics.py` | The evaluation maths for classification **and** RAG (fact checks with alternatives, hallucination rate); the test sets are valid |
| `test_rate_limit.py` | Login blocked after 10 tries a minute (429 + `Retry-After`); the sign-up limit is separate and stricter; Redis down → requests still allowed |
| `test_metrics.py` | `/metrics` works; routes are labelled by template (`/tickets/{ticket_id}`, not every id); all metric families exist; tickets, escalations and AI errors are counted |
| `test_ai_*.py` | AI layer with a **fake LLM**: JSON validation + retry, secrets removed before sending, Ollama errors |

## How the tests are built

- **Real PostgreSQL**, in a separate `support_test` database. The schema is built by running the
  migrations (the same way production does it).
- **Each test is rolled back** at the end, so tests never see each other's data.
- **The LLM is faked** (`tests/fakes.py`) so AI tests are fast and give the same result every time.
- **Time limit**: any single test that runs longer than 60 s fails with a stack trace (`pytest-timeout`), and each CI job stops after 15 minutes, so a hang can't block CI.
- **Test world**: the `world` fixture creates 2 customers, 2 agents, a manager, an admin and 2 teams.

## Were the tests checked?

Yes. Each important protection was removed from the code on purpose, and the tests were run to see if
they noticed. All 7 were caught: role check, disabled-user check, ticket visibility, internal-note
filter, team-membership check, status role check, and "refresh token works only once".
For the agent, 6 more were checked and caught: the read-only guard, the write-once limit, refusing extra
arguments, the ban on RESOLVED, hiding write tools in read-only mode, and the turn limit.

## Celery in tests

Tests don't start a worker. They call the task function directly (`tasks.check_sla()`), with the
database session swapped for the test one. The rule itself (`sla_service`) is tested separately.
A real worker + beat run is described in [celery.md](celery.md#verified).

## Tests never touch real Redis or Ollama

The `api` fixture sets `AI_TRIAGE_ENABLED=false`, so creating tickets in tests doesn't queue real jobs.
The triage tests replace the queue and the LLM with fakes. Real-model checks are the evaluation
(`python -m evals.run_classification`) and the optional live tests.

## Fake embeddings

`tests/fakes.py` → `fake_embedding()`: each word is hashed to one of 768 positions, so texts that share words get similar
vectors (like real embeddings, only simpler). Search can then be tested with a real pgvector database and no model.
Fake similarities are lower than real ones, so RAG tests set `RAG_MIN_SIMILARITY=0.1`.

## Frontend

```bash
cd frontend
npm test            # Vitest + Testing Library, in a fake browser (jsdom)
npm run lint
npm run build       # also type-checks
```

| File | What it checks |
|---|---|
| `src/test/client.test.ts` | The access token is added to calls; on a 401 the client refreshes **once** (even when several calls fail together) and retries; a failed refresh ends the session; error messages (API detail, validation problem, server unreachable) are readable |
| `src/test/components.test.tsx` | Visitors are sent to login; users without the role are sent back to their tickets; the right role sees the page; status badges are readable |

The whole UI was also checked by hand in a real browser (headless Chromium) for every role: customer, agent, manager, admin.

## CI

`.github/workflows/ci.yml` runs on every push to `main` and every pull request:

1. **backend**: ruff lint + format check → create the test DB → `alembic upgrade head` + `alembic check` on an empty database → pytest → pip-audit.
2. **frontend**: `npm ci` → lint → tests → build → `npm audit --omit=dev --audit-level=high`.
3. **docker**: builds both images (only if 1 and 2 passed).

Every command was run locally and passes. The workflow itself has **not run on GitHub yet**, because the project isn't pushed.
