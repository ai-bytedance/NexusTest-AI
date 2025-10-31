[English](../../en/setup/local-dev.md) | 中文

# 本地开发

本文档介绍在开发模式下运行后端与前端（热重载）、执行数据库迁移与测试的方法。

---

## 后端（FastAPI）

前置条件：
- Python 3.11+
- PostgreSQL 与 Redis（使用 Docker Compose 或本地服务）

环境准备：
```bash
cd backend
python -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 复制环境变量
cd ..
cp .env.example .env
```

执行数据库迁移：
```bash
cd backend
alembic upgrade head
```

启动 API（热重载）：
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Swagger UI: http://localhost:8000/api/docs

注意：若通过 Docker Compose 使用仓库内的 nginx 代理，对外访问 URL 为 http://localhost/api/。

---

## 前端（Vite + React）

前置条件：
- Node.js 18+

安装与运行：
```bash
cd frontend
npm install
npm run dev
```

开发服务默认监听 5173 端口。后端的 CORS_ORIGINS 已包含 http://localhost:5173 与 http://127.0.0.1:5173 以便本地使用。

---

## 常用开发任务

Makefile 任务（在仓库根目录）：
- make up：启动 Docker Compose
- make down：停止服务
- make logs：实时查看日志
- make shell：进入 API 容器
- make migrate：在容器内执行 Alembic 迁移
- make revision msg="message"：创建迁移
- make test：运行 pytest
- make lint：运行 pre-commit 钩子
- make format：对 backend/ 运行 black + isort

测试：
```bash
pip install -r backend/requirements.txt
pip install pytest
pytest backend/tests -q
```

代码规范（pre-commit）：
```bash
pip install pre-commit ruff black isort
pre-commit install
pre-commit run --all-files
```

---

## 初始化最小数据

通过 curl 注册用户、登录并创建项目（与快速开始一致）。随后创建 API 定义与测试用例并触发执行。命令示例见 ./quickstart.md。
