from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models.test_report import ReportStatus, TestReport


@dataclass(frozen=True)
class FlakinessResult:
    score: float
    is_flaky: bool
    notes: dict[str, Any]


_MIN_SEQUENCE_LENGTH = 2


def compute_flakiness(session: Session, report: TestReport, window: int) -> FlakinessResult:
    if window <= 0:
        window = 1

    stmt: Select[tuple[ReportStatus]] = (
        select(TestReport.status)
        .where(
            TestReport.project_id == report.project_id,
            TestReport.entity_type == report.entity_type,
            TestReport.entity_id == report.entity_id,
            TestReport.is_deleted.is_(False),
        )
        .order_by(TestReport.started_at.desc(), TestReport.created_at.desc())
        .limit(window)
    )
    rows = session.execute(stmt).all()
    sequence: list[str] = []
    for row in rows:
        normalized = _normalize_status(row[0])
        if normalized is not None:
            sequence.append(normalized)

    if len(sequence) < _MIN_SEQUENCE_LENGTH:
        return FlakinessResult(score=0.0, is_flaky=False, notes={"window": len(sequence)})

    transitions = sum(1 for idx in range(1, len(sequence)) if sequence[idx] != sequence[idx - 1])
    pass_count = sequence.count("pass")
    fail_count = sequence.count("fail")

    score = transitions / max(1, len(sequence) - 1)
    is_flaky = pass_count > 0 and fail_count > 0 and score >= 0.4

    notes = {
        "window": len(sequence),
        "pass_count": pass_count,
        "fail_count": fail_count,
        "transitions": transitions,
    }

    return FlakinessResult(score=round(score, 3), is_flaky=is_flaky, notes=notes)


def _normalize_status(status: ReportStatus | str | None) -> str | None:
    if status is None:
        return None
    if isinstance(status, ReportStatus):
        value = status.value
    else:
        value = str(status)
    value = value.lower()
    if value in {ReportStatus.PASSED.value}:
        return "pass"
    if value in {ReportStatus.FAILED.value, ReportStatus.ERROR.value}:
        return "fail"
    return None
