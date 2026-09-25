# Migrations

Database changes are made with **Alembic**. Each change is a small Python file in
`backend/migrations/versions/`, with an `upgrade()` (apply) and a `downgrade()` (undo).

**Rule: never change the database by hand.** Every change is a migration, so every database
(your laptop, the tests, production) ends up with exactly the same tables. A test fails if a
model changes without a migration (`test_models_match_migrations`).

## Commands (run in `backend/`)

| Task | Command |
|---|---|
| Apply all migrations | `.venv/bin/alembic upgrade head` |
| Undo the last one | `.venv/bin/alembic downgrade -1` |
| Undo everything | `.venv/bin/alembic downgrade base` |
| Where am I? | `.venv/bin/alembic current` |
| Do the models match the database? | `.venv/bin/alembic check` |
| Make a new migration from model changes | `.venv/bin/alembic revision --autogenerate --rev-id 0002 -m "what changed"` |
| Same, for the test database | add `-x db=test`, e.g. `.venv/bin/alembic -x db=test upgrade head` |

**Always read a generated migration before applying it.** Autogenerate misses some things
(extensions, data, default changes) and sometimes renders things oddly.

## Current state (checked 25 Sept 2026)

| Database | `alembic current` |
|---|---|
| `support` (the app) | `0004 (head)` |
| `support_test` (pytest) | `0004 (head)` |

There is one head (`alembic heads` → `0004`), and `alembic check` says "No new upgrade operations detected", so the models
and the migrations match.

## A clean database from zero

- **Docker:** the `migrate` service runs `alembic upgrade head` on every `docker compose up`, before the API starts. On an
  empty volume it applies 0001 → 0004. By hand: `docker compose run --rm migrate`. Where am I: `docker compose run --rm migrate alembic current`.
- **Manual:** `docker compose up -d postgres`, then in `backend/`: `.venv/bin/alembic upgrade head`.
- **Start over** (deletes all data): `docker compose down -v && docker compose up -d --build`, or
  `.venv/bin/alembic downgrade base && .venv/bin/alembic upgrade head`.
- **Tests:** the test suite migrates `support_test` itself (`test_migrations.py` also applies, undoes and re-applies everything).
- **CI:** runs `alembic upgrade head && alembic check` on a brand-new database on every push.

## Migration log

| Revision | What it does |
|---|---|
| `0001` | The whole starting schema |
| `0002` | Let the system (background jobs) escalate tickets and change status |
| `0003` | New `ai_interactions` table: every AI answer about a ticket |
| `0004` | Knowledge base: documents, chunks with `vector(768)` embeddings, HNSW index |

### 0001: initial schema

**File:** `migrations/versions/0001_initial_schema.py`

**Creates:** the `pgvector` extension and 8 tables: `users`, `refresh_tokens`, `teams`, `team_members`,
`tickets`, `ticket_messages`, `ticket_status_history`, `ticket_escalations` (details in [database.md](database.md)).

Generated with `--autogenerate`, then the `CREATE EXTENSION vector` line was added by hand.

**Apply:** `.venv/bin/alembic upgrade head` → `Running upgrade  -> 0001, initial schema`

**Undo:** `.venv/bin/alembic downgrade base`. Drops all tables and the extension. **This deletes all data.**
Back up first if it matters: `docker compose exec postgres pg_dump -U support -d support > backup.sql`

**Tested:** applied → 8 tables + pgvector → `alembic check` clean → undone (0 tables left) → applied again.

## History note

The project first had 4 migrations. While simplifying the design (before any real data existed),
they were replaced by this single clean migration. Both databases were rolled back to empty first,
then the old files were removed.
Once a project has real data, you **never** rewrite old migrations: you always add a new one.

### 0002: allow system actions in ticket history

**File:** `migrations/versions/0002_allow_system_actions_in_ticket_history.py`

**What changed:** `ticket_escalations.raised_by_id` and `ticket_status_history.changed_by_id` can now be
**NULL**. NULL means "done automatically by the system", e.g. the SLA check escalating an overdue ticket.

**Apply:** `.venv/bin/alembic upgrade head` → `Running upgrade 0001 -> 0002, …`

**Undo:** `.venv/bin/alembic downgrade 0001`. If any history rows were made by the system, the downgrade
**stops on purpose** with "N history rows were made by the system…", because those rows have no person
to put back. Delete or fix those rows first.

**Tested:** applied; `alembic check` clean; with a system-made escalation present, the downgrade stopped
with the message and stayed at 0002; after removing the row, downgrade and upgrade both worked.

### 0003: ai interactions

**File:** `migrations/versions/0003_ai_interactions.py`

**What changed:** new table `ai_interactions` (one row per AI call about a ticket), with an index on
`ticket_id` and a CHECK on `status` (`OK`, `INVALID_OUTPUT`, `UNAVAILABLE`). Deleting a ticket deletes its rows.

**Apply:** `.venv/bin/alembic upgrade head` → `Running upgrade 0002 -> 0003, ai interactions`
**Undo:** `.venv/bin/alembic downgrade 0002`. Drops the table, so **all saved AI answers are lost** (tickets are not affected).
**Tested:** applied → undone → applied again; `alembic check` clean.

### 0004: knowledge base

**File:** `migrations/versions/0004_knowledge_base.py`

**What changed:** two new tables. `knowledge_documents` stores uploaded documents (cleaned text, status, uploader).
`knowledge_chunks` stores pieces of each document with an `embedding vector(768)` column. There's also an
**HNSW index** on `embedding` (`vector_cosine_ops`, m=16, ef_construction=64) for fast similarity search.

**Review note:** the autogenerated draft used pgvector's type as `pgvector.sqlalchemy.vector.VECTOR(dim=768)`
**without importing pgvector**, so it would have crashed with a NameError. The import was added, and 768 is
written as a plain number (migrations shouldn't import app code).

**Apply:** `.venv/bin/alembic upgrade head` → `Running upgrade 0003 -> 0004, knowledge base`
**Undo:** `.venv/bin/alembic downgrade 0003`. Drops both tables, so **the knowledge base is lost** (re-load it with `load-knowledge`).
**Tested:** applied; the index is `USING hnsw (embedding vector_cosine_ops)`; the column is `vector(768)`;
undone and applied again; `alembic check` clean.
