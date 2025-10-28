from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.api import Api
from app.models.project import Project
from app.schemas.api import HTTPMethod
from app.schemas.importers import ImportSummary

logger = logging.getLogger(__name__)

SUPPORTED_METHODS = {method.value for method in HTTPMethod}


@dataclass
class OpenAPIImportResult:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    details: list[str] = field(default_factory=list)

    def to_summary(self) -> ImportSummary:
        return ImportSummary(created=self.created, updated=self.updated, skipped=self.skipped, details=self.details)


class OpenAPIImporter:
    def __init__(self, db: Session, project: Project, *, dry_run: bool = False) -> None:
        self.db = db
        self.project = project
        self.dry_run = dry_run
        self.result = OpenAPIImportResult()
        self._components: dict[str, Any] = {}
        self._seen: set[tuple[str, str, str]] = set()

    def import_spec(self, document: dict[str, Any]) -> ImportSummary:
        self._components = document.get("components", {}).get("schemas", {})
        version = document.get("info", {}).get("version", "v1")

        paths: dict[str, Any] = document.get("paths", {})
        for raw_path, operations in paths.items():
            if not isinstance(operations, dict):
                continue
            for method, payload in operations.items():
                method_upper = method.upper()
                if method_upper not in SUPPORTED_METHODS:
                    continue

                normalized_path = raw_path if raw_path.startswith("/") else f"/{raw_path}"
                dedupe_key = (method_upper, normalized_path, version)
                if dedupe_key in self._seen:
                    self.result.skipped += 1
                    continue
                self._seen.add(dedupe_key)

                operation: dict[str, Any] = payload if isinstance(payload, dict) else {}
                api_payload = self._build_api_payload(operation, method_upper, normalized_path, version)
                self._upsert_api(api_payload)

        if not self.dry_run and (self.result.created or self.result.updated):
            self.db.commit()

        return self.result.to_summary()

    def _build_api_payload(
        self,
        operation: dict[str, Any],
        method: str,
        path: str,
        version: str,
    ) -> dict[str, Any]:
        name = operation.get("summary") or operation.get("operationId") or f"{method} {path}"
        tags = operation.get("tags") or []
        group_name = tags[0] if tags else None

        parameters = operation.get("parameters") or []
        headers: dict[str, Any] = {}
        params: dict[str, Any] = {}
        for parameter in parameters:
            if not isinstance(parameter, dict):
                continue
            location = parameter.get("in")
            key = parameter.get("name")
            if not key:
                continue
            example = self._extract_example(parameter)
            if location == "header":
                headers[key] = example
            elif location == "query":
                params[key] = example

        body = self._extract_request_body(operation)
        mock_example = self._extract_mock_examples(operation)

        payload = {
            "project_id": self.project.id,
            "name": name,
            "method": method,
            "path": path,
            "version": version,
            "group_name": group_name,
            "headers": headers,
            "params": params,
            "body": body,
            "mock_example": mock_example,
        }
        return payload

    def _extract_example(self, definition: dict[str, Any]) -> Any:
        if not isinstance(definition, dict):
            return None
        if "example" in definition:
            return definition["example"]
        schema = definition.get("schema") if "schema" in definition else definition
        if isinstance(schema, dict):
            if "example" in schema:
                return schema["example"]
            if "default" in schema:
                return schema["default"]
            if "enum" in schema:
                enum_values = schema.get("enum")
                if isinstance(enum_values, Iterable):
                    enum_values = list(enum_values)
                    return enum_values[0] if enum_values else None
        return None

    def _extract_request_body(self, operation: dict[str, Any]) -> dict[str, Any]:
        body: dict[str, Any] = {}
        request_body = operation.get("requestBody") or {}
        if not isinstance(request_body, dict):
            return body
        content = request_body.get("content") or {}
        for media_type, media_payload in content.items():
            if not isinstance(media_payload, dict):
                continue
            schema = self._resolve_schema(media_payload.get("schema"))
            body[media_type] = {
                "schema": schema,
                "example": media_payload.get("example")
                or media_payload.get("examples")
                or self._generate_example(schema),
            }
        return body

    def _extract_mock_examples(self, operation: dict[str, Any]) -> dict[str, Any]:
        examples: dict[str, Any] = {}

        request_body = self._extract_request_body(operation)
        if request_body:
            examples["request"] = request_body

        responses = operation.get("responses") or {}
        for status_code, response_payload in responses.items():
            if not isinstance(response_payload, dict):
                continue
            content = response_payload.get("content") or {}
            for media_type, media_payload in content.items():
                if not isinstance(media_payload, dict):
                    continue
                schema = self._resolve_schema(media_payload.get("schema"))
                example = (
                    media_payload.get("example")
                    or media_payload.get("examples")
                    or self._generate_example(schema)
                )
                if example is None:
                    continue
                examples.setdefault("responses", {}).setdefault(status_code, {})[media_type] = example
        return examples

    def _resolve_schema(self, schema: Any) -> Any:
        if not isinstance(schema, dict):
            return schema
        ref = schema.get("$ref")
        if ref and isinstance(ref, str) and ref.startswith("#/components/schemas/"):
            key = ref.split("/")[-1]
            resolved = self._components.get(key)
            if resolved:
                return resolved
        return schema

    def _generate_example(self, schema: Any, depth: int = 0) -> Any:
        if depth > 3 or not isinstance(schema, dict):
            return None
        if "example" in schema:
            return schema["example"]
        schema_type = schema.get("type")
        if schema_type == "object":
            properties = schema.get("properties") or {}
            example_obj = {}
            for key, value in properties.items():
                example_obj[key] = self._generate_example(value, depth + 1)
            return example_obj
        if schema_type == "array":
            items = schema.get("items") or {}
            generated = self._generate_example(items, depth + 1)
            return [generated] if generated is not None else []
        if schema_type == "string":
            return schema.get("default") or "string"
        if schema_type == "integer":
            return schema.get("default") or 0
        if schema_type == "number":
            return schema.get("default") or 0.0
        if schema_type == "boolean":
            return schema.get("default") or True
        if "enum" in schema and isinstance(schema["enum"], list):
            return schema["enum"][0] if schema["enum"] else None
        return None

    def _upsert_api(self, payload: dict[str, Any]) -> None:
        stmt = select(Api).where(
            Api.project_id == payload["project_id"],
            Api.method == payload["method"],
            Api.path == payload["path"],
            Api.version == payload["version"],
            Api.is_deleted.is_(False),
        )
        existing = self.db.execute(stmt).scalar_one_or_none()
        if existing is None:
            self._create_api(payload)
            return

        fields = ["name", "group_name", "headers", "params", "body", "mock_example"]
        has_changes = any(getattr(existing, field) != payload[field] for field in fields)
        if has_changes:
            for field in fields:
                setattr(existing, field, payload[field])
            if not self.dry_run:
                self.db.add(existing)
            self.result.updated += 1
        else:
            self.result.skipped += 1

    def _create_api(self, payload: dict[str, Any]) -> None:
        self.result.created += 1
        if self.dry_run:
            return
        api = Api(**payload)
        self.db.add(api)


def fetch_openapi_spec(url: str, *, timeout: float = 15.0) -> dict[str, Any]:
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as exc:
        logger.error("openapi_fetch_failed", url=url, error=str(exc))
        raise ValueError(f"Failed to fetch OpenAPI document from {url}") from exc


def import_openapi_spec(
    db: Session,
    project: Project,
    document: dict[str, Any],
    *,
    dry_run: bool = False,
) -> ImportSummary:
    importer = OpenAPIImporter(db, project, dry_run=dry_run)
    return importer.import_spec(document)
