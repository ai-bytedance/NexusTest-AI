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
- nginx: reverse proxy binding 0.0.0.0:8080 → 80 in the container (security headers + basic rate limits) so the UI is reachable from other machines on your network

Access points:
- http://localhost:8080/api/healthz
- http://localhost:8080/api/readyz
- http://localhost:8080/api/docs
- http://localhost:8080/flower
- http://<host>:8080/ (from another device on the LAN, assuming host firewall allows 8080)

If you prefer a different host port, edit infra/docker-compose.yml and update the nginx service ports. The default uses "0.0.0.0:8080:80" so remote clients can reach the stack without extra overrides.

> Builder note: Compose commands in this repository set `COMPOSE_DOCKER_CLI_BUILD=0` and `DOCKER_BUILDKIT=0` to force the classic Docker builder and avoid docker/dockerfile frontend pulls. Switch both variables to `1` once your network allows BuildKit again.

Start:
```bash
COMPOSE_DOCKER_CLI_BUILD=0 DOCKER_BUILDKIT=0 docker compose -f infra/docker-compose.yml up -d postgres redis
COMPOSE_DOCKER_CLI_BUILD=0 DOCKER_BUILDKIT=0 docker compose -f infra/docker-compose.yml build api celery-worker celery-beat flower --no-cache --progress=plain
COMPOSE_DOCKER_CLI_BUILD=0 DOCKER_BUILDKIT=0 docker compose -f infra/docker-compose.yml up -d
```
The API, worker, beat, and Flower services now build locally from `backend/Dockerfile` and share the `nexustest-backend:local` image tag (drop `--no-cache` after the first successful build if you prefer cached layers).

> Tip: once the docker/dockerfile frontend is reachable again, set `COMPOSE_DOCKER_CLI_BUILD=1` and `DOCKER_BUILDKIT=1` (for example: `COMPOSE_DOCKER_CLI_BUILD=1 DOCKER_BUILDKIT=1 docker compose …`) and configure registry mirrors if base image pulls are slow in your environment.

Stop:
```bash
docker compose -f infra/docker-compose.yml down
```

Logs:
```bash
docker compose -f infra/docker-compose.yml logs -f
```

---

## Frontend build configuration

The nginx image builds the Vite frontend during `docker compose build nginx`. If your network requires an npm mirror or corporate proxy, adjust the build arguments in `infra/docker-compose.yml`:

```yaml
services:
  nginx:
    build:
      args:
        NODE_BASE_IMAGE: ${NODE_BASE_IMAGE:-node:18-alpine}
        NGINX_BASE_IMAGE: ${NGINX_BASE_IMAGE:-registry.cn-hangzhou.aliyuncs.com/dockerhub/nginx:1.25-alpine}
        NPM_REGISTRY: https://registry.npmmirror.com
        # To use the official Docker Hub tag once connectivity allows:
        # NGINX_BASE_IMAGE: nginx:1.25-alpine
        # NODE_BASE_IMAGE: mirror.gcr.io/library/node:18-alpine
        # HTTP_PROXY: http://proxy.yourcorp:8080
        # HTTPS_PROXY: http://proxy.yourcorp:8080
        # USE_LOCAL_DIST: "true"
```

- `NGINX_BASE_IMAGE` defaults to the Alibaba Cloud Docker Hub mirror so builds succeed in restricted networks. Override it via `.env` or `export NGINX_BASE_IMAGE=nginx:1.25-alpine` once Docker Hub is reachable.
- `NODE_BASE_IMAGE` keeps the Docker Hub default; uncomment the mirror example above if you need to swap registries.
- `NPM_REGISTRY` defaults to the npm mirror shown above and enables additional fetch retries inside the image build.
- Uncomment `HTTP_PROXY` / `HTTPS_PROXY` if you need to route traffic through a proxy.
- Set `USE_LOCAL_DIST=true` to reuse a prebuilt `frontend/dist/` directory.

When `USE_LOCAL_DIST=true`, ensure `frontend/dist/` exists (e.g. run `npm ci && npm run build` locally). The Dockerfile will skip `npm ci` / `npm run build` and copy those artifacts straight into nginx, which allows builds to succeed even without external npm access.

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
