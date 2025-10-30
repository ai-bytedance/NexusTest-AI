from __future__ import annotations

import copy
import logging
from dataclasses import dataclass
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse

import httpx
from sqlalchemy.orm import Session

from app.core.errors import ErrorCode, http_exception
from app.models.import_source import ImportSource, ImportSourceType, ImporterKind
from app.models.project import Project
from app.schemas.api import HTTPMethod
from app.schemas.importers import ImportSummary, OpenAPIImportOptions
from app.services.importers.common import ImportCandidate, compute_hash, normalize_method, normalize_path
from app.services.importers.manager import ImportManager, SourceDescriptor
from app.services.importers.workflow import SourceDescriptor as WorkflowSourceDescriptor

logger = logging.getLogger(__name__)

SUPPORTED_METHODS = {method.value for method in HTTPMethod}
DEFAULT_TIMEOUT = 15.0


@dataclass(slots=True)
class ResolvedServer:
    url: str
    description: str | None = None
    variables: dict[str, Any] | None = None


class OpenAPISpecResolver:
    def __init__(
        self,
        document: dict[str, Any],
        *,
        base_url: str | None = None,
        resolve_remote: bool = True,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._document = document
        self._base_url = base_url
        self._resolve_remote = resolve_remote
        self._timeout = timeout
        self._ref_cache: dict[str, Any] = {}
        self._remote_cache: dict[str, Any] = {}

    def resolve(self, value: Any) -> Any:
        return self._resolve(copy.deepcopy(value), set())

    def resolve_schema(self, schema: Any) -> Any:
        return self.resolve(schema)

    def _resolve(self, value: Any, seen: set[str]) -> Any:
        if isinstance(value, dict):
            if "$ref" in value:
                ref = value["$ref"]
                if ref in seen:
                    return {}
                nested_seen = set(seen)
                nested_seen.add(ref)
                resolved = self._resolve_ref(ref, nested_seen)
                remainder = {key: val for key, val in value.items() if key != "$ref"}
                merged = merge_objects(resolved, self._resolve(remainder, nested_seen))
                return self._merge_combinators(merged, nested_seen)
            resolved_dict: dict[str, Any] = {}
            for key, val in value.items():
                if key in {"allOf", "oneOf", "anyOf"}:
                    resolved_dict[key] = [self._resolve(item, set(seen)) for item in val or []]
                else:
                    resolved_dict[key] = self._resolve(val, set(seen))
            return self._merge_combinators(resolved_dict, seen)
        if isinstance(value, list):
            return [self._resolve(item, set(seen)) for item in value]
        return value

    def _merge_combinators(self, schema: dict[str, Any], seen: set[str]) -> dict[str, Any]:
        result = dict(schema)
        if "allOf" in result:
            merged: dict[str, Any] = {}
            for item in result.pop("allOf", []) or []:
                if isinstance(item, dict):
                    merged = merge_objects(merged, item)
            result = merge_objects(result, merged)
        for key in ("oneOf", "anyOf"):
            if key not in result:
                continue
            variants = [variant for variant in result.get(key) or [] if isinstance(variant, dict)]
            if not variants:
                result.pop(key, None)
                continue
            result.setdefault("x-merged", {})[key] = variants
            merged_variant: dict[str, Any] = {}
            for variant in variants:
                merged_variant = merge_objects(merged_variant, variant)
            result.pop(key, None)
            result = merge_objects(result, merged_variant)
        return result

    def _resolve_ref(self, ref: str, seen: set[str]) -> Any:
        if ref in self._ref_cache:
            return copy.deepcopy(self._ref_cache[ref])
        if ref.startswith("#"):
            resolved = self._resolve_pointer(self._document, ref)
        else:
            url, pointer = self._split_ref(ref)
            absolute = self._absolute_url(url)
            document = self._get_remote_document(absolute)
            if pointer:
                resolved = self._resolve_pointer(document, f"#{pointer}")
            else:
                resolved = document
        resolved_value = self._resolve(copy.deepcopy(resolved), seen)
        self._ref_cache[ref] = copy.deepcopy(resolved_value)
        return resolved_value

    def _split_ref(self, ref: str) -> tuple[str, str | None]:
        if "#" in ref:
            url, pointer = ref.split("#", 1)
            return url, pointer
        return ref, None

    def _absolute_url(self, url: str) -> str:
        if self._base_url and not urlparse(url).netloc:
            return urljoin(self._base_url, url)
        return url

    def _get_remote_document(self, url: str) -> Any:
        if url in self._remote_cache:
            return self._remote_cache[url]
        if not self._resolve_remote:
            raise http_exception(
                status_code=400,
                code=ErrorCode.IMPORT_RESOLVE_FAILED,
                message=f"Remote reference resolution disabled but required for {url}",
            )
        try:
            response = httpx.get(url, timeout=self._timeout)
            response.raise_for_status()
            document = response.json()
        except httpx.HTTPError as exc:  # pragma: no cover - network failure path
            logger.error("openapi_remote_ref_failed", url=url, error=str(exc))
            raise http_exception(
                status_code=400,
                code=ErrorCode.IMPORT_RESOLVE_FAILED,
                message=f"Failed to resolve remote reference: {url}",
            ) from exc
        self._remote_cache[url] = document
        return document

    def _resolve_pointer(self, document: Any, pointer: str) -> Any:
        if pointer in {"#", ""}:
            return document
        path = pointer[2:] if pointer.startswith("#/") else pointer.lstrip("#")
        segments = [segment.replace("~1", "/").replace("~0", "~") for segment in path.split("/") if segment]
        current = document
        for segment in segments:
            if isinstance(current, dict):
                current = current.get(segment)
            elif isinstance(current, list):
                try:
                    index = int(segment)
                except ValueError as exc:
                    raise KeyError(pointer) from exc
                current = current[index]
            else:
                raise KeyError(pointer)
            if current is None:
                raise KeyError(pointer)
        return current


def build_openapi_descriptor(
    document: dict[str, Any],
    *,
    options: OpenAPIImportOptions | None = None,
    source_type: ImportSourceType,
    location: str | None,
    base_url: str | None = None,
    existing_source: ImportSource | None = None,
) -> tuple[list[ImportCandidate], WorkflowSourceDescriptor]:
    normalized_options = options or OpenAPIImportOptions()
    resolver = OpenAPISpecResolver(
        document,
        base_url=base_url,
        resolve_remote=normalized_options.resolve_remote_refs,
    )
    parser = OpenAPIParser(document, options=normalized_options, resolver=resolver, base_url=base_url)
    candidates, metadata = parser.parse()
    descriptor = WorkflowSourceDescriptor(
        source_type=source_type,
        location=location,
        options=normalized_options.model_dump(mode="json", exclude_none=True),
        payload_snapshot=document,
        metadata=metadata,
        payload_hash=compute_hash(document),
        base_url=base_url,
        existing=existing_source,
    )
    return candidates, descriptor


def merge_objects(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in incoming.items():
        if key == "properties" and isinstance(value, dict):
            properties = result.setdefault("properties", {})
            for name, definition in value.items():
                if (
                    name in properties
                    and isinstance(properties[name], dict)
                    and isinstance(definition, dict)
                ):
                    properties[name] = merge_objects(properties[name], definition)
                else:
                    properties[name] = copy.deepcopy(definition)
        elif key == "required" and isinstance(value, list):
            existing = set(result.get("required", []))
            existing.update(value)
            result["required"] = sorted(existing)
        elif key == "enum" and isinstance(value, list):
            existing_enum = result.get("enum")
            combined = []
            if isinstance(existing_enum, list):
                combined.extend(existing_enum)
            combined.extend(value)
            # Preserve order but remove duplicates
            seen: set[Any] = set()
            unique: list[Any] = []
            for item in combined:
                if item in seen:
                    continue
                seen.add(item)
                unique.append(item)
            result["enum"] = unique
        else:
            result[key] = copy.deepcopy(value)
    return result


class OpenAPIParser:
    def __init__(
        self,
        document: dict[str, Any],
        *,
        options: OpenAPIImportOptions,
        resolver: OpenAPISpecResolver,
        base_url: str | None = None,
    ) -> None:
        self.document = document
        self.options = options
        self.resolver = resolver
        self.base_url = base_url
        self.spec_version = "3" if document.get("openapi") else "2"
        self.version = (document.get("info") or {}).get("version") or "v1"
        self.environment = dict(options.environment)
        self.global_servers = self._collect_servers(document)
        self.security_schemes = self._collect_security_schemes()
        self.global_security = document.get("security") or []
        self.components_parameters = self._collect_component_parameters()

    def parse(self) -> tuple[list[ImportCandidate], dict[str, Any]]:
        paths = self.document.get("paths")
        if not isinstance(paths, dict):
            raise http_exception(
                status_code=400,
                code=ErrorCode.IMPORT_INVALID_SPEC,
                message="OpenAPI document is missing 'paths' definitions",
            )
        candidates: list[ImportCandidate] = []
        metadata = {
            "version": self.version,
            "info": self.document.get("info") or {},
            "servers": [server.__dict__ for server in self.global_servers],
            "base_url": self.base_url,
            "spec_version": self.spec_version,
        }
        for raw_path, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue
            path_extensions = self._extract_vendor_extensions(path_item)
            path_parameters = self._resolve_parameters(path_item.get("parameters"))
            path_servers = self._collect_servers(path_item)
            for method, operation in path_item.items():
                lower_method = method.lower()
                if lower_method not in {m.lower() for m in SUPPORTED_METHODS}:
                    continue
                if not isinstance(operation, dict):
                    operation = {}
                tags = operation.get("tags") or []
                if not self._is_tag_allowed(tags):
                    continue
                method_upper = normalize_method(method)
                normalized_path = normalize_path(raw_path)
                group_name = self._determine_group(tags)
                parameters = path_parameters + self._resolve_parameters(operation.get("parameters"))
                headers, params, path_variables = self._extract_parameters(parameters)
                request_body = self._parse_request_body(operation, parameters)
                mock_example = self._build_mock_examples(operation, request_body)
                servers, selected_server = self._resolve_operation_servers(operation, path_servers)
                self._apply_security(operation, headers, params, path_item.get("security"))
                name = operation.get("summary") or operation.get("operationId") or f"{method_upper} {normalized_path}"
                source_key = operation.get("operationId") or f"{method_upper}:{normalized_path}"
                candidate_metadata = {
                    "openapi": {
                        "operation_id": operation.get("operationId"),
                        "tags": tags,
                        "deprecated": bool(operation.get("deprecated")),
                        "description": operation.get("description"),
                        "servers": [server.__dict__ for server in servers],
                        "selected_server": selected_server.__dict__ if selected_server else None,
                        "path_vendor_extensions": path_extensions,
                        "operation_vendor_extensions": self._extract_vendor_extensions(operation),
                        "path_variables": path_variables,
                        "security": operation.get("security") or path_item.get("security") or self.global_security,
                        "responses": list((operation.get("responses") or {}).keys()),
                    }
                }
                candidate = ImportCandidate(
                    method=method_upper,
                    path=normalized_path,
                    normalized_path=normalized_path,
                    version=self.version,
                    name=name,
                    group_name=group_name,
                    headers=headers,
                    params=params,
                    body=request_body,
                    mock_example=mock_example,
                    metadata=candidate_metadata,
                    source_key=source_key,
                )
                candidates.append(candidate)
        return candidates, metadata

    def _collect_servers(self, node: dict[str, Any]) -> list[ResolvedServer]:
        raw_servers = []
        if self.spec_version == "3":
            raw_servers = node.get("servers") or []
        else:
            schemes = node.get("schemes") or self.document.get("schemes") or ["http"]
            host = node.get("host") or self.document.get("host")
            base_path = node.get("basePath") or self.document.get("basePath") or ""
            raw_servers = []
            if host:
                for scheme in schemes:
                    url = f"{scheme}://{host}{base_path}" if base_path else f"{scheme}://{host}"
                    raw_servers.append({"url": url, "description": None})
        servers: list[ResolvedServer] = []
        for entry in raw_servers:
            if not isinstance(entry, dict):
                continue
            url = entry.get("url") or ""
            variables = entry.get("variables") if isinstance(entry.get("variables"), dict) else {}
            expanded = self._expand_server_url(url, variables)
            servers.append(
                ResolvedServer(
                    url=expanded,
                    description=entry.get("description"),
                    variables=variables,
                )
            )
        if not servers and self.base_url:
            servers.append(ResolvedServer(url=self.base_url, description="default"))
        return servers

    def _expand_server_url(self, url: str, variables: dict[str, Any]) -> str:
        expanded = url or ""
        for key, definition in (variables or {}).items():
            default = definition.get("default") if isinstance(definition, dict) else None
            override = self.options.server_variables.get(key) or self.environment.get(key)
            value = override or default or ""
            expanded = expanded.replace(f"{{{key}}}", str(value))
        if expanded.startswith("//") and self.base_url:
            parsed_base = urlparse(self.base_url)
            expanded = f"{parsed_base.scheme}:{expanded}"
        if expanded.startswith("/") and self.base_url:
            expanded = urljoin(self.base_url, expanded)
        return expanded

    def _collect_security_schemes(self) -> dict[str, Any]:
        if self.spec_version == "3":
            return (self.document.get("components") or {}).get("securitySchemes") or {}
        return self.document.get("securityDefinitions") or {}

    def _collect_component_parameters(self) -> dict[str, Any]:
        if self.spec_version == "3":
            return (self.document.get("components") or {}).get("parameters") or {}
        return self.document.get("parameters") or {}

    def _resolve_parameters(self, parameters: Iterable[Any] | None) -> list[dict[str, Any]]:
        resolved: list[dict[str, Any]] = []
        for parameter in parameters or []:
            item = parameter
            if isinstance(parameter, dict) and "$ref" in parameter:
                ref = parameter["$ref"]
                item = self.resolver.resolve(self.components_parameters.get(ref.split("/")[-1], parameter))
            item = self.resolver.resolve(item)
            if isinstance(item, dict):
                resolved.append(item)
        return resolved

    def _extract_parameters(
        self, parameters: list[dict[str, Any]]
    ) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
        headers: dict[str, Any] = {}
        params: dict[str, Any] = {}
        path_variables: list[dict[str, Any]] = []
        for parameter in parameters:
            location = parameter.get("in")
            name = parameter.get("name")
            if not name:
                continue
            schema = parameter.get("schema") or parameter
            schema = self.resolver.resolve(schema)
            example = self._extract_example(parameter, schema)
            if location == "header":
                headers.setdefault(name, example)
            elif location == "query":
                params.setdefault(name, example)
            elif location == "path":
                path_variables.append({"name": name, "schema": schema})
        return headers, params, path_variables

    def _parse_request_body(
        self,
        operation: dict[str, Any],
        parameters: list[dict[str, Any]],
    ) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if self.spec_version == "3":
            request_body = operation.get("requestBody")
            if not request_body:
                return body
            resolved_body = self.resolver.resolve(request_body)
            content = resolved_body.get("content") or {}
            for media_type, media_payload in content.items():
                if not isinstance(media_payload, dict):
                    continue
                schema = self.resolver.resolve(media_payload.get("schema") or {})
                example = self._extract_media_example(media_payload, schema)
                entry: dict[str, Any] = {"schema": schema}
                if example is not None:
                    entry["example"] = example
                encoding = media_payload.get("encoding")
                if isinstance(encoding, dict):
                    entry["encoding"] = encoding
                if media_type in {"multipart/form-data", "application/x-www-form-urlencoded"}:
                    entry["fields"] = self._build_form_fields(schema)
                body[media_type] = entry
        else:
            form_parameters = [param for param in parameters if param.get("in") == "formData"]
            body_parameters = [param for param in parameters if param.get("in") == "body"]
            if form_parameters:
                schema = {"type": "object", "properties": {}}
                fields: dict[str, Any] = {}
                for param in form_parameters:
                    name = param.get("name")
                    if not name:
                        continue
                    param_schema = self.resolver.resolve(param)
                    schema["properties"][name] = param_schema
                    fields[name] = self._extract_example(param, param_schema)
                body["application/x-www-form-urlencoded"] = {
                    "schema": schema,
                    "fields": fields,
                }
            if body_parameters:
                body_param = body_parameters[0]
                schema = self.resolver.resolve(body_param.get("schema") or {})
                example = self._extract_example(body_param, schema)
                entry = {"schema": schema}
                if example is not None:
                    entry["example"] = example
                body[body_param.get("consumes", ["application/json"])[0]] = entry
        return body

    def _build_mock_examples(
        self,
        operation: dict[str, Any],
        request_body: dict[str, Any],
    ) -> dict[str, Any]:
        examples: dict[str, Any] = {}
        if request_body:
            examples["request"] = request_body
        responses = operation.get("responses") or {}
        for status_code, response in responses.items():
            if not isinstance(response, dict):
                continue
            content = response.get("content") or {}
            if not content and "schema" in response:
                schema = self.resolver.resolve(response.get("schema"))
                example = response.get("examples") or response.get("example") or self._generate_example(schema)
                if example is not None:
                    examples.setdefault("responses", {}).setdefault(status_code, {})["application/json"] = example
            for media_type, media_payload in content.items():
                if not isinstance(media_payload, dict):
                    continue
                schema = self.resolver.resolve(media_payload.get("schema") or {})
                example = self._extract_media_example(media_payload, schema)
                if example is None:
                    example = self._generate_example(schema)
                if example is None:
                    continue
                examples.setdefault("responses", {}).setdefault(status_code, {})[media_type] = example
        return examples

    def _extract_media_example(self, media_payload: dict[str, Any], schema: dict[str, Any]) -> Any:
        if "example" in media_payload:
            return media_payload["example"]
        examples = media_payload.get("examples")
        if isinstance(examples, dict) and examples:
            first_value = next(iter(examples.values()))
            if isinstance(first_value, dict) and "value" in first_value:
                return first_value["value"]
            return first_value
        if "example" in schema:
            return schema["example"]
        return None

    def _extract_example(self, definition: dict[str, Any], schema: dict[str, Any]) -> Any:
        if definition.get("example") is not None:
            return definition["example"]
        if "examples" in definition and isinstance(definition["examples"], dict):
            first = next(iter(definition["examples"].values()), None)
            if isinstance(first, dict) and "value" in first:
                return first["value"]
            return first
        if schema.get("example") is not None:
            return schema["example"]
        if schema.get("default") is not None:
            return schema["default"]
        if "enum" in schema and isinstance(schema["enum"], list) and schema["enum"]:
            return schema["enum"][0]
        return self._generate_example(schema)

    def _generate_example(self, schema: Any, depth: int = 0) -> Any:
        if depth > 5 or not isinstance(schema, dict):
            return None
        if schema.get("example") is not None:
            return schema["example"]
        schema_type = schema.get("type")
        if schema_type == "object":
            properties = schema.get("properties") or {}
            example_obj: dict[str, Any] = {}
            for key, value in properties.items():
                example_obj[key] = self._generate_example(value, depth + 1)
            return example_obj
        if schema_type == "array":
            items = schema.get("items") or {}
            generated = self._generate_example(items, depth + 1)
            return [generated] if generated is not None else []
        if schema_type == "string":
            fmt = schema.get("format")
            if fmt == "binary" or fmt == "byte":
                return "<file>"
            if fmt == "date":
                return "1970-01-01"
            if fmt == "date-time":
                return "1970-01-01T00:00:00Z"
            return schema.get("default") or schema.get("pattern") or "string"
        if schema_type == "integer":
            return schema.get("default") or 0
        if schema_type == "number":
            return schema.get("default") or 0.0
        if schema_type == "boolean":
            default = schema.get("default")
            if default is not None:
                return default
            return True
        if "enum" in schema and isinstance(schema["enum"], list) and schema["enum"]:
            return schema["enum"][0]
        return None

    def _build_form_fields(self, schema: dict[str, Any]) -> dict[str, Any]:
        properties = schema.get("properties") if isinstance(schema, dict) else {}
        fields: dict[str, Any] = {}
        for key, value in (properties or {}).items():
            fields[key] = {
                "schema": value,
                "example": self._generate_example(value),
            }
        return fields

    def _resolve_operation_servers(
        self,
        operation: dict[str, Any],
        path_servers: list[ResolvedServer],
    ) -> tuple[list[ResolvedServer], ResolvedServer | None]:
        operation_servers = self._collect_servers(operation)
        servers = operation_servers or path_servers or self.global_servers
        if not servers and self.base_url:
            servers = [ResolvedServer(url=self.base_url)]
        selected: ResolvedServer | None = None
        if servers:
            selected = self._choose_server(servers)
        return servers, selected

    def _choose_server(self, servers: list[ResolvedServer]) -> ResolvedServer:
        if not servers:
            raise ValueError("No servers available")
        prefer = self.options.prefer_server
        if isinstance(self.options.server, int) and 0 <= self.options.server < len(servers):
            return servers[self.options.server]
        if isinstance(self.options.server, str):
            for server in servers:
                if server.url == self.options.server or server.description == self.options.server:
                    return server
        if prefer:
            for server in servers:
                if prefer in (server.url, server.description):
                    return server
        return servers[0]

    def _apply_security(
        self,
        operation: dict[str, Any],
        headers: dict[str, Any],
        params: dict[str, Any],
        path_security: list[dict[str, Any]] | None,
    ) -> None:
        requirements = operation.get("security")
        if requirements is None:
            requirements = path_security if path_security is not None else self.global_security
        for requirement in requirements:
            if not isinstance(requirement, dict):
                continue
            for scheme_name in requirement.keys():
                scheme = self.security_schemes.get(scheme_name)
                if not isinstance(scheme, dict):
                    continue
                scheme_type = scheme.get("type")
                if scheme_type == "http":
                    http_scheme = (scheme.get("scheme") or "").lower()
                    if http_scheme == "bearer":
                        headers.setdefault("Authorization", "Bearer {{token}}")
                    elif http_scheme == "basic":
                        headers.setdefault("Authorization", "Basic {{credentials}}")
                elif scheme_type == "apiKey":
                    location = scheme.get("in")
                    name = scheme.get("name")
                    if not name:
                        continue
                    placeholder = scheme.get("x-placeholder") or "{{apiKey}}"
                    if location == "header":
                        headers.setdefault(name, placeholder)
                    elif location == "query":
                        params.setdefault(name, placeholder)
                elif scheme_type == "oauth2":
                    headers.setdefault("Authorization", "Bearer {{token}}")

    def _extract_vendor_extensions(self, node: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in node.items() if isinstance(key, str) and key.startswith("x-")}

    def _determine_group(self, tags: Iterable[str]) -> str | None:
        tags_list = list(tags)
        if not tags_list:
            return None
        return tags_list[0]

    def _is_tag_allowed(self, tags: Iterable[str]) -> bool:
        tags_set = set(tags or [])
        include = set(self.options.include_tags or []) if self.options.include_tags else None
        exclude = set(self.options.exclude_tags or [])
        if include is not None and not (tags_set & include):
            return False
        if exclude and (tags_set & exclude):
            return False
        return True


def fetch_openapi_spec(url: str, *, timeout: float = DEFAULT_TIMEOUT) -> tuple[dict[str, Any], str]:
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.json(), url
    except httpx.HTTPError as exc:  # pragma: no cover - network failure path
        logger.error("openapi_fetch_failed", url=url, error=str(exc))
        raise ValueError(f"Failed to fetch OpenAPI document from {url}") from exc


def import_openapi_spec(
    db: Session,
    project: Project,
    document: dict[str, Any],
    *,
    options: OpenAPIImportOptions | None = None,
    source_type: ImportSourceType,
    location: str | None,
    dry_run: bool = False,
    base_url: str | None = None,
    existing_source: ImportSource | None = None,
) -> ImportSummary:
    normalized_options = options or OpenAPIImportOptions()
    resolver = OpenAPISpecResolver(
        document,
        base_url=base_url,
        resolve_remote=normalized_options.resolve_remote_refs,
    )
    parser = OpenAPIParser(document, options=normalized_options, resolver=resolver, base_url=base_url)
    candidates, metadata = parser.parse()
    descriptor = SourceDescriptor(
        source_type=source_type,
        location=location,
        content_hash=compute_hash(document),
        options=normalized_options.model_dump(mode="json", exclude_none=True),
        payload_snapshot=document,
        metadata=metadata,
        existing=existing_source,
    )
    manager = ImportManager(db, project, ImporterKind.OPENAPI, dry_run=dry_run)
    return manager.run(candidates, descriptor)
