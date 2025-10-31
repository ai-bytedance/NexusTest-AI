English | [中文](../../zh/deploy/docker-compose.md)

# Docker Compose Deployment

This document explains the default stack shipped in infra/docker-compose.yml and how to extend it with optional services (MailHog, Prometheus, Grafana, etc.).

---

## Default services

- postgres: Postgres 15 with a named volume
- redis: Redis 7
- api: FastAPI backend (applies Alembic migrations on start)
- celery-worker: background workers (queues: cases,suites)
- celery-beat: periodic scheduler
- flower: Celery monitoring UI (exposed through nginx at /flower)
- nginx: reverse proxy exposing port 8080 on the host, adds security headers and basic rate limits

Access points:
- http://localhost:8080/api/healthz
- http://localhost:8080/api/readyz
- http://localhost:8080/api/docs
- http://localhost:8080/flower

If you prefer to keep using port 80 and it is free on your machine, edit infra/docker-compose.yml to change the nginx service ports back to "80:80" before starting the stack.

Start:
```bash
docker compose -f infra/docker-compose.yml up -d postgres redis
docker compose -f infra/docker-compose.yml build api celery-worker celery-beat flower --no-cache --progress=plain
docker compose -f infra/docker-compose.yml up -d
```
The API, worker, beat, and Flower services now build locally from `backend/Dockerfile` and share the `nexustest-backend:local` image tag (drop `--no-cache` after the first successful build if you prefer cached layers).

> Tip: enable BuildKit (`DOCKER_BUILDKIT=1 docker compose …`) and configure registry mirrors if base image pulls are slow in your environment.

Stop:
```bash
docker compose -f infra/docker-compose.yml down
```

Logs:
```bash
docker compose -f infra/docker-compose.yml logs -f
```

---

## Environment files

- The stack reads ../.env into API, workers, and Flower.
- nginx supports optional HSTS via container env HSTS_ENABLED=1 (set in an override file or docker-compose command).

---

## Optional services via override

Create infra/docker-compose.override.yml with the services you need (or use Compose profiles if you maintain multiple variants).

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

## Email testing

- Set SMTP_* to point to a real SMTP or route mail via MailHog SMTP (smtp://mailhog:1025) if you add MailHog.

---

## Agents note

- Agents are a logical concept tracked by the backend (with heartbeats and tokens). There is no separate "agent container" required in the default Compose stack. Remote agents can integrate by calling API endpoints with their token.

---

## Production notes

- Prefer a dedicated reverse proxy/ingress with TLS offload and managed certificates.
- Separate stateful stores (Postgres/Redis) from app lifecycle and enable persistent volumes and backups.
- Configure CORS_ORIGINS explicitly; avoid "*" in production.
- Consider external monitoring stacks; enable METRICS_ENABLED and scrape /metrics on the API container.
