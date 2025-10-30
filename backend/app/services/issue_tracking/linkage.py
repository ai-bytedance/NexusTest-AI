from __future__ import annotations

import re
from typing import Any, Iterable, MutableMapping

from app.models.issue import Issue

_GITHUB_PR_PATTERN = re.compile(r"https?://(?:www\.)?github\.com/([^/]+)/([^/]+)/pull/(\d+)")
_GITHUB_COMMIT_PATTERN = re.compile(r"https?://(?:www\.)?github\.com/([^/]+)/([^/]+)/commit/([0-9a-fA-F]{7,40})")


def _provider_value(provider: Any) -> str:
    if provider is None:
        return ""
    if hasattr(provider, "value"):
        return str(getattr(provider, "value"))
    return str(provider)


def normalize_pull_request_reference(
    provider: Any,
    *,
    pr_url: str | None = None,
    owner: str | None = None,
    repo: str | None = None,
    number: int | str | None = None,
    title: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    provider_value = _provider_value(provider)
    url = pr_url.strip() if isinstance(pr_url, str) else None
    resolved_owner = owner.strip() if isinstance(owner, str) and owner.strip() else None
    resolved_repo = repo.strip() if isinstance(repo, str) and repo.strip() else None
    resolved_number: int | None

    if isinstance(number, str):
        resolved_number = int(number) if number.isdigit() else None
    else:
        resolved_number = number

    if provider_value == "github" and url:
        match = _GITHUB_PR_PATTERN.match(url)
        if match:
            resolved_owner = resolved_owner or match.group(1)
            resolved_repo = resolved_repo or match.group(2)
            try:
                resolved_number = resolved_number or int(match.group(3))
            except ValueError:  # pragma: no cover - defensive
                resolved_number = resolved_number or None

    reference = {
        "provider": provider_value,
        "url": url,
        "owner": resolved_owner,
        "repo": resolved_repo,
        "number": resolved_number,
        "title": title.strip() if isinstance(title, str) and title.strip() else None,
        "metadata": metadata or {},
    }
    return reference


def normalize_commit_reference(
    provider: Any,
    *,
    sha: str,
    commit_url: str | None = None,
    owner: str | None = None,
    repo: str | None = None,
    message: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    provider_value = _provider_value(provider)
    normalized_sha = sha.strip()
    url = commit_url.strip() if isinstance(commit_url, str) else None
    resolved_owner = owner.strip() if isinstance(owner, str) and owner.strip() else None
    resolved_repo = repo.strip() if isinstance(repo, str) and repo.strip() else None
    resolved_message = message.strip() if isinstance(message, str) and message.strip() else None

    if provider_value == "github" and url:
        match = _GITHUB_COMMIT_PATTERN.match(url)
        if match:
            resolved_owner = resolved_owner or match.group(1)
            resolved_repo = resolved_repo or match.group(2)
            normalized_sha = match.group(3)

    reference = {
        "provider": provider_value,
        "sha": normalized_sha,
        "url": url,
        "owner": resolved_owner,
        "repo": resolved_repo,
        "message": resolved_message,
        "metadata": metadata or {},
    }
    return reference


def _merge_items(
    existing: list[dict[str, Any]],
    new_items: Iterable[dict[str, Any]],
    *,
    identity_fn,
) -> tuple[list[dict[str, Any]], bool]:
    updated = False
    registry: MutableMapping[str, dict[str, Any]] = {}
    result: list[dict[str, Any]] = []

    for item in existing or []:
        identity = identity_fn(item)
        if identity is None:
            continue
        registry[identity] = item.copy()
        result.append(registry[identity])

    for candidate in new_items:
        identity = identity_fn(candidate)
        if identity is None:
            continue
        payload = registry.get(identity)
        if payload is None:
            payload = candidate.copy()
            registry[identity] = payload
            result.append(payload)
            updated = True
            continue
        # Merge metadata and fill missing fields
        for key, value in candidate.items():
            if value in (None, "", [], {}):
                continue
            if key == "metadata":
                existing_meta = payload.get("metadata") or {}
                merged_meta = {**existing_meta, **value}
                if merged_meta != existing_meta:
                    payload["metadata"] = merged_meta
                    updated = True
                continue
            if payload.get(key) in (None, "", []):
                payload[key] = value
                updated = True
    return result, updated


def _pr_identity(payload: dict[str, Any]) -> str | None:
    provider = _provider_value(payload.get("provider")).lower()
    url = str(payload.get("url") or "").strip().rstrip("/")
    number = payload.get("number")
    owner = str(payload.get("owner") or "").lower()
    repo = str(payload.get("repo") or "").lower()
    if url:
        return f"{provider}|url|{url}"
    if provider and repo and number is not None:
        return f"{provider}|repo|{owner}/{repo}|#{number}"
    if provider and number is not None:
        return f"{provider}|number|{number}"
    if provider and repo:
        return f"{provider}|repo|{owner}/{repo}"
    return None


def _commit_identity(payload: dict[str, Any]) -> str | None:
    provider = _provider_value(payload.get("provider")).lower()
    sha = str(payload.get("sha") or "").lower()
    url = str(payload.get("url") or "").strip().rstrip("/")
    if sha and provider:
        return f"{provider}|sha|{sha}"
    if url and provider:
        return f"{provider}|url|{url}"
    return None


def attach_pull_requests(issue: Issue, references: Iterable[dict[str, Any]]) -> bool:
    existing = list(issue.linked_prs or [])
    merged, updated = _merge_items(existing, references, identity_fn=_pr_identity)
    if updated:
        issue.linked_prs = merged
    return updated


def attach_commits(issue: Issue, references: Iterable[dict[str, Any]]) -> bool:
    existing = list(issue.linked_commits or [])
    merged, updated = _merge_items(existing, references, identity_fn=_commit_identity)
    if updated:
        issue.linked_commits = merged
    return updated


__all__ = [
    "attach_commits",
    "attach_pull_requests",
    "normalize_commit_reference",
    "normalize_pull_request_reference",
]
