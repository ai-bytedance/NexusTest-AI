English | [中文](README.zh-CN.md)

# NexusTest-AI

NexusTest-AI is a backend-first, AI-assisted API testing platform. It ships with a FastAPI backend, Celery workers, Docker Compose stack, and a Helm chart for Kubernetes.

[Docs (EN)](docs/en/README.md) | [Docs (ZH)](docs/zh/README.md)

---

## Contents
- Overview & Features
- Architecture
- Prerequisites
- Quick Start (Docker Compose)
- Environment variables
- First-run setup & URLs
- Roles & login
- Sample workflow
- AI providers
- Troubleshooting
- Common commands
- FAQ
- Docs index

---

## Overview & Features

- FastAPI backend with JWT auth, RBAC, and personal access tokens
- Projects, APIs, Test Cases, Test Suites; importers for OpenAPI and Postman
- Celery workers for asynchronous execution; Flower dashboard
- AI helpers to generate test assets and summaries (DeepSeek/OpenAI/Claude/Gemini/Qwen/GLM/Doubao/mock)
- Report exports (Markdown, PDF-ready) with redaction controls
- Security hardening at the edge (nginx) with basic rate limiting and headers
- Helm chart for production-grade K8s deployments; ServiceMonitor support

---

## Architecture

- Backend API: FastAPI + SQLAlchemy + Alembic
- Workers: Celery (Redis broker)
- DB: PostgreSQL
- Edge: nginx (reverse proxy; rate limits; security headers)
- Observability: optional Prometheus scraping; Grafana (via override)

Repo layout:
- backend/: FastAPI app, Alembic migrations, Dockerfile
- infra/: docker-compose.yml, nginx config
- charts/: Helm chart (charts/nexustest-ai)
- frontend/: Vite + React dev scaffold
- scripts/: nt_cli.py (CI-friendly CLI)

---

## Prerequisites
- Docker 24+ and Docker Compose plugin
- curl or an HTTP client (for examples)
- For local dev: Python 3.11+, Node.js 18+

---

## Quick Start (Docker Compose)

For the full step-by-step quickstart (with a demo run), see docs/en/setup/quickstart.md. The outline below summarises the steps.

```bash
git clone <your-repo-url>.git
cd <repo>
cp .env.example .env

docker compose -f infra/docker-compose.yml up -d postgres redis
docker compose -f infra/docker-compose.yml build api celery-worker celery-beat flower --no-cache --progress=plain
docker compose -f infra/docker-compose.yml up -d
# Access: http://localhost/api/healthz, /api/docs, /flower

# Create admin, then login to get an access token (copy access_token from response)
curl -X POST http://localhost/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"changeme123","role":"admin"}'

curl -X POST http://localhost/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.com","password":"changeme123"}'
# Copy .data.access_token as TOKEN

# Create project (copy .data.id as PROJECT)
curl -X POST http://localhost/api/v1/projects \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"name":"Demo","key":"DEMO"}'

# Minimal demo: create case (status 200) and run it; see docs/en/setup/quickstart.md
```

Shutdown:
```bash
docker compose -f infra/docker-compose.yml down
```

---

## Environment variables (common)

See .env.example for a complete list. Highlights below.

| Name | Purpose | Default |
|------|---------|---------|
| APP_ENV | Environment name | local |
| SECRET_KEY | JWT signing secret | replace_me |
| SECRET_ENC_KEY | Optional encryption key | empty |
| DATABASE_URL | Postgres connection URL | postgresql+psycopg2://app:app@postgres:5432/app |
| REDIS_URL | Redis URL | redis://redis:6379/0 |
| ACCESS_TOKEN_EXPIRE_MINUTES | JWT expiry | 60 |
| TOKEN_CLOCK_SKEW_SECONDS | JWT clock skew | 30 |
| CORS_ORIGINS | Comma list or * | * |
| PROVIDER | AI provider | mock |
| REQUEST_TIMEOUT_SECONDS | HTTP request timeout | 30 |
| MAX_RESPONSE_SIZE_BYTES | Response payload cap | 512000 |
| REPORT_EXPORT_MAX_BYTES | Report export cap | 5242880 |
| PDF_ENGINE | PDF renderer | weasyprint |
| REDACT_FIELDS | Masked fields | authorization,password,token,secret |

AI provider keys:
- DEEPSEEK_API_KEY (+ DEEPSEEK_BASE_URL, DEEPSEEK_MODEL)
- OPENAI_API_KEY (+ OPENAI_BASE_URL, OPENAI_MODEL)
- ANTHROPIC_API_KEY (+ ANTHROPIC_BASE_URL, ANTHROPIC_MODEL)
- GOOGLE_API_KEY (+ GOOGLE_BASE_URL, GEMINI_MODEL)
- QWEN_API_KEY (+ QWEN_BASE_URL, QWEN_MODEL)
- ZHIPU_API_KEY (+ ZHIPU_BASE_URL, GLM_MODEL)
- DOUBAO_API_KEY (+ DOUBAO_BASE_URL, DOUBAO_MODEL)

Email:
- SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM, SMTP_FROM_NAME, SMTP_TLS
- SENDGRID_API_KEY, MAILGUN_API_KEY

Metrics:
- METRICS_ENABLED, METRICS_NAMESPACE, METRICS_HOST, METRICS_PORT, CELERY_METRICS_PORT

More in docs/en/security.md and docs/en/ai-providers.md.

---

## First-run setup & URLs

- Health: http://localhost/api/healthz
- Swagger: http://localhost/api/docs
- Flower: http://localhost/flower
- Register an admin then login to obtain a bearer token for API calls

---

## Roles & login

System roles: admin, member. New users default to member unless role is explicitly set at registration. Admins can access system-level endpoints (e.g., backups). Project roles are managed per project (admin/member) for fine-grained access.

---

## Sample workflow

Minimal smoke flow (simplified):
- Register and login to get TOKEN
- Create a project (PROJECT)
- Create a minimal API definition
- Create a test case that asserts status_code==200 for https://httpbin.org/get
- Trigger: POST /api/v1/projects/{PROJECT}/execute/case/{CASE_ID}
- Poll: GET /api/v1/reports/{REPORT_ID}

See docs/en/setup/quickstart.md for copy-paste commands.

---

## AI providers

- Default provider is DeepSeek; when no API key is configured, the backend falls back to the mock provider for deterministic output.
- Full configuration and troubleshooting: docs/en/ai-providers.md

---

## Troubleshooting

- Docker build fails with redis/celery dependency conflicts → pull latest dependencies (`redis>=4.6,<5.0`) and rerun the build step with `--no-cache`.
- Compose tries to pull `api-automation-backend` → update to the latest infra/docker-compose.yml; services now build locally to `nexustest-backend:local`.
- Slow image builds or base image pulls → run with BuildKit enabled (`DOCKER_BUILDKIT=1 docker compose …`) and configure registry mirrors if available.
- Port 80 already in use → stop the conflicting service or change host port mapping in infra/docker-compose.yml
- Database connection errors → ensure postgres container is healthy; check DATABASE_URL
- Migrations failed on start → docker compose logs api; run make migrate to retry
- 401 errors → missing/expired token; re-login and pass Authorization: Bearer <token>
- CORS issues in local dev → verify CORS_ORIGINS includes your frontend dev URL
- nginx HSTS off by default → set HSTS_ENABLED=1 on nginx to enable

---

## Common commands

Makefile shortcuts:
- make up – start the compose stack
- make down – stop the stack
- make logs – tail logs
- make shell – enter the API container
- make migrate – run Alembic migrations
- make revision msg="message" – create a migration
- make test – run pytest
- make lint – pre-commit checks
- make format – black + isort

---

## FAQ

- Q: Is there a web UI?
  - A: The repo includes a frontend dev scaffold (frontend/). For quick evaluation use Swagger UI (/api/docs) and the APIs.
- Q: How to enable TLS locally?
  - A: Prefer using a local reverse proxy (e.g., Caddy/Traefik) or Kubernetes Ingress with TLS. nginx in Compose is HTTP by default.
- Q: Which AI provider is recommended by default?
  - A: DeepSeek is the default; see docs/en/ai-providers.md for alternatives and keys.
- Q: Where can I tune rate limits?
  - A: Edge limits in infra/nginx/nginx.conf; app-level policies under project rate limit APIs.
- Q: How to export PDF reports?
  - A: Set PDF_ENGINE and optionally REPORT_EXPORT_FONT_PATH (for CJK fonts).

---

## Docs index

- Quickstart: docs/en/setup/quickstart.md
- Local development: docs/en/setup/local-dev.md
- Docker Compose deployment: docs/en/deploy/docker-compose.md
- Helm deployment: docs/en/deploy/helm.md
- CI/CD and CLI: docs/en/ci-cd.md
- Security: docs/en/security.md
- AI providers: docs/en/ai-providers.md
- Webhooks: docs/en/webhooks.md

License: see LICENSE.
