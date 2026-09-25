# Docker

The whole system runs with **one command**. `docker-compose.yml` is at the project root, and Compose reads the root `.env`.

```bash
docker compose up -d --build     # everything (first build: a few minutes)
docker compose ps                # status of every service
docker compose logs -f worker    # follow one service's logs
docker compose down              # stop (data stays in the volumes)
docker compose down -v           # stop AND delete all data (database, Grafana, Prometheus)
```

After the first start, create the data (once):

```bash
docker compose exec worker python -m app.cli seed-teams
docker compose exec worker python -m app.cli load-knowledge /knowledge-base
docker compose exec worker python -m app.cli create-admin --email you@example.com --name "You"
```

## The services

| Service | Image | Host address | What it does |
|---|---|---|---|
| `postgres` | `pgvector/pgvector:pg17` | 127.0.0.1:5433 | Database, with pgvector |
| `redis` | `redis:7-alpine` | 127.0.0.1:6380 | Celery job queue |
| `ollama` | `ollama/ollama:0.34.4` | **not published** | The local LLM. Reuses the models in `./.ollama/models` (no second download). Memory limit 10 GB |
| `migrate` | `ai-support-backend` (built) | – | Runs `alembic upgrade head` **once**, then exits |
| `api` | `ai-support-backend` | 127.0.0.1:8000 | FastAPI. Starts only **after `migrate` succeeded** |
| `worker` | `ai-support-backend` | – (metrics on 9808 inside) | Celery worker **+ beat** (one process, `--pool=threads`) |
| `frontend` | `ai-support-frontend` (built) | 127.0.0.1:`FRONTEND_PORT` (8080) | React app served by nginx |
| `prometheus` | `prom/prometheus:v3.5.0` | 127.0.0.1:9090 | Collects metrics from `api` and `worker` |
| `grafana` | `grafana/grafana:12.1.1` | 127.0.0.1:3002 | Dashboards (user `admin`, password `GRAFANA_ADMIN_PASSWORD`) |

## How the containers talk to each other

```
browser ──► frontend (nginx, :80 → host FRONTEND_PORT)      static files only
browser ──► api (:8000)                                     the React app calls the API directly
api / worker ──► postgres:5432, redis:6379, ollama:11434    by service name, on the private "backend" network
worker  ──► redis (takes jobs)   api ──► redis (puts jobs)
prometheus ──► api:8000/metrics, worker:9808                every 15 s
grafana ──► prometheus:9090                                 data source, set up automatically
```

- Inside Docker, services find each other by **name** (Docker's built-in DNS). That's why `docker-compose.yml`
  overrides `POSTGRES_HOST=postgres`, `REDIS_HOST=redis`, `OLLAMA_BASE_URL=http://ollama:11434` for the backend.
- Only the ports in the table are published, and **only on 127.0.0.1**, so nothing is reachable from other machines.
  Ollama isn't published at all.
- The frontend's JavaScript runs in the **browser**, so it calls the API at `http://localhost:8000` (baked in at build time).

## The images

**Backend** (`backend/Dockerfile`, 245 MB): `python:3.12-slim`; dependencies installed in their own layer (cached
until `requirements.txt` changes); runs as a **non-root user**. The same image runs the API, the worker and `migrate`,
with a different command each.

**Frontend** (`frontend/Dockerfile`, 49 MB): **two stages**. Node builds the React app, then only the built files are copied
into a small `nginx` image. Node isn't in the final image. `nginx.conf` sends unknown paths to `index.html` (so
`/tickets/123` works on reload), caches hashed assets for a year, and adds basic security headers.

## Design choices

| Choice | Why |
|---|---|
| `migrate` as its own one-off service | The schema is always up to date before the API starts, and only one process runs migrations (not every API copy) |
| `depends_on` with `condition: service_healthy` | Services wait until their dependencies are actually ready, not just started |
| One worker with `--beat` | Beat must run exactly once, or every scheduled job runs twice. To scale, add worker copies **without** `--beat` |
| `--pool=threads` for the worker | One process, so the in-memory metrics are complete; the jobs mostly wait on Ollama/the database |
| Ollama models mounted from `./.ollama/models` | No second 5 GB download; the dev setup and Docker share the same files |
| Required secrets (`POSTGRES_PASSWORD`, `JWT_SECRET_KEY`, `GRAFANA_ADMIN_PASSWORD`) | Compose refuses to start without them, instead of starting with empty passwords |
| Named volumes | Data survives `docker compose down` and image rebuilds |

## Development without Docker for the app

For fast code changes, run only the databases in Docker and the app on your machine (hot reload):

```bash
docker compose up -d postgres redis
# then backend, worker, frontend and Ollama as in docs/setup.md
```

## Verified (25 Sept 2026)

- `docker compose up -d --build`: all 9 services up; `migrate` exited 0; `api` and `ollama` healthy.
- In Docker: a new ticket was triaged by the worker using the Ollama container (21 s, routed to Billing), `suggest-reply` answered
  from the knowledge base with sources, the agent ran through Celery (43 s), a security ticket was auto-escalated.
- Prometheus targets `api` and `worker` both **up**; the Grafana dashboard shows data in all 14 panels.
- The frontend on `FRONTEND_PORT` works, including reloading a deep link like `/tickets/<id>`.
