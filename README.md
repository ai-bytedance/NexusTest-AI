# NexusTest-AI

English | 中文

NexusTest-AI is a backend-first, AI-assisted API testing platform. It ships with a FastAPI backend, Celery workers, Docker Compose stack, and a Helm chart for Kubernetes. This README gives a bilingual overview, quick start, and links to deeper docs.

NexusTest-AI 是一款后端优先、具备 AI 助力能力的 API 测试平台。项目包含 FastAPI 后端、Celery 任务、Docker Compose 一键启动方案，以及用于 Kubernetes 的 Helm Chart。本文档提供中英双语概览、快速开始和详细文档链接。

---

## Contents / 目录
- Overview & Features / 概览与特性
- Architecture / 架构
- Prerequisites / 前置条件
- Quick Start (Docker Compose) / 快速开始（Docker Compose）
- Environment variables / 环境变量
- First-run setup & URLs / 首次启动与访问地址
- Roles & login / 角色与登录
- Sample workflow / 示例流程
- AI providers / AI 提供商
- Troubleshooting / 故障排查
- Common commands / 常用命令
- FAQ
- Docs index / 文档索引

---

## Overview & Features / 概览与特性

- FastAPI backend with JWT auth, RBAC, and personal access tokens
- Projects, APIs, Test Cases, Test Suites; importers for OpenAPI and Postman
- Celery workers for asynchronous execution; Flower dashboard
- AI helpers to generate test assets and summaries (DeepSeek/OpenAI/Claude/Gemini/Qwen/GLM/Doubao/mock)
- Report exports (Markdown, PDF-ready) with redaction controls
- Security hardening at the edge (nginx) with basic rate limiting and headers
- Helm chart for production-grade K8s deployments; ServiceMonitor support

- FastAPI 后端：JWT 登录、RBAC、PAT 令牌
- 资源模型：项目/接口/用例/套件；支持 OpenAPI 与 Postman 导入
- Celery 异步执行；Flower 可视化面板
- AI 助手：生成测试资产与报告摘要（支持 DeepSeek/OPENAI/Claude/Gemini/Qwen/GLM/Doubao/mock）
- 报告导出（Markdown、可拓展至 PDF），支持字段脱敏
- 边缘安全：nginx 基础限流与安全响应头
- Helm Chart：生产级 Kubernetes 部署；可选 ServiceMonitor 集成

---

## Architecture / 架构

- Backend API: FastAPI + SQLAlchemy + Alembic
- Workers: Celery (Redis broker)
- DB: PostgreSQL
- Edge: nginx (reverse proxy; rate limits; security headers)
- Observability: optional Prometheus scraping; Grafana (via override)

目录结构 / Repo layout:
- backend/: FastAPI app, Alembic migrations, Dockerfile
- infra/: docker-compose.yml, nginx config
- charts/: Helm chart (charts/nexustest-ai)
- frontend/: Vite + React dev scaffold
- scripts/: nt_cli.py (CI-friendly CLI)

---

## Prerequisites / 前置条件
- Docker 24+ and Docker Compose plugin
- curl or an HTTP client (for examples)
- For local dev: Python 3.11+, Node.js 18+

---

## Quick Start (Docker Compose) / 快速开始（Docker Compose）

For the full step-by-step quickstart (with a demo run), see docs/setup/quickstart.md. The outline below summarises the steps.

完整分步说明（含示例执行）见 docs/setup/quickstart.md。以下为简要步骤：

```bash
git clone <your-repo-url>.git
cd <repo>
cp .env.example .env

docker compose -f infra/docker-compose.yml up -d --build
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

# Minimal demo: create case (status 200) and run it; see docs/setup/quickstart.md
```

Shutdown / 关闭：
```bash
docker compose -f infra/docker-compose.yml down
```

---

## Environment variables (common) / 常用环境变量

See .env.example for a complete list. Highlights below.
完整列表见 .env.example，以下为重点：

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

AI provider keys / AI 提供商密钥：
- DEEPSEEK_API_KEY (+ DEEPSEEK_BASE_URL, DEEPSEEK_MODEL)
- OPENAI_API_KEY (+ OPENAI_BASE_URL, OPENAI_MODEL)
- ANTHROPIC_API_KEY (+ ANTHROPIC_BASE_URL, ANTHROPIC_MODEL)
- GOOGLE_API_KEY (+ GOOGLE_BASE_URL, GEMINI_MODEL)
- QWEN_API_KEY (+ QWEN_BASE_URL, QWEN_MODEL)
- ZHIPU_API_KEY (+ ZHIPU_BASE_URL, GLM_MODEL)
- DOUBAO_API_KEY (+ DOUBAO_BASE_URL, DOUBAO_MODEL)

Email / 邮件:
- SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM, SMTP_FROM_NAME, SMTP_TLS
- SENDGRID_API_KEY, MAILGUN_API_KEY

Metrics / 指标:
- METRICS_ENABLED, METRICS_NAMESPACE, METRICS_HOST, METRICS_PORT, CELERY_METRICS_PORT

More in docs/security.md and docs/ai-providers.md.
更多内容见 docs/security.md 与 docs/ai-providers.md。

---

## First-run setup & URLs / 首次启动与地址

- Health: http://localhost/api/healthz
- Swagger: http://localhost/api/docs
- Flower: http://localhost/flower
- Register an admin then login to obtain a bearer token for API calls

---

## Roles & login / 角色与登录

System roles: admin, member. New users default to member unless role is explicitly set at registration. Admins can access system-level endpoints (e.g., backups). Project roles are managed per project (admin/member) for fine-grained access.

系统角色：admin、member。新用户默认 member；注册时可显式设置为 admin（仅限首次初始化场景）。管理员可访问系统级接口（如备份）。项目内另有管理员/成员角色用于细粒度管控。

---

## Sample workflow / 示例流程

Minimal smoke flow (simplified):
- Register and login to get TOKEN
- Create a project (PROJECT)
- Create a minimal API definition
- Create a test case that asserts status_code==200 for https://httpbin.org/get
- Trigger: POST /api/v1/projects/{PROJECT}/execute/case/{CASE_ID}
- Poll: GET /api/v1/reports/{REPORT_ID}

详见 docs/setup/quickstart.md 提供的可复制命令。

---

## AI providers / AI 提供商

- Default provider is DeepSeek; when no API key is configured, the backend falls back to the mock provider for deterministic output.
- Full configuration and troubleshooting: docs/ai-providers.md

- 默认提供商为 DeepSeek；如未配置 API Key，后端会自动回退至 Mock 提供商以保证可用性。
- 完整配置与排障指南：docs/ai-providers.md

---

## Troubleshooting / 故障排查

- Port 80 already in use → stop the conflicting service or change host port mapping in infra/docker-compose.yml
- Database connection errors → ensure postgres container is healthy; check DATABASE_URL
- Migrations failed on start → docker compose logs api; run make migrate to retry
- 401 errors → missing/expired token; re-login and pass Authorization: Bearer <token>
- CORS issues in local dev → verify CORS_ORIGINS includes your frontend dev URL
- nginx HSTS off by default → set HSTS_ENABLED=1 on nginx to enable

---

## Common commands / 常用命令

Makefile shortcuts / Makefile 命令：
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

- Q: Is there a web UI? 目前是否有 Web UI？
  - A: The repo includes a frontend dev scaffold (frontend/). For quick evaluation use Swagger UI (/api/docs) and the APIs. 本仓库包含前端开发脚手架；评估阶段可直接使用 Swagger UI 与 API。
- Q: How to enable TLS locally? 本地如何启用 TLS？
  - A: Prefer using a local reverse proxy (e.g., Caddy/Traefik) or Kubernetes Ingress with TLS. nginx in Compose is HTTP by default. 建议使用本地反代或 K8s Ingress 实现 TLS；Compose 内置 nginx 默认仅 HTTP。
- Q: Which AI provider is recommended by default? 默认推荐哪个 AI 提供商？
  - A: DeepSeek is the default; see docs/ai-providers.md for alternatives and keys. 默认 DeepSeek，其他提供商与密钥配置见 docs/ai-providers.md。
- Q: Where can I tune rate limits? 如何调整限流？
  - A: Edge limits in infra/nginx/nginx.conf; app-level policies under project rate limit APIs. 边缘限流见 nginx.conf；应用内限流通过项目策略接口。
- Q: How to export PDF reports? 如何导出 PDF 报告？
  - A: Set PDF_ENGINE and optionally REPORT_EXPORT_FONT_PATH (for CJK fonts). 通过 PDF_ENGINE 与 REPORT_EXPORT_FONT_PATH 配置（中文字体需额外字体文件）。

---

## Docs index / 文档索引

- Quickstart / 快速开始: docs/setup/quickstart.md
- Local development / 本地开发: docs/setup/local-dev.md
- Docker Compose deployment / 使用 Compose 部署: docs/deploy/docker-compose.md
- Helm deployment / 使用 Helm 部署: docs/deploy/helm.md
- CI/CD and CLI / CI/CD 与 CLI: docs/ci-cd.md
- Security / 安全: docs/security.md
- AI providers / AI 提供商: docs/ai-providers.md
- Webhooks: docs/webhooks.md

License: see LICENSE.
