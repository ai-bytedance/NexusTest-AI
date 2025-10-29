from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from app.models.integration import Integration, IntegrationProvider


class IssueTrackerError(RuntimeError):
    """Raised when an issue tracker operation fails."""


@dataclass(slots=True)
class IssueCreateData:
    title: str
    description: str
    labels: list[str] = field(default_factory=list)
    assignees: list[str] = field(default_factory=list)
    components: list[str] = field(default_factory=list)
    status: str | None = None
    fields: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class IssueResult:
    external_id: str
    url: str
    title: str
    status: str
    raw: dict[str, Any] = field(default_factory=dict)


class IssueTrackerProvider:
    def __init__(self, integration: Integration) -> None:
        self.integration = integration
        self.config: dict[str, Any] = dict(integration.config or {})
        self.operations: list[dict[str, Any]] = []

    def test_connection(self) -> None:
        if not self.config:
            raise IssueTrackerError("Integration is missing configuration")

    def create_issue(self, data: IssueCreateData) -> IssueResult:
        raise NotImplementedError

    def add_comment(self, external_id: str, body: str) -> None:
        self._record("comment", external_id=external_id, body=body)

    def transition_issue(self, external_id: str, status: str) -> None:
        self._record("transition", external_id=external_id, status=status)

    def close_issue(self, external_id: str) -> None:
        self.transition_issue(external_id, "closed")

    def reopen_issue(self, external_id: str) -> None:
        self.transition_issue(external_id, "reopened")

    def _generate_key(self, prefix: str) -> str:
        suffix = uuid.uuid4().hex[:8].upper()
        return f"{prefix}-{suffix}"

    def _record(self, operation: str, **payload: Any) -> None:
        self.operations.append({"operation": operation, "payload": payload})


class JiraProvider(IssueTrackerProvider):
    def test_connection(self) -> None:
        super().test_connection()
        required = {"base_url", "project_key"}
        missing = [key for key in required if not self.config.get(key)]
        if missing:
            raise IssueTrackerError(f"Missing Jira configuration values: {', '.join(missing)}")

    def create_issue(self, data: IssueCreateData) -> IssueResult:
        self.test_connection()
        project_key = str(self.config["project_key"]).upper()
        issue_type = (data.fields or {}).get("issuetype") or self.config.get("issue_type", "Task")
        external_id = self._generate_key(project_key)
        base_url = str(self.config.get("browse_url") or self.config.get("base_url"))
        url = f"{base_url.rstrip('/')}/browse/{external_id}"
        payload = {
            "project_key": project_key,
            "summary": data.title,
            "description": data.description,
            "labels": data.labels,
            "components": data.components,
            "assignees": data.assignees,
            "issue_type": issue_type,
            "fields": data.fields,
            "metadata": data.metadata,
        }
        self._record("create_issue", external_id=external_id, payload=payload)
        return IssueResult(external_id=external_id, url=url, title=data.title, status=data.status or "open", raw=payload)


class LinearProvider(IssueTrackerProvider):
    def test_connection(self) -> None:
        super().test_connection()
        if not self.config.get("team_key"):
            raise IssueTrackerError("Linear configuration requires team_key")

    def create_issue(self, data: IssueCreateData) -> IssueResult:
        self.test_connection()
        team_key = str(self.config.get("team_key")).upper()
        external_id = self._generate_key(team_key)
        base_url = str(self.config.get("base_url", "https://linear.app"))
        url = f"{base_url.rstrip('/')}/{team_key.lower()}/{external_id.lower()}"
        payload = {
            "team_key": team_key,
            "title": data.title,
            "description": data.description,
            "labels": data.labels,
            "assignees": data.assignees,
            "status": data.status or "triage",
            "fields": data.fields,
            "metadata": data.metadata,
        }
        self._record("create_issue", external_id=external_id, payload=payload)
        return IssueResult(external_id=external_id, url=url, title=data.title, status=data.status or "open", raw=payload)


class GitHubProvider(IssueTrackerProvider):
    def test_connection(self) -> None:
        super().test_connection()
        required = {"owner", "repo"}
        missing = [item for item in required if not self.config.get(item)]
        if missing:
            raise IssueTrackerError(f"Missing GitHub configuration values: {', '.join(missing)}")

    def create_issue(self, data: IssueCreateData) -> IssueResult:
        self.test_connection()
        owner = self.config["owner"]
        repo = self.config["repo"]
        base_url = str(self.config.get("base_url", "https://github.com"))
        number = int(uuid.uuid4().int % 9000) + 1000
        external_id = str(number)
        url = f"{base_url.rstrip('/')}/{owner}/{repo}/issues/{external_id}"
        payload = {
            "owner": owner,
            "repo": repo,
            "title": data.title,
            "body": data.description,
            "labels": data.labels,
            "assignees": data.assignees,
            "metadata": data.metadata,
        }
        self._record("create_issue", external_id=external_id, payload=payload)
        return IssueResult(external_id=external_id, url=url, title=data.title, status=data.status or "open", raw=payload)

    def close_issue(self, external_id: str) -> None:
        self._record("close_issue", external_id=external_id)

    def reopen_issue(self, external_id: str) -> None:
        self._record("reopen_issue", external_id=external_id)


def get_provider(integration: Integration) -> IssueTrackerProvider:
    if integration.provider == IntegrationProvider.JIRA:
        return JiraProvider(integration)
    if integration.provider == IntegrationProvider.LINEAR:
        return LinearProvider(integration)
    if integration.provider == IntegrationProvider.GITHUB:
        return GitHubProvider(integration)
    raise IssueTrackerError(f"Unsupported provider: {integration.provider}")


__all__ = [
    "IssueTrackerError",
    "IssueCreateData",
    "IssueResult",
    "IssueTrackerProvider",
    "JiraProvider",
    "LinearProvider",
    "GitHubProvider",
    "get_provider",
]
