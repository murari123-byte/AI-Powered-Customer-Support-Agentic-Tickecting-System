# Architecture

## The big picture

```
                      ┌───────────── Docker Compose (9 services) ─────────────┐
Browser ──► frontend (nginx: the built React app)                             │
   │                                                                          │
   └──► api: FastAPI :8000 ──► PostgreSQL + pgvector   users, tickets, AI log, document chunks + embeddings
          │  (JWT in the          ▲                                           │
          │   Authorization       │                                           │
          │   header)             │                                           │
          ├──► Redis (job queue) ──► worker: Celery + beat ──┐                │
          │                                                  ├──► Ollama      │  qwen2.5:7b, nomic-embed-text
          └──► AIService (suggest-reply, ask) ───────────────┘                │
                                                                              │
Prometheus ──► api /metrics, worker :9808 ──► Grafana (dashboard)             │
migrate: runs `alembic upgrade head` once, before the api starts              │
                      └───────────────────────────────────────────────────────┘
```

| Part | Job |
|---|---|
| **frontend** | React + TypeScript pages for each role. Keeps the access token in memory; refreshes it with the httpOnly cookie |
| **api** | FastAPI. Checks login and role, applies the business rules, stores data. Answers fast; slow AI work is queued |
| **worker** | Celery. Runs AI triage, document processing and agent runs in the background; beat runs the SLA check every 5 minutes |
| **PostgreSQL + pgvector** | All data, including 768-number embeddings for RAG search (HNSW index) |
| **Redis** | The job queue between api and worker; also the rate-limit counters |
| **Ollama** | The local LLM. Only the api and worker can reach it, and only through `AIService` |
| **Prometheus + Grafana** | Collect and show metrics: requests, errors, latency, AI calls, escalations, queue length |

## What happens when a customer raises a ticket

1. The browser sends `POST /api/v1/tickets` with the access token.
2. The api checks the token and the role (CUSTOMER), validates the input (Pydantic), saves the ticket (status OPEN) and
   its first message, and puts a `tickets.triage` job on Redis. It answers **201** right away.
3. The worker takes the job. `AIService` removes secrets from the text and asks the model for
   `{category, priority, confidence, reasoning}` as JSON, validated with Pydantic (one retry if invalid).
4. **Code decides**: if the text looks like a prompt injection, or a person already set the fields, or confidence < 0.7,
   nothing changes. Otherwise it sets category and priority, routes the ticket to the team for that category, and
   escalates SECURITY or CRITICAL tickets. Every AI answer and the decision are saved in `ai_interactions`.
5. Staff of that team now see the ticket. They can ask for a suggested reply (RAG) or start the agent.
6. Every 5 minutes, beat runs the SLA check and escalates tickets left OPEN too long.

## Backend code layout

```
backend/app/
├── main.py          builds the app, registers routes
├── core/            config (settings from .env), roles, security (passwords, tokens), rate limit, metrics
├── db/              database connection + Base class for tables
├── models/          database tables (SQLAlchemy)
├── schemas/         what the API accepts and returns (Pydantic)
├── services/        the business rules: auth, users, teams, tickets, status rules, SLA, triage, knowledge, agent + its tools
├── api/             routes (HTTP endpoints), deps.py (login/role checks), errors.py, metrics.py
├── ai/              AIService (the only code that talks to the LLM), Ollama provider, prompts, redaction, injection guard
├── workers/         Celery app + background tasks (thin: they call services)
└── cli.py           create-admin, seed-teams, load-knowledge
```

**A request goes: route → service → database.**
- **Routes** only read the input, check the login/role, call a service, and return the result.
- **Services** hold the rules and never touch HTTP, so they're easy to test.
- **Errors** from services become HTTP codes in one place (`api/errors.py`), e.g. `TicketNotFoundError` → 404.

## Roles

Each user has **one** role. The code checks it with `Depends(require_roles(...))`.

| Action | CUSTOMER | SUPPORT_AGENT | SUPPORT_MANAGER | ADMIN |
|---|:-:|:-:|:-:|:-:|
| Raise tickets, reply, close/reopen own tickets | ✅ | | | |
| See tickets | own | their teams' + assigned to them | all | all |
| Reply as staff, internal notes, change status, edit priority | | ✅ | ✅ | ✅ |
| Take a ticket from own team | | ✅ | ✅ | ✅ |
| Assign any ticket to any team/agent | | | ✅ | ✅ |
| Escalate | | ✅ | ✅ | ✅ |
| Take a ticket out of ESCALATED | | | ✅ | ✅ |
| List users | | | ✅ | ✅ |
| Change roles, deactivate users, manage teams | | | | ✅ |

A ticket you're not allowed to see returns **404** (not 403), so you can't even learn that it exists.

## Ticket status rules

```
OPEN ──► IN_PROGRESS ◄──► WAITING_FOR_CUSTOMER
  │           │                  │
  └───────────┴────► RESOLVED ◄──┘      (staff)
                       │   │
         reopen ◄──────┘   └──► CLOSED  (final)

OPEN / IN_PROGRESS / WAITING ──escalate (with reason)──► ESCALATED ──manager──► IN_PROGRESS or RESOLVED
```

| Rule | Detail |
|---|---|
| Staff move tickets between OPEN, IN_PROGRESS, WAITING_FOR_CUSTOMER and RESOLVED | |
| The customer can close their own ticket at any time | |
| The customer can reopen a RESOLVED ticket | Only within `TICKET_REOPEN_WINDOW_DAYS` (7) |
| ESCALATED is only set by the escalate action | It needs a reason |
| Only managers/admins take a ticket out of ESCALATED | |
| CLOSED is final | No more messages or changes: open a new ticket |
| Customer replies move the ticket automatically | WAITING → IN_PROGRESS; RESOLVED → OPEN (within the window) |

Wrong move = **409**. Allowed move, but not for your role = **403**.
All the rules are in one table: `ALLOWED_MOVES` in `app/services/ticket_workflow.py`.

## Assignment rules

- A ticket goes to a **team**, then optionally to one **person in that team**.
- The person must be active support staff **and** a member of the team.
- Agents can only take a ticket from their own team for **themselves**. Managers/admins can assign anyone.

## Key decisions

| Decision | Why |
|---|---|
| One role per user, checked directly | Simple to understand and explain; enough for 4 fixed roles |
| Role read from the database on every request (not stored in the JWT) | Role changes and deactivation work immediately |
| Services separate from routes | Rules can be tested without HTTP |
| `/health` (alive?) separate from `/health/ready` (database OK?) | A database hiccup shouldn't make Docker restart a healthy API |
| All AI calls go through `AIService` | One place for secret removal, output validation and logging |
| Database changes only through Alembic migrations | Every database gets exactly the same schema |
| Slow AI work in Celery jobs | A ticket is saved in milliseconds even if the model takes 20 s, or is down |
| "The LLM suggests, code decides" | The model can be wrong or tricked; the rules that change data are plain, tested code |
| Agent tools run with the rights of the person who started the run | The AI can never do more than that person could |
| pgvector instead of a separate vector database | One database to run, back up and migrate; enough for thousands of chunks |
| Local Ollama behind an `LLMProvider` interface | Free, private; a paid API could be added as one new class |

Frontend details: [frontend.md](frontend.md). Containers: [docker.md](docker.md). Metrics: [monitoring.md](monitoring.md).
