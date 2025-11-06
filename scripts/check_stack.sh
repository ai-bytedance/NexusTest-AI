#!/usr/bin/env bash
# Comprehensive stack self-check helper for local/docker deployments.

set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE_DEFAULT="$ROOT_DIR/infra/docker-compose.yml"
COMPOSE_FILE="${COMPOSE_FILE:-$COMPOSE_FILE_DEFAULT}"

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "compose file not found: $COMPOSE_FILE" >&2
  exit 1
fi

if docker compose version >/dev/null 2>&1; then
  COMPOSE_CMD=(docker compose -f "$COMPOSE_FILE")
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE_CMD=(docker-compose -f "$COMPOSE_FILE")
else
  echo "docker compose plugin or docker-compose binary is required" >&2
  exit 1
fi

compose_exec() {
  "${COMPOSE_CMD[@]}" exec -T "$@"
}

overall=0

print_check_result() {
  local label="$1"
  local status="$2"
  if [[ "$status" -eq 0 ]]; then
    echo "$label->OK"
  else
    echo "$label->FAIL"
    overall=1
  fi
}

# 1. Reach API health endpoint directly from nginx container (via service discovery)
if compose_exec nginx sh -c 'curl -sf http://api:8000/health >/dev/null'; then
  print_check_result "api" 0
else
  print_check_result "api" 1
fi

# 2. Verify nginx can proxy to API using public path
if compose_exec nginx sh -c 'curl -sf http://nginx/api/health >/dev/null'; then
  print_check_result "nginx" 0
else
  print_check_result "nginx" 1
fi

# 3. Confirm API process is bound to 0.0.0.0:8000
if compose_exec api sh -c 'ss -lntp 2>/dev/null | grep -q ":8000" || netstat -lntp 2>/dev/null | grep -q ":8000"'; then
  print_check_result "api-port" 0
else
  print_check_result "api-port" 1
fi

# 4. Dump nginx configuration and ensure /api/ proxy targets api_upstream without trailing slash
nginx_dump="$(mktemp)"
trap 'rm -f "$nginx_dump"' EXIT
if compose_exec nginx nginx -T >"$nginx_dump" 2>&1; then
  if grep -Fq "location /api/ {" "$nginx_dump" \
    && grep -Fq "proxy_pass http://api_upstream;" "$nginx_dump" \
    && ! grep -Fq "proxy_pass http://api_upstream/" "$nginx_dump"; then
    print_check_result "nginx-proxy" 0
  else
    print_check_result "nginx-proxy" 1
    echo "nginx configuration does not proxy /api/ to api_upstream as expected" >&2
  fi
else
  print_check_result "nginx-proxy" 1
  echo "failed to execute 'nginx -T' inside nginx container" >&2
fi

# 5. Optional login probe (disabled unless payload is provided explicitly)
if [[ -n "${CHECK_STACK_LOGIN_PAYLOAD:-}" ]]; then
  response="$(compose_exec nginx sh -c "curl -s -o /tmp/check-stack-login.out -w '%{http_code}' -H 'Content-Type: application/json' -X POST -d '$CHECK_STACK_LOGIN_PAYLOAD' http://nginx/api/v1/auth/login")" || true
  compose_exec nginx cat /tmp/check-stack-login.out 2>/dev/null || true
  if [[ "$response" = "200" || "$response" = "401" ]]; then
    print_check_result "login-endpoint" 0
  else
    print_check_result "login-endpoint" 1
  fi
  compose_exec nginx rm -f /tmp/check-stack-login.out 2>/dev/null || true
else
  echo "login-endpoint->SKIP (set CHECK_STACK_LOGIN_PAYLOAD to probe)"
fi

exit $overall
