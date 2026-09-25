# API reference

Base URL: `http://localhost:8000`. Interactive docs, where you can try every endpoint: **http://localhost:8000/docs**
(click **Authorize** and paste an access token). The same information as JSON: `/openapi.json`.

- Business endpoints are under `/api/v1`. Health checks and `/metrics` are at the root.
- "Auth: token" means the call must send `Authorization: Bearer <access_token>` (from login or refresh).
- Bodies are JSON unless stated. Unknown fields are rejected (422), so you can't sneak in e.g. `"role"`.
- Every error has the same shape: `{"detail": "message"}` (422 gives a list of field problems instead).
- Role groups used below: **staff** = SUPPORT_AGENT, SUPPORT_MANAGER, ADMIN · **managers** = SUPPORT_MANAGER, ADMIN.

## Status codes

| Code | Meaning |
|---|---|
| 200 / 201 / 202 / 204 | OK / created / accepted (runs in the background) / done, no body |
| 400 | Not valid for this case (e.g. assignee not in the team, not a real PDF) |
| 401 | Not logged in, or bad/expired token. The frontend then refreshes once and retries |
| 403 | Logged in, but your role can't do this |
| 404 | Not found, **or not visible to you** (so nobody can probe which ticket ids exist) |
| 409 | Not possible right now (ticket closed, email already registered, bad status move) |
| 413 | Uploaded file bigger than `KNOWLEDGE_MAX_UPLOAD_MB` |
| 422 | Input breaks the rules (missing field, too short, unknown value or field) |
| 429 | Too many login/sign-up attempts. `Retry-After` header says how many seconds to wait |
| 503 | A dependency is down: database/Redis (health), the AI, or background jobs. Fixed, safe messages |

Every endpoint that needs a token can also return **401**; every endpoint with a body can return **422**. The tables
below list only the other errors.

## Summary

| Method | Path | Auth | Role | What it does |
|---|---|---|---|---|
| GET | `/health` | none | anyone | Is the API process alive? |
| GET | `/health/ready` | none | anyone | Can it reach the database and Redis? |
| GET | `/health/ai` | none | anyone | Is Ollama up with both models? |
| GET | `/metrics` | none | Prometheus | Metrics in Prometheus text format |
| POST | `/api/v1/auth/register` | none | anyone | Create a customer account |
| POST | `/api/v1/auth/login` | none | anyone | Access token + refresh cookie |
| POST | `/api/v1/auth/refresh` | refresh cookie | anyone | New access token + new refresh cookie |
| POST | `/api/v1/auth/logout` | refresh cookie | anyone | End this session |
| GET | `/api/v1/auth/me` | token | any | Your own account |
| GET | `/api/v1/admin/users` | token | managers | List users |
| PATCH | `/api/v1/admin/users/{user_id}` | token | ADMIN | Change role / active |
| GET | `/api/v1/teams` | token | staff | Teams with members |
| POST | `/api/v1/teams` | token | ADMIN | Create a team |
| PATCH | `/api/v1/teams/{team_id}` | token | ADMIN | Rename, describe, deactivate |
| POST | `/api/v1/teams/{team_id}/members` | token | ADMIN | Add a staff member |
| DELETE | `/api/v1/teams/{team_id}/members/{user_id}` | token | ADMIN | Remove a member |
| POST | `/api/v1/tickets` | token | CUSTOMER | Raise a ticket |
| GET | `/api/v1/tickets` | token | any | Tickets you can see |
| GET | `/api/v1/tickets/{ticket_id}` | token | can see it | One ticket |
| PATCH | `/api/v1/tickets/{ticket_id}` | token | staff | Change subject / priority / category |
| POST | `/api/v1/tickets/{ticket_id}/status` | token | depends on the move | Change status |
| GET | `/api/v1/tickets/{ticket_id}/messages` | token | can see it | The conversation |
| POST | `/api/v1/tickets/{ticket_id}/messages` | token | owner or staff | Reply, or add an internal note |
| POST | `/api/v1/tickets/{ticket_id}/assign` | token | staff | Set team / assignee |
| POST | `/api/v1/tickets/{ticket_id}/escalate` | token | staff | Escalate with a reason |
| GET | `/api/v1/tickets/{ticket_id}/history` | token | staff | Status changes |
| GET | `/api/v1/tickets/{ticket_id}/ai` | token | staff | Every AI answer and what code did with it |
| POST | `/api/v1/tickets/{ticket_id}/suggest-reply` | token | staff | AI draft reply with sources |
| POST | `/api/v1/tickets/{ticket_id}/agent` | token | staff | Start the AI agent (background) |
| POST | `/api/v1/knowledge` | token | ADMIN | Upload a document |
| GET | `/api/v1/knowledge` | token | staff | List documents |
| DELETE | `/api/v1/knowledge/{document_id}` | token | ADMIN | Delete a document |
| POST | `/api/v1/knowledge/search` | token | staff | Matching chunks with scores |
| POST | `/api/v1/knowledge/ask` | token | staff | Answer from the knowledge base, with sources |

Values used in tickets: `status` = OPEN, IN_PROGRESS, WAITING_FOR_CUSTOMER, ESCALATED, RESOLVED, CLOSED ·
`priority` = LOW, MEDIUM, HIGH, CRITICAL · `category` = BILLING, PAYMENT, TECHNICAL, ACCOUNT, LOGIN, PRODUCT, SECURITY, OTHER ·
`role` = CUSTOMER, SUPPORT_AGENT, SUPPORT_MANAGER, ADMIN.

Common response shapes:

- **User** = `{id, email, full_name, role, is_active, created_at}`
- **Ticket** = `{id, number, subject, status, priority, category|null, customer:{id, full_name}, team:{id, name}|null, assignee:{id, full_name}|null, created_at, resolved_at|null}`
- **Team** = `{id, name, description|null, is_active, members:[{user:{id, full_name}, is_lead}]}`
- **Answer** = `{answerable, answer, sources:[{document_id, title, chunk_index, similarity, excerpt}], reason, latency_ms|null}`

---

## Health and metrics

### GET /health
Auth: none. Response `200`: `{"status": "ok", "app": "AI Support Platform", "version": "0.1.0", "environment": "development"}`. No errors.

### GET /health/ready
Auth: none. Checks the database and Redis. Used by Docker's health check.
Response `200`: `{"status": "ok", "checks": {"database": "ok", "redis": "ok"}}`.
Errors: `503` with the same shape, the failing check marked `"unavailable"`.

### GET /health/ai
Auth: none. Asks Ollama which models it has.
Response `200`:
```json
{"status": "ok", "provider": "ollama", "chat_model": "qwen2.5:7b", "embed_model": "nomic-embed-text",
 "models": {"qwen2.5:7b": true, "nomic-embed-text": true}, "detail": null}
```
Errors: `503` (Ollama down or a model missing; `detail` says which).

### GET /metrics
Auth: none, on purpose (Prometheus scrapes it). Published only on 127.0.0.1; block it at the proxy in production.
Response `200`, text: `http_requests_total{method="GET",route="/api/v1/tickets/{ticket_id}",status="200"} 12` and so on.
See [monitoring.md](monitoring.md).

---

## Authentication

### POST /api/v1/auth/register
Auth: none. **Rate limit: 5 per hour per IP.** Always creates a CUSTOMER (you can't choose the role).

| Field | Rules |
|---|---|
| `email` | required, valid email |
| `password` | required, 10–128 characters |
| `full_name` | required, 1–120 characters |

Response `201`: User. Errors: `409` email already registered · `429` too many sign-ups.
```bash
curl -X POST localhost:8000/api/v1/auth/register -H 'Content-Type: application/json' \
  -d '{"email":"ana@example.com","password":"at-least-10-chars","full_name":"Ana Silva"}'
```
```json
{"id": "5b1e…", "email": "ana@example.com", "full_name": "Ana Silva", "role": "CUSTOMER", "is_active": true, "created_at": "2026-09-25T10:00:00Z"}
```

### POST /api/v1/auth/login
Auth: none. **Rate limit: 10 per minute per IP.** Body: `{"email", "password"}`.
Response `200`:
```json
{"access_token": "eyJhbGciOi…", "token_type": "bearer", "expires_in": 900, "user": {"id": "…", "role": "CUSTOMER", "…": "…"}}
```
Also sets `Set-Cookie: refresh_token=…; HttpOnly; Secure; SameSite=strict; Path=/api/v1/auth`.
Errors: `401` "Invalid email or password" (same message for wrong email, wrong password and disabled account) · `429`.

### POST /api/v1/auth/refresh
Auth: the `refresh_token` cookie (the browser sends it by itself). No body.
Response `200`: same as login, with a **new** cookie. The old refresh token stops working (single use).
Errors: `401` "Please log in again" (missing, expired, already used, or the user was deactivated).

### POST /api/v1/auth/logout
Auth: the refresh cookie, if any. Deletes that refresh token and clears the cookie. Response `204`. No errors.

### GET /api/v1/auth/me
Auth: token. Response `200`: User.

---

## Users (admin)

### GET /api/v1/admin/users
Auth: token. Role: managers. Query: `search` (name or email, 1–100 chars), `limit` (1–200, default 50), `offset` (default 0).
Response `200`: `{"items": [User, …], "total": 42}`. Errors: `403`.

### PATCH /api/v1/admin/users/{user_id}
Auth: token. Role: ADMIN. Body (any of): `{"role": "SUPPORT_AGENT", "is_active": false}`.
Response `200`: User. Takes effect on that user's next request.
Errors: `403` · `404` user not found · `400` "You cannot remove your own admin access".

---

## Teams

### GET /api/v1/teams
Auth: token. Role: staff. Response `200`: `[Team, …]`. Errors: `403`.

### POST /api/v1/teams
Auth: token. Role: ADMIN. Body: `{"name": "Billing Team", "description": "Refunds and invoices"}` (`name` 2–100 chars).
Response `201`: Team. Errors: `403` · `409` name already used.

### PATCH /api/v1/teams/{team_id}
Auth: token. Role: ADMIN. Body (any of): `name`, `description`, `is_active`.
Response `200`: Team. Errors: `403` · `404` · `409` name already used.

### POST /api/v1/teams/{team_id}/members
Auth: token. Role: ADMIN. Body: `{"user_id": "…", "is_lead": false}`.
Response `200`: Team. Errors: `403` · `404` team · `400` "Only active support staff can join a team".

### DELETE /api/v1/teams/{team_id}/members/{user_id}
Auth: token. Role: ADMIN. Response `204`.
Errors: `403` · `404` team · `400` "User is not a member of this team".

---

## Tickets

Who sees what: a customer sees only their own tickets; an agent sees tickets of their teams (and ones assigned to them);
managers and admins see all. A ticket you can't see gives **404** on every endpoint below.

### POST /api/v1/tickets
Auth: token. Role: CUSTOMER. Body: `subject` (3–200), `description` (1–10,000), optional `category`. Customers can't set priority.
Response `201`: Ticket, status OPEN, priority MEDIUM. AI triage then runs in the background, so for a few seconds `team`
and `category` may still be empty. The ticket is saved even if Redis is down (triage is then skipped). Errors: `403` staff.
```json
{"subject": "Charged twice", "description": "I paid 500 twice on 24 Sept", "category": "BILLING"}
```
```json
{"id": "…", "number": 1001, "subject": "Charged twice", "status": "OPEN", "priority": "MEDIUM", "category": "BILLING",
 "customer": {"id": "…", "full_name": "Ana Silva"}, "team": null, "assignee": null, "created_at": "…", "resolved_at": null}
```

### GET /api/v1/tickets
Auth: token. Role: any (filtered by who you are). Query: `status`, `priority`, `team_id`, `assigned_to_me` (true/false),
`search` (subject, up to 100 chars), `limit` (1–100, default 25), `offset`.
Response `200`: `{"items": [Ticket, …], "total": 7}`, newest first.

### GET /api/v1/tickets/{ticket_id}
Auth: token. Role: anyone who can see it. Response `200`: Ticket. Errors: `404`.

### PATCH /api/v1/tickets/{ticket_id}
Auth: token. Role: staff. Body (any of): `subject`, `priority`, `category`.
Response `200`: Ticket. Errors: `403` "Only support staff can edit tickets" · `404`.

### POST /api/v1/tickets/{ticket_id}/status
Auth: token. Role: depends on the move ([rules](architecture.md#ticket-status-rules)); a customer may close their own ticket, and reopen it
within `TICKET_REOPEN_WINDOW_DAYS` of it being resolved; only managers move an ESCALATED ticket. Body: `{"status": "RESOLVED", "reason": "Refund issued"}` (`reason` optional).
Response `200`: Ticket. Errors: `404` · `403` "You cannot move this ticket to …" · `409` "Cannot move a ticket from X to Y",
"Use the escalate action to escalate a ticket", "Too late to reopen; please open a new ticket".

### GET /api/v1/tickets/{ticket_id}/messages
Auth: token. Role: anyone who can see it. Customers never get internal notes (filtered in the database query).
Response `200`: `[{"id", "author": {"id", "full_name"}, "body", "is_internal", "created_at"}, …]`, oldest first. Errors: `404`.

### POST /api/v1/tickets/{ticket_id}/messages
Auth: token. Role: the ticket's customer, or staff. Body: `{"body": "…", "is_internal": false}` (`body` 1–10,000).
Response `201`: the message. Errors: `404` · `403` "Only support staff can add internal notes" · `409` "This ticket is closed…".

### POST /api/v1/tickets/{ticket_id}/assign
Auth: token. Role: staff ([rules](architecture.md#assignment-rules): agents may only take tickets of their own team for
themselves; managers assign anyone). Body: `{"team_id": "…", "assignee_id": "…"}` (either can be null).
Response `200`: Ticket. Errors: `404` · `403` "Agents can only take tickets from their team for themselves" ·
`400` "Choose an active team", "Assignee is not a member of this team" · `409` "Closed tickets can't be reassigned".

### POST /api/v1/tickets/{ticket_id}/escalate
Auth: token. Role: staff. Body: `{"reason": "Customer threatens chargeback"}` (3–1000 chars).
Response `200`: Ticket with status ESCALATED; an escalation record is saved. Errors: `404` · `403` · `409` "A RESOLVED ticket can't be escalated" (only OPEN, IN_PROGRESS and WAITING_FOR_CUSTOMER can be).

### GET /api/v1/tickets/{ticket_id}/history
Auth: token. Role: staff. Response `200`:
`[{"from_status": null, "to_status": "OPEN", "changed_by": {"id", "full_name"}, "reason": null, "created_at": "…"}, …]`,
oldest first. `changed_by: null` means the system did it (SLA job, AI triage). Errors: `403` · `404`.

### GET /api/v1/tickets/{ticket_id}/ai
Auth: token. Role: staff. Every AI call about this ticket (triage, suggested replies, agent runs) and what the code decided.
Response `200`:
```json
[{"kind": "classification", "status": "OK", "model": "qwen2.5:7b", "prompt_version": "classify-v2",
  "result": {"category": "BILLING", "priority": "HIGH", "confidence": 0.9, "reasoning": "Double charge on the card."},
  "confidence": 0.9, "applied": true, "decision": "Set BILLING / HIGH; routed to Billing Team",
  "latency_ms": 6200, "created_at": "…"}]
```
Errors: `403` · `404`.

### POST /api/v1/tickets/{ticket_id}/suggest-reply
Auth: token. Role: staff. No body. Uses the ticket text as the question for RAG. **Never sent to the customer**; saved in `/ai`.
Response `200`: Answer (see `/knowledge/ask`). Errors: `403` · `404` · `503` "The AI is not available right now…". Takes 5–30 s on a CPU.

### POST /api/v1/tickets/{ticket_id}/agent
Auth: token. Role: staff. No body. Queues an agent run that uses tools **with your rights**
([agentic-workflow.md](agentic-workflow.md)). Response `202`:
```json
{"queued": true, "results": "/api/v1/tickets/ced3…/ai"}
```
About 30–60 s later `/ai` has an entry with `"kind": "agent_run"`:
```json
{"kind": "agent_run", "status": "OK", "prompt_version": "agent-v3", "applied": true,
 "decision": "2 tool calls; changes made: assign_ticket; blocked: none; finished",
 "result": {"steps": [{"tool": "search_knowledge_base", "arguments": {"query": "double charge refund"}, "ok": true, "blocked": false, "output": {"…": "…"}},
                      {"tool": "assign_ticket", "arguments": {"team": "Billing Team"}, "ok": true, "blocked": false, "output": {"ok": "Ticket assigned to Billing Team"}}],
            "final": "SUMMARY: … DRAFT REPLY: …", "stopped_because": "finished", "read_only": false}}
```
Errors: `403` customers · `404` · `409` "The agent doesn't work RESOLVED tickets" (or CLOSED) · `503` "Background jobs are not available right now".

---

## Knowledge base

### POST /api/v1/knowledge
Auth: token. Role: ADMIN. **Multipart form**: `file` (.md, .txt or .pdf) and optional `title`.
Response `202`: `{"id", "title", "filename", "status": "PROCESSING", "chunk_count": 0, "error": null, "created_at"}`.
The worker then chunks and embeds it; `status` becomes `READY` (or `FAILED` with `error`).
Errors: `403` · `413` bigger than 5 MB · `400` wrong type, "The file is not a real PDF", "Text files must be UTF-8",
"No text found in the PDF (is it a scanned image?)", more than 200 pages.
```bash
curl -X POST localhost:8000/api/v1/knowledge -H "Authorization: Bearer $TOKEN" -F file=@refund-policy.md
```

### GET /api/v1/knowledge
Auth: token. Role: staff. Response `200`: `[Document, …]`. Errors: `403`.

### DELETE /api/v1/knowledge/{document_id}
Auth: token. Role: ADMIN. Deletes the document and its chunks. Response `204`. Errors: `403` · `404`.

### POST /api/v1/knowledge/search
Auth: token. Role: staff. Body: `{"question": "…"}` (3–1000). No LLM call, only embeddings; useful to see *why* an answer
used a source. Response `200`: `{"results": [{"document_id", "title", "chunk_index", "similarity": 0.78, "excerpt"}, …]}`.
Errors: `403` · `503` AI down (the question has to be embedded).

### POST /api/v1/knowledge/ask
Auth: token. Role: staff. Body: `{"question": "How long is the password reset link valid?"}`.
Response `200`:
```json
{"answerable": true, "answer": "The password reset link is valid for 1 hour [1].",
 "sources": [{"document_id": "…", "title": "Signing in, passwords and two-factor authentication",
              "chunk_index": 0, "similarity": 0.78, "excerpt": "## Forgot your password …"}],
 "reason": "Answered from sources", "latency_ms": 7400}
```
When the documents don't cover it: `"answerable": false`, `"answer": "I couldn't find this in the knowledge base. A support
agent should handle it."`, `"sources": []`, and `reason` says why. Errors: `403` · `503` "The AI is not available right now…"
or "The AI gave an unusable answer…".
