English | [中文](../../zh/setup/local-dev.md)

# Local Development

This guide explains how to run backend and frontend in dev mode with hot reload, run database migrations, and execute tests.

---

## Backend (FastAPI)

Prerequisites:
- Python 3.11+
- PostgreSQL & Redis (use Docker Compose or your local services)

Setup:
```bash
cd backend
python -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# copy env
cd ..
cp .env.example .env
```

Run migrations:
```bash
cd backend
alembic upgrade head
```

Run API with hot reload:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Swagger UI: http://localhost:8000/api/docs

Note: when using the repo's nginx proxy via Docker Compose, the external URL is http://localhost:8080/api/ (or http://<host>:8080/api/ from another machine).

---

## Frontend (Vite + React)

Prerequisites:
- Node.js 18+

Setup & run:
```bash
cd frontend
npm install
npm run dev
```

The dev server listens on 5173 by default. CORS_ORIGINS in the backend already includes http://localhost:5173 and http://127.0.0.1:5173 for local use.

---

## Common developer tasks

Makefile targets (at repo root):
- make up: start Docker Compose stack
- make down: stop stack
- make logs: tail logs
- make shell: enter API container
- make migrate: run Alembic migrations in container
- make revision msg="message": create a new migration
- make test: run pytest
- make lint: run pre-commit hooks
- make format: black + isort on backend/

Testing:
```bash
pip install -r backend/requirements.txt
pip install pytest
pytest backend/tests -q
```

Pre-commit:
```bash
pip install pre-commit ruff black isort
pre-commit install
pre-commit run --all-files
```

---

## Seed minimal data

Register user, login, create project via curl (similar to quickstart). Then create API definition and test case, and trigger an execution. See ./quickstart.md for copy-pastable commands.
