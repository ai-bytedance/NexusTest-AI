English | [中文](../../zh/setup/quickstart.md)

# Quick Start (Docker Compose)

This quick start spins up NexusTest-AI locally with Docker Compose and walks you through first login and a demo test run.

---

## Prerequisites
- Docker 24+ and Docker Compose Plugin
- Ports available: 8080 (nginx host port)
- Optional: curl or HTTP client

---

## 1) Clone and configure

```bash
git clone <your-repo-url>.git
cd <repo>
cp .env.example .env
# (optional) copy infra env template
cp infra/env.example infra/.env || true
```

Edit .env as needed. Minimal defaults work for local runs.

---

## 2) Start data stores

Bring up Postgres and Redis first so the application containers can pass health checks on boot.

```bash
docker compose -f infra/docker-compose.yml up -d postgres redis
```

Wait until both services show `healthy` (check with `docker compose -f infra/docker-compose.yml ps`).

---

## 3) Build backend images

Build the backend images (API, worker, beat, Flower) from the local Dockerfile. The `--no-cache` flag guarantees new dependencies are picked up when requirements change; omit it after the first successful build if you prefer cached layers.

```bash
docker compose -f infra/docker-compose.yml build api celery-worker celery-beat flower --no-cache --progress=plain
```

---

## 4) Start stack

```bash
docker compose -f infra/docker-compose.yml up -d
```

This brings up Postgres, Redis, API, Celery worker/beat, Flower, and nginx. The API container applies Alembic migrations automatically.

---

## 5) Access URLs
- Web UI: http://localhost:8080/ (nginx serves the Vite build with VITE_API_BASE=/api)
- API health: http://localhost:8080/api/healthz
- Readiness: http://localhost:8080/api/readyz
- Swagger UI: http://localhost:8080/api/docs
- Flower: http://localhost:8080/flower

If port 80 is free and you prefer to use it, change the nginx service port mapping in infra/docker-compose.yml back to "80:80" and restart the stack.

---

## 6) First user (admin)

```bash
curl -X POST http://localhost:8080/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"changeme123","role":"admin"}'

curl -X POST http://localhost:8080/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"changeme123"}'
# copy access_token from response
```

---

## 7) Create a project
```bash
TOKEN=<paste-access-token>

curl -X POST http://localhost:8080/api/v1/projects \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Demo","key":"DEMO","description":"Quickstart project"}'
# capture returned project id as PROJECT
```

---

## 8) Demo case and run

1) Create an API definition
```bash
curl -X POST http://localhost:8080/api/v1/projects/$PROJECT/apis \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
        "name": "HTTPBin GET",
        "method": "GET",
        "path": "/get",
        "version": "v1",
        "group_name": "demo",
        "headers": {},
        "params": {},
        "body": {},
        "mock_example": {}
      }'
# capture API id as API_ID
```

2) Create a minimal test case (assert status 200)
```bash
curl -X POST http://localhost:8080/api/v1/projects/$PROJECT/test-cases \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
        "name": "GET status ok",
        "api_id": "'"$API_ID"'",
        "inputs": {"method":"GET","url":"https://httpbin.org/get"},
        "expected": {},
        "assertions": [{"operator":"status_code","expected":200}],
        "enabled": true
      }'
# capture case id as CASE_ID
```

3) Trigger execution
```bash
curl -X POST http://localhost:8080/api/v1/projects/$PROJECT/execute/case/$CASE_ID \
  -H "Authorization: Bearer $TOKEN"
# note report_id from response as REPORT_ID
```

4) Check report
```bash
curl http://localhost:8080/api/v1/reports/$REPORT_ID -H "Authorization: Bearer $TOKEN"
```

Status should become "passed" shortly.

---

## 9) Shutdown
```bash
docker compose -f infra/docker-compose.yml down
```

---

## Troubleshooting

- **pip dependency conflict (redis / celery)** → ensure you pulled the latest backend/requirements.txt (uses `redis>=4.6,<5.0` with Celery 5.3). Re-run the build step with `--no-cache` to force pip to resolve with the updated constraints.
- **Compose tries to pull `api-automation-backend`** → update infra/docker-compose.yml and rebuild. The backend services now build locally to the `nexustest-backend:local` tag.
- **Slow base image pulls** → enable BuildKit (`DOCKER_BUILDKIT=1 docker compose …`) and optionally configure Docker registry mirrors for your environment.
- **Services not ready after `up -d`** → confirm Postgres/Redis are healthy (`docker compose ps`) and check logs (`docker compose logs api` / `celery-worker`).

---

## Next steps
- Configure AI provider keys: ../ai-providers.md
- Local development (hot reload, tests): ./local-dev.md
- CI/CD integration: ../ci-cd.md
- Security hardening: ../security.md
