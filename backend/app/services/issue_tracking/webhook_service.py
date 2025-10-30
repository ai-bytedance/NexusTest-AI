from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models import Integration, IntegrationWebhook, IntegrationWebhookStatus, Issue, IssueSyncState
from app.services.issue_tracking.linkage import (
    attach_commits,
    attach_pull_requests,
    normalize_commit_reference,
    normalize_pull_request_reference,
)
from app.services.issue_tracking.service import find_issue_by_external
from app.services.notify.signing import verify_signature

_HEADER_SIGNATURE = "x-integration-signature"
_HEADER_TIMESTAMP = "x-integration-timestamp"
_HEADER_NONCE = "x-integration-nonce"
_HEADER_DELIVERY = "x-integration-delivery"


class WebhookVerificationError(Exception):
    """Raised when a webhook request cannot be verified."""


class WebhookProcessingError(RuntimeError):
    """Raised when a webhook event cannot be processed."""


def _normalize_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {str(key).lower(): str(value) for key, value in headers.items()}


def verify_webhook_request(
    secret: str,
    headers: Mapping[str, str],
    payload: bytes,
    *,
    tolerance_seconds: int = 300,
) -> dict[str, str]:
    normalized = _normalize_headers(headers)
    signature = normalized.get(_HEADER_SIGNATURE)
    timestamp = normalized.get(_HEADER_TIMESTAMP)
    nonce = normalized.get(_HEADER_NONCE)

    if not secret:
        raise WebhookVerificationError("Webhook secret is not configured")
    if not signature or not timestamp:
        raise WebhookVerificationError("Missing signature headers")
    if not nonce:
        raise WebhookVerificationError("Missing replay nonce header")

    if not verify_signature(secret, payload, timestamp, signature, tolerance_seconds=tolerance_seconds):
        raise WebhookVerificationError("Signature verification failed")

    delivery_key = normalized.get(_HEADER_DELIVERY) or f"{timestamp}:{nonce}"
    return {
        "timestamp": timestamp,
        "signature": signature,
        "nonce": nonce,
        "idempotency_key": delivery_key,
    }


def record_webhook_event(
    session: Session,
    integration: Integration | None,
    *,
    provider: str,
    payload: dict[str, Any],
    headers: Mapping[str, str],
    signature: str | None,
    idempotency_key: str,
) -> tuple[IntegrationWebhook, bool]:
    stmt = (
        sa.select(IntegrationWebhook)
        .where(
            IntegrationWebhook.provider == provider,
            IntegrationWebhook.idempotency_key == idempotency_key,
            IntegrationWebhook.is_deleted.is_(False),
        )
        .limit(1)
    )
    existing = session.execute(stmt).scalar_one_or_none()
    if existing is not None:
        return existing, False

    event = IntegrationWebhook(
        integration_id=integration.id if integration else None,
        project_id=integration.project_id if integration else None,
        provider=provider,
        event_type=str(payload.get("type") or payload.get("event") or ""),
        idempotency_key=idempotency_key,
        signature=signature,
        payload=payload,
        headers=dict(headers),
        status=IntegrationWebhookStatus.PENDING,
        attempts=0,
    )
    session.add(event)
    session.flush()
    return event, True


def _extract_issue_payload(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("issue", "data", "resource"):
        candidate = payload.get(key)
        if isinstance(candidate, dict):
            return candidate
    return payload


def _iter_pull_requests(provider: str, data: Any) -> Iterable[dict[str, Any]]:
    if data is None:
        return []
    items = data if isinstance(data, (list, tuple)) else [data]
    references: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, str):
            references.append(normalize_pull_request_reference(provider, pr_url=item))
            continue
        if isinstance(item, dict):
            payload = dict(item)
            inferred_provider = payload.pop("provider", provider)
            url = payload.pop("url", payload.pop("html_url", None))
            owner = payload.pop("owner", payload.pop("user", payload.pop("organization", None)))
            repo = payload.pop("repo", payload.pop("repository", None))
            number = payload.pop("number", payload.pop("id", None))
            title = payload.pop("title", None)
            references.append(
                normalize_pull_request_reference(
                    inferred_provider,
                    pr_url=url,
                    owner=owner,
                    repo=repo,
                    number=number,
                    title=title,
                    metadata=payload,
                )
            )
            continue
    return references


def _iter_commits(provider: str, data: Any) -> Iterable[dict[str, Any]]:
    if data is None:
        return []
    items = data if isinstance(data, (list, tuple)) else [data]
    references: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, str):
            sha = item.strip()
            if sha:
                references.append(normalize_commit_reference(provider, sha=sha))
            continue
        if isinstance(item, dict):
            payload = dict(item)
            inferred_provider = payload.pop("provider", provider)
            sha = payload.pop("sha", payload.pop("id", "")).strip()
            if not sha:
                continue
            url = payload.pop("url", payload.pop("html_url", None))
            owner = payload.pop("owner", payload.pop("user", None))
            repo = payload.pop("repo", payload.pop("repository", None))
            message = payload.pop("message", payload.pop("title", None))
            references.append(
                normalize_commit_reference(
                    inferred_provider,
                    sha=sha,
                    commit_url=url,
                    owner=owner,
                    repo=repo,
                    message=message,
                    metadata=payload,
                )
            )
            continue
    return references


def process_webhook_event(
    session: Session,
    event: IntegrationWebhook,
    *,
    provider: str,
) -> Issue:
    now = datetime.now(timezone.utc)
    event.status = IntegrationWebhookStatus.PROCESSING
    event.attempts = (event.attempts or 0) + 1
    session.add(event)

    payload = dict(event.payload or {})
    issue_payload = _extract_issue_payload(payload)

    external_id = str(
        issue_payload.get("external_id")
        or issue_payload.get("id")
        or issue_payload.get("key")
        or ""
    ).strip()
    if not external_id:
        raise WebhookProcessingError("Webhook payload missing issue identifier")

    project_id = event.project_id
    integration_id = event.integration_id

    issue = find_issue_by_external(
        session,
        project_id=project_id,
        provider=provider,
        external_id=external_id,
    )
    if issue is None:
        raise WebhookProcessingError(f"Issue {external_id!r} for provider {provider} not found")

    remote_status = issue_payload.get("status") or issue_payload.get("state")
    remote_title = issue_payload.get("title")
    remote_url = issue_payload.get("url") or issue_payload.get("self")
    remote_labels = issue_payload.get("labels")
    remote_assignees = issue_payload.get("assignee") or issue_payload.get("assignees")

    if isinstance(remote_status, str) and remote_status.strip():
        issue.status = remote_status.strip()
    if isinstance(remote_title, str) and remote_title.strip():
        issue.title = remote_title.strip()
    if isinstance(remote_url, str) and remote_url.strip():
        issue.url = remote_url.strip()

    metadata = dict(issue.metadata or {})
    remote_state = dict(metadata.get("remote_state") or {})
    remote_state.update(
        {
            "status": issue.status,
            "labels": remote_labels,
            "assignees": remote_assignees,
            "raw": issue_payload,
            "updated_at": now.isoformat(),
        }
    )
    metadata["remote_state"] = remote_state
    issue.metadata = metadata

    prs = list(_iter_pull_requests(provider, issue_payload.get("pull_requests") or issue_payload.get("prs")))
    commits = list(_iter_commits(provider, issue_payload.get("commits") or issue_payload.get("commit_refs")))

    links_updated = False
    if prs:
        links_updated = attach_pull_requests(issue, prs) or links_updated
    if commits:
        links_updated = attach_commits(issue, commits) or links_updated

    issue.last_sync_at = now
    issue.last_webhook_at = now
    issue.sync_state = IssueSyncState.OK
    issue.last_error = None

    event.status = IntegrationWebhookStatus.PROCESSED
    event.processed_at = now
    event.error = None

    session.add(issue)
    session.add(event)
    if links_updated:
        session.flush()
    return issue


def fail_webhook_event(event: IntegrationWebhook, message: str) -> None:
    event.status = IntegrationWebhookStatus.FAILED
    event.error = message
    event.processed_at = datetime.now(timezone.utc)


def parse_payload(body: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:  # pragma: no cover - defensive
        raise WebhookProcessingError("Webhook payload is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise WebhookProcessingError("Webhook payload must be a JSON object")
    return payload


__all__ = [
    "WebhookProcessingError",
    "WebhookVerificationError",
    "fail_webhook_event",
    "parse_payload",
    "process_webhook_event",
    "record_webhook_event",
    "verify_webhook_request",
]
