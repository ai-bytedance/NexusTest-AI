#!/usr/bin/env python3
"""nt_cli: Lightweight CLI for triggering and monitoring API test executions.

This script authenticates against the NetTests backend, triggers a test suite or
case execution, polls for completion, and exits with a non-zero status code when
the configured pass-rate threshold is not met.

Environment variables map to the available CLI flags for Docker/CI usage:

- NT_API_BASE: Base URL for the backend API (e.g. https://api.example.com)
- NT_REPORT_BASE_URL: Optional base used when constructing human-friendly links
- NT_EMAIL / NT_PASSWORD: Login credentials (used when NT_API_TOKEN is absent)
- NT_API_TOKEN: Personal access token for bearer authentication
- NT_PROJECT_ID: Project identifier used for triggering executions
- NT_SUITE_ID / NT_CASE_ID: Identifier of the suite or case to execute
- NT_PASS_THRESHOLD: Minimum pass rate required to succeed (fraction or percent)
- NT_POLL_INTERVAL: Seconds between poll attempts (default: 10)
- NT_TIMEOUT: Max seconds to wait for completion (default: 900)
- NT_VERIFY_SSL: Toggle TLS verification (true/false, default: true)
- NT_OUTPUT_FORMAT: text, markdown, or json output (default: text)
- NT_OUTPUT_FILE: Optional path to persist the rendered output
- NT_NO_WAIT: If truthy, trigger and exit without waiting for completion
- NT_TASK_ID / NT_REPORT_ID: Resume polling for an existing execution

Usage examples::

    # Run with explicit arguments
    python scripts/nt_cli.py \
        --base-url https://api.example.com \
        --project-id 123e4567-e89b-12d3-a456-426614174000 \
        --suite-id 22222222-3333-4444-5555-666666666666 \
        --email runner@example.com --password changeme \
        --threshold 0.9

    # Resume from an existing task (e.g. stored by a CI job)
    python scripts/nt_cli.py --task-id abcd --report-id efgh --api-token env:NT_TOKEN
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Any, Iterable
from urllib.parse import urljoin

import httpx

__all__ = ["main", "parse_args", "determine_outcome", "render_output"]

FINAL_STATUSES = {"passed", "failed", "error", "skipped"}
FAILED_STATUSES = {"failed", "error"}
SUCCESS_STATUSES = {"passed"}
SKIPPED_STATUSES = {"skipped"}
TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}


class CLIError(RuntimeError):
    """Raised for recoverable CLI errors."""


@dataclass(slots=True)
class CLIConfig:
    base_url: str
    report_base_url: str | None
    email: str | None
    password: str | None
    api_token: str | None
    project_id: str | None
    suite_id: str | None
    case_id: str | None
    pass_threshold: float
    poll_interval: int
    timeout: int
    verify_ssl: bool
    output_format: str
    output_file: str | None
    no_wait: bool
    task_id: str | None
    report_id: str | None


def log(message: str) -> None:
    """Emit a message on stderr without disrupting stdout capture."""

    print(message, file=sys.stderr)


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    lower = value.strip().lower()
    if lower in TRUE_VALUES:
        return True
    if lower in FALSE_VALUES:
        return False
    return default


def parse_args(argv: Iterable[str]) -> CLIConfig:
    env = os.environ
    parser = argparse.ArgumentParser(description="Trigger and monitor NetTests executions")

    parser.add_argument("--base-url", default=env.get("NT_API_BASE"), help="Backend API base URL")
    parser.add_argument(
        "--report-base-url",
        default=env.get("NT_REPORT_BASE_URL"),
        help="Optional base URL used to construct report links",
    )
    parser.add_argument("--email", default=env.get("NT_EMAIL"), help="Account email for login")
    parser.add_argument("--password", default=env.get("NT_PASSWORD"), help="Account password for login")
    parser.add_argument(
        "--api-token",
        default=env.get("NT_API_TOKEN"),
        help="Personal access token (skips interactive login)",
    )
    parser.add_argument("--project-id", default=env.get("NT_PROJECT_ID"), help="Target project identifier")
    parser.add_argument("--suite-id", default=env.get("NT_SUITE_ID"), help="Suite identifier to execute")
    parser.add_argument("--case-id", default=env.get("NT_CASE_ID"), help="Case identifier to execute")
    parser.add_argument(
        "--threshold",
        default=env.get("NT_PASS_THRESHOLD", "1.0"),
        help="Minimum acceptable pass rate (fraction or percentage)",
    )
    parser.add_argument(
        "--poll-interval",
        default=env.get("NT_POLL_INTERVAL", "10"),
        help="Seconds between polling attempts",
    )
    parser.add_argument(
        "--timeout",
        default=env.get("NT_TIMEOUT", "900"),
        help="Maximum seconds to wait for completion",
    )
    default_verify = _env_flag("NT_VERIFY_SSL", True)
    parser.set_defaults(verify_ssl=default_verify)
    parser.add_argument(
        "--insecure",
        dest="verify_ssl",
        action="store_false",
        help="Disable TLS verification (NOT recommended)",
    )
    parser.add_argument(
        "--format",
        dest="output_format",
        choices=("text", "json", "markdown"),
        default=env.get("NT_OUTPUT_FORMAT", "text"),
        help="Rendering format for the final summary",
    )
    parser.add_argument(
        "--output-file",
        default=env.get("NT_OUTPUT_FILE"),
        help="Optional file path to persist the rendered summary",
    )
    parser.add_argument(
        "--no-wait",
        action="store_true",
        default=_env_flag("NT_NO_WAIT", False),
        help="Trigger execution and exit immediately without polling",
    )
    parser.add_argument(
        "--task-id",
        default=env.get("NT_TASK_ID"),
        help="Resume polling for an existing Celery task",
    )
    parser.add_argument(
        "--report-id",
        default=env.get("NT_REPORT_ID"),
        help="Optional report identifier when resuming",
    )

    args = parser.parse_args(list(argv))

    if not args.base_url:
        raise CLIError("API base URL is required (set --base-url or NT_API_BASE)")

    threshold = _parse_float(args.threshold, "threshold")
    threshold = _normalize_threshold(threshold)
    poll_interval_value = int(_parse_float(args.poll_interval, "poll-interval"))
    timeout_value = int(_parse_float(args.timeout, "timeout"))
    if poll_interval_value <= 0:
        raise CLIError("poll-interval must be a positive integer")
    if timeout_value <= 0:
        raise CLIError("timeout must be a positive integer")
    if timeout_value < poll_interval_value:
        raise CLIError("timeout must be greater than poll-interval")

    base_url = args.base_url.rstrip("/")
    report_base = args.report_base_url.rstrip("/") if args.report_base_url else None

    config = CLIConfig(
        base_url=base_url,
        report_base_url=report_base,
        email=args.email,
        password=args.password,
        api_token=args.api_token,
        project_id=args.project_id,
        suite_id=args.suite_id,
        case_id=args.case_id,
        pass_threshold=threshold,
        poll_interval=poll_interval_value,
        timeout=timeout_value,
        verify_ssl=args.verify_ssl,
        output_format=args.output_format,
        output_file=args.output_file,
        no_wait=args.no_wait,
        task_id=args.task_id,
        report_id=args.report_id,
    )

    if not config.task_id and not config.suite_id and not config.case_id:
        raise CLIError(
            "Provide a suite-id, case-id, or task-id to resume (via CLI args or environment variables)"
        )

    if config.task_id and not config.project_id:
        raise CLIError("project-id is required when resuming from an existing task")

    if not config.api_token and not (config.email and config.password):
        raise CLIError("Provide either an API token or email/password credentials")

    return config


def _parse_float(raw: str | float, label: str) -> float:
    if isinstance(raw, (float, int)):
        return float(raw)
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError) as exc:  # pragma: no cover - defensive guard
        raise CLIError(f"Invalid value for {label}: {raw!r}") from exc


def _normalize_threshold(value: float) -> float:
    if value < 0:
        raise CLIError("threshold must be non-negative")
    if value > 1:
        if value <= 100:
            return round(value / 100.0, 4)
        raise CLIError("threshold cannot exceed 100%")
    return round(value, 4)


def authenticate(client: httpx.Client, config: CLIConfig) -> str:
    if config.api_token:
        return config.api_token
    if not config.email or not config.password:
        raise CLIError("Email and password are required when API token is absent")

    log("Authenticating with supplied credentials …")
    response = client.post(
        "/api/auth/login",
        json={"email": config.email, "password": config.password},
        headers={"Accept": "application/json"},
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != "SUCCESS":
        raise CLIError(f"Authentication failed: {payload.get('message', 'Unknown error')}")
    data = payload.get("data") or {}
    token = data.get("access_token")
    if not token:
        raise CLIError("Authentication response missing access token")
    return token


def trigger_execution(client: httpx.Client, config: CLIConfig, headers: dict[str, str]) -> dict[str, Any]:
    if config.project_id is None:
        raise CLIError("project-id is required to trigger executions")

    if config.suite_id:
        endpoint = f"/api/v1/projects/{config.project_id}/execute/suite/{config.suite_id}"
    elif config.case_id:
        endpoint = f"/api/v1/projects/{config.project_id}/execute/case/{config.case_id}"
    else:
        raise CLIError("suite-id or case-id must be provided to trigger execution")

    log(f"Triggering execution via {endpoint} …")
    response = client.post(endpoint, headers=headers)
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != "SUCCESS":
        raise CLIError(f"Execution request failed: {payload.get('message', 'Unknown error')}")
    data = payload.get("data") or {}
    task_id = data.get("task_id")
    if not task_id:
        raise CLIError("Execution response missing task_id")
    return data


def resolve_task_metadata(
    client: httpx.Client,
    headers: dict[str, str],
    task_id: str,
    report_id: str | None,
    poll_interval: int,
    timeout: int,
) -> tuple[str, str | None]:
    if not task_id:
        raise CLIError("task_id is required to resolve report metadata")

    resolved_report_id = report_id
    resolved_report_url: str | None = None
    deadline = time.time() + timeout

    while True:
        response = client.get(f"/api/v1/tasks/{task_id}", headers=headers)
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != "SUCCESS":
            raise CLIError(f"Unable to read task status: {payload.get('message', 'Unknown error')}")
        data = payload.get("data") or {}
        resolved_report_id = resolved_report_id or data.get("report_id")
        resolved_report_url = resolved_report_url or data.get("report_url")

        if resolved_report_id and resolved_report_url:
            break
        if resolved_report_id and resolved_report_url is None:
            resolved_report_url = f"/reports/{resolved_report_id}"
            break

        if time.time() >= deadline:
            if not resolved_report_id:
                raise CLIError("Timed out waiting for report information from task")
            resolved_report_url = resolved_report_url or f"/reports/{resolved_report_id}"
            break

        time.sleep(poll_interval)

    return resolved_report_id, resolved_report_url


def wait_for_report_completion(
    client: httpx.Client,
    headers: dict[str, str],
    report_id: str,
    poll_interval: int,
    timeout: int,
) -> dict[str, Any]:
    deadline = time.time() + timeout
    last_status: str | None = None

    while True:
        response = client.get(f"/api/v1/reports/{report_id}", headers=headers)
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != "SUCCESS":
            raise CLIError(f"Failed to fetch report: {payload.get('message', 'Unknown error')}")
        data = payload.get("data") or {}
        status = str(data.get("status", "pending")).lower()

        if status != last_status:
            log(f"Report {report_id} status: {status}")
            last_status = status

        if status in FINAL_STATUSES:
            return data

        if time.time() >= deadline:
            raise CLIError(f"Timed out waiting for report {report_id} to finish (last status: {status})")

        time.sleep(poll_interval)


def determine_outcome(status: str, pass_rate: float | None, threshold: float) -> tuple[str, int, bool]:
    normalized_status = (status or "").lower()
    normalized_pass = float(pass_rate or 0.0)
    meets_threshold = normalized_pass >= threshold

    if normalized_status in FAILED_STATUSES:
        return "failed", 2, False
    if not meets_threshold:
        return "threshold_not_met", 3, False
    if normalized_status in SUCCESS_STATUSES:
        return "passed", 0, True
    if normalized_status in SKIPPED_STATUSES:
        return "skipped", 4, False
    return "unknown", 1, meets_threshold


def build_summary(
    *,
    status: str,
    pass_rate: float | None,
    threshold: float,
    report_id: str | None,
    report_url: str | None,
    report_url_full: str | None,
    task_id: str | None,
    assertions_total: int | None,
    assertions_passed: int | None,
    started_at: str | None,
    finished_at: str | None,
    duration_ms: int | None,
    elapsed_seconds: float,
    message: str,
    outcome: str,
    exit_code: int,
    met_threshold: bool,
) -> dict[str, Any]:
    return {
        "status": status,
        "pass_rate": pass_rate,
        "threshold": threshold,
        "report_id": report_id,
        "report_url": report_url,
        "report_url_full": report_url_full,
        "task_id": task_id,
        "assertions_total": assertions_total,
        "assertions_passed": assertions_passed,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_ms": duration_ms,
        "elapsed_seconds": round(elapsed_seconds, 2),
        "message": message,
        "outcome": outcome,
        "exit_code": exit_code,
        "met_threshold": met_threshold,
    }


def render_output(summary: dict[str, Any], fmt: str) -> str:
    fmt_normalized = fmt.lower()
    if fmt_normalized == "json":
        return json.dumps(summary, indent=2, sort_keys=True)
    if fmt_normalized == "markdown":
        return _render_markdown(summary)
    return _render_text(summary)


def _render_text(summary: dict[str, Any]) -> str:
    status = str(summary.get("status", "unknown")).upper()
    pass_rate = summary.get("pass_rate")
    pass_rate_pct = f"{pass_rate * 100:.1f}%" if isinstance(pass_rate, (int, float)) else "n/a"
    assertions_total = summary.get("assertions_total")
    assertions_passed = summary.get("assertions_passed")
    assertions_segment = "n/a"
    if isinstance(assertions_total, int) and isinstance(assertions_passed, int):
        assertions_segment = f"{assertions_passed}/{assertions_total}"
    outcome = summary.get("outcome", "unknown").replace("_", " ").title()
    report_url = summary.get("report_url_full") or summary.get("report_url") or "n/a"

    lines = [
        "Test Execution Summary",
        "======================",
        f"Status        : {status}",
        f"Outcome       : {outcome}",
        f"Pass Rate     : {pass_rate_pct}",
        f"Assertions    : {assertions_segment}",
        f"Threshold     : {summary.get('threshold') * 100:.1f}%",
        f"Report Link   : {report_url}",
        f"Task ID       : {summary.get('task_id') or 'n/a'}",
        f"Report ID     : {summary.get('report_id') or 'n/a'}",
        f"Elapsed (s)   : {summary.get('elapsed_seconds', 'n/a')}",
    ]

    message = summary.get("message")
    if message:
        lines.extend(["", message])

    return "\n".join(lines)


def _render_markdown(summary: dict[str, Any]) -> str:
    status = str(summary.get("status", "unknown")).upper()
    pass_rate = summary.get("pass_rate")
    pass_rate_pct = f"{pass_rate * 100:.1f}%" if isinstance(pass_rate, (int, float)) else "n/a"
    threshold_pct = f"{summary.get('threshold', 0) * 100:.1f}%"
    report_url = summary.get("report_url_full") or summary.get("report_url")
    report_link = report_url if report_url else "_Unavailable_"
    assertions_total = summary.get("assertions_total")
    assertions_passed = summary.get("assertions_passed")
    assertions_segment = "n/a"
    if isinstance(assertions_total, int) and isinstance(assertions_passed, int):
        assertions_segment = f"{assertions_passed}/{assertions_total}"

    lines = [
        "### NetTests Execution",
        "",
        f"- **Status:** {status}",
        f"- **Outcome:** {summary.get('outcome', 'unknown').replace('_', ' ').title()}",
        f"- **Pass rate:** {pass_rate_pct} (threshold {threshold_pct})",
        f"- **Assertions:** {assertions_segment}",
        f"- **Report:** {report_link}",
        f"- **Task ID:** `{summary.get('task_id') or 'n/a'}`",
        f"- **Report ID:** `{summary.get('report_id') or 'n/a'}`",
        f"- **Elapsed:** {summary.get('elapsed_seconds', 'n/a')} seconds",
    ]

    message = summary.get("message")
    if message:
        lines.extend(["", f"> {message}"])

    return "\n".join(lines)


def write_output_file(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
        if not content.endswith("\n"):
            handle.write("\n")


def execute(config: CLIConfig) -> dict[str, Any]:
    start_time = time.time()
    http_timeout = httpx.Timeout(10.0, connect=5.0, read=30.0, write=30.0)
    headers = {"Accept": "application/json"}
    task_id = config.task_id
    report_id = config.report_id
    report_url: str | None = None

    with httpx.Client(base_url=config.base_url, timeout=http_timeout, verify=config.verify_ssl) as client:
        token = authenticate(client, config)
        headers_with_auth = {**headers, "Authorization": f"Bearer {token}"}

        if task_id is None:
            trigger_data = trigger_execution(client, config, headers_with_auth)
            task_id = trigger_data["task_id"]
            report_id = trigger_data.get("report_id")
            log(f"Triggered execution. Task ID: {task_id}, report: {report_id}")
            if config.no_wait:
                elapsed = time.time() - start_time
                report_url = f"/reports/{report_id}" if report_id else None
                absolute = _build_absolute_url(config.report_base_url, report_url)
                outcome, exit_code, met = "pending", 0, False
                message = "Execution triggered. Waiting skipped (--no-wait)."
                return build_summary(
                    status="pending",
                    pass_rate=None,
                    threshold=config.pass_threshold,
                    report_id=report_id,
                    report_url=report_url,
                    report_url_full=absolute,
                    task_id=task_id,
                    assertions_total=None,
                    assertions_passed=None,
                    started_at=None,
                    finished_at=None,
                    duration_ms=None,
                    elapsed_seconds=elapsed,
                    message=message,
                    outcome=outcome,
                    exit_code=exit_code,
                    met_threshold=met,
                )
        else:
            log(f"Resuming execution for task {task_id}")

        if not report_id or not report_url:
            metadata_timeout = max(config.poll_interval, min(config.timeout, 120))
            report_id, report_url = resolve_task_metadata(
                client,
                headers_with_auth,
                task_id,
                report_id,
                config.poll_interval,
                metadata_timeout,
            )

        report_url = report_url or (f"/reports/{report_id}" if report_id else None)
        if not report_id:
            raise CLIError("Unable to resolve report_id for the triggered task")

        if config.no_wait:
            elapsed = time.time() - start_time
            absolute = _build_absolute_url(config.report_base_url, report_url)
            outcome, exit_code, met = "pending", 0, False
            message = "Execution resumed without waiting (--no-wait)."
            return build_summary(
                status="pending",
                pass_rate=None,
                threshold=config.pass_threshold,
                report_id=report_id,
                report_url=report_url,
                report_url_full=absolute,
                task_id=task_id,
                assertions_total=None,
                assertions_passed=None,
                started_at=None,
                finished_at=None,
                duration_ms=None,
                elapsed_seconds=elapsed,
                message=message,
                outcome=outcome,
                exit_code=exit_code,
                met_threshold=met,
            )

        report_data = wait_for_report_completion(
            client,
            headers_with_auth,
            report_id,
            config.poll_interval,
            config.timeout,
        )

        status = str(report_data.get("status", "unknown")).lower()
        pass_rate = report_data.get("pass_rate")
        assertions_total = report_data.get("assertions_total")
        assertions_passed = report_data.get("assertions_passed")
        started_at = report_data.get("started_at")
        finished_at = report_data.get("finished_at")
        duration_ms = report_data.get("duration_ms")

        outcome, exit_code, met = determine_outcome(status, pass_rate, config.pass_threshold)
        elapsed = time.time() - start_time
        absolute = _build_absolute_url(config.report_base_url, report_url)

        if outcome == "threshold_not_met":
            message = f"Pass rate {pass_rate or 0:.3f} below threshold {config.pass_threshold:.3f}."
        elif outcome == "failed":
            message = "Execution did not complete successfully."
        elif outcome == "skipped":
            message = "Execution finished with status SKIPPED."
        else:
            message = "Execution completed successfully." if exit_code == 0 else "Execution finished."

        return build_summary(
            status=status,
            pass_rate=pass_rate,
            threshold=config.pass_threshold,
            report_id=report_id,
            report_url=report_url,
            report_url_full=absolute,
            task_id=task_id,
            assertions_total=assertions_total,
            assertions_passed=assertions_passed,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            elapsed_seconds=elapsed,
            message=message,
            outcome=outcome,
            exit_code=exit_code,
            met_threshold=met,
        )


def _build_absolute_url(base: str | None, report_url: str | None) -> str | None:
    if not base or not report_url:
        return None
    if not report_url.startswith("/"):
        report_url = f"/{report_url}"
    return urljoin(base.rstrip("/") + "/", report_url.lstrip("/"))


def main(argv: Iterable[str] | None = None) -> int:
    argv_list = list(sys.argv[1:] if argv is None else argv)
    try:
        config = parse_args(argv_list)
    except CLIError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    try:
        summary = execute(config)
    except CLIError as exc:
        elapsed = 0.0
        summary = build_summary(
            status="error",
            pass_rate=None,
            threshold=config.pass_threshold,
            report_id=config.report_id,
            report_url=None,
            report_url_full=None,
            task_id=config.task_id,
            assertions_total=None,
            assertions_passed=None,
            started_at=None,
            finished_at=None,
            duration_ms=None,
            elapsed_seconds=elapsed,
            message=str(exc),
            outcome="error",
            exit_code=1,
            met_threshold=False,
        )
    except httpx.HTTPError as exc:
        elapsed = 0.0
        summary = build_summary(
            status="error",
            pass_rate=None,
            threshold=config.pass_threshold,
            report_id=config.report_id,
            report_url=None,
            report_url_full=None,
            task_id=config.task_id,
            assertions_total=None,
            assertions_passed=None,
            started_at=None,
            finished_at=None,
            duration_ms=None,
            elapsed_seconds=elapsed,
            message=f"HTTP error: {exc}",
            outcome="error",
            exit_code=1,
            met_threshold=False,
        )

    rendered = render_output(summary, config.output_format)
    print(rendered)

    if config.output_file:
        try:
            write_output_file(config.output_file, rendered)
        except OSError as exc:  # pragma: no cover - filesystem specific
            log(f"Warning: Unable to write output file {config.output_file}: {exc}")

    return int(summary.get("exit_code", 1))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
