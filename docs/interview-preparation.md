# Interview preparation

Honest explanations of what this project does, in my own words. Every number here comes from a real run (see the
evaluation sections in [ai.md](ai.md), [rag.md](rag.md) and [agentic-workflow.md](agentic-workflow.md)).

## The 2-minute explanation

> "I built an AI-powered customer support system. Customers raise tickets; support agents work them in teams;
> managers oversee; admins manage users, teams and the help documents.
>
> The backend is FastAPI with PostgreSQL, JWT login and four roles. The AI runs **locally and for free** on Ollama,
> with the qwen2.5 7B model. It does three things. First, when a ticket comes in, a Celery background job asks the
> model to classify it (category, priority, confidence), and plain code decides whether to use that answer and
> which team gets the ticket. Second, a RAG knowledge base: help documents are split into chunks, stored as
> embeddings in pgvector, and the model answers questions **only from those sources, with citations**, or says
> 'I don't know'. Third, an AI agent that uses tool calling to work a ticket: it searches the docs, routes,
> escalates and drafts a reply, but every tool request is checked by code and runs with the rights of the person
> who started it.
>
> I measured everything: 94% classification accuracy on unseen tickets, 86% correct RAG answers, and the agent got
> 12 of 15 scenarios fully right with zero forbidden actions. It runs with one `docker compose up`, with Prometheus
> and Grafana for monitoring, 262 automated tests and a GitHub Actions pipeline."

## The 5-minute explanation

Add these to the 2-minute version, in this order:

1. **The problem.** Support teams lose time sorting tickets and answering the same questions. But an AI that acts on
   its own can be wrong or tricked. So my design rule was: **the LLM suggests, code decides, people stay in charge.**
2. **Request flow.** A customer creates a ticket → the API validates it, saves it and returns 201 in milliseconds →
   a job goes on Redis → the Celery worker asks the model → code applies the answer only if it's confident, the ticket
   doesn't look like a prompt injection, and no person has already set it → it routes the ticket and escalates
   security or critical ones → everything is logged in `ai_interactions`.
3. **RAG details.** 800-character chunks with 150 overlap, nomic-embed-text embeddings (768 numbers), HNSW index,
   top 4 chunks above a similarity cut-off. If nothing is similar enough, I don't even call the LLM. The code checks
   that the answer cites sources that really exist.
4. **The agent.** A loop: the model sees the ticket and 6 tools, asks for one, my code validates and runs it, sends the
   result back, up to 6 turns. Tools take no ids, each write works once, it can never resolve or close, and on a
   suspicious ticket it gets only read-only tools.
5. **Evaluation.** I wrote labelled datasets and scripts that score each prompt version. I kept held-out sets I didn't
   tune on. The most interesting lessons: the model's confidence was useless as a signal, and a stronger "you MUST
   escalate" prompt made the model escalate everything.
6. **Engineering.** Alembic migrations only, Docker Compose with 9 services, non-root containers, rate limiting, a strict
   CSP, secrets only in `.env`, redaction before anything reaches the model, and CI that runs lint, migrations, tests and
   dependency audits.
7. **What I'd do next.** Move part of the escalation decision into code, add hybrid search, and deploy it on AWS.

## Architecture

```
Browser ──► frontend (React, nginx) 
   └──────► api (FastAPI) ──► PostgreSQL + pgvector
               │     └──────► Redis ──► worker (Celery + beat) ──► Ollama (qwen2.5:7b, nomic-embed-text)
               └────────────────────────────────────────────────► Ollama (suggest-reply, ask)
Prometheus ──► api /metrics + worker ──► Grafana
```

Inside the backend, **a request goes route → service → database**. Routes handle HTTP only; services hold the rules and
know nothing about HTTP; errors become status codes in one file. All LLM calls go through one class, `AIService`.
Details: [architecture.md](architecture.md).

## Why each technology

| Technology | Why I chose it | What I'd consider instead |
|---|---|---|
| FastAPI | Input validation with Pydantic, automatic `/docs`, simple dependency injection for auth | Django (more built in, heavier) |
| PostgreSQL | Reliable, free, enforces rules (unique, foreign keys, CHECK) | MySQL |
| pgvector | Embeddings next to the data: one database, same backups and access rules | Pinecone, Qdrant (for millions of vectors) |
| SQLAlchemy 2 + Alembic | Typed models; every schema change is a reviewed, reversible migration | raw SQL files |
| Celery + Redis | Slow AI work and the SLA timer outside the request; retries; very common in Python jobs | RQ, Dramatiq, AWS SQS |
| Ollama + qwen2.5:7b | Free, private, offline; good at JSON and tool calling for its size | a hosted API (paid) |
| JWT + refresh cookie | Stateless short-lived access token; long-lived token JavaScript can't read | server sessions |
| React + TypeScript + Vite | Types catch mistakes; Vite is fast; the most common frontend stack | Vue, Next.js |
| Docker Compose | The whole system with one command, same on every machine | Kubernetes (overkill here) |
| Prometheus + Grafana | Standard, free, pull-based metrics and dashboards | CloudWatch, Datadog (paid) |

---

## Questions and answers

### The project

**1. What problem does your project solve?**
Support teams spend a lot of time sorting tickets and answering repeated questions. My system sorts and routes tickets
automatically, finds answers in the help documents, and prepares drafts, while people keep the final say.

**2. What was the hardest part?**
Making the AI safe, not making it work. Getting a model to classify tickets took a day. Making sure it can't be tricked,
can't do more than the user could, and can't send made-up answers to customers took much longer, and needed evaluations to prove.

**3. What are you most proud of?**
That I measured things instead of guessing. For example, I found that a prompt I thought was better (agent-v2) actually
made the model escalate almost everything. Without the evaluation I would have shipped it.

**4. Why a local model and not OpenAI?**
It's free, customer data never leaves the machine, and it works offline. The cost is lower quality and slower answers
(5–30 seconds on a CPU), so I designed the system to never trust the model blindly. The provider is behind an interface,
so a hosted model would be one new class.

**5. How big is it?**
33 API endpoints (plus `/metrics`), 11 database tables, 4 migrations, 9 Docker services, 251 backend tests and 11 frontend tests,
and three evaluation sets: 80 labelled tickets, 28 RAG questions and 15 agent scenarios.

### Backend, PostgreSQL and Alembic

**6. How is the backend organised?**
Routes → services → database. Routes read the input, check the login and role, and call a service. Services hold the rules
and raise normal Python errors; one file maps those errors to HTTP codes. That keeps rules testable without HTTP.

**7. Why did you use sync routes and not async?**
The database driver calls and most work are blocking. FastAPI runs normal `def` routes in a thread pool, which is simple and
correct. I actually found a bug where an upload route was `async def` but did blocking database work, which froze the server during uploads. I changed it to `def`.

**8. What is Alembic and why is it a rule that every change is a migration?**
Alembic is version control for the database schema. Each migration has `upgrade` and `downgrade`. If nobody changes the
database by hand, my laptop, the tests, CI and production all have exactly the same tables. A test and `alembic check` in CI fail
if a model changes without a migration.

**9. Tell me about a migration you had to think about.**
Migration 0002 lets the system (the SLA job) appear in the ticket history with no person, so `changed_by` became nullable.
Its downgrade would break if system rows exist, so the downgrade stops on purpose with a clear message instead of losing data.

**10. What did you learn about autogenerate?**
Always read the file. The autogenerated 0004 used pgvector's type without importing it, so it would have crashed. Earlier it also
created duplicate CHECK constraints for enums, which I fixed by making the constraints explicit.

**11. Tell me about a bug you found.**
Ticket timelines sometimes showed events in the wrong order. PostgreSQL's `now()` is the start time of the **transaction**,
so events saved together had identical times. I switched those columns to `clock_timestamp()`, the real current time.

**12. Why UUIDs and also a ticket number?**
The UUID is the id in the API and can't be guessed. The number (1001, 1002…) is for people to read on the phone.

### Authentication, JWT and RBAC

**13. How does login work?**
The password is checked against an Argon2id hash. The user gets a 15-minute access token (JWT) in the response body and a 7-day
refresh token in an httpOnly cookie. The frontend keeps the access token in memory and sends it in the `Authorization` header.

**14. Why two tokens?**
The access token goes with every request, so it's short-lived: if stolen, it expires soon. The refresh token lives longer, but
JavaScript can't read it, it's only sent to `/api/v1/auth`, and the server can delete it.

**15. What's inside your JWT, and why not the role?**
Only the user id and the times. A JWT is signed, not encrypted, so anyone can read it. And I load the user from the database on
every request, so a role change or deactivation takes effect immediately, not after the token expires.

**16. How do refresh tokens work?**
A random string; only its SHA-256 hash is stored. Each one works once: refresh deletes it with `DELETE … RETURNING` and issues a new one,
so two requests with the same token can't both win. Deactivating a user deletes all their tokens.

**17. What is RBAC in your project?**
Role-based access control. Each user has one of four roles. Each endpoint declares who may call it with
`Depends(require_roles(...))`: no token is 401, wrong role is 403.

**18. Why does a ticket you can't see return 404 instead of 403?**
403 would tell an attacker "this ticket exists". One function builds the visibility condition (customers: own tickets; agents:
their teams' tickets and ones assigned to them; managers and admins: all) and every ticket action goes through it.

**19. How do you stop someone from signing up as admin?**
Sign-up always creates a customer, and the schema rejects unknown fields like `"role"` with 422. The first admin is created from
the command line. After that, only admins change roles, and an admin can't remove their own admin access.

**20. How did you check your access checks actually work?**
Mutation testing by hand: I removed 7 checks one at a time (role check, ticket visibility, internal-note filter, single-use refresh…)
and confirmed a test failed each time. Then I did the same for 6 agent protections.

### Redis and Celery

**21. Why Celery?**
AI calls take seconds to a minute on a CPU. In the request, customers would wait and a few calls could block the API. The API
saves the ticket, puts a job on Redis and answers immediately; the worker does the slow part.

**22. Worker versus beat?**
The worker runs jobs. Beat is a timer that puts scheduled jobs on the queue, like the SLA check every 5 minutes. You can run many
workers, but only one beat, or scheduled jobs run twice.

**23. What does the SLA job do?**
It finds tickets that waited in OPEN longer than their priority allows (from 1 hour for CRITICAL to 72 hours for LOW) and escalates them,
with "system" as the actor. It's safe to run repeatedly because an escalated ticket isn't OPEN any more.

**24. What if a worker crashes mid-job?**
With `acks_late`, Redis only forgets a job after it has finished, so it runs again. That's why jobs must be safe to run twice.

**25. What if Redis is down when a ticket is created?**
The ticket is still created. Queueing uses `retry=False` and the error is caught, so the customer gets 201 and people handle the
ticket without AI. The same idea in the rate limiter: if Redis is down it lets requests through rather than locking everyone out.

**26. Why JSON and not pickle for tasks?**
Pickle can run code when loading, so anyone who can write to Redis could run code on the worker. JSON is only data.

### AI basics and structured output

**27. How do you get reliable output from an LLM?**
I ask for JSON matching a Pydantic model's schema, Ollama constrains the output to it, and I validate it again with Pydantic
(for ranges like confidence 0–1). If it's invalid, I show the model the error and retry once. If it's still invalid, a person decides.

**28. How does triage decide what to apply?**
The model only suggests. Code applies simple rules in order: the ticket must not look like an injection, a person must not have
already set the fields, confidence must be at least 0.7. Then it routes by a fixed category → team table and escalates SECURITY
or CRITICAL tickets. The answer and the decision are saved.

**29. How accurate is the classifier?**
On 64 labelled tickets the first prompt got 81% on category; after studying the mistakes, 94%. On 16 held-out tickets I never
tuned on it got 93.8% (15 of 16), up from 87.5%. Priority is harder: exactly right 62–73% of the time, within one level 94–97%.

**30. What's a held-out set?**
Data you don't look at while improving the prompt. If you tune and score on the same data, you "study for the exam". The
held-out score is the honest one. My held-out gain was only one ticket, and I say that openly.

**31. What was the most surprising result?**
The model's confidence was nearly always 0.8–0.9, and 1.0 on its worst mistake. So the threshold alone can't make automation
safe. I kept it, but the real protection is the other rules, logging, and people.

**32. What is `prompt_version` for?**
Every AI answer is saved with the prompt version that produced it. When I change a prompt I bump the version and re-run the
evaluation, so I compare versions with numbers, and I can trace any old answer to its prompt.

**33. How do you stop secrets reaching the model?**
Every text sent to the model, including embedding input and agent tool results, goes through redaction first: passwords, JWTs,
API keys, card numbers and one-time codes are replaced. It's pattern-based, so it's a safety net, not a guarantee.

### RAG

**34. What is RAG?**
Retrieval-Augmented Generation. The model doesn't know our product's rules and would make them up. So I first search our help
documents for the relevant parts, give only those to the model, and tell it to answer from them and cite them.

**35. Walk me through your RAG pipeline.**
Upload → check the file is really text or PDF → extract and clean → split into ~800-character chunks with 150 overlap → a Celery job
embeds each chunk with nomic-embed-text → stored in a pgvector column with an HNSW index. For a question: embed it, take the 4
nearest chunks by cosine similarity, drop those below 0.55, and send the rest to the model as numbered sources.

**36. What is an embedding?**
A list of numbers (768 here) that represents meaning. Similar meanings give similar vectors, so "money back" finds "refund" even
without shared words. nomic-embed-text also needs `search_document:` and `search_query:` prefixes, which I found in its docs.

**37. Why chunks, and why overlap?**
One vector for a whole document is too blurry, and the whole document is too long for the prompt. Small chunks let search find the
exact paragraph. The overlap means a fact on a boundary isn't cut in half.

**38. How do you prevent hallucination in RAG?**
In layers. No similar chunk → "I don't know" without calling the model. The prompt says: only use sources, else answerable=false.
The answer must cite at least one source, and code checks every citation number exists, rejecting the answer otherwise. And answers
are only suggestions for staff.

**39. How good is it?**
28 questions, 22 answerable and 6 not. The right document was found 100% of the time, 86% of answers had the right facts and source,
and 5 of 6 unanswerable questions got "I don't know". The one hallucination mixed up the attachment limit with the export limit.

**40. Why not only a similarity threshold to detect unanswerable questions?**
I checked: unanswerable questions scored up to 0.67 and real ones as low as 0.58, so the ranges overlap. The threshold removes
clearly unrelated questions; the model's judgement, checked by code, does the rest.

**41. Why pgvector instead of a vector database?**
One system less to run, and embeddings share the database's backups, transactions and access rules. For millions of vectors or
very high query rates, a dedicated vector database could be worth it.

### The agent and tool calling

**42. What makes it agentic?**
It's a loop, not one question. The model sees the ticket and a list of tools, asks for a tool, gets the result, and decides the next
step until it finishes with a summary and a draft reply. The model plans; my code acts.

**43. What is tool calling technically?**
I send the model JSON schemas of functions: name, description, parameters. It can answer with a structured request like
`assign_ticket(team="Billing Team")`. My code runs it and sends the result back as a message with role "tool".

**44. Which tools does it have?**
Three read tools (search the knowledge base, get the ticket history, get basic customer details) and three write tools
(assign to a team, set status to IN_PROGRESS or WAITING_FOR_CUSTOMER, escalate). No tool to reply, resolve, close or delete.

**45. How do you stop it from doing something unauthorized?**
It never touches the database; it only asks. Every request goes through `run_tool()`: the tool must exist, the arguments are
validated with Pydantic (fixed team names, two allowed statuses, no extra fields), and it calls the same services as the API **as the
person who started the run**. Each write works once, and there's a limit of 6 turns and 8 calls.

**46. Why don't the tools take a ticket id?**
Otherwise a prompt injection could say "now assign ticket 1234". The ticket is fixed by my code when the run starts, and an unexpected
`ticket_id` argument is rejected.

**47. Could a customer trick the agent?**
If the ticket text looks like an injection, the run is read-only: write tools aren't even offered, and refused if requested. In a test
where the fake model obeys the attacker, nothing changes. In the real evaluation, across 37 runs, the model made 0 forbidden changes.

**48. How did you evaluate the agent?**
15 realistic scenarios, scoring what it **did**: right team, escalated or not, forbidden changes. agent-v1 got 7 of 11 but never
escalated. v2 added "you MUST escalate" and over-escalated normal tickets. v3 used contrast examples and got 12 of 15.

**49. You found test leakage. What happened?**
A v3 draft used a held-out scenario (a VAT receipt) as an example in the prompt, which would inflate the score. I replaced it and wrote 4 new
held-out scenarios after v3 was final, so its held-out score (5 of 7) is honest.

**50. Why doesn't the agent reply to customers directly?**
With a 7B model and prompt injection possible, a wrong answer reaching a customer is the biggest risk. It drafts; a person reviews the
draft and the sources, and sends it.

### Frontend

**51. How does the frontend handle tokens?**
The access token is kept in memory, not localStorage, so an XSS bug can't simply read it from storage. When a call gets 401,
an Axios interceptor calls refresh once and retries. If several calls fail together, they share one refresh, because a refresh
token works only once. I have a test for exactly that.

**52. Tell me about a frontend bug.**
A race in the reply box: the box was cleared when the send finished, so anything typed while the request was
still running was wiped. I found it while testing in a real browser. Now the box is locked while sending.

### Docker, monitoring and CI

**53. How does Docker Compose run it?**
9 services. A one-off `migrate` service runs `alembic upgrade head`, and the API starts only after it succeeds. Services wait for real
health checks. Ports are published on 127.0.0.1 only; Ollama not at all. The backend image runs as a non-root user.

**54. Why only one worker with beat?**
Beat must run exactly once. To scale, I'd add worker copies without `--beat`.

**55. What do you monitor?**
Requests by route template (so `/tickets/{ticket_id}` is one line, not one per id), error rates, latency percentiles, AI call counts
and latency by kind, RAG answered versus "I don't know", tickets created, escalations by source, Celery task results, and queue length.
Grafana shows it on a 14-panel dashboard that is provisioned automatically.

**56. What does your CI do?**
On every push: ruff lint and format, migrations on an empty database plus `alembic check`, all tests, pip-audit; then the frontend
lint, tests, build and npm audit; then both Docker images are built. I ran every step locally; it hasn't run on GitHub yet.

### Security

**57. What security measures did you add in the review?**
Rate limiting on login (10 a minute) and sign-up (5 an hour) with 429 and `Retry-After`; uploads read in 1 MB pieces with a 5 MB limit
so a huge file can't fill memory; a strict Content-Security-Policy; and ruff's security rules. pip-audit and npm audit found 0 known vulnerabilities.

**58. Known security limits?**
Access tokens can't be revoked before their 15 minutes; no reuse detection for stolen refresh tokens; `/metrics` has no login (only on localhost);
redaction and the injection guard are pattern-based. They're documented in `security.md` with what production would add.

### AWS and scalability

**59. How would you deploy on AWS?**
Cheapest: one EC2 instance with 16 GB RAM running the same Compose file, HTTPS via Caddy, only ports 80/443 open. More managed:
React on S3 + CloudFront, API and worker on EC2 or ECS, RDS PostgreSQL (supports pgvector), ElastiCache Redis, an ALB with an ACM certificate.
The LLM is the expensive part: a CPU instance for the 7B model is roughly $120/month if always on, so for a portfolio I'd start it only for demos.

**60. How would it scale?**
The API is stateless (JWT, no sessions), so I can run more copies behind a load balancer. Workers scale by adding copies. The database scales
with a bigger instance and read replicas. The real bottleneck is the model: one CPU handles one answer at a time, so I'd use a GPU or a
hosted model, and the queue already absorbs bursts.

### Trade-offs, challenges and improvements

**61. What trade-offs did you make?**
Simplicity over features: one role per user instead of permissions tables; pgvector instead of a vector database; stateless JWTs that can't
be revoked early; a local 7B model that is free but slower and less accurate; no automatic replies to customers.

**62. What would you improve?**
See the list below. The first one would be moving part of the agent's escalation decision into code, because the evaluation shows the prompt
alone still misses an outage and a chargeback threat.

## Challenges I solved

| Challenge | What I did |
|---|---|
| The model accepted a prompt injection ("SYSTEM OVERRIDE") | Added a code guard; the agent gets read-only tools on those tickets |
| Model confidence was meaningless | Kept the threshold but relied on code rules, logging and people |
| agent-v2 over-escalated after an emphatic prompt | v3 used contrast examples: escalation decisions 64% → 80% right |
| The agent's read-only mode was always on | The guard matched our own "Priority:" line; now it checks only customer text |
| Events in the wrong order | `clock_timestamp()` instead of `now()` |
| A bad chunk left documents stuck in PROCESSING | Flush inside the error handling; mark FAILED; test added |
| Blocking upload in an `async` route | Normal `def` route; size limit while reading |

## Future improvements

1. Put the agent's escalation rule partly in code (like triage's SECURITY/CRITICAL rule).
2. Hybrid search (keywords + vectors) and a reranker for RAG; a second RAG prompt version with new held-out questions.
3. Refresh-token families to detect stolen tokens; a denylist to revoke access tokens.
4. Email notifications and password reset.
5. Row locking when two agents edit the same ticket.
6. Deploy to AWS with HTTPS and a budget alarm; run the evaluations in CI against a small model.
7. A feedback button on AI suggestions, to build real evaluation data from staff decisions.
