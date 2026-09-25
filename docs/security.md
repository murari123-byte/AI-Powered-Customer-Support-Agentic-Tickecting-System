# Security

What protects the system, where it's in the code, and how it was checked. Reviewed 25 Sept 2026.

## Summary

| Area | Protection | Where | Checked by |
|---|---|---|---|
| **Passwords** | Argon2id hashes (salted, slow on purpose); 10–128 chars; same error for wrong email/password/disabled | `core/security.py`, `services/auth_service.py` | `test_security.py`, `test_auth_api.py` |
| **Brute force** | **Rate limit**: 10 logins/min and 5 sign-ups/hour per IP (Redis); 429 + `Retry-After`. If Redis is down, requests are allowed (logged) rather than locking everyone out | `core/rate_limit.py` | `test_rate_limit.py` |
| **JWT** | HS256 with a required 32+ char secret; algorithm fixed in code (`alg: none` rejected); 15 min; only user id inside | `core/security.py` | `test_security.py` (forged, expired, `alg: none`, garbage) |
| **Refresh tokens** | Random, stored as SHA-256 hash, single use (`DELETE … RETURNING`), httpOnly + Secure + SameSite=Strict cookie limited to `/api/v1/auth` | `services/auth_service.py`, `routes/auth.py` | `test_auth_api.py` |
| **RBAC** | `require_roles(...)` on endpoints; role read from the DB on every request (changes apply immediately); sign-up can't pick a role; admins can't lock themselves out | `api/deps.py`, `core/roles.py` | `test_users_admin.py` (7 protections mutation-tested) |
| **Ticket access** | One visibility rule for every ticket action; invisible = **404** (existence not leaked); internal notes filtered in the query | `services/ticket_service.py` | `test_tickets.py` |
| **Input validation** | Pydantic on every request: lengths, enums, `extra="forbid"` (unknown fields such as `role` rejected) | `schemas/` | many API tests (422 cases) |
| **SQL injection** | Only SQLAlchemy with bound parameters; user text in `LIKE` has `%`/`_` escaped | services | search tests with `%` |
| **XSS** | React escapes all text (no `dangerouslySetInnerHTML` anywhere); access token kept in memory, not localStorage; **CSP** header in nginx | frontend, `frontend/nginx.conf` | browser check: app works with CSP, no violations |
| **CSRF** | API calls use the `Authorization` header (browsers never add it by themselves); the refresh cookie is `SameSite=Strict` | | |
| **CORS** | Exact allow-list from `CORS_ORIGINS` (no `*`), credentials allowed only for those origins | `main.py` | `test_health.py` |
| **File uploads** | Only .md/.txt/.pdf; **content** checked (PDF magic bytes, UTF-8, no null bytes); max 5 MB, read in pieces so a huge upload can't fill memory (413); max 200 PDF pages; the file itself isn't stored, only its text | `services/document_processing.py`, `routes/knowledge.py` | `test_document_processing.py`, `test_rag.py` (fake PDF, .exe, 413) |
| **Prompt injection** | Customer text wrapped as data in prompts; **code guard** refuses to act on AI answers for injection-looking tickets; the agent runs read-only on them | `ai/injection.py`, `triage_service.py`, `agent_service.py` | `test_injection.py`, `test_triage.py`, `test_agent.py`, evaluations |
| **AI tool authorization** | The LLM only *requests* tools; code validates arguments, uses no ids from the model, runs tools **with the starter's rights**, limits writes, never resolves/closes | `services/agent_tools.py` | `test_agent.py` (6 protections mutation-tested), agent evaluation: 0 forbidden changes in 37 runs |
| **Secrets to the LLM** | Every message (and embedding input, and agent tool result) is redacted: passwords, JWTs, API keys, card numbers, OTPs | `ai/redaction.py`, `ai/service.py` | `test_ai_redaction.py`, `test_agent.py` |
| **Secrets in config** | Only in `.env` (git-ignored); no defaults for `POSTGRES_PASSWORD`, `JWT_SECRET_KEY`, `GRAFANA_ADMIN_PASSWORD` (app and Compose refuse to start); `SecretStr`; `alembic.ini` has no URL | `core/config.py`, `docker-compose.yml` | start-up refused without them (tested) |
| **Sensitive logging** | Logs hold metadata only (model, latency, kinds of redacted secrets), never prompts, messages, tokens or passwords; error details from the DB/AI aren't returned to users (fixed 503 messages) | `ai/service.py`, `api/errors.py` | `test_rag.py` (internal host not leaked) |
| **Containers** | Backend runs as a non-root user; ports published only on 127.0.0.1; Ollama not published; required secrets | Dockerfiles, `docker-compose.yml` | `docker compose ps` |
| **Dependencies** | `pip-audit` and `npm audit` in CI | `.github/workflows/ci.yml` | 0 known vulnerabilities (25 Sept 2026) |
| **Static checks** | `ruff` with security rules (bandit `S`) and bug rules (`B`) | `backend/ruff.toml` | all checks pass |

## Fixed in the security review

| Problem found | Risk | Fix |
|---|---|---|
| No rate limiting on login/register | Password guessing, mass sign-ups | Redis fixed-window limiter (tested) |
| Upload size checked only after reading the whole file | A huge upload could exhaust memory | Read in 1 MB pieces, stop at the limit, 413 |
| Upload endpoint was `async def` with blocking DB calls | Blocked the whole server during uploads | Normal `def` (runs in a thread pool) |
| No Content-Security-Policy on the frontend | Injected scripts from other sites could run | Strict CSP in nginx (app verified working) |

## Known limits (accepted, documented)

| Limit | Why it's accepted for now | What production would add |
|---|---|---|
| Access tokens can't be revoked before they expire (≤ 15 min) | Stateless JWTs; deactivation is still immediate because every request checks the user | A Redis denylist of token ids |
| No reuse detection for stolen refresh tokens | Simplicity; each token still works only once | Token "families": revoke the whole login if an old token is reused |
| `/metrics` has no login | Standard for Prometheus; only published on 127.0.0.1 | Block it at the reverse proxy |
| Registration says "email already registered" (409) | Clear for users; rate limiting slows probing | Send a "check your email" message instead |
| Redaction and injection guard are pattern-based | They catch common shapes, not every trick | More patterns, a classifier model, human review of flagged tickets |
| No HTTPS locally | It's localhost | TLS at the load balancer / reverse proxy (see deployment.md) |
| No email verification or password reset | Out of scope | Signed, expiring email links |

## How an AI agent is stopped from unauthorized actions

1. The model never gets database access, only a list of tools. **It asks; code acts.**
2. Tools have **no id arguments**: the ticket is fixed by the server when the run starts, and unexpected arguments are refused.
3. Each tool's arguments are **validated** (fixed team names, only IN_PROGRESS/WAITING_FOR_CUSTOMER statuses).
4. Tools call the **same services as the API**, as the **staff member who started the run**: the normal role and ticket rules apply.
5. Each write tool works **once** per run; at most 6 turns / 8 calls; RESOLVED and CLOSED are impossible.
6. If the ticket looks like an injection attempt, write tools aren't offered at all (**read-only**).
7. Every request, allowed or blocked, is **logged** in `ai_interactions`, and nothing is sent to customers without a person.
