# Final checklist

Every item was checked on **25 Sept 2026**, on the running Docker stack or on a **fresh copy** of the project
(new `.env` from `.env.example`, new secrets, empty volumes; see [setup.md](setup.md#verified-on-a-clean-copy-25-sept-2026)).
An item is ticked only if it was actually run and seen working.

| # | Item | ✓ | How it was checked |
|---|---|:-:|---|
| 1 | **The application runs** | ✅ | `docker compose up -d --build`: 9 services up, `api` healthy; fresh copy the same |
| 2 | **Database** | ✅ | `/health/ready` → database ok; 11 tables; pgvector `vector(768)` column with HNSW index |
| 3 | **Migrations** | ✅ | Fresh empty DB: `migrate` ran 0001 → 0004 and exited 0; `alembic current` = `0004 (head)` on app and test DBs; `alembic check` clean; `test_migrations.py` applies, undoes and re-applies all |
| 4 | **Authentication** | ✅ | Sign-up 201 (always CUSTOMER), duplicate 409, extra `role` field 422, login 200, wrong password 401, no token 401; 11th login in a minute → 429 `Retry-After: 60` |
| 5 | **RBAC** | ✅ | Customer on `/teams` → 403, on `/tickets/{id}/ai` → 403; customer can't resolve (403); invisible/unknown ticket → 404; 7 protections mutation-tested |
| 6 | **Tickets** | ✅ | Create, route, resolve by staff; escalating a RESOLVED ticket → 409; UI re-checked today in headless Chromium (admin: queue, ticket page with AI panel, deep-link reload, no page errors); every role was checked the same way when the frontend was built |
| 7 | **AI (triage)** | ✅ | Real model on the fresh stack: billing ticket → BILLING, routed to Billing Team in ~24 s; decision saved in `/ai`; eval: 93.8% on held-out tickets |
| 8 | **RAG** | ✅ | `ask` answered "valid for 1 hour" with sources; off-topic question → "I don't know" (no source); suggest-reply cited the refund policy; 8 documents READY; eval: retrieval 100%, answers 86% |
| 9 | **AI agent** | ✅ | Agent run via Celery finished in ~44 s (2 tool calls, assigned team); 409 on a resolved ticket; eval: 12/15 scenarios, 0 forbidden changes in 37 runs |
| 10 | **Escalation** | ✅ | Hacked-account ticket → SECURITY/CRITICAL, Security Team, ESCALATED automatically; manual escalation and SLA escalation covered by tests (`test_sla.py`, `test_tickets.py`) |
| 11 | **Celery** | ✅ | Worker + beat running; `tickets.triage`, `agent.run` and the scheduled `tickets.check_sla` all succeeded (Grafana "Jobs finished", 0 failed); document processing covered by `test_rag.py` |
| 12 | **Docker** | ✅ | Fresh copy from zero; only 127.0.0.1 ports; required secrets enforced; frontend deep-link reload works; CSP header present |
| 13 | **Tests** | ✅ | Backend **251 passed, 3 skipped**; frontend **11 passed**; ruff and oxlint clean; `npm run build` ok; pip-audit and npm audit: 0 vulnerabilities |
| 14 | **Monitoring** | ✅ | Prometheus targets `api` and `worker` up; Grafana login with `.env` password; dashboard provisioned, 14 panels, 0 "No data" |
| 15 | **Documentation** | ✅ | All 34 endpoints documented in api.md; every setting in `.env.example`; all internal links and anchors resolve (script check); no stale "next"/"later" notes |
| 16 | **README** | ✅ | Results, stack, run steps, features, structure, finished roadmap, doc index; test counts match the real run |
| 17 | **Interview preparation** | ✅ | 2- and 5-minute explanations, architecture, technology choices, 62 Q&As, challenges, trade-offs, future improvements; numbers match the evaluation reports |

## Not checked (and why)

| Item | Why |
|---|---|
| CI on GitHub | The project isn't pushed yet. Every CI command was run locally and passes |
| AWS deployment | Not deployed on purpose (costs money). `deployment.md` is a plan; prices are rough, not checked live |
| `pip-audit -r requirements.txt` exactly as in CI | Fails on this machine (no `ensurepip`); the installed environment was audited instead (same pinned packages) |
| Downloading the models inside a brand-new Ollama container | The fresh test reused the downloaded models; `ollama pull` in the container ran and reported success (already up to date) |
