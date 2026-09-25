# AI-Powered Customer Support & Agentic Ticketing System

A help-desk system where customers raise support tickets and a support team solves them, with AI helping along the way.
The AI runs on your own computer using [Ollama](https://ollama.com), so it is free and needs no API key.

## What it does

- **Customers** create tickets and chat with the support team.
- **Support agents** work on tickets for their team. **Managers** see everything and handle escalations.
  **Admins** manage users, teams and help documents.
- **The AI sorts new tickets.** It guesses the category (billing, login, security…) and the priority, and the ticket goes
  to the right team. If the AI is unsure, it changes nothing and a person decides.
- **The AI answers from help documents.** Staff can ask a question or get a suggested reply. The answer only uses the
  company's help articles and shows which article it came from. If the articles don't cover it, it says "I don't know".
- **The AI agent can work on a ticket.** It searches the help articles, reads the ticket history, sends the ticket to a
  team, escalates it if needed, and writes a draft reply. It can only do what the staff member who started it is
  allowed to do, and it never sends anything to a customer by itself.
- **Overdue tickets are escalated automatically** by a background job.
- **Security and critical tickets** (for example "my account was hacked") are escalated automatically.

## Results

I tested the AI with the real model, running on a CPU only (no GPU):

| Test | Result |
|---|---|
| Ticket category correct (16 tickets not used while building) | 94% (15 of 16) |
| Help-document answers: right article found | 100% |
| Help-document answers: correct answer | 86% |
| Said "I don't know" when it should | 5 of 6 |
| AI agent: handled the scenario fully right | 12 of 15 |
| AI agent: did something it was not allowed to do | 0 times in 37 runs |

There are also 251 backend tests and 11 frontend tests.

## Tech stack

| Part | Tools |
|---|---|
| Backend | Python, FastAPI, SQLAlchemy, Alembic |
| Database | PostgreSQL with pgvector (for AI search) |
| AI | Ollama, `qwen2.5:7b` model, `nomic-embed-text` for search |
| Background jobs | Celery and Redis |
| Login | JWT tokens, roles, password hashing, rate limiting |
| Frontend | React, TypeScript, Vite |
| Running it | Docker Compose |
| Monitoring | Prometheus and Grafana |
| Checks | pytest, Vitest, GitHub Actions |

## How to run it

You need Docker, about 10 GB of free disk space and at least 8 GB of free memory.

**1. Create your settings file**

```bash
cp .env.example .env
```

Open `.env` and set `POSTGRES_PASSWORD`, `JWT_SECRET_KEY` and `GRAFANA_ADMIN_PASSWORD` to your own random values.
You can make one with:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

**2. Start everything**

```bash
docker compose up -d --build
```

**3. Download the AI models (only once, about 5 GB)**

```bash
docker compose exec ollama ollama pull qwen2.5:7b
docker compose exec ollama ollama pull nomic-embed-text
```

**4. Add the starting data**

```bash
docker compose exec worker python -m app.cli seed-teams
docker compose exec worker python -m app.cli load-knowledge /knowledge-base
docker compose exec worker python -m app.cli create-admin --email you@example.com --name "Your Name"
```

**5. Open it**

| What | Address |
|---|---|
| The app | http://localhost:8080 |
| API documentation | http://localhost:8000/docs |
| Grafana dashboard | http://localhost:3002 (user `admin`) |

Sign up in the app to get a customer account. Log in as the admin to make other users support staff.

To stop it: `docker compose down`. To stop it and delete all data: `docker compose down -v`.

More detail, including how to run it without Docker: [docs/setup.md](docs/setup.md).

## Try it

1. Sign up as a customer and create a ticket such as "I was charged twice this month".
2. Wait about 20 seconds, then open it as the admin. The category, priority and team are filled in.
3. Click **Suggest a reply** to see an answer with its source article.
4. Click **Let the AI agent work it** and watch each step it takes.
5. Create a ticket saying "someone hacked my account" and see it escalated automatically.
6. Open Grafana to see requests, AI calls and tickets on the dashboard.

## How it works

```
Browser ──► React app ──► FastAPI ──► PostgreSQL + pgvector
                             │
                             └──► Redis ──► Celery worker ──► Ollama (local AI)
```

- The API saves a ticket straight away and puts the AI work in a queue, so nobody waits for the AI.
- A background worker asks the AI about the ticket. **The AI only suggests; the code decides.** Normal code checks the
  answer before anything changes.
- Help articles are cut into small pieces and stored as vectors in PostgreSQL, so the AI can find the right piece for a question.
- Passwords, tokens and card numbers are removed from any text before it is sent to the AI.

## Project layout

```
backend/          FastAPI app, database migrations, tests, AI evaluations
frontend/         React app
knowledge-base/   sample help articles
infrastructure/   Prometheus and Grafana settings
docs/             documentation
docker-compose.yml
```

## Documentation

| Doc | About |
|---|---|
| [Setup](docs/setup.md) | Install and run, step by step |
| [Architecture](docs/architecture.md) | How the parts fit together, roles and ticket rules |
| [API](docs/api.md) | Every endpoint with examples |
| [Database](docs/database.md) and [Migrations](docs/migrations.md) | Tables and schema changes |
| [Authentication](docs/authentication.md) and [Security](docs/security.md) | Login, tokens, roles, security checks |
| [AI](docs/ai.md), [RAG](docs/rag.md) and [Agent](docs/agentic-workflow.md) | How the AI parts work and how they were tested |
| [Background jobs](docs/celery.md), [Docker](docs/docker.md) and [Monitoring](docs/monitoring.md) | Celery, containers, metrics |
| [Frontend](docs/frontend.md) and [Testing](docs/testing.md) | The React app and the tests |
| [Deployment](docs/deployment.md) | Optional AWS setup and its costs |
| [Troubleshooting](docs/troubleshooting.md) | Common problems and fixes |
| [Interview preparation](docs/interview-preparation.md) | Short explanations and common questions about the project |
| [Final checklist](docs/final-checklist.md) | What was checked before release, and how |
| [Changelog](CHANGELOG.md) | What changed in each version |

## Cost

Running it on your own computer is free. Everything used is open source, and there are no paid APIs.
Only the optional AWS deployment costs money (see [docs/deployment.md](docs/deployment.md)).
