[English](../../en/deploy/docker-compose.md) | 中文

# 使用 Docker Compose 部署

本文档说明 infra/docker-compose.yml 中的默认服务，并介绍如何通过覆盖文件扩展（MailHog、Prometheus、Grafana 等）。

---

## 默认服务

- postgres：Postgres 15，使用命名卷
- redis：Redis 7
- api：FastAPI 后端（启动时自动应用 Alembic 迁移）
- celery-worker：后台工作进程（队列：cases、suites）
- celery-beat：周期调度器
- flower：Celery 监控 UI（通过 nginx 暴露在 /flower）
- nginx：对外暴露主机 8080 端口的反向代理，添加安全响应头与基础限流

访问入口：
- http://localhost:8080/api/healthz
- http://localhost:8080/api/readyz
- http://localhost:8080/api/docs
- http://localhost:8080/flower

如需继续使用 80 端口且本机无冲突，可在 infra/docker-compose.yml 中将 nginx 的端口映射改回 "80:80" 后再启动。

启动：
```bash
docker compose -f infra/docker-compose.yml up -d --build
```

停止：
```bash
docker compose -f infra/docker-compose.yml down
```

日志：
```bash
docker compose -f infra/docker-compose.yml logs -f
```

---

## 环境变量文件

- 该栈会将仓库根目录的 .env 注入 API、workers 与 Flower。
- nginx 支持通过容器环境变量 HSTS_ENABLED=1 启用可选 HSTS（在 override 文件或 compose 命令中设置）。

---

## 通过覆盖文件启用可选服务

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

随后按常规方式启动，Compose 会自动加载 docker-compose.override.yml。

Prometheus 抓取配置示例（prometheus.yml）：
```yaml
global:
  scrape_interval: 15s
scrape_configs:
  - job_name: nexustest-api
    static_configs:
      - targets: ["api:9464"]
```

---

## 邮件测试

- 配置 SMTP_* 变量使用真实 SMTP，或在启用 MailHog 后将 SMTP_HOST=mailhog、SMTP_PORT=1025。

---

## Agent 说明

- Agent 是后端中的逻辑实体（心跳与令牌管理）。默认 Compose 不需要单独的 Agent 容器。远端执行器可通过 API + 令牌进行集成。

---

## 生产环境提示

- 优先使用独立的反向代理/Ingress，实现 TLS 卸载与证书管理。
- 将有状态存储（Postgres/Redis）与应用生命周期解耦，启用持久化卷与备份。
- 明确配置 CORS_ORIGINS，避免在生产环境中使用 "*"。
- 如需监控，启用 METRICS_ENABLED 并抓取 API 容器的 /metrics。
