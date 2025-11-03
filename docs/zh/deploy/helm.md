[English](../../en/deploy/helm.md) | 中文

# 使用 Helm 部署

本文介绍通过随仓库提供的 Helm Chart（charts/nexustest-ai）在 Kubernetes 中部署 NexusTest-AI。

---

## 前置条件
- Kubernetes 1.24+
- Helm 3.12+
- 可用的后端镜像仓库（或使用默认值）

---

## 最简 values 配置

创建 values.local.yaml：

```yaml
image:
  repository: ghcr.io/example/nexustest-ai/backend
  tag: latest

config:
  create: true
  env:
    APP_ENV: production
    CORS_ORIGINS: "https://app.example.com"

secrets:
  create: true
  stringData:
    SECRET_KEY: "replace-me"
    DATABASE_URL: "postgresql+psycopg://app:app@postgresql:5432/app"
    REDIS_URL: "redis://redis:6379/0"


nginx:
  enabled: true
  ingress:
    enabled: true
    hosts:
      - host: app.example.com
        paths:
          - path: /
            pathType: Prefix
    tls:
      - secretName: nexustest-ai-tls
        hosts:
          - app.example.com
```

安装：
```bash
helm upgrade --install nexustest-ai charts/nexustest-ai -f values.local.yaml -n nexustest --create-namespace
```

---

## 水平扩缩容

- API：设置 api.replicaCount 或启用 api.autoscaling
- Celery workers：设置 celeryWorker.replicaCount 或 autoscaling
- Flower/nginx：按需调整 replicaCount

```yaml
api:
  replicaCount: 2
  autoscaling:
    enabled: true
    minReplicas: 2
    maxReplicas: 10

celeryWorker:
  replicaCount: 2
  autoscaling:
    enabled: true
    minReplicas: 2
    maxReplicas: 10
```

---

## 指标采集

- 在使用 Prometheus Operator 时启用 API 指标与可选的 ServiceMonitor：

```yaml
api:
  metrics:
    enabled: true
    serviceMonitor:
      enabled: true
      interval: 30s
      scrapeTimeout: 10s
```

- Celery exporter：启用 celeryWorker.metrics（使用 ovhcom/celery-exporter）

```yaml
celeryWorker:
  metrics:
    enabled: true
```

---

## 外部存储

通过禁用内置 Postgres/Redis 并在 secrets 中设置 URL 使用外部存储：

```yaml
postgresql:
  enabled: false
redis:
  enabled: false

secrets:
  stringData:
    DATABASE_URL: postgresql+psycopg://user:pass@db.example.com:5432/app
    REDIS_URL: redis://cache.example.com:6379/0
```

---

## 安全

- 配置 CORS_ORIGINS、SECRET_KEY、SECRET_ENC_KEY
- 可选：通过环境变量在 nginx 上启用 HSTS
- 根据集群策略设置资源 limits/requests 与 PodSecurityContext

---

## 卸载
```bash
helm uninstall nexustest-ai -n nexustest
```
