from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Set

from fastapi import Request

from app.core.api_tokens import TokenScope


@dataclass(frozen=True)
class ScopeRule:
    required_scopes: frozenset[str]
    path_prefix: str
    methods: frozenset[str] | None = None
    include_subpaths: bool = True
    allow_pat: bool = True

    def matches(self, template_path: str, method: str) -> bool:
        if self.methods and method not in self.methods:
            return False
        if self.include_subpaths:
            return template_path.startswith(self.path_prefix)
        return template_path == self.path_prefix


# Rules ordered by priority (more specific first).
_SCOPE_RULES: tuple[ScopeRule, ...] = (
    ScopeRule(required_scopes=frozenset(), path_prefix="/api/v1/tokens", allow_pat=False),
    ScopeRule(required_scopes=frozenset({TokenScope.EXECUTE.value}), path_prefix="/api/v1/projects/{project_id}/execute"),
    ScopeRule(required_scopes=frozenset({TokenScope.EXECUTE.value}), path_prefix="/api/v1/projects/{project_id}/plans/{plan_id}/run", methods=frozenset({"POST"})),
    ScopeRule(required_scopes=frozenset({TokenScope.EXECUTE.value}), path_prefix="/api/v1/projects/{project_id}/plans/{plan_id}/run-now", methods=frozenset({"POST"})),
    ScopeRule(required_scopes=frozenset({TokenScope.READ_REPORTS.value}), path_prefix="/api/v1/reports"),
    ScopeRule(required_scopes=frozenset({TokenScope.WRITE_INTEGRATIONS.value}), path_prefix="/api/v1/integrations", methods=frozenset({"POST", "PUT", "PATCH", "DELETE"})),
    ScopeRule(required_scopes=frozenset({TokenScope.WRITE_APIS.value}), path_prefix="/api/v1/apis", methods=frozenset({"POST", "PUT", "PATCH", "DELETE"})),
    ScopeRule(required_scopes=frozenset({TokenScope.READ_APIS.value}), path_prefix="/api/v1/apis", methods=frozenset({"GET"})),
    ScopeRule(required_scopes=frozenset({TokenScope.WRITE_CASES.value}), path_prefix="/api/v1/test-cases", methods=frozenset({"POST", "PUT", "PATCH", "DELETE"})),
    ScopeRule(required_scopes=frozenset({TokenScope.WRITE_CASES.value}), path_prefix="/api/v1/test-suites", methods=frozenset({"POST", "PUT", "PATCH", "DELETE"})),
    ScopeRule(required_scopes=frozenset({TokenScope.READ_CASES.value}), path_prefix="/api/v1/test-cases", methods=frozenset({"GET"})),
    ScopeRule(required_scopes=frozenset({TokenScope.READ_CASES.value}), path_prefix="/api/v1/test-suites", methods=frozenset({"GET"})),
    ScopeRule(required_scopes=frozenset({TokenScope.WRITE_INTEGRATIONS.value}), path_prefix="/api/v1/integrations/{integration_id}/secrets", methods=frozenset({"POST", "PUT", "PATCH", "DELETE"})),
    ScopeRule(required_scopes=frozenset({TokenScope.WRITE_PROJECTS.value}), path_prefix="/api/v1/projects", methods=frozenset({"POST", "PUT", "PATCH", "DELETE"})),
    ScopeRule(required_scopes=frozenset({TokenScope.READ_PROJECTS.value}), path_prefix="/api/v1/projects", methods=frozenset({"GET"})),
    ScopeRule(required_scopes=frozenset({TokenScope.ADMIN.value}), path_prefix="/api/v1/admin"),
)


def resolve_required_scopes(request: Request) -> tuple[Set[str], bool]:
    route = request.scope.get("route")
    template_path = getattr(route, "path", request.url.path)
    method = request.method.upper()

    for rule in _SCOPE_RULES:
        if rule.matches(template_path, method):
            return set(rule.required_scopes), rule.allow_pat
    return set(), True


__all__ = ["resolve_required_scopes"]
