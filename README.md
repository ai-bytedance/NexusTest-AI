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
