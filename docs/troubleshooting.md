# Troubleshooting

Each entry: **what you see → why → how to fix**.

## Setup

**`python3 -m venv .venv` fails: "ensurepip is not available"**
Ubuntu is missing the `python3.12-venv` package.
Fix with sudo: `sudo apt install python3.12-venv`. Without sudo:

```bash
python3 -m venv --without-pip .venv
curl -fsSL -o /tmp/get-pip.py https://bootstrap.pypa.io/get-pip.py
.venv/bin/python /tmp/get-pip.py
```

**Backend won't start: `postgres_password Field required` or `jwt_secret_key …`**
A required secret is missing from `.env`. There are no defaults on purpose. Add it (see setup.md), then restart.

**`docker compose up` says "set POSTGRES_PASSWORD in .env"**
Same cause: add `POSTGRES_PASSWORD` to `.env`.

**"port is already allocated" / "Address already in use"**
Something else uses the port. Change `POSTGRES_PORT` / `REDIS_PORT` in `.env`, or stop the other
program (`lsof -i :8000` shows it).

## Database

**`/health/ready` returns 503**
PostgreSQL isn't reachable. Run `docker compose ps` (it should be "healthy"), then `docker compose up -d`.

**`password authentication failed` after changing `POSTGRES_PASSWORD`**
PostgreSQL only reads the password the **first** time its data volume is created.
Keep your data: `docker compose exec postgres psql -U support -d support -c "ALTER USER support PASSWORD 'new';"`
Or start fresh (**deletes all data**): `docker compose down -v && docker compose up -d`.

**Tests say "skipped: Test database not reachable"**
Docker isn't running. Run `docker compose up -d`.

**`test_models_match_migrations` fails: "New upgrade operations detected"**
A model changed without a migration. Create one: `.venv/bin/alembic revision --autogenerate --rev-id 0002 -m "what changed"`,
read it, then run `alembic upgrade head`.

## Login

**Every request says 401 "Invalid or expired token"**
The access token expired (after 15 min) or `JWT_SECRET_KEY` changed. Log in again, or call `/api/v1/auth/refresh`.

**`/auth/refresh` always says "Please log in again"**
- The cookie is only sent to `/api/v1/auth/...`, and only over HTTPS or `localhost`.
- From the frontend, Axios must use `withCredentials: true`.
- From curl, keep a cookie jar: `-c jar.txt` on login, `-b jar.txt -c jar.txt` on refresh.
- Each refresh token works **once**. Reusing an old one fails. That's on purpose.

**Register gives 422 for `me@company.test` or `me@localhost`**
Those domains are reserved. Use a normal-looking one, like `@example.com`.

## Tickets

**A ticket returns 404, but it exists**
You're not allowed to see it (that's on purpose). Agents only see tickets in their teams or assigned to them.
Fix: assign the ticket to the agent's team, or add the agent to the team.

**Status change: 409 or 403?**
409 = that move doesn't exist (e.g. from CLOSED). 403 = the move exists, but not for your role
(e.g. an agent taking a ticket out of ESCALATED). See the rules in [architecture.md](architecture.md#ticket-status-rules).

**Assign returns 400 "Assignee is not a member of this team"**
Add the person to the team first (`POST /api/v1/teams/{id}/members`).

**Adding a team member returns 400 "Only active support staff can join a team"**
The user is a CUSTOMER. An admin must change their role first.

## Background jobs (Celery)

**Worker says `Cannot connect to redis://localhost:6380/0`**
Redis isn't running: `docker compose up -d`. Check `REDIS_HOST` / `REDIS_PORT` in `.env`.

**The SLA check never runs**
Beat isn't running. Start the worker **with `--beat`** (or a separate `celery … beat` process).
The first run happens after `SLA_CHECK_INTERVAL_SECONDS` (default 5 minutes).

**Jobs run twice**
Two beat processes are running (e.g. two workers both started with `--beat`). Run beat only once.

**Stopping a worker**
Press Ctrl+C once and wait: it finishes the current job first ("warm shutdown").

**`alembic downgrade` below 0002 says "history rows were made by the system"**
That's the safety check: system-made escalations have no person to put back. Delete those rows first
if you really want to go back.

## AI (Ollama)

**New tickets never get a category or team**
Check in order: (1) the Celery worker is running; (2) Ollama is running (`/health/ai`);
(3) `AI_TRIAGE_ENABLED=true`; (4) look at `GET /api/v1/tickets/{id}/ai`: the `decision` says why
(e.g. "confidence 0.55 is below 0.70" or "no active team named 'Account Support'"; for the latter, run `python -m app.cli seed-teams`).

**`ai_interactions` shows INVALID_OUTPUT often**
The model's JSON failed validation twice. Check the `error` column; a smaller model (3B) does this more.


**`/health/ai` says "Cannot reach Ollama"**
Start it: `scripts/ollama.sh serve`. Check it: `curl localhost:11434/api/version`.

**`/health/ai` says "Model not downloaded"**
`scripts/ollama.sh pull qwen2.5:7b` and `scripts/ollama.sh pull nomic-embed-text`.

**AI calls time out**
The first call loads the model (can take 30 s on a CPU). Raise `AI_TIMEOUT_SECONDS`, or use `qwen2.5:3b`.

**Ollama crashes**
Probably out of memory (`free -h`). Use `qwen2.5:3b` or lower `OLLAMA_NUM_CTX` to 4096.

## Knowledge base (RAG)

**A document stays PROCESSING**
No worker picked it up. Start the Celery worker (it will process queued documents), or load documents with
`python -m app.cli load-knowledge <folder>`, which embeds them right away without a worker.

**A document is FAILED**
See its `error` in `GET /api/v1/knowledge`. Typical causes: the embedding model isn't pulled
(`scripts/ollama.sh pull nomic-embed-text`), or a changed embedding model with a different vector size (needs a migration).

**Upload returns 400**
Only .md, .txt and .pdf; text files must be UTF-8; PDFs must contain real text (scanned images have none); max `KNOWLEDGE_MAX_UPLOAD_MB`.

**`/ask` always says "I couldn't find this in the knowledge base"**
Check `POST /api/v1/knowledge/search` with the same question: if the best similarity is below `RAG_MIN_SIMILARITY`, no source
reaches the LLM. Either the documents don't cover it, or the cut-off is too high. The RAG evaluation shows good values.

**`/ask` returns 503**
Ollama isn't reachable, or its answer was unusable twice. Check `/health/ai`.

## Frontend

**"Cannot reach the API"**
Is the backend running (`curl localhost:8000/health`)? Does `VITE_API_BASE_URL` in `.env` match?
Restart `npm run dev` after changing `.env`. A "blocked by CORS" error in the browser console means
`CORS_ORIGINS` must include the exact frontend URL.

**The app page is blank or login says "Network Error" (Docker)**
The frontend was built for `http://localhost:8000`. Open the app on the same machine, on `http://localhost:<FRONTEND_PORT>`
(not `127.0.0.1`: the CORS allow-list uses `localhost`).

## Docker

**`port is already allocated` / `address already in use`**
Something else uses that port. For the frontend, set `FRONTEND_PORT=3080` (any free port) in `.env`. For the others, stop the
other program, or change the left side of the `ports:` line in `docker-compose.yml`. Find the user: `ss -ltnp | grep :8080`.

**`required variable POSTGRES_PASSWORD is missing` (or `JWT_SECRET_KEY`, `GRAFANA_ADMIN_PASSWORD`)**
On purpose: Compose refuses to start without secrets. Set them in `.env` ([setup.md](setup.md#1-settings-file-both-ways)).

**`api` never becomes healthy / `migrate` exited with an error**
`docker compose logs migrate api`. Usually the database password in `.env` changed after the database volume was created
(see "Database" above), or the database isn't ready yet: `docker compose up -d` again.

**`no configuration file provided: not found` although `docker-compose.yml` is there**
Docker installed as a **snap** (Ubuntu) can't see folders under `/tmp`. Keep the project under your home folder.

**Code changes don't show up in Docker**
The containers run the built image. Rebuild: `docker compose up -d --build`.

**AI features time out in Docker**
The models aren't in `.ollama/models` yet: `docker compose exec ollama ollama list`, then pull them
([setup.md](setup.md#models-once-about-5-gb)). Also check the memory Docker may use: the 7B model needs ~6 GB.

## Monitoring

**Grafana panels say "No data"**
Metrics appear only after something happened (a request, a ticket, an AI call). Use the app for a minute. Check that both
targets are **UP** at http://localhost:9090/targets.

**Grafana screenshot or print shows empty panels**
Grafana draws panels only when they are scrolled into view. Scroll down, or use a taller window.

**Forgot the Grafana password**
It's `GRAFANA_ADMIN_PASSWORD` in `.env`, used only when Grafana's data volume is first created. After changing it:
`docker compose exec grafana grafana cli admin reset-admin-password <new>`.

## Limits

**Login or sign-up gives 429 "Too many attempts"**
The rate limit (10 logins a minute, 5 sign-ups an hour, per IP). Wait for the time in the `Retry-After` header.
For local testing you can set `RATE_LIMIT_ENABLED=false` in `.env` (never in production).

**Upload gives 413**
The file is bigger than `KNOWLEDGE_MAX_UPLOAD_MB` (5). Split it, or raise the value.
