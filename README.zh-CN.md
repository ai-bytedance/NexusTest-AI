[English](README.en.md) | 中文

# NexusTest-AI

NexusTest-AI 是一款后端优先、具备 AI 助力能力的 API 测试平台。项目包含 FastAPI 后端、Celery 任务、Docker Compose 一键启动方案，以及用于 Kubernetes 的 Helm Chart。

[文档（中文）](docs/zh/README.md) | [Docs (EN)](docs/en/README.md)

---

## 目录
- 概览与特性
- 架构
- 前置条件
- 快速开始（Docker Compose）
- 环境变量
- 首次启动与访问地址
- 角色与登录
- 示例流程
- AI 提供商
- 故障排查
- 常用命令
- FAQ
- 文档索引

---

## 概览与特性

- FastAPI 后端：JWT 登录、RBAC、个人访问令牌（PAT）
- 资源模型：项目 / 接口 / 用例 / 套件；支持 OpenAPI 与 Postman 导入
- Celery 异步执行；Flower 可视化面板
- AI 助手：生成测试资产与报告摘要（支持 DeepSeek/OPENAI/Claude/Gemini/Qwen/GLM/Doubao/mock）
- 报告导出（Markdown、可拓展至 PDF），支持字段脱敏
- 边缘安全：nginx 基础限流与安全响应头
- Helm Chart：生产级 Kubernetes 部署；可选 ServiceMonitor 集成

---

## 架构

- 后端 API：FastAPI + SQLAlchemy + Alembic
- Workers：Celery（Redis 作为 broker）
- 数据库：PostgreSQL
- 边缘：nginx（反向代理；限流；安全响应头）
- 可观测性：可选 Prometheus 抓取；Grafana（通过覆盖文件启用）

仓库结构：
- backend/：FastAPI 应用、Alembic 迁移、Dockerfile
- infra/：docker-compose.yml、nginx 配置
- charts/：Helm Chart（charts/nexustest-ai）
- frontend/：Vite + React 开发脚手架
- scripts/：nt_cli.py（适配 CI 的 CLI）

---

## 前置条件
- Docker 24+ 与 Docker Compose 插件
- curl 或其他 HTTP 客户端（用于示例）
- 本地开发：Python 3.11+、Node.js 18+

---

## 快速开始（Docker Compose）

完整分步说明（含示例执行）见 docs/zh/setup/quickstart.md。以下为简要步骤：

```bash
git clone <your-repo-url>.git
cd <repo>
cp .env.example .env

docker compose -f infra/docker-compose.yml up -d --build
# 访问: http://localhost:8080/api/healthz, /api/docs, /flower
# 如需继续使用 80 端口，可在 infra/docker-compose.yml 中把 nginx 端口映射改为 "80:80" 并重启栈。

# 创建管理员账号并登录获取 access_token
curl -X POST http://localhost:8080/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"changeme123","role":"admin"}'

curl -X POST http://localhost:8080/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.com","password":"changeme123"}'
# 复制响应中的 .data.access_token 到 TOKEN

# 创建项目（复制响应 .data.id 到 PROJECT）
curl -X POST http://localhost:8080/api/v1/projects \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"name":"Demo","key":"DEMO"}'

# 最小示例：创建仅断言 200 的用例并执行；详见 docs/zh/setup/quickstart.md
```

关闭：
```bash
docker compose -f infra/docker-compose.yml down
```

---

## 环境变量（常用）

完整列表见 .env.example，以下为重点：

| 名称 | 作用 | 默认值 |
|------|------|--------|
| APP_ENV | 环境名称 | local |
| SECRET_KEY | JWT 签名密钥 | replace_me |
| SECRET_ENC_KEY | 可选加密密钥 | 空 |
| DATABASE_URL | Postgres 连接 URL | postgresql+psycopg2://app:app@postgres:5432/app |
| REDIS_URL | Redis URL | redis://redis:6379/0 |
| ACCESS_TOKEN_EXPIRE_MINUTES | JWT 过期时间 | 60 |
| TOKEN_CLOCK_SKEW_SECONDS | JWT 时间偏差 | 30 |
| BACKEND_CORS_ORIGINS | CORS 白名单，可为空、逗号分隔、JSON 数组或 * | "" |
| PROVIDER | AI 提供商 | mock |
| REQUEST_TIMEOUT_SECONDS | HTTP 请求超时 | 30 |
| MAX_RESPONSE_SIZE_BYTES | 响应大小上限 | 512000 |
| REPORT_EXPORT_MAX_BYTES | 报告导出大小上限 | 5242880 |
| PDF_ENGINE | PDF 渲染引擎 | weasyprint |
| REDACT_FIELDS | 脱敏字段 | authorization,password,token,secret |

AI 提供商密钥：
- DEEPSEEK_API_KEY（可选：DEEPSEEK_BASE_URL, DEEPSEEK_MODEL）
- OPENAI_API_KEY（可选：OPENAI_BASE_URL, OPENAI_MODEL）
- ANTHROPIC_API_KEY（可选：ANTHROPIC_BASE_URL, ANTHROPIC_MODEL）
- GOOGLE_API_KEY（可选：GOOGLE_BASE_URL, GEMINI_MODEL）
- QWEN_API_KEY（可选：QWEN_BASE_URL, QWEN_MODEL）
- ZHIPU_API_KEY（可选：ZHIPU_BASE_URL, GLM_MODEL）
- DOUBAO_API_KEY（可选：DOUBAO_BASE_URL, DOUBAO_MODEL）

邮件：
- SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM, SMTP_FROM_NAME, SMTP_TLS
- SENDGRID_API_KEY, MAILGUN_API_KEY

指标：
- METRICS_ENABLED, METRICS_NAMESPACE, METRICS_HOST, METRICS_PORT, CELERY_METRICS_PORT

更多内容见 docs/zh/security.md 与 docs/zh/ai-providers.md。

---

## 首次启动与地址

- 健康检查：http://localhost:8080/api/healthz
- Swagger：http://localhost:8080/api/docs
- Flower：http://localhost:8080/flower
- 先注册管理员，再登录以获取 Bearer Token 用于 API 调用

---

## 角色与登录

系统角色：admin、member。新用户默认 member；注册时可显式设置为 admin（仅限首次初始化场景）。管理员可访问系统级接口（如备份）。项目内另有管理员/成员角色用于细粒度管控。

---

## 示例流程

最小烟囱流程（简化）：
- 注册并登录获取 TOKEN
- 创建项目（PROJECT）
- 创建最小化 API 定义
- 创建仅断言 200 的测试用例（https://httpbin.org/get）
- 触发：POST /api/v1/projects/{PROJECT}/execute/case/{CASE_ID}
- 轮询：GET /api/v1/reports/{REPORT_ID}

可复制命令见 docs/zh/setup/quickstart.md。

---

## AI 提供商

- 默认提供商为 DeepSeek；如未配置 API Key，后端会自动回退至 Mock 提供商以保证可用性。
- 完整配置与排障指南：docs/zh/ai-providers.md

---

## 故障排查

- 8080 端口被占用 → 关闭冲突服务，或按需修改 infra/docker-compose.yml（默认映射为 "0.0.0.0:8080:80" 以便其他主机访问；仅在确定需要时才改动）
- 数据库连接错误 → 确认 postgres 容器健康；检查 DATABASE_URL
- 启动迁移失败 → docker compose logs api；使用 make migrate 重试
- SQLAlchemy 报 `Mapped['Model' | None]` 等错误 → 在模型文件头部加入 `from __future__ import annotations`，并将关系类型改为 `Mapped[Model | None]` / `Mapped[list[Model]]`，避免带引号的联合类型，否则 Alembic upgrade 会失败
- 401 错误 → 缺少/过期 Token；请重新登录并携带 Authorization: Bearer <token>
- 本地 CORS 问题 → 确认 CORS_ORIGINS 包含前端开发 URL
- nginx 配置报 "add_header is not allowed here" → 仅在 `http`/`server` 块中添加响应头（参见 infra/nginx/nginx.conf），修改后可执行 `docker compose exec nginx nginx -t` 验证
- 外部主机无法访问 → 检查宿主机防火墙是否放行 8080 端口，或在 Compose 中重新映射端口
- nginx 默认未启用 HSTS → 在 nginx 容器上设置 HSTS_ENABLED=1

---

## 常用命令

Makefile 命令：
- make up – 启动 Compose 栈
- make down – 停止栈
- make logs – 查看日志
- make shell – 进入 API 容器
- make migrate – 运行 Alembic 迁移
- make revision msg="message" – 创建迁移
- make test – 运行 pytest
- make lint – 运行 pre-commit 检查
- make format – black + isort

---

## FAQ

- 问：是否提供 Web UI？
  - 答：本仓库包含前端开发脚手架（frontend/）。评估阶段可直接使用 Swagger UI（/api/docs）与 API。
- 问：本地如何启用 TLS？
  - 答：建议使用本地反代（Caddy/Traefik）或 Kubernetes Ingress 实现 TLS；Compose 内置 nginx 默认仅 HTTP。
- 问：默认推荐哪个 AI 提供商？
  - 答：默认 DeepSeek；其他提供商与密钥配置见 docs/zh/ai-providers.md。
- 问：如何调整限流？
  - 答：边缘限流见 infra/nginx/nginx.conf；应用内限流通过项目策略接口。
- 问：如何导出 PDF 报告？
  - 答：设置 PDF_ENGINE 并按需设置 REPORT_EXPORT_FONT_PATH（中文字体需额外字体文件）。

---

## 文档索引

- 快速开始：docs/zh/setup/quickstart.md
- 本地开发：docs/zh/setup/local-dev.md
- 使用 Compose 部署：docs/zh/deploy/docker-compose.md
- 使用 Helm 部署：docs/zh/deploy/helm.md
- CI/CD 与 CLI：docs/zh/ci-cd.md
- 安全：docs/zh/security.md
- AI 提供商：docs/zh/ai-providers.md
- Webhooks：docs/zh/webhooks.md

License：见 LICENSE。
