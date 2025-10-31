English | [中文](../zh/ci-cd.md)

# CI/CD Guide and CLI Usage

This guide shows how to integrate NexusTest-AI into automation pipelines using the included Python CLI (scripts/nt_cli.py) and ready-to-use examples for GitHub Actions, Jenkins, and GitLab CI.

---

## 1) CLI (scripts/nt_cli.py)

- Authenticates, triggers a suite/case execution, optionally waits, and exits with non-zero code if pass-rate is below threshold.

Prerequisites:
- Python 3.11+
- httpx

Install:
```bash
python -m pip install --upgrade pip
python -m pip install httpx
```

Environment variables:
- NT_API_BASE: Backend API base URL (required)
- NT_REPORT_BASE_URL: Optional base for human links (optional)
- NT_PROJECT_ID: Target project id (required)
- NT_SUITE_ID / NT_CASE_ID / NT_TASK_ID: one of them to execute or resume
- NT_REPORT_ID: optional when resuming
- NT_API_TOKEN or NT_EMAIL + NT_PASSWORD: auth method
- NT_PASS_THRESHOLD: pass-rate threshold, fraction (0-1) or percent (0-100), default 1.0
- NT_POLL_INTERVAL: seconds between polls, default 10
- NT_TIMEOUT: max seconds to wait, default 900
- NT_VERIFY_SSL: true/false, default true
- NT_OUTPUT_FORMAT: text|markdown|json, default text
- NT_OUTPUT_FILE: optional output path
- NT_NO_WAIT: truthy to trigger and exit immediately

Example:
```bash
python scripts/nt_cli.py \
  --base-url http://localhost:8080 \
  --project-id 123e4567-e89b-12d3-a456-426614174000 \
  --suite-id 9aa9f8b0-aaaa-4a1f-9ff0-123456789abc \
  --email runner@example.com \
  --password changeme \
  --threshold 0.9
```

Exit codes:
- 0: passed and met threshold
- 2: report failed/error
- 3: below threshold
- 4: skipped
- 1: configuration/network error

---

## 2) GitHub Actions

- A reusable workflow is included at .github/workflows/test-on-pr.yml.

Setup:
- Repository variables: NT_API_BASE, NT_PROJECT_ID, NT_SUITE_ID (optional: NT_PASS_THRESHOLD, NT_REPORT_BASE_URL)
- Repository secrets: NT_API_TOKEN or NT_EMAIL + NT_PASSWORD

Reusing example:
```yaml
jobs:
  suite:
    uses: ./.github/workflows/test-on-pr.yml
    with:
      project_id: 123e4567-e89b-12d3-a456-426614174000
      suite_id: 9aa9f8b0-aaaa-4a1f-9ff0-123456789abc
      threshold: 0.9
      base_url: https://api.example.com
    secrets:
      nt_api_token: ${{ secrets.NETTESTS_TOKEN }}
```

The workflow posts a PR comment and enforces threshold.

---

## 3) Jenkins

- The Jenkinsfile in the repo demonstrates Trigger → Wait → Publish stages.

Credentials:
- nt-api-user: username/password → NT_EMAIL/NT_PASSWORD
- nt-api-base, nt-project-id, nt-suite-id, nt-threshold: secret text variables

Flow:
1) Setup environment and install dependencies
2) Trigger with --no-wait and save nt_trigger.json
3) Wait by reading task/report id to continue polling, produce nt_result.json
4) Publish summary and enforce exit code

---

## 4) GitLab CI

- See .gitlab-ci.yml job api-tests for a drop-in example.

CI variables:
- NT_API_BASE, NT_PROJECT_ID, NT_SUITE_ID
- NT_API_TOKEN or NT_EMAIL + NT_PASSWORD
- Optional: NT_PASS_THRESHOLD, NT_REPORT_BASE_URL

Artifacts keep nt_result.json for later review.

---

## 5) Backend task support

GET /api/v1/tasks/{task_id} returns:
```json
{
  "code": "SUCCESS",
  "data": {
    "task_id": "...",
    "status": "success",
    "report_id": "...",
    "report_url": "/reports/..."
  }
}
```
CLI uses it for resuming and link building.

---

## 6) Failure criteria summary

- failed/error → exit 2
- below threshold → exit 3
- skipped → exit 4
- success above threshold → exit 0
- configuration/network errors → exit 1
