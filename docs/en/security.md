English | [中文](../zh/security.md)

# Security Guide

This document summarises key security topics for NexusTest-AI deployments: secrets rotation, API token hygiene, rate limiting, and TLS/headers at the edge.

---

## Secrets rotation

- SECRET_KEY: JWT signing key. When rotating, plan a short dual-run window to ensure both old and new tokens validate.
- SECRET_ENC_KEY: Optional data encryption key. Use a versioned format (e.g., v1:BASE64...) to enable smooth migrations.
- TOKEN_ROTATION_GRACE_SECONDS: Grace period for rotated Personal Access Tokens (if configured)

Store the above in a secure KMS/Secrets Manager with least-privilege read access and auditing.

---

## Personal Access Tokens & scopes

- Create PATs via API with minimum scopes and restricted project_ids.
- Rotation and revocation: supports rotate/revoke actions; revoked tokens return 401 on use.
- Auditing: all create/use/revoke events are recorded.

See ../../README/security-tokens.md for details (or integrate with your corporate secrets service).

---

## Application rate limits

- Nginx enforces global throttling on /api and /api/v1/auth paths: 10 r/s (burst 20); adjust in infra/nginx/nginx.conf as needed.
- The application also supports project-level policies and token-level policies (execution APIs are recommended to have dedicated limits).
- Over-limit requests return 429 with a Retry-After header.

---

## TLS and security headers

Edge (nginx) defaults include:
- X-Content-Type-Options: nosniff
- X-Frame-Options: DENY
- X-XSS-Protection: 1; mode=block
- Referrer-Policy: no-referrer-when-downgrade
- Content-Security-Policy: default-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'self'
- Optional HSTS: enable by setting HSTS_ENABLED=1 on the nginx container

Frontend/edge recommendations:
- Enable TLS in production (Ingress/Load Balancer or nginx SSL termination)
- Configure HSTS (include subdomains and preload as required)
- Configure explicit CORS whitelist (avoid "*" for CORS_ORIGINS in production)

---

## Email and notifications

- Configure SMTP_* to send emails (notifications/alerts). Supports SMTP_TLS, SENDGRID_API_KEY, MAILGUN_API_KEY, etc.
- Use a dedicated sending domain with DKIM/SPF; enable rate limit and retries (NOTIFY_*).

---

## Backups and retention

- BACKUP_* defines backup storage (local dir or S3-compatible object storage) and retention rules.
- Enable backup verification and periodic restore drills; encrypt sensitive data with a GPG public key as needed.
- REPORT_RETENTION_DAYS / AI_TASK_RETENTION_DAYS / AUDIT_LOG_RETENTION_DAYS control data lifecycle.
