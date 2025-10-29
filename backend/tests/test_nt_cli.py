from __future__ import annotations

import json

import pytest

from scripts.nt_cli import CLIError, determine_outcome, parse_args, render_output


@pytest.fixture(autouse=True)
def clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure CLI-related environment variables do not leak between tests."""

    keys = [
        "NT_API_BASE",
        "NT_REPORT_BASE_URL",
        "NT_EMAIL",
        "NT_PASSWORD",
        "NT_API_TOKEN",
        "NT_PROJECT_ID",
        "NT_SUITE_ID",
        "NT_CASE_ID",
        "NT_PASS_THRESHOLD",
        "NT_POLL_INTERVAL",
        "NT_TIMEOUT",
        "NT_VERIFY_SSL",
        "NT_OUTPUT_FORMAT",
        "NT_OUTPUT_FILE",
        "NT_NO_WAIT",
        "NT_TASK_ID",
        "NT_REPORT_ID",
    ]
    for key in keys:
        monkeypatch.delenv(key, raising=False)


def test_parse_args_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NT_API_BASE", "https://api.example.com")
    monkeypatch.setenv("NT_PROJECT_ID", "proj-123")
    monkeypatch.setenv("NT_SUITE_ID", "suite-456")
    monkeypatch.setenv("NT_API_TOKEN", "token-abc")
    monkeypatch.setenv("NT_PASS_THRESHOLD", "90")
    monkeypatch.setenv("NT_POLL_INTERVAL", "5")
    monkeypatch.setenv("NT_TIMEOUT", "120")

    config = parse_args([])

    assert config.base_url == "https://api.example.com"
    assert config.project_id == "proj-123"
    assert config.suite_id == "suite-456"
    assert config.api_token == "token-abc"
    assert pytest.approx(config.pass_threshold, rel=1e-6) == 0.9
    assert config.poll_interval == 5
    assert config.timeout == 120
    assert config.verify_ssl is True


def test_parse_args_requires_authentication(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NT_API_BASE", "https://api.example.com")
    monkeypatch.setenv("NT_PROJECT_ID", "proj-123")
    monkeypatch.setenv("NT_SUITE_ID", "suite-456")

    with pytest.raises(CLIError, match="Provide either an API token or email/password"):
        parse_args([])


def test_parse_args_accepts_email_login(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NT_API_BASE", "https://api.example.com")
    monkeypatch.setenv("NT_PROJECT_ID", "proj-123")
    monkeypatch.setenv("NT_CASE_ID", "case-789")
    config = parse_args(
        [
            "--email",
            "runner@example.com",
            "--password",
            "secret",
        ]
    )
    assert config.email == "runner@example.com"
    assert config.password == "secret"
    assert config.case_id == "case-789"


@pytest.mark.parametrize(
    "status,pass_rate,threshold,expected_outcome,expected_exit",
    [
        ("passed", 1.0, 0.9, "passed", 0),
        ("failed", 0.2, 0.5, "failed", 2),
        ("passed", 0.5, 0.8, "threshold_not_met", 3),
        ("skipped", None, 0.5, "skipped", 4),
        ("unknown", 1.0, 0.5, "unknown", 1),
    ],
)
def test_determine_outcome(
    status: str,
    pass_rate: float | None,
    threshold: float,
    expected_outcome: str,
    expected_exit: int,
) -> None:
    outcome, exit_code, met = determine_outcome(status, pass_rate, threshold)
    assert outcome == expected_outcome
    assert exit_code == expected_exit
    if expected_exit == 0:
        assert met is True
    else:
        assert met is False


def test_render_output_json_contains_values() -> None:
    summary = {
        "status": "passed",
        "pass_rate": 0.95,
        "threshold": 0.9,
        "report_id": "report-123",
        "report_url": "/reports/report-123",
        "task_id": "task-xyz",
        "assertions_total": 10,
        "assertions_passed": 9,
        "elapsed_seconds": 42.5,
        "message": "Execution completed successfully.",
        "outcome": "passed",
        "exit_code": 0,
        "met_threshold": True,
    }

    rendered = render_output(summary, "json")
    payload = json.loads(rendered)
    assert payload["status"] == "passed"
    assert payload["pass_rate"] == pytest.approx(0.95)
    assert payload["exit_code"] == 0


def test_render_output_markdown() -> None:
    summary = {
        "status": "passed",
        "pass_rate": 1.0,
        "threshold": 0.95,
        "report_url_full": "https://app.example.com/reports/abc",
        "task_id": "task-123",
        "report_id": "abc",
        "assertions_total": 12,
        "assertions_passed": 12,
        "elapsed_seconds": 12.3,
        "message": "Execution completed successfully.",
        "outcome": "passed",
        "exit_code": 0,
        "met_threshold": True,
    }

    rendered = render_output(summary, "markdown")
    assert "### NetTests Execution" in rendered
    assert "**Status:** PASSED" in rendered
    assert "Execution completed successfully." in rendered
