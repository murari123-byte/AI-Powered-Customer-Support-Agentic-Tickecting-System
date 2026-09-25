# Deployment (optional, AWS)

> **Nothing here has been deployed.** This is a plan, with costs, for when you choose to put the project online.
> Everything in this project works locally for free. **Every AWS service below can cost money.**
> Prices are **rough estimates** of on-demand prices in **us-east-1 (N. Virginia)**, based on AWS's usual published
> rates. They were **not checked live** and they change, so **check the AWS Pricing Calculator (calculator.aws) before
> creating anything**.

## The main cost problem: the LLM

On a laptop the model is free. In the cloud, **running a 7B model is the most expensive part**:

| Option | Rough cost | Notes |
|---|---|---|
| CPU instance big enough for qwen2.5:7b (16 GB RAM, e.g. `t3.xlarge`) | ~$120/month if always on | Slow (~6 s per triage, ~30 s per agent run), like this machine |
| GPU instance (e.g. `g4dn.xlarge`) | ~$380/month if always on | Fast, but expensive for a portfolio demo |
| Smaller model (`qwen2.5:3b`) on a smaller instance (8 GB, `t3.large`) | ~$60/month | Cheaper, less accurate: re-run the evaluations |
| A hosted LLM API instead of Ollama | Pay per call | Needs a new provider class (the `LLMProvider` interface makes this a one-file change); **no longer free** |

**Recommendation for a portfolio:** don't keep it running. Deploy for a demo or an interview, then **stop the instance**
(you pay only for disk while stopped, a few dollars a month), or show the local Docker version and screenshots.

## Option A: cheapest (one EC2 instance, everything in Docker)

Run the same `docker-compose.yml` on one server.

```
Internet ──► EC2 (t3.xlarge, Ubuntu)  ── Caddy/nginx with HTTPS ──► frontend, api
                 └─ docker compose: postgres, redis, ollama, worker, prometheus, grafana
```

| Item | Approx. cost |
|---|---|
| EC2 `t3.xlarge` (4 vCPU, 16 GB) always on | ~$120/month (**~$0.17/hour**, stop it when not in use) |
| EBS disk, 40 GB gp3 | ~$3.20/month |
| Public IPv4 address | ~$3.60/month |
| Domain name (optional) | ~$10–15/year |
| HTTPS certificate (Let's Encrypt via Caddy) | free |
| **Total if always on** | **~$127/month**; a few $/month if stopped when not demoing |

Steps (outline):
1. Create the instance with **16 GB RAM**, a security group allowing only **22 (SSH, your IP only), 80 and 443**. Never open 5433, 6380, 9090, 3002 or 11434.
2. Install Docker; copy the project; create `.env` **on the server** with new random secrets (`POSTGRES_PASSWORD`, `JWT_SECRET_KEY`, `GRAFANA_ADMIN_PASSWORD`).
3. Build the frontend with the real API address: `VITE_API_BASE_URL=https://api.your-domain`; set `CORS_ORIGINS=https://your-domain`.
4. Put **Caddy** (or nginx + certbot) in front for HTTPS, proxy `your-domain` → frontend and `api.your-domain` → api; **block `/metrics`** at the proxy.
5. `docker compose up -d --build`, then pull the models inside the Ollama container and run `seed-teams`, `load-knowledge`, `create-admin`.
6. Back up the database: a daily `pg_dump` to S3 (below).

## Option B: managed services (more "production", more cost)

```
Users ──► CloudFront + S3 (React static files)
      ──► Application Load Balancer (HTTPS, ACM certificate)
             ──► EC2 (api + worker in Docker, Ollama)   [or ECS]
                    ├─► RDS PostgreSQL (with pgvector)
                    ├─► ElastiCache Redis (or Redis in Docker on the EC2)
                    └─► S3 (uploaded documents, database backups)
```

| Service | Use | Approx. cost |
|---|---|---|
| **S3 + CloudFront** | Host the built React app | Cents at portfolio traffic (S3 ~$0.023/GB-month; CloudFront has a free allowance) |
| **EC2** (`t3.xlarge`) | API, worker, Ollama | ~$120/month |
| **RDS PostgreSQL** `db.t4g.micro`, 20 GB | Database (pgvector is supported on RDS PostgreSQL) | ~$15/month + storage; **new accounts may get 12 months free tier** for small instances |
| **ElastiCache Redis** `cache.t4g.micro` | Celery queue | ~$12/month (or run Redis in Docker on the EC2 for $0) |
| **Application Load Balancer** | HTTPS entry point | ~$16/month + usage |
| **ACM** certificate | HTTPS | free |
| **S3** | Uploads + nightly `pg_dump` backups | Cents |
| **Total** | | **~$165–190/month always on** |

Code changes for option B (small, because of how the code is built):
- `DATABASE_URL` points to RDS (already supported: it overrides the `POSTGRES_*` parts).
- `REDIS_HOST` points to ElastiCache.
- Uploaded files: today only the extracted text is stored (in the database), so S3 is only needed if you want to keep originals.
- Run `alembic upgrade head` as a one-off step before starting the new version (like the `migrate` service).

## Hidden costs to watch

| Trap | How to avoid it |
|---|---|
| Forgetting a running instance or database | Stop or delete everything after a demo; **set an AWS Budget alarm** (e.g. $10) on day one |
| NAT Gateway (~$33/month + data) | Don't create one; keep the EC2 in a public subnet with a strict security group |
| Elastic IP / public IPv4 | ~$3.60/month each, even when the instance is stopped |
| RDS backups and snapshots | Keep retention short; delete manual snapshots |
| Data transfer out | Small at demo traffic; large downloads cost ~$0.09/GB |
| CloudWatch Logs | Set retention (e.g. 7 days) |

## Before going public

- New random secrets in `.env` on the server; never reuse the local ones.
- HTTPS everywhere (`AUTH_COOKIE_SECURE=true` stays on).
- `CORS_ORIGINS` = the real frontend address only.
- Only 80/443 open to the world; SSH limited to your IP.
- `/metrics`, Grafana and Prometheus not public (VPN, SSH tunnel, or IP allow-list).
- Uvicorn behind the proxy with `--proxy-headers`, so rate limiting sees real client IPs.
- A backup and a tested restore.
