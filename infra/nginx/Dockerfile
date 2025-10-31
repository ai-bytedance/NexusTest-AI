# syntax=docker/dockerfile:1.6

FROM node:18-alpine AS builder

WORKDIR /app

ARG NPM_REGISTRY=https://registry.npmmirror.com
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG USE_LOCAL_DIST=false

ENV HTTP_PROXY=$HTTP_PROXY \
    HTTPS_PROXY=$HTTPS_PROXY \
    NO_PROXY=localhost,127.0.0.1

RUN npm config set registry $NPM_REGISTRY \
    && npm config set fetch-retries 5 \
    && npm config set fetch-retry-maxtimeout 120000 \
    && npm config set fetch-retry-mintimeout 20000 \
    && npm config set audit false \
    && npm config set fund false

COPY frontend/package.json ./
COPY frontend/package-lock.json ./

RUN --mount=type=cache,target=/root/.npm \
    if [ "$USE_LOCAL_DIST" = "true" ]; then \
      echo "USE_LOCAL_DIST enabled, skipping npm ci"; \
    else \
      npm ci --prefer-offline --no-audit --no-fund; \
    fi

COPY frontend/ ./

RUN if [ "$USE_LOCAL_DIST" = "true" ]; then \
      if [ ! -d /app/dist ]; then \
        echo "frontend/dist/ is required when USE_LOCAL_DIST=true" >&2; \
        exit 1; \
      fi; \
    fi

ENV VITE_API_BASE=/api

RUN if [ "$USE_LOCAL_DIST" = "true" ]; then \
      echo "USE_LOCAL_DIST enabled, skipping npm run build"; \
    else \
      npm run build; \
    fi

FROM nginx:1.25-alpine

ARG USE_LOCAL_DIST=false

COPY infra/nginx/nginx.conf /etc/nginx/nginx.conf
COPY --from=builder /app/dist/ /usr/share/nginx/html/
