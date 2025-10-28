# API Automation Platform Skeleton

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

## API Overview

All business endpoints live under `/api/v1` and return a standard envelope:

```json
{
  "code": "SUCCESS",
  "message": "Success",
  "data": {}
}
```

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

## Makefile Helpers

```bash
make up        # start the compose stack
make down      # stop the stack
make logs      # tail logs from the stack
make shell     # enter the running API container
```

## Tooling

Install [ruff](https://github.com/astral-sh/ruff) and [black](https://github.com/psf/black) locally to lint and format the backend codebase:

```bash
pip install --upgrade ruff black
ruff check backend/app
black backend/app
```

## Next Steps

- Add database migrations (Alembic)
- Expand API modules and schemas
- Implement frontend application
- Harden deployments and CI pipelines

## License

See [LICENSE](./LICENSE) for placeholder licensing information.
