# CI/CD Cookbook and API Trigger Examples

This guide walks through the end-to-end setup for integrating NetTests into your automation pipelines. It covers the lightweight Python CLI (`scripts/nt_cli.py`), ready-to-use workflow examples for GitHub Actions, Jenkins, and GitLab CI, plus the supporting backend endpoint to simplify result retrieval.

---

## 1. CLI Utility (`scripts/nt_cli.py`)

The CLI authenticates with the NetTests backend, triggers a suite/case execution, polls for completion, and returns a non-zero exit code when the pass-rate threshold is not met.

### Requirements

- Python 3.9+
- [httpx](https://www.python-httpx.org/)

Install dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install httpx
```

### Environment variables

| Variable | Description |
| --- | --- |
| `NT_API_BASE` | **Required.** Backend API base URL (e.g. `https://api.example.com`). |
| `NT_REPORT_BASE_URL` | Optional. Base URL used when constructing report links (defaults to `NT_API_BASE`). |
| `NT_PROJECT_ID` | **Required.** Project identifier that owns the suite/case. |
| `NT_SUITE_ID` | Suite identifier to execute. Provide one of `NT_SUITE_ID`, `NT_CASE_ID`, or `NT_TASK_ID`. |
| `NT_CASE_ID` | Case identifier to execute. |
| `NT_TASK_ID` | Resume an existing execution by task ID. |
| `NT_REPORT_ID` | Optional when resuming; skips an extra lookup if provided. |
| `NT_API_TOKEN` | Personal access token for bearer auth. Provide this **or** `NT_EMAIL`/`NT_PASSWORD`. |
| `NT_EMAIL` / `NT_PASSWORD` | Credentials for login when a token is not available. |
| `NT_PASS_THRESHOLD` | Pass-rate threshold (fraction `0-1` or percentage `0-100`). Defaults to `1.0` (100%). |
| `NT_POLL_INTERVAL` | Seconds between poll attempts. Default: `10`. |
| `NT_TIMEOUT` | Maximum seconds to wait for completion. Default: `900` (15 minutes). |
| `NT_VERIFY_SSL` | Toggle TLS verification (`true`/`false`). Default: `true`. |
| `NT_OUTPUT_FORMAT` | `text`, `markdown`, or `json`. Default: `text`. |
| `NT_OUTPUT_FILE` | Optional path to persist the rendered output. |
| `NT_NO_WAIT` | Truthy value triggers execution and exits immediately without waiting. |

All CLI switches mirror these variables, so you can mix flags and env vars as needed. For example:

```bash
python scripts/nt_cli.py \
  --base-url https://api.example.com \
  --project-id 123e4567-e89b-12d3-a456-426614174000 \
  --suite-id 9aa9f8b0-aaaa-4a1f-9ff0-123456789abc \
  --email runner@example.com \
  --password changeme \
  --threshold 0.9
```

### Output formats and exit codes

- Text and Markdown outputs are human-friendly summaries.
- JSON output is perfect for automation (GitHub Actions, Jenkins, GitLab examples all use it).
- Exit codes:
  - `0`: execution passed and met the threshold.
  - `2`: execution finished with `failed`/`error` status.
  - `3`: execution passed but the pass rate fell below the configured threshold.
  - `4`: execution completed with `skipped` status.
  - `1`: configuration or unexpected errors.

Example text output:

```
Test Execution Summary
======================
Status        : PASSED
Outcome       : Passed
Pass Rate     : 100.0%
Assertions    : 12/12
Threshold     : 90.0%
Report Link   : https://app.example.com/reports/123
Task ID       : b448...
Report ID     : 123...
Elapsed (s)   : 37.4
```

### Resuming in multi-stage pipelines

- `--no-wait` (or `NT_NO_WAIT=true`) triggers the run and exits immediately, returning a JSON payload with the `task_id` and `report_id` for later stages.
- `--task-id` (and optionally `--report-id`) resumes an execution that was previously triggered.

---

## 2. GitHub Actions (`.github/workflows/test-on-pr.yml`)

The repository ships with a ready-to-use workflow that:

1. Installs the CLI dependency (`httpx`).
2. Executes the CLI with JSON output.
3. Posts a PR comment summarising the result (status, pass rate, report link).
4. Fails the job if the pass rate does not meet the configured threshold.

### Configuration steps

1. **Set repository variables** (Settings → Secrets and variables → Actions → Variables):
   - `NT_API_BASE`
   - `NT_PROJECT_ID`
   - `NT_SUITE_ID`
   - Optional: `NT_PASS_THRESHOLD`, `NT_REPORT_BASE_URL`

2. **Add secrets** (Settings → Secrets and variables → Actions → Secrets):
   - Either `NT_API_TOKEN`, or `NT_EMAIL` + `NT_PASSWORD`.

3. The workflow responds to pull requests automatically. To customise values without editing the file, invoke it as a reusable workflow:

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

The workflow comments on pull requests using the built-in `GITHUB_TOKEN`. When running as a reusable workflow outside of PR contexts, the comment step is skipped automatically.

---

## 3. Jenkins Pipeline (`Jenkinsfile`)

The included Jenkinsfile demonstrates a declarative pipeline with three stages (`Trigger → Wait → Publish`). It uses `withCredentials` to inject secrets and stores the CLI output between stages.

### Credentials expected

- `nt-api-user`: `Username/Password` credentials mapped to `NT_EMAIL` and `NT_PASSWORD`.
- `nt-api-base`, `nt-project-id`, `nt-suite-id`, `nt-threshold`: `Secret text` credentials for the respective environment variables.

### Stage overview

1. **Setup** – creates a virtual environment and installs `httpx`.
2. **Trigger** – runs `nt_cli.py --no-wait` to start the execution and produce `nt_trigger.json` containing `task_id` and `report_id`.
3. **Wait** – reuses the stored IDs (`NT_TASK_ID`/`NT_REPORT_ID`) to poll until completion, writing results to `nt_result.json`.
4. **Publish** – prints a JSON summary to the Jenkins console and fails the build if the exit code indicates failure/threshold miss.

Artifacts (`nt_trigger.json`, `nt_result.json`) are archived for post-run inspection.

---

## 4. GitLab CI (`.gitlab-ci.yml`)

The `api-tests` job provides a drop-in example:

1. Uses the `python:3.11` image.
2. Installs `httpx` and runs the CLI with JSON output.
3. Prints a structured summary and respects the CLI exit code (failing the pipeline on threshold breaches).
4. Keeps `nt_result.json` as a job artifact for later review.

Define the following CI/CD variables in your project/group settings:

- `NT_API_BASE`
- `NT_PROJECT_ID`
- `NT_SUITE_ID`
- Either `NT_API_TOKEN` or `NT_EMAIL` + `NT_PASSWORD`
- Optional: `NT_PASS_THRESHOLD`, `NT_REPORT_BASE_URL`

---

## 5. Backend Support Endpoint

The API now exposes `GET /api/v1/tasks/{task_id}` with an enriched payload:

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

The CLI uses this endpoint to resolve the report URL when resuming executions, and the value is included in CI comments.

CORS headers on the FastAPI application already permit the CLI and automation tools to interact without additional configuration.

---

## 6. Failure Criteria Summary

| Condition | CLI Exit Code | Outcome |
| --- | --- | --- |
| Report status is `failed`/`error` | `2` | `failed` |
| Report status `passed`, pass rate below threshold | `3` | `threshold_not_met` |
| Report status `skipped` | `4` | `skipped` |
| Successful run above threshold | `0` | `passed` |
| Configuration / network errors | `1` | `error` |

Use these semantics to gate merges, break builds, or notify stakeholders via your preferred CI system.

---

With these assets in place, a new team can wire NetTests into their CI/CD pipelines in **under 30 minutes**—from installing the CLI to receiving automated feedback on every change.
