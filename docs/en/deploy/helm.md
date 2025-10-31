English | [中文](../../zh/deploy/helm.md)

# Helm Deployment

This guide shows how to deploy NexusTest-AI on Kubernetes using the bundled Helm chart (charts/nexustest-ai).

---

## Prerequisites
- Kubernetes 1.24+
- Helm 3.12+
- A container registry with your backend image (or use defaults)

---

## Values quick start

Create values.local.yaml:

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
    DATABASE_URL: "postgresql+psycopg2://app:app@postgresql:5432/app"
    REDIS_URL: "redis://redis:6379/0"
    DEEPSEEK_API_KEY: ""

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

Install:
```bash
helm upgrade --install nexustest-ai charts/nexustest-ai -f values.local.yaml -n nexustest --create-namespace
```

---

## Scaling

- API: set api.replicaCount or enable api.autoscaling
- Celery workers: set celeryWorker.replicaCount or autoscaling
- Flower/nginx: adjust replicaCount as needed

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

## Metrics

- Enable API metrics and optional ServiceMonitor when using Prometheus Operator:

```yaml
api:
  metrics:
    enabled: true
    serviceMonitor:
      enabled: true
      interval: 30s
      scrapeTimeout: 10s
```

- Celery exporter: enable celeryWorker.metrics (uses ovhcom/celery-exporter)

```yaml
celeryWorker:
  metrics:
    enabled: true
```

---

## External stores

Use external Postgres/Redis by disabling internal ones and setting URLs in secrets:

```yaml
postgresql:
  enabled: false
redis:
  enabled: false

secrets:
  stringData:
    DATABASE_URL: postgresql+psycopg2://user:pass@db.example.com:5432/app
    REDIS_URL: redis://cache.example.com:6379/0
```

---

## Security

- Configure CORS_ORIGINS, SECRET_KEY, SECRET_ENC_KEY
- Optionally enable HSTS on nginx via env
- Consider setting resources limits/requests and PodSecurityContext per your cluster policy

---

## Uninstall
```bash
helm uninstall nexustest-ai -n nexustest
```
