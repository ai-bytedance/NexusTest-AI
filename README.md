# API Automation Platform Skeleton

![CI](https://github.com/your-org/api-automation-platform/actions/workflows/ci.yml/badge.svg)

This repository contains the initial backend-first skeleton for the API automation platform. It provides a FastAPI-based backend, Docker Compose stack, and placeholders for future frontend and infrastructure work.

## Project Structure

```
backend/            # FastAPI application source
infra/              # Docker compose and infrastructure configuration
frontend/           # Placeholder for future frontend implementation
```

## Quickstart

1. Copy the environment template and update values as needed:

   ```bash
   cp .env.example .env
   cp infra/env.example infra/.env
   ```

2. Start the stack:

   ```bash
   docker compose -f infra/docker-compose.yml up -d --build
   ```

3. Access the services:

   - API health check: http://localhost/api/healthz
   - Readiness probe: http://localhost/api/readyz
   - Interactive docs: http://localhost/api/docs
   - Flower dashboard: http://localhost/flower

4. Interact with the API:

   ```bash
   curl -X POST http://localhost/api/auth/register \
     -H "Content-Type: application/json" \
     -d '{"email": "user@example.com", "password": "changeme"}'

   curl -X POST http://localhost/api/auth/login \
     -H "Content-Type: application/json" \
     -d '{"email": "user@example.com", "password": "changeme"}'
   ```

## Configuration

The backend reads its configuration from environment variables (see `.env.example`). Key toggles include:

- `ACCESS_TOKEN_EXPIRE_MINUTES` (default `60`): lifetime of issued access tokens.
- `TOKEN_CLOCK_SKEW_SECONDS` (default `0`): allowable leeway when validating JWT expiry to handle clock drift between services.
- `APP_VERSION`, `GIT_COMMIT_SHA`, and `BUILD_TIME`: surfaced via the `/api/v1/version` endpoint for build metadata.
- `MAX_RESPONSE_SIZE_BYTES` (default `512000`): upper bound for response payloads sent back to the UI. Anything larger is replaced with a truncation note.
- `REDACT_FIELDS` (comma-separated list): case-insensitive field names to mask with `***` inside request/response payloads (defaults to `authorization,password,token,secret`).

## API Overview

All business endpoints live under `/api/v1` and return a standard envelope:

```json
{
  "code": "SUCCESS",
  "message": "Success",
  "data": {}
}
```

### Authentication

Authentication endpoints under `/api/auth` follow the same `{code, message, data}` envelope. Common error codes include:

| Code   | Description                    |
|--------|--------------------------------|
| AUTH001 | Invalid credentials            |
| AUTH002 | Email already registered       |
| AUTH003 | Authentication token invalid   |

Token lifetimes are governed by `ACCESS_TOKEN_EXPIRE_MINUTES` and `TOKEN_CLOCK_SKEW_SECONDS`.

### Projects and RBAC

Create a project (the creator becomes the project admin):

```bash
curl -X POST http://localhost/api/v1/projects \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
        "name": "Payments",
        "key": "PAY",
        "description": "Demo project"
      }'
```

Add another user as a member:

```bash
curl -X POST http://localhost/api/v1/projects/<project-id>/members \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"email": "teammate@example.com", "role": "member"}'
```

Project admins can update or delete the project and manage membership, while members can manage APIs, test cases, and test suites.

### CRUD Examples

Create an API definition inside a project:

```bash
curl -X POST http://localhost/api/v1/projects/<project-id>/apis \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
        "name": "Get user",
        "method": "GET",
        "path": "/users/{id}",
        "version": "v1",
        "group_name": "users",
        "headers": {},
        "params": {},
        "body": {},
        "mock_example": {}
      }'
```

Test cases live under `/projects/<project-id>/test-cases` and test suites under `/projects/<project-id>/test-suites` with the same CRUD semantics.

### Importers

Import an OpenAPI document (supports URL fetch or raw JSON payload) and upsert API definitions by method/path/version:

```bash
curl -X POST http://localhost/api/v1/projects/<project-id>/import/openapi \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/openapi.json", "dry_run": false}'
```

Import a Postman v2 collection via JSON:

```bash
curl -X POST http://localhost/api/v1/projects/<project-id>/import/postman \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"collection": {"info": {"name": "Demo", "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"}, "item": []}}'
```

For form uploads, submit the `collection` file (JSON) using `multipart/form-data` with optional `dry_run=true`.

### AI Assistance

AI-powered helpers are exposed under `/api/v1/ai` to bootstrap test assets, generate mock payloads, and summarise execution reports.

#### Configure providers

Set the `PROVIDER` environment variable to the vendor you want to use. Supported values are `deepseek`, `openai`, `anthropic`, `gemini`, `qwen`, `glm`, `doubao`, and `mock` (default).

Provide the matching API keys in `.env`:

- `DEEPSEEK_API_KEY` (+ optional `DEEPSEEK_BASE_URL`)
- `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `QWEN_API_KEY`, `ZHIPU_API_KEY`, `DOUBAO_API_KEY` (+ optional `<PROVIDER>_BASE_URL` where applicable)

If a required key is missing, the registry automatically falls back to the deterministic mock provider so the platform keeps working in local environments.

#### Sample requests

```bash
# Generate test cases from an API specification
curl -X POST http://localhost/api/v1/ai/generate-cases \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
        "project_id": "<project-id>",
        "api_spec": {"path": "/users", "method": "GET"}
      }'

# Generate assertions from an example response payload
curl -X POST http://localhost/api/v1/ai/generate-assertions \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
        "project_id": "<project-id>",
        "example_response": {"status": "success", "data": {"id": 1}}
      }'

# Produce mock data using a JSON schema
curl -X POST http://localhost/api/v1/ai/mock-data \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
        "project_id": "<project-id>",
        "json_schema": {"type": "object", "properties": {"id": {"type": "string"}}}
      }'

# Summarise an execution report (inline payload)
curl -X POST http://localhost/api/v1/ai/summarize-report \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
        "project_id": "<project-id>",
        "report": {"status": "passed", "metrics": {"total": 10, "passed": 9, "failed": 1}}
      }'
```

Each response follows the standard `{code, message, data}` envelope. On success the payload includes the generated artefacts alongside the `task_id` that was recorded in the `ai_tasks` table.

### Reporting & Metrics

Reports and analytics endpoints live under `/api/v1/reports` and `/api/v1/metrics`.

List reports with filters, ordering, and pagination:

```bash
curl -G http://localhost/api/v1/reports \
  -H "Authorization: Bearer <token>" \
  --data-urlencode "project_id=<project-id>" \
  --data-urlencode "status=passed" \
  --data-urlencode "entity_type=case" \
  --data-urlencode "date_from=2024-10-01T00:00:00Z" \
  --data-urlencode "page=1" \
  --data-urlencode "page_size=10"
```

Fetch a detailed report with computed assertion metrics and redacted payloads:

```bash
curl http://localhost/api/v1/reports/<report-id> \
  -H "Authorization: Bearer <token>"
```

Generate (or refresh) an AI summary for a report:

```bash
curl -X POST http://localhost/api/v1/reports/<report-id>/summarize \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"overwrite": false}'
```

Export a report as Markdown (the payload contains the filename, content type, and Markdown string):

```bash
curl -G http://localhost/api/v1/reports/<report-id>/export \
  -H "Authorization: Bearer <token>" \
  --data-urlencode "format=markdown"
```

Retrieve aggregated pass/fail/error counts for charting:

```bash
curl -G http://localhost/api/v1/metrics/reports/summary \
  -H "Authorization: Bearer <token>" \
  --data-urlencode "project_id=<project-id>" \
  --data-urlencode "days=14"
```

The reporting endpoints always respond with the `{code, message, data}` envelope. When exports are requested, the `data` object carries the file metadata and content (Markdown text today; PDF returns a `501` error with code `R002` until a generator is configured).

## Gateway & Security

The edge nginx proxy defined in `infra/nginx/nginx.conf` now:

- Limits authenticated and general API traffic to 10 requests/second with a burst tolerance of 20 (`/api` and `/api/auth`).
- Caps request bodies at 10 MB and tightens client/proxy timeouts to reduce slowloris-style attacks.
- Adds security headers (`X-Content-Type-Options`, `X-Frame-Options`, `X-XSS-Protection`, `Referrer-Policy`, `Content-Security-Policy`) alongside gzip tuning.
- Serves static assets under `/static/` with caching directives while keeping the `/ws` WebSocket proxy untouched.

## Makefile Helpers

```bash
make up        # start the compose stack
make down      # stop the stack
make logs      # tail logs from the stack
make shell     # enter the running API container
make lint      # run pre-commit checks across the repo
make format    # apply black + isort formatting to backend/
make test      # execute pytest against the backend test suite
make ci        # run lint + test targets (useful locally before pushing)
```

## Tooling

Install [pre-commit](https://pre-commit.com), [ruff](https://github.com/astral-sh/ruff), and [black](https://github.com/psf/black) locally to match the automated checks:

```bash
pip install --upgrade pre-commit ruff black isort
pre-commit install
ruff check backend
black backend
isort --profile black backend
```

## Next Steps

- Add database migrations (Alembic)
- Expand API modules and schemas
- Implement frontend application
- Harden deployments and CI pipelines

## License

See [LICENSE](./LICENSE) for placeholder licensing information.
