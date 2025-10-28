from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.api import Api
from app.models.project import Project
from app.schemas.api import HTTPMethod
from app.schemas.importers import ImportSummary

SUPPORTED_METHODS = {method.value for method in HTTPMethod}


@dataclass
class PostmanImportResult:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    details: list[str] = field(default_factory=list)

    def to_summary(self) -> ImportSummary:
        return ImportSummary(created=self.created, updated=self.updated, skipped=self.skipped, details=self.details)


class PostmanImporter:
    def __init__(self, db: Session, project: Project, *, dry_run: bool = False) -> None:
        self.db = db
        self.project = project
        self.dry_run = dry_run
        self.result = PostmanImportResult()
        self._seen: set[tuple[str, str, str]] = set()

    def import_collection(self, collection: dict[str, Any]) -> ImportSummary:
        info = collection.get("info") or {}
        version = str(info.get("version") or "v1")
        items = collection.get("item") or []
        self._traverse_items(items, version, parent_group=None)

        if not self.dry_run and (self.result.created or self.result.updated):
            self.db.commit()

        return self.result.to_summary()

    def _traverse_items(self, items: list[Any], version: str, parent_group: str | None) -> None:
        for item in items:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if "item" in item:
                self._traverse_items(item.get("item") or [], version, parent_group=name or parent_group)
                continue

            request = item.get("request") or {}
            method = str(request.get("method") or "GET").upper()
            if method not in SUPPORTED_METHODS:
                continue

            url = request.get("url")
            path, params = self._parse_url(url)
            if not path:
                continue

            dedupe_key = (method, path, version)
            if dedupe_key in self._seen:
                self.result.skipped += 1
                continue
            self._seen.add(dedupe_key)

            headers = self._parse_headers(request.get("header") or [])
            body = self._parse_body(request.get("body"))
            responses = self._parse_responses(item.get("response") or [])
            mock_example = {"responses": responses} if responses else {}
            if body:
                mock_example.setdefault("request", body)

            payload = {
                "project_id": self.project.id,
                "name": name or f"{method} {path}",
                "method": method,
                "path": path,
                "version": version,
                "group_name": parent_group,
                "headers": headers,
                "params": params,
                "body": body,
                "mock_example": mock_example,
            }
            self._upsert_api(payload)

    def _parse_url(self, url: Any) -> tuple[str, dict[str, Any]]:
        if isinstance(url, str):
            parsed = urlparse(url)
            return parsed.path or "/", {key: values[0] if values else None for key, values in parse_qs(parsed.query).items()}
        if isinstance(url, dict):
            raw = url.get("raw")
            if raw:
                return self._parse_url(raw)
            path_segments = url.get("path") or []
            path = "/" + "/".join(segment for segment in path_segments if segment)
            path = path or "/"
            query = {}
            for query_param in url.get("query") or []:
                if not isinstance(query_param, dict):
                    continue
                key = query_param.get("key")
                if not key:
                    continue
                query[key] = query_param.get("value")
            return path, query
        return "/", {}

    def _parse_headers(self, headers: list[Any]) -> dict[str, Any]:
        parsed: dict[str, Any] = {}
        for header in headers:
            if not isinstance(header, dict):
                continue
            key = header.get("key")
            if not key:
                continue
            parsed[key] = header.get("value")
        return parsed

    def _parse_body(self, body: Any) -> dict[str, Any]:
        if not isinstance(body, dict):
            return {}
        mode = body.get("mode")
        result: dict[str, Any] = {"mode": mode}
        if mode == "raw":
            raw = body.get("raw")
            if isinstance(raw, str):
                try:
                    result["parsed"] = json.loads(raw)
                except json.JSONDecodeError:
                    result["raw"] = raw
            return result
        if mode in {"formdata", "urlencoded"}:
            entries = body.get(mode) or []
            data: dict[str, Any] = {}
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                key = entry.get("key")
                if not key:
                    continue
                data[key] = entry.get("value")
            result[mode] = data
            return result
        return {}

    def _parse_responses(self, responses: list[Any]) -> dict[str, Any]:
        parsed: dict[str, Any] = {}
        for response in responses:
            if not isinstance(response, dict):
                continue
            code = str(response.get("code") or "200")
            body = response.get("body")
            if isinstance(body, str):
                try:
                    parsed_body = json.loads(body)
                except json.JSONDecodeError:
                    parsed_body = body
            else:
                parsed_body = body
            parsed[code] = parsed_body
        return parsed

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


def import_postman_collection(
    db: Session,
    project: Project,
    collection: dict[str, Any],
    *,
    dry_run: bool = False,
) -> ImportSummary:
    importer = PostmanImporter(db, project, dry_run=dry_run)
    return importer.import_collection(collection)
