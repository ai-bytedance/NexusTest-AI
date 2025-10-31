# Local Development / 本地开发

This guide explains how to run backend and frontend in dev mode with hot reload, run database migrations, and execute tests.

本文档介绍在开发模式下运行后端与前端（热重载）、执行数据库迁移与测试的方法。

---

## Backend (FastAPI)

Prerequisites / 前置条件:
- Python 3.11+
- PostgreSQL & Redis (use Docker Compose or your local services)

Setup / 环境准备:
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

Run migrations / 执行数据库迁移:
```bash
cd backend
alembic upgrade head
```

Run API with hot reload / 启动 API（热重载）:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Swagger UI: http://localhost:8000/api/docs

Note: when using the repo's nginx proxy via Docker Compose, the external URL is http://localhost/api/.

---

## Frontend (Vite + React)

Prerequisites / 前置条件:
- Node.js 18+

Setup & run / 安装与运行:
```bash
cd frontend
npm install
npm run dev
```

The dev server listens on 5173 by default. CORS_ORIGINS in the backend already includes http://localhost:5173 and http://127.0.0.1:5173 for local use.

---

## Common developer tasks / 常用开发任务

Makefile targets / Makefile 任务（在仓库根目录）:
- make up: start Docker Compose stack
- make down: stop stack
- make logs: tail logs
- make shell: enter API container
- make migrate: run Alembic migrations in container
- make revision msg="message": create a new migration
- make test: run pytest
- make lint: run pre-commit hooks
- make format: black + isort on backend/

Testing / 测试:
```bash
pip install -r backend/requirements.txt
pip install pytest
pytest backend/tests -q
```

Pre-commit / 代码规范:
```bash
pip install pre-commit ruff black isort
pre-commit install
pre-commit run --all-files
```

---

## Seed minimal data / 初始化最小数据

Register user, login, create project via curl (similar to quickstart). Then create API definition and test case, and trigger an execution. See docs/setup/quickstart.md for copy-pastable commands.

通过 curl 注册用户、登录并创建项目（与快速开始一致）。随后创建 API 定义与测试用例并触发执行。命令示例见 docs/setup/quickstart.md。
