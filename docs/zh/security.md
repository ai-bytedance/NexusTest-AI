[English](../en/security.md) | 中文

# 安全指南

本文汇总 NexusTest-AI 部署的安全要点：密钥轮换、API Token 管理、限流策略、边缘 TLS 与安全响应头。

---

## 密钥轮换

- SECRET_KEY：JWT 签名密钥。轮换时需短期双运行窗口，确保新旧颁发的令牌都可验证。
- SECRET_ENC_KEY：数据加密密钥（如需）。采用版本化格式（示例：v1:BASE64...），通过新版本前缀实现平滑迁移。
- TOKEN_ROTATION_GRACE_SECONDS：个人令牌（PAT）旋转后的宽限期（如配置）。

建议将上述密钥存储于安全的 KMS/Secrets Manager，并限制只读权限与审计。

---

## 个人访问令牌与权限范围

- 通过 API 创建 PAT，并最小化 scopes 和 project_ids。
- 轮换与吊销：支持 rotate/revoke 动作；吊销后使用返回 401。
- 审计：所有创建/使用/吊销事件会记录到审计日志。

详见 ../../README/security-tokens.md（或在企业环境中集成到统一的密钥服务）。

---

## 应用层限流

- Nginx 在 /api 与 /api/v1/auth 路径做全局节流：10 r/s（突发 20），可按需调整 infra/nginx/nginx.conf。
- 应用内还支持项目级策略与 Token 级策略（执行类接口建议单独限制）。
- 超限返回 429，带 Retry-After 头。

---

## TLS 与安全响应头

边缘（nginx）默认包含：
- X-Content-Type-Options: nosniff
- X-Frame-Options: DENY
- X-XSS-Protection: 1; mode=block
- Referrer-Policy: no-referrer-when-downgrade
- Content-Security-Policy: default-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'self'
- 可选 HSTS：通过在 nginx 容器上设置 HSTS_ENABLED=1 启用

前端/边缘建议：
- 在生产环境启用 TLS（Ingress/负载均衡或 nginx 终止 SSL）
- 配置 HSTS（含子域与预加载，如业务需求）
- 配置 CORS 白名单（生产环境不要将 CORS_ORIGINS 设为 "*")

---

## 邮件与通知通道

- SMTP_* 配置用于发送邮件（通知/告警）。支持 SMTP_TLS、SENDGRID_API_KEY、MAILGUN_API_KEY 等。
- 建议使用专用发信域名与 DKIM/SPF 配置，并开启速率限制与重试策略（NOTIFY_*）。

---

## 备份与留存

- BACKUP_* 配置定义备份存储（本地目录或 S3 兼容对象存储）与留存规则。
- 建议开启备份校验与周期性恢复演练；敏感数据可启用 GPG 公钥加密。
- REPORT_RETENTION_DAYS / AI_TASK_RETENTION_DAYS / AUDIT_LOG_RETENTION_DAYS 用于数据生命周期管理。
