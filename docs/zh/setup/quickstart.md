[English](../../en/setup/quickstart.md) | 中文

# 快速开始（Docker Compose）

本指南使用 Docker Compose 在本地启动 NexusTest-AI，并带你完成首次登录与一个示例测试流程。

---

## 前置条件
- Docker 24+ 与 Docker Compose 插件
- 端口可用：8080（nginx 主机端口）
- 可选：curl 或其他 HTTP 客户端

---

## 1) 克隆与配置

```bash
git clone <your-repo-url>.git
cd <repo>
cp .env.example .env
# （可选）复制 infra 环境模板
cp infra/env.example infra/.env || true
```

如有需要编辑 .env；默认值已适配本地运行。

---

## 2) 启动服务

```bash
docker compose -f infra/docker-compose.yml up -d --build
```

该命令会启动 Postgres、Redis、API、Celery worker/beat、Flower 与 nginx。API 容器会自动执行数据库迁移。

---

## 3) 访问地址
- API 健康检查: http://localhost:8080/api/healthz
- 就绪检查: http://localhost:8080/api/readyz
- Swagger UI: http://localhost:8080/api/docs
- Flower: http://localhost:8080/flower

如本机的 80 端口空闲且你希望继续使用它，可在 infra/docker-compose.yml 中把 nginx 的端口映射改回 "80:80"，然后重新启动 Compose 栈。

---

## 4) 创建首个用户（管理员）

```bash
curl -X POST http://localhost:8080/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"changeme123","role":"admin"}'

curl -X POST http://localhost:8080/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"changeme123"}'
# 从响应中复制 access_token
```

---

## 5) 创建项目
```bash
TOKEN=<paste-access-token>

curl -X POST http://localhost:8080/api/v1/projects \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Demo","key":"DEMO","description":"Quickstart project"}'
# 记录返回的 project id 为 PROJECT
```

---

## 6) 示例用例与执行

1) 创建 API 定义
```bash
curl -X POST http://localhost:8080/api/v1/projects/$PROJECT/apis \
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
# 记录返回的 API id 为 API_ID
```

2) 创建最小化用例（仅断言 200）
```bash
curl -X POST http://localhost:8080/api/v1/projects/$PROJECT/test-cases \
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
# 记录返回的 case id 为 CASE_ID
```

3) 触发执行
```bash
curl -X POST http://localhost:8080/api/v1/projects/$PROJECT/execute/case/$CASE_ID \
  -H "Authorization: Bearer $TOKEN"
# 从响应中记录 report_id 为 REPORT_ID
```

4) 查看报告
```bash
curl http://localhost:8080/api/v1/reports/$REPORT_ID -H "Authorization: Bearer $TOKEN"
```

片刻后状态应为 "passed"。

---

## 7) 关闭
```bash
docker compose -f infra/docker-compose.yml down
```

---

## 下一步
- 配置 AI 提供商：../ai-providers.md
- 本地开发（热重载、测试）：./local-dev.md
- 集成 CI/CD：../ci-cd.md
- 安全加固：../security.md
