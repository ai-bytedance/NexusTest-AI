from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Iterable
from urllib.parse import parse_qs, urlparse

import httpx
from sqlalchemy.orm import Session

from app.core.errors import ErrorCode, http_exception
from app.models.import_source import ImportSource, ImportSourceType, ImporterKind
from app.models.project import Project
from app.schemas.api import HTTPMethod
from app.schemas.importers import ImportSummary, PostmanImportOptions
from app.services.importers.common import ImportCandidate, compute_hash, normalize_method, normalize_path
from app.services.importers.manager import ImportManager, SourceDescriptor
from app.services.importers.workflow import SourceDescriptor as WorkflowSourceDescriptor

logger = logging.getLogger(__name__)

SUPPORTED_METHODS = {method.value for method in HTTPMethod}
PLACEHOLDER_PATTERN = re.compile(r"{{\s*([^{}\s]+)\s*}}")
DEFAULT_TIMEOUT = 15.0


@dataclass(slots=True)
class AuthInfo:
    headers: dict[str, Any]
    params: dict[str, Any]
    type: str | None = None
    raw: dict[str, Any] | None = None


class PostmanParser:
    def __init__(
        self,
        collection: dict[str, Any],
        *,
        options: PostmanImportOptions,
    ) -> None:
        self.collection = collection
        self.options = options
        self.collection_info = collection.get("info") or {}
        self.collection_name = self.collection_info.get("name")
        self.version = str(self.collection_info.get("version") or "v1")
        self.base_variables = self._build_variable_scope(collection.get("variable"))
        self.environment = self._prepare_environment()
        self.global_auth = self._normalize_auth(collection.get("auth"), self.environment)

    def parse(self) -> tuple[list[ImportCandidate], dict[str, Any]]:
        items = self.collection.get("item") or []
        if not isinstance(items, list):
            raise http_exception(
                status_code=400,
                code=ErrorCode.IMPORT_INVALID_SPEC,
                message="Postman collection 'item' must be a list",
            )
        candidates: list[ImportCandidate] = []
        self._walk_items(items, folder_stack=[], inherited_auth=self.global_auth, variables=self.environment, sink=candidates)
        metadata = {
            "collection": {
                "name": self.collection_name,
                "version": self.version,
                "variable_keys": sorted(self.environment.keys()),
            }
        }
        return candidates, metadata

    def _walk_items(
        self,
        items: Iterable[Any],
        *,
        folder_stack: list[str],
        inherited_auth: AuthInfo | None,
        variables: dict[str, Any],
        sink: list[ImportCandidate],
    ) -> None:
        for item in items:
            if not isinstance(item, dict):
                continue
            local_variables = self._merge_variables(variables, item.get("variable"))
            folder_auth = self._normalize_auth(item.get("auth"), local_variables) or inherited_auth
            name = self._resolve_value(item.get("name"), local_variables)

            if "item" in item:
                new_stack = folder_stack + ([name] if name else [])
                self._walk_items(
                    item.get("item") or [],
                    folder_stack=new_stack,
                    inherited_auth=folder_auth,
                    variables=local_variables,
                    sink=sink,
                )
                continue

            request = item.get("request")
            if not isinstance(request, dict):
                continue
            method = self._resolve_value(request.get("method"), local_variables) or "GET"
            method_upper = normalize_method(method)
            if method_upper not in SUPPORTED_METHODS:
                continue

            url_info = self._parse_url(request.get("url"), local_variables)
            if not url_info:
                continue
            path, params, resolved_url, base_url = url_info
            normalized_path = normalize_path(path)

            headers = self._parse_headers(request.get("header"), local_variables)
            body = self._parse_body(request.get("body"), local_variables)
            responses = self._parse_responses(item.get("response"))
            mock_example: dict[str, Any] = {"responses": responses} if responses else {}
            if body:
                mock_example.setdefault("request", body)

            effective_auth = self._normalize_auth(request.get("auth"), local_variables) or folder_auth
            if effective_auth and self.options.inherit_auth:
                for key, value in effective_auth.headers.items():
                    headers.setdefault(key, value)
                for key, value in effective_auth.params.items():
                    params.setdefault(key, value)

            group_name = self._determine_group(folder_stack)
            source_key = item.get("id") or f"{method_upper}:{normalized_path}"

            metadata = {
                "postman": {
                    "name": name,
                    "folder_path": folder_stack,
                    "raw_url": self._extract_raw_url(request.get("url")),
                    "resolved_url": resolved_url,
                    "base_url": base_url,
                    "auth": effective_auth.raw if effective_auth else None,
                    "pre_request_script": self._parse_scripts(item.get("event")),
                }
            }

            candidate = ImportCandidate(
                method=method_upper,
                path=normalized_path,
                normalized_path=normalized_path,
                version=self.version,
                name=name or f"{method_upper} {normalized_path}",
                group_name=group_name,
                headers=headers,
                params=params,
                body=body,
                mock_example=mock_example,
                metadata=metadata,
                source_key=source_key,
            )
            sink.append(candidate)

    def _prepare_environment(self) -> dict[str, Any]:
        variables = dict(self.base_variables)
        variables.update(self._normalise_option_variables(self.options.globals))
        variables.update(self._normalise_option_variables(self.options.environment))
        return variables

    def _merge_variables(self, base: dict[str, Any], additions: Any) -> dict[str, Any]:
        merged = dict(base)
        merged.update(self._build_variable_scope(additions))
        return merged

    def _build_variable_scope(self, variables: Any) -> dict[str, Any]:
        scope: dict[str, Any] = {}
        if not variables:
            return scope
        if isinstance(variables, dict) and "values" in variables:
            variables = variables.get("values")
        for variable in variables or []:
            if not isinstance(variable, dict):
                continue
            key = variable.get("key") or variable.get("name")
            if not key:
                continue
            value = variable.get("value")
            scope[str(key)] = value
        return scope

    def _normalise_option_variables(self, variables: Any) -> dict[str, Any]:
        return self._build_variable_scope(variables)

    def _resolve_value(self, value: Any, variables: dict[str, Any]) -> Any:
        if isinstance(value, str):
            if not self.options.resolve_variables:
                return value
            def replacer(match: re.Match[str]) -> str:
                key = match.group(1)
                resolved = variables.get(key)
                return str(resolved) if resolved is not None else match.group(0)
            return PLACEHOLDER_PATTERN.sub(replacer, value)
        if isinstance(value, list):
            return [self._resolve_value(item, variables) for item in value]
        if isinstance(value, dict):
            return {key: self._resolve_value(val, variables) for key, val in value.items()}
        return value

    def _parse_url(
        self,
        url: Any,
        variables: dict[str, Any],
    ) -> tuple[str, dict[str, Any], str, str | None] | None:
        if isinstance(url, str):
            resolved = self._resolve_value(url, variables)
            parsed = urlparse(resolved)
            path = parsed.path or "/"
            params = {key: values[0] if values else None for key, values in parse_qs(parsed.query).items()}
            return path, params, resolved, f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else None
        if isinstance(url, dict):
            raw = url.get("raw")
            if raw:
                return self._parse_url(raw, variables)
            raw_path_segments = url.get("path") or []
            host = self._resolve_value(url.get("host"), variables)
            if isinstance(host, list):
                host = ".".join(host)
            resolved_segments = self._resolve_value(url.get("path"), variables) or []
            normalized_segments: list[str] = []
            for index, segment in enumerate(resolved_segments):
                original_segment = raw_path_segments[index] if index < len(raw_path_segments) else segment
                normalized_segments.append(self._normalise_path_segment(segment, original_segment))
            path = "/" + "/".join(segment for segment in normalized_segments if segment)
            path = path or "/"
            query_params: dict[str, Any] = {}
            for query_param in url.get("query") or []:
                if not isinstance(query_param, dict):
                    continue
                key = query_param.get("key")
                if not key:
                    continue
                value = self._resolve_value(query_param.get("value"), variables)
                query_params[key] = value
            scheme = self._resolve_value(url.get("protocol"), variables) or "https"
            port = url.get("port")
            base = None
            if host:
                base = f"{scheme}://{host}{f':{port}' if port else ''}"
            resolved_url = base + path if base else path
            if query_params:
                encoded = "&".join(f"{key}={value}" for key, value in query_params.items())
                resolved_url = f"{resolved_url}?{encoded}"
            return path, query_params, resolved_url, base
        return None

    def _extract_raw_url(self, url: Any) -> str | None:
        if isinstance(url, str):
            return url
        if isinstance(url, dict):
            raw = url.get("raw")
            if isinstance(raw, str):
                return raw
        return None

    def _parse_headers(self, headers: Any, variables: dict[str, Any]) -> dict[str, Any]:
        parsed: dict[str, Any] = {}
        for header in headers or []:
            if not isinstance(header, dict):
                continue
            key = header.get("key")
            if not key:
                continue
            value = self._resolve_value(header.get("value"), variables)
            parsed[str(key)] = value
        return parsed

    def _parse_body(self, body: Any, variables: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(body, dict):
            return {}
        mode = body.get("mode")
        result: dict[str, Any] = {"mode": mode}
        if mode == "raw":
            raw_payload = body.get("raw")
            if isinstance(raw_payload, str):
                resolved = self._resolve_value(raw_payload, variables)
                try:
                    result["parsed"] = json.loads(resolved)
                except json.JSONDecodeError:
                    result["raw"] = resolved
            return result
        if mode == "file":
            file_info = body.get("file") or {}
            return {
                "mode": mode,
                "file": self._resolve_value(file_info, variables),
            }
        if mode in {"formdata", "urlencoded"}:
            entries = body.get(mode) or []
            data: dict[str, Any] = {}
            files: dict[str, Any] = {}
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                key = entry.get("key")
                if not key:
                    continue
                entry_type = entry.get("type") or "text"
                if entry_type == "file":
                    files[key] = self._resolve_value(entry.get("src"), variables)
                else:
                    data[key] = self._resolve_value(entry.get("value"), variables)
            result[mode] = data
            if files:
                result.setdefault("files", files)
            return result
        if mode == "graphql":
            return {
                "mode": mode,
                "graphql": self._resolve_value(body.get("graphql"), variables),
            }
        return {}

    def _parse_responses(self, responses: Any) -> dict[str, Any]:
        parsed: dict[str, Any] = {}
        for response in responses or []:
            if not isinstance(response, dict):
                continue
            code = str(response.get("code") or response.get("status") or "200")
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

    def _parse_scripts(self, events: Any) -> str | None:
        if not events or not self.options.capture_scripts:
            return None
        scripts: list[str] = []
        for event in events:
            if not isinstance(event, dict):
                continue
            if event.get("listen") != "prerequest":
                continue
            script = event.get("script")
            if isinstance(script, dict):
                exec_lines = script.get("exec")
                if isinstance(exec_lines, list):
                    scripts.extend(str(line) for line in exec_lines)
                elif isinstance(exec_lines, str):
                    scripts.append(exec_lines)
        if not scripts:
            return None
        return "\n".join(scripts)

    def _normalize_auth(self, auth: Any, variables: dict[str, Any] | None = None) -> AuthInfo | None:
        if not auth or not isinstance(auth, dict):
            return None
        auth_type = auth.get("type")
        if auth_type in {None, "inherit"}:
            return None
        entries = auth.get(auth_type)
        if isinstance(entries, dict) and "token" in entries:
            token_value = entries.get("token")
            entries = [{"key": "token", "value": token_value}]
        values = self._entries_to_dict(entries)
        resolved_values = {
            key: self._resolve_value(value, variables or {}) for key, value in values.items()
        }
        headers: dict[str, Any] = {}
        params: dict[str, Any] = {}
        placeholder = "{{token}}"
        if auth_type == "bearer":
            token = resolved_values.get("token") or placeholder
            headers["Authorization"] = f"Bearer {token}"
        elif auth_type == "apikey":
            key = (
                resolved_values.get("key")
                or resolved_values.get("name")
                or values.get("key")
                or values.get("name")
                or "X-API-Key"
            )
            value = resolved_values.get("value") or placeholder
            location = resolved_values.get("in") or values.get("in") or "header"
            if location == "query":
                params[key] = value
            else:
                headers[key] = value
        elif auth_type == "basic":
            user = resolved_values.get("username") or "user"
            password = resolved_values.get("password") or "password"
            headers["Authorization"] = f"Basic {{base64({user}:{password})}}"
        elif auth_type in {"oauth2", "hawk", "digest"}:
            headers["Authorization"] = auth_type.capitalize() + " {{token}}"
        else:
            # Unsupported auth types are recorded but not applied
            pass
        return AuthInfo(headers=headers, params=params, type=auth_type, raw=auth)

    def _entries_to_dict(self, entries: Any) -> dict[str, Any]:
        if isinstance(entries, dict):
            return {key: value for key, value in entries.items() if value is not None}
        values: dict[str, Any] = {}
        for entry in entries or []:
            if not isinstance(entry, dict):
                continue
            key = entry.get("key")
            value = entry.get("value")
            if key:
                values[str(key)] = value
        return values

    def _determine_group(self, folder_stack: list[str]) -> str | None:
        if not folder_stack:
            return None
        if not self.options.resolve_variables:
            return folder_stack[-1]
        return " / ".join(folder_stack)


def build_postman_descriptor(
    collection: dict[str, Any],
    *,
    options: PostmanImportOptions | None = None,
    source_type: ImportSourceType,
    location: str | None,
    existing_source: ImportSource | None = None,
) -> tuple[list[ImportCandidate], WorkflowSourceDescriptor]:
    normalized_options = options or PostmanImportOptions()
    parser = PostmanParser(collection, options=normalized_options)
    candidates, metadata = parser.parse()
    descriptor = WorkflowSourceDescriptor(
        source_type=source_type,
        location=location,
        options=normalized_options.model_dump(mode="json", exclude_none=True),
        payload_snapshot=collection,
        metadata=metadata,
        payload_hash=compute_hash(collection),
        existing=existing_source,
    )
    return candidates, descriptor


def import_postman_collection(
    db: Session,
    project: Project,
    collection: dict[str, Any],
    *,
    options: PostmanImportOptions | None = None,
    source_type: ImportSourceType,
    location: str | None,
    dry_run: bool = False,
    existing_source: ImportSource | None = None,
) -> ImportSummary:
    normalized_options = options or PostmanImportOptions()
    parser = PostmanParser(collection, options=normalized_options)
    candidates, metadata = parser.parse()
    descriptor = SourceDescriptor(
        source_type=source_type,
        location=location,
        content_hash=compute_hash(collection),
        options=normalized_options.model_dump(mode="json", exclude_none=True),
        payload_snapshot=collection,
        metadata=metadata,
        existing=existing_source,
    )
    manager = ImportManager(db, project, ImporterKind.POSTMAN, dry_run=dry_run)
    return manager.run(candidates, descriptor)


def fetch_postman_collection(url: str, *, timeout: float = DEFAULT_TIMEOUT) -> dict[str, Any]:
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(url)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("Postman collection response must be an object")
            return payload
    except (httpx.HTTPError, ValueError) as exc:
        logger.error("postman_fetch_failed", url=url, error=str(exc))
        raise ValueError(f"Failed to fetch Postman collection from {url}") from exc
