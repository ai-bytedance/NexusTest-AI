from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field, model_validator

from app.models.integration import IntegrationProvider
from app.models.issue import IssueLinkSource, IssueSyncState
from app.schemas.common import IdentifierModel, ORMModel


class IssueTemplatePayload(ORMModel):
    title: str | None = None
    description: str | None = None
    labels: list[str] = Field(default_factory=list)
    status: str | None = None
    assignees: list[str] = Field(default_factory=list)
    components: list[str] = Field(default_factory=list)
    fields: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LinkedPullRequest(ORMModel):
    provider: str
    url: str
    repo: str | None = None
    number: int | None = None
    title: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class LinkedCommit(ORMModel):
    provider: str
    sha: str
    url: str | None = None
    repo: str | None = None
    message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class IssueLinkRead(IdentifierModel):
    report_id: UUID
    issue_id: UUID
    linked_by: UUID | None
    source: IssueLinkSource
    note: str | None
    metadata: dict[str, Any]


class IssueRead(IdentifierModel):
    project_id: UUID
    integration_id: UUID | None
    provider: str
    external_id: str
    url: str
    title: str
    status: str
    sync_state: IssueSyncState
    dedupe_key: str | None
    created_by: UUID | None
    external_created_at: datetime | None
    last_sync_at: datetime | None
    last_webhook_at: datetime | None
    last_error: str | None
    metadata: dict[str, Any]
    linked_prs: list[LinkedPullRequest] = Field(default_factory=list)
    linked_commits: list[LinkedCommit] = Field(default_factory=list)


class IssueWithLinks(IssueRead):
    links: list[IssueLinkRead] = Field(default_factory=list)


class ReportIssueCreateRequest(ORMModel):
    integration_id: UUID | None = None
    provider: IntegrationProvider | None = None
    template: IssueTemplatePayload | None = None
    note: str | None = None
    category: str | None = None

    @model_validator(mode="after")
    def _validate_target(self) -> "ReportIssueCreateRequest":
        if self.integration_id is None and self.provider is None:
            raise ValueError("integration_id or provider must be provided")
        return self


class ReportIssueLinkRequest(ORMModel):
    issue_id: UUID | None = None
    external_id: str | None = None
    provider: IntegrationProvider | None = None
    note: str | None = None

    @model_validator(mode="after")
    def _validate_payload(self) -> "ReportIssueLinkRequest":
        if self.issue_id is None and (self.external_id is None or self.provider is None):
            raise ValueError("Provide issue_id or external_id with provider")
        return self


class ReportIssuePRLinkRequest(ORMModel):
    provider: IntegrationProvider
    pr_url: str | None = None
    owner: str | None = None
    repo: str | None = None
    number: int | None = Field(default=None, ge=1)
    title: str | None = None
    issue_id: UUID | None = None
    post_comment: bool = False

    @model_validator(mode="after")
    def _validate_pr_payload(self) -> "ReportIssuePRLinkRequest":
        if not self.pr_url and not (self.owner and self.repo and self.number is not None):
            raise ValueError("Provide pr_url or owner/repo/number")
        return self


class ReportIssueListResponse(ORMModel):
    report_id: UUID
    issues: list[IssueWithLinks]


__all__ = [
    "IssueTemplatePayload",
    "LinkedPullRequest",
    "LinkedCommit",
    "IssueLinkRead",
    "IssueRead",
    "IssueWithLinks",
    "ReportIssueCreateRequest",
    "ReportIssueLinkRequest",
    "ReportIssuePRLinkRequest",
    "ReportIssueListResponse",
]
