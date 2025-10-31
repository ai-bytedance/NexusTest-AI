English | [中文](../../zh/setup/quickstart.md)

# Quick Start (Docker Compose)

This quick start spins up NexusTest-AI locally with Docker Compose and walks you through first login and a demo test run.

---

## Prerequisites
- Docker 24+ and Docker Compose Plugin
- Ports available: 80 (nginx)
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

## 2) Start stack

```bash
docker compose -f infra/docker-compose.yml up -d --build
```

This brings up Postgres, Redis, API, Celery worker/beat, Flower, and nginx. The API container applies Alembic migrations automatically.

---

## 3) Access URLs
- API health: http://localhost/api/healthz
- Readiness: http://localhost/api/readyz
- Swagger UI: http://localhost/api/docs
- Flower: http://localhost/flower

---

## 4) First user (admin)

```bash
curl -X POST http://localhost/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"changeme123","role":"admin"}'

curl -X POST http://localhost/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"changeme123"}'
# copy access_token from response
```

---

## 5) Create a project
```bash
TOKEN=<paste-access-token>

curl -X POST http://localhost/api/v1/projects \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Demo","key":"DEMO","description":"Quickstart project"}'
# capture returned project id as PROJECT
```

---

## 6) Demo case and run

1) Create an API definition
```bash
curl -X POST http://localhost/api/v1/projects/$PROJECT/apis \
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
curl -X POST http://localhost/api/v1/projects/$PROJECT/test-cases \
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
curl -X POST http://localhost/api/v1/projects/$PROJECT/execute/case/$CASE_ID \
  -H "Authorization: Bearer $TOKEN"
# note report_id from response as REPORT_ID
```

4) Check report
```bash
curl http://localhost/api/v1/reports/$REPORT_ID -H "Authorization: Bearer $TOKEN"
```

Status should become "passed" shortly.

---

## 7) Shutdown
```bash
docker compose -f infra/docker-compose.yml down
```

---

## Next steps
- Configure AI provider keys: ../ai-providers.md
- Local development (hot reload, tests): ./local-dev.md
- CI/CD integration: ../ci-cd.md
- Security hardening: ../security.md
