# Deploying NexusTest AI on Kubernetes

This guide explains how to package and run the NexusTest AI platform on Kubernetes with Helm. The chart delivers API, Celery workers/beat, Flower, an NGINX edge proxy, and optional Postgres/Redis dependencies with production-friendly defaults for scaling, resiliency, and observability.

## Prerequisites

- A Kubernetes cluster (v1.25 or newer recommended) with sufficient capacity.
- `kubectl` and `helm` (v3.11+) configured for the target cluster.
- Container registry credentials if your images are not public (configure via `imagePullSecrets`).
- TLS issuer (e.g. [cert-manager](https://cert-manager.io)) if you plan to terminate HTTPS via Ingress.
- [Prometheus Operator](https://github.com/prometheus-operator/prometheus-operator) (optional) for `ServiceMonitor` support.
- Persistent storage class for Postgres (if using the bundled database).

## Directory layout

```
charts/
  nexustest-ai/
    Chart.yaml
    values.yaml
    templates/
```

## Quick start (all-in-one install)

Create a values file (for example `values-prod.yaml`) and adjust for your environment:

```yaml
image:
  repository: ghcr.io/your-org/nexustest-ai-backend
  tag: "2024.10.15"
  pullPolicy: IfNotPresent

config:
  env:
    APP_ENV: production
    CORS_ORIGINS: "https://app.your-domain.com"
    PROVIDER: deepseek

secrets:
  stringData:
    SECRET_KEY: "generate-a-strong-secret"
    SECRET_ENC_KEY: "optional-extra-secret"
    DEEPSEEK_API_KEY: "${DEEPSEEK_API_KEY}"

nginx:
  ingress:
    enabled: true
    className: nginx
    annotations:
      cert-manager.io/cluster-issuer: letsencrypt-prod
    hosts:
      - host: app.your-domain.com
        paths:
          - path: /
            pathType: Prefix
    tls:
      - secretName: nexustest-ai-tls
        hosts:
          - app.your-domain.com
  config:
    upstreams:
      frontend:
        enabled: true
        url: "http://frontend.default.svc.cluster.local:4173"  # point to your SPA service

api:
  replicaCount: 2
  resources:
    requests:
      cpu: 250m
      memory: 512Mi
    limits:
      cpu: 1
      memory: 1Gi
  autoscaling:
    enabled: true
    minReplicas: 2
    maxReplicas: 6

celeryWorker:
  replicaCount: 2
  resources:
    requests:
      cpu: 250m
      memory: 512Mi
    limits:
      cpu: 1
      memory: 1Gi
  autoscaling:
    enabled: true
    minReplicas: 2
    maxReplicas: 8

api:
  metrics:
    enabled: true
    serviceMonitor:
      enabled: true

celeryWorker:
  metrics:
    enabled: true
    command:
      - /bin/sh
      - -c
      - "celery-exporter --broker-url=$(REDIS_URL) --port=9540"

postgresql:
  persistence:
    size: 20Gi

redis:
  persistence:
    enabled: true
    size: 5Gi
```

Install the release:

```bash
helm upgrade --install nexustest-ai ./charts/nexustest-ai \
  --namespace nexus --create-namespace \
  -f values-prod.yaml
```

### Validating the render

Before applying, you can inspect the rendered manifests locally:

```bash
helm template nexustest-ai ./charts/nexustest-ai -f values-prod.yaml > rendered.yaml
```

Use [`kubeval`](https://www.kubeval.com/) or [`kubectl diff`](https://kubernetes.io/docs/tasks/manage-kubernetes-objects/declarative-config/#diff-before-applying) for an additional safety net.

## Managing secrets

- The chart wraps non-sensitive configuration in a `ConfigMap` and sensitive data in a `Secret`.
- Override any secret entry by setting `secrets.stringData.<KEY>`.
- External providers: set `DEEPSEEK_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc. in the `secrets` section.
- Database/Redis URLs are computed automatically when the bundled services are enabled. To use external services, disable the internal component and supply connection strings:

```yaml
postgresql:
  enabled: false

redis:
  enabled: false

secrets:
  stringData:
    DATABASE_URL: postgresql://user:pass@db.example.com:5432/app
    REDIS_URL: redis://:pass@redis.example.com:6379/0
```

## Ingress, TLS & WebSockets

- The chart exposes an internal NGINX deployment (`nginx.enabled=true`) that routes:
  - `/` → frontend SPA (configure `nginx.config.upstreams.frontend` to point at your UI service).
  - `/api/` → FastAPI service.
  - `/flower/` → Celery Flower dashboard.
  - `/ws/` → FastAPI WebSocket endpoint.
- Enable TLS via Ingress using cert-manager:

```yaml
nginx:
  ingress:
    enabled: true
    className: nginx
    annotations:
      cert-manager.io/cluster-issuer: letsencrypt-prod
    tls:
      - secretName: nexustest-ai-tls
        hosts:
          - app.your-domain.com
```

## Database migrations

A pre-install/upgrade hook runs `alembic upgrade head` via the backend image. Check job status if schema changes fail:

```bash
kubectl get jobs -n nexus
kubectl logs job/nexustest-ai-migrations -n nexus
```

## Horizontal scaling & resilience

- HPA targets CPU and memory utilization for both the API and Celery workers. Tune thresholds with `api.autoscaling` and `celeryWorker.autoscaling`.
- `PodDisruptionBudget` ensures at least one API and one worker remain during voluntary disruptions.
- Configure node targeting via `nodeSelector`, `tolerations`, and `affinity` on each workload (or globally via the values file) to spread across zones.
- Readiness/Startup probes hit FastAPI `/api/readyz` and issue Celery `inspect ping` commands to ensure queue availability before routing traffic.
- All workloads run as non-root by default (`runAsUser: 1000`). Adjust the security context only if your base images require it.

### Cost-saving tips

- Lower replica counts and disable HPA in dev/staging.
- Turn off the bundled Postgres/Redis when using managed services.
- Reduce resource requests/limits cautiously after monitoring actual usage via Prometheus/Grafana.
- Scale Flower and Celery Beat to one replica (default) unless your workload requires more.

## Observability

- Enable FastAPI/uvicorn metrics by exposing the `/metrics` endpoint on the API container (update the application or add middleware) and toggle `api.metrics.enabled=true`.
- If Prometheus Operator is installed, set `api.metrics.serviceMonitor.enabled=true` to generate a `ServiceMonitor` resource.
- The chart supports an optional Celery exporter sidecar. Provide the command/args to your preferred exporter (e.g. [`ovhcom/celery-exporter`](https://github.com/ovh/celery-exporter)).
- Structured JSON logs are emitted by default; forward them with your cluster logging stack (e.g. Fluent Bit → OpenSearch).
- Suggested dashboards (import into Grafana):
  - FastAPI / Uvicorn dashboard (ID 13939) for request latency.
  - Celery exporter dashboard (ID 11985) for worker queues.

## Upgrades & rollbacks

- Apply changes with `helm upgrade --install ...`.
- To roll back quickly:

```bash
helm rollback nexustest-ai <REVISION> -n nexus
```

- Monitor rollout status:

```bash
kubectl rollout status deployment/nexustest-ai-api -n nexus
kubectl rollout status deployment/nexustest-ai-celery-worker -n nexus
```

## Verification checklist

- `helm template` renders without errors.
- Migrations job completes successfully during install/upgrade.
- Ingress routes `/`, `/api/`, `/flower/`, and `/ws/` appropriately.
- Readiness probes for API and Celery workloads become `Ready`.
- HPA observes metrics and scales under load.
- Secrets are mounted into pods; confirm no secrets are logged.

## Troubleshooting

- `kubectl describe pod/<name>` – inspect events for probe or scheduling failures.
- `kubectl logs` – API/worker logs are structured JSON (`app.logging`).
- Celery worker readiness probe failures usually indicate Redis/DB connectivity; confirm `REDIS_URL` and `DATABASE_URL` values.
- If the migrations job fails, check DB credentials or schema permissions.
- For Ingress TLS issues, confirm cert-manager certificates and DNS records.

## Further customization

Refer to [`values.yaml`](../../charts/nexustest-ai/values.yaml) for additional toggles such as pod-level security contexts, topology spread constraints, and custom annotations/labels for every component.
