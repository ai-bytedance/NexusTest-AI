# Docker Compose Deployment / 使用 Docker Compose 部署

This document explains the default stack shipped in infra/docker-compose.yml and how to extend it with optional services (MailHog, Prometheus, Grafana, etc.).

本文档说明 infra/docker-compose.yml 中的默认服务，并介绍如何通过覆盖文件扩展（MailHog、Prometheus、Grafana 等）。

---

## Default services / 默认服务

- postgres: Postgres 15 with a named volume
- redis: Redis 7
- api: FastAPI backend (applies Alembic migrations on start)
- celery-worker: background workers (queues: cases,suites)
- celery-beat: periodic scheduler
- flower: Celery monitoring UI (exposed through nginx at /flower)
- nginx: reverse proxy on port 80, adds security headers and basic rate limits

Access points / 访问入口:
- http://localhost/api/healthz
- http://localhost/api/readyz
- http://localhost/api/docs
- http://localhost/flower

Start / 启动:
```bash
docker compose -f infra/docker-compose.yml up -d --build
```

Stop / 停止:
```bash
docker compose -f infra/docker-compose.yml down
```

Logs / 日志:
```bash
docker compose -f infra/docker-compose.yml logs -f
```

---

## Environment files / 环境变量文件

- The stack reads ../.env into API, workers, and Flower.
- 可根据需要复制并编辑 .env：cp .env.example .env
- nginx supports optional HSTS via container env HSTS_ENABLED=1 (set in an override file or docker-compose command).

---

## Optional services via override / 通过覆盖文件启用可选服务

Create infra/docker-compose.override.yml with the services you need (or use Compose profiles if you maintain multiple variants).

在 infra/docker-compose.override.yml 中添加扩展服务（或使用 Docker Compose profiles 在同一文件中按需启用不同服务集），例如：

```yaml
version: "3.9"

services:
  mailhog:
    image: mailhog/mailhog:v1.0.1
    ports:
      - "8025:8025"
    environment:
      - MH_STORAGE=memory
    restart: unless-stopped

  prometheus:
    image: prom/prometheus:v2.53.0
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml:ro
    ports:
      - "9090:9090"
    restart: unless-stopped

  grafana:
    image: grafana/grafana:10.4.2
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_USER=admin
      - GF_SECURITY_ADMIN_PASSWORD=admin
    restart: unless-stopped

  api:
    environment:
      METRICS_ENABLED: "true"
      METRICS_PORT: 9464

  nginx:
    environment:
      HSTS_ENABLED: "1"
```

Then start as usual. Compose auto-loads docker-compose.override.yml.

随后按常规方式启动，Compose 会自动加载 override 文件。

Prometheus scrape config example (prometheus.yml):
```yaml
global:
  scrape_interval: 15s
scrape_configs:
  - job_name: nexustest-api
    static_configs:
      - targets: ["api:9464"]
```

---

## Email testing / 邮件测试

- Set SMTP_* to point to a real SMTP or route mail via MailHog SMTP (smtp://mailhog:1025) if you add MailHog.
- 配置 SMTP_* 变量使用真实 SMTP，或在启用 MailHog 后将 SMTP_HOST=mailhog, SMTP_PORT=1025。

---

## Agents note / Agent 说明

- Agents are a logical concept tracked by the backend (with heartbeats and tokens). There is no separate "agent container" required in the default Compose stack. Remote agents can integrate by calling API endpoints with their token.
- Agent 是后端中的逻辑实体（心跳与令牌管理）。默认 Compose 不需要单独的 Agent 容器。远端执行器可通过 API + 令牌进行集成。

---

## Production notes / 生产环境提示

- Prefer a dedicated reverse proxy/ingress with TLS offload and managed certificates.
- Separate stateful stores (Postgres/Redis) from app lifecycle and enable persistent volumes and backups.
- Configure CORS_ORIGINS explicitly; avoid "*" in production.
- Consider external monitoring stacks; enable METRICS_ENABLED and scrape /metrics on the API container.
