# Setup on a fresh machine

Two ways to run it:

- **A. Docker (recommended)**: everything in containers, one command. Best for a demo.
- **B. Manual**: only PostgreSQL and Redis in Docker, the app on your machine with hot reload. Best for changing code.

## What it costs

**Nothing.** Everything is free and open source, and the AI runs on your own computer. There are no API keys and no accounts.

| Thing | Cost | Note |
|---|---|---|
| Docker, Python, Node.js, Ollama, the models | free | open source / free downloads |
| PostgreSQL, Redis, Prometheus, Grafana images | free | Docker Hub |
| GitHub Actions CI | free on public repositories | private repositories get a free monthly allowance of minutes |
| AWS deployment | **costs money** | optional, see [deployment.md](deployment.md) |

## What you need

| Tool | Check | Needed for |
|---|---|---|
| Docker + Compose v2 | `docker compose version` | both ways |
| ~10 GB free disk | | models (5 GB) + images |
| **8 GB+ free RAM** | | the 7B model needs about 6 GB. Less? Use `qwen2.5:3b` (see "Models") |
| Python 3.12 with `venv` | `python3 --version` | way B only |
| Node.js 20.19+ | `node --version` | way B only |

No GPU needed. On a CPU, one AI answer takes 5–60 seconds.

## 1. Settings file (both ways)

```bash
cp .env.example .env
```

Put your own random values in these **three** variables. Make each one with
`python3 -c "import secrets; print(secrets.token_urlsafe(32))"`:

| Variable | What it is |
|---|---|
| `POSTGRES_PASSWORD` | Database password |
| `JWT_SECRET_KEY` | Signs login tokens (32+ characters) |
| `GRAFANA_ADMIN_PASSWORD` | Grafana `admin` login (Docker only) |

Everything else has working defaults, explained line by line in `.env.example`. `.env` is git-ignored: never commit it.
If port 8080 is taken on your machine, also set `FRONTEND_PORT` (e.g. `3080`).

## A. Docker

```bash
docker compose up -d --build                  # first build: a few minutes
docker compose ps                             # wait until api and postgres say (healthy)
```

### Models (once, about 5 GB)

The Ollama container keeps its models in the project folder `.ollama/models` (git-ignored), so they survive rebuilds.

```bash
docker compose exec ollama ollama pull qwen2.5:7b          # chat model, 4.7 GB
docker compose exec ollama ollama pull nomic-embed-text    # embeddings, 274 MB
curl localhost:8000/health/ai                              # "status":"ok"
```

Short on memory? Pull `qwen2.5:3b` instead and set `OLLAMA_CHAT_MODEL=qwen2.5:3b` in `.env`, then
`docker compose up -d` again. It is less accurate (the evaluation numbers are for 7B).

### Data (once)

```bash
docker compose exec worker python -m app.cli seed-teams                   # the 5 teams AI triage routes to
docker compose exec worker python -m app.cli load-knowledge /knowledge-base   # help articles for RAG
docker compose exec worker python -m app.cli create-admin --email you@example.com --name "You"   # asks for a password
```

The database tables were already created by the `migrate` service (`alembic upgrade head`) before the API started.

### Open

| What | Address |
|---|---|
| App | http://localhost:8080 (or your `FRONTEND_PORT`) |
| API docs | http://localhost:8000/docs |
| Grafana | http://localhost:3002, user `admin`, password = `GRAFANA_ADMIN_PASSWORD` |
| Prometheus | http://localhost:9090 |

Sign up in the app to get a customer account. Make staff accounts: log in as the admin → **Admin** page → change a user's role,
and add them to a team. More in [docker.md](docker.md).

## B. Manual (for development)

```bash
docker compose up -d postgres redis
```

### Backend

```bash
cd backend
python3 -m venv .venv                        # "ensurepip is not available"? see troubleshooting.md
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/alembic upgrade head               # creates the tables
.venv/bin/python -m app.cli create-admin --email you@example.com --name "You"
.venv/bin/python -m app.cli seed-teams
.venv/bin/uvicorn app.main:app --reload --port 8000
```

Background worker, in a second terminal (in `backend/`):

```bash
.venv/bin/celery -A app.workers.celery_app worker --beat --pool=threads --concurrency=2 --loglevel=info
```

### Ollama, inside the project

Ollama lives in `.ollama/` (git-ignored), so nothing is installed system-wide and deleting the folder removes it.

```bash
mkdir -p .ollama/program .ollama/models .ollama/home
curl -fsSL -o .ollama/ollama.tar.zst https://ollama.com/download/ollama-linux-amd64.tar.zst
tar --zstd -xf .ollama/ollama.tar.zst -C .ollama/program && rm .ollama/ollama.tar.zst

scripts/ollama.sh serve                      # third terminal, keep it open
scripts/ollama.sh pull qwen2.5:7b
scripts/ollama.sh pull nomic-embed-text
```

Then load the help articles: `cd backend && .venv/bin/python -m app.cli load-knowledge ../knowledge-base`.
The Docker setup reuses the same `.ollama/models` folder, so the models are downloaded only once.

### Frontend

```bash
cd frontend
npm install
npm run dev                                  # http://localhost:5173
```

## Check that it works

| Check | Expected |
|---|---|
| `curl localhost:8000/health/ready` | `{"status":"ok","checks":{"database":"ok","redis":"ok"}}` |
| `curl localhost:8000/health/ai` | `"status":"ok"` and both models `true` |
| Raise a ticket in the app, wait ~20 s, open it as staff | category, priority and team filled in by the AI |
| `cd backend && .venv/bin/pytest` (way B) | **251 passed, 3 skipped** (the 3 live-AI tests are off by default) |
| `cd frontend && npm test` | **11 passed** |

## Ports

| Service | Host port | Note |
|---|---|---|
| Frontend (Docker) | 8080 (`FRONTEND_PORT`) | |
| Frontend (dev server) | 5173 | |
| API | 8000 | |
| PostgreSQL | 5433 | not 5432, in case another PostgreSQL uses it |
| Redis | 6380 | not 6379, same reason |
| Ollama | 11434 (manual only) | the Docker one isn't published |
| Prometheus / Grafana | 9090 / 3002 | Docker only |

All published ports listen on 127.0.0.1 only.

## Remove everything

```bash
docker compose down -v            # containers and all data
rm -rf .ollama backend/.venv frontend/node_modules
```

## Verified on a clean copy (25 Sept 2026)

This guide (way A) was followed on a fresh copy of the project: no `.venv`, no `node_modules`, no `.env`, empty Docker volumes,
a new `.env` made from `.env.example` with new random secrets. Only the already-downloaded models were reused.

| Step | Result |
|---|---|
| `docker compose up -d --build` | all 9 services up; `migrate` ran 0001 → 0004 on the empty database and exited 0 |
| `seed-teams`, `load-knowledge`, `create-admin` | 5 teams; 8 documents READY; admin created |
| Smoke test (23 API checks) | all passed: sign-up/login/roles/404/409 rules; AI triage routed a billing ticket in ~24 s; a hacked-account ticket was escalated to the Security Team; suggest-reply and ask answered with sources; an off-topic question got "I don't know"; the agent finished in ~44 s |
| Limits | 11th login in a minute → 429 with `Retry-After: 60`; 6 MB upload → 413; fake PDF → 400 |
| Frontend, Grafana, Prometheus | app and deep links load, CSP header present; Grafana login works, dashboard provisioned; both Prometheus targets up with data |
