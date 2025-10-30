# Personal Access Tokens and Rate Limiting

This document explains how to create and manage Personal Access Tokens (PATs) for automation scenarios, how scopes restrict access, and how to configure per-project rate limiting policies.

## Creating a Personal Access Token

1. Authenticate to the application’s API using a regular user session (either through the UI or by logging in to obtain a JWT access token).
2. Call `POST /api/v1/tokens` with a JSON payload similar to:

   ```json
   {
     "name": "CI Pipeline",
     "scopes": ["read:projects", "execute"],
     "project_ids": ["<project-uuid>"],
     "expires_at": "2024-12-31T00:00:00Z"
   }
   ```

   The response contains a `token` field once. Store it securely – it cannot be recovered later.
3. Use the PAT in subsequent API requests by sending it as a bearer token:

   ```http
   Authorization: Bearer <token-prefix>.<token-secret>
   ```

### Supported Scopes

| Scope              | Description                                           |
| ------------------ | ----------------------------------------------------- |
| `read:projects`    | Read project metadata and listings.                   |
| `write:projects`   | Create or modify projects and membership.             |
| `read:apis`        | Read API definitions.                                 |
| `write:apis`       | Create or modify API definitions.                     |
| `read:cases`       | Read test cases and suites.                           |
| `write:cases`      | Create or modify test cases and suites.               |
| `execute`          | Trigger executions, plans, or test runs.              |
| `read:reports`     | Fetch reports and report exports.                     |
| `write:integrations` | Configure integrations and webhooks.               |
| `admin`            | Full administrative access to all endpoints.          |

Tokens with the `admin` scope implicitly satisfy all other scope checks.

### Token Rotation and Revocation

- To rotate a token, call `PATCH /api/v1/tokens/{token_id}` with `{ "action": "rotate" }`. A new secret is returned once; the previous secret stops working immediately.
- To revoke access, call the same endpoint with `{ "action": "revoke" }`. Revoked tokens return `401 Unauthorized` when used.
- Tokens can also be deleted via `DELETE /api/v1/tokens/{token_id}` which removes them from listings.

### Audit Logging

Every create, rotate, revoke, delete, and usage event generates an entry in the audit log containing the actor, token identifier, path invoked, and originating IP address.

## Configuring Rate Limits

Rate limit policies are defined per project and can optionally be assigned to individual tokens. A policy consists of one or more rules:

```json
{
  "name": "strict-ci",
  "enabled": true,
  "rules": [
    {
      "per_minute": 60,
      "burst": 10,
      "path_patterns": ["/api/v1/projects/{project_id}/execute/*"],
      "methods": ["POST"]
    }
  ]
}
```

### Managing Policies via API

1. Create a policy: `POST /api/v1/projects/{project_id}/rate-limit-policies`
2. Set the default policy: `PUT /api/v1/projects/{project_id}/rate-limit-policies/default`
3. View current policies: `GET /api/v1/projects/{project_id}/rate-limit-policies`
4. Inspect effective limits (optionally for a token):
   `GET /api/v1/projects/{project_id}/rate-limit-policies/effective?token_id=<token-uuid>`

Requests exceeding the configured thresholds return HTTP `429 Too Many Requests` with a `Retry-After` header specifying when the client may retry.

## Usage in CI/CD Pipelines

Store the provisioned PAT in the CI secret manager and supply it as the bearer token when invoking the platform’s API. Prefer the minimum set of scopes needed by the pipeline and restrict the token’s project access to only the projects it must operate against.

For example, to trigger an execution:

```bash
curl -H "Authorization: Bearer $PAT" \
     -X POST \
     https://api.example.com/api/v1/projects/<project-id>/execute/suite/<suite-id>
```

Monitor the rate limit headers and audit logs to ensure automation jobs operate within agreed policies.
