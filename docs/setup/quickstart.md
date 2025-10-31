# Quick Start (Docker Compose) / 快速开始（Docker Compose）

This quick start spins up NexusTest-AI locally with Docker Compose and walks you through first login and a demo test run.

本指南使用 Docker Compose 在本地启动 NexusTest-AI，并带你完成首次登录与一个示例测试流程。

---

## Prerequisites / 前置条件
- Docker 24+ and Docker Compose Plugin
- Ports available: 80 (nginx)
- Optional: curl or HTTP client

---

## 1) Clone and configure / 克隆与配置

```bash
git clone <your-repo-url>.git
cd <repo>
cp .env.example .env
# (optional) copy infra env template
cp infra/env.example infra/.env || true
```

Edit .env as needed. Minimal defaults work for local runs. / 如有需要编辑 .env；默认值已适配本地运行。

---

## 2) Start stack / 启动服务

```bash
docker compose -f infra/docker-compose.yml up -d --build
```

This brings up Postgres, Redis, API, Celery worker/beat, Flower, and nginx. The API container applies Alembic migrations automatically.

该命令会启动 Postgres、Redis、API、Celery worker/beat、Flower 与 nginx。API 容器会自动执行数据库迁移。

---

## 3) Access URLs / 访问地址
- API health: http://localhost/api/healthz
- Readiness: http://localhost/api/readyz
- Swagger UI: http://localhost/api/docs
- Flower: http://localhost/flower

---

## 4) First user (admin) / 创建首个用户（管理员）

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

## 5) Create a project / 创建项目
```bash
TOKEN=<paste-access-token>

curl -X POST http://localhost/api/v1/projects \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Demo","key":"DEMO","description":"Quickstart project"}'
# capture returned project id as PROJECT
```

---

## 6) Demo case and run / 示例用例与执行

1) Create an API definition / 创建 API 定义
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

2) Create a minimal test case (assert status 200) / 创建最小化用例（仅断言 200）
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

3) Trigger execution / 触发执行
```bash
curl -X POST http://localhost/api/v1/projects/$PROJECT/execute/case/$CASE_ID \
  -H "Authorization: Bearer $TOKEN"
# note report_id from response as REPORT_ID
```

4) Check report / 查看报告
```bash
curl http://localhost/api/v1/reports/$REPORT_ID -H "Authorization: Bearer $TOKEN"
```

Status should become "passed" shortly. / 片刻后状态应为 "passed"。

---

## 7) Shutdown / 关闭
```bash
docker compose -f infra/docker-compose.yml down
```

---

## Next steps / 下一步
- Configure AI provider keys: docs/ai-providers.md
- Local development (hot reload, tests): docs/setup/local-dev.md
- CI/CD integration: docs/ci-cd.md
- Security hardening: docs/security.md

- 配置 AI 提供商：docs/ai-providers.md
- 本地开发（热重载、测试）：docs/setup/local-dev.md
- 集成 CI/CD：docs/ci-cd.md
- 安全加固：docs/security.md
