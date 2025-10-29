from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urljoin

from app.core.crypto import decrypt_secret_mapping
from app.models.dataset import Dataset
from app.models.environment import Environment
from app.models.test_case import TestCase
from app.services.execution.context import ExecutionContext, render_value

_PLACEHOLDER = "***"


class ParameterizationError(RuntimeError):
    """Raised when parameterization cannot be completed."""


@dataclass(slots=True)
class PreparedIteration:
    index: int
    prepared_inputs: dict[str, Any]
    sanitized_inputs: dict[str, Any]
    context: ExecutionContext
    dataset_row: dict[str, Any] | None


class ParameterizationEngine:
    def __init__(self, *, placeholder: str = _PLACEHOLDER) -> None:
        self._placeholder = placeholder

    def prepare_iterations(
        self,
        case: TestCase,
        *,
        environment: Environment | None,
        dataset_rows: list[dict[str, Any]] | None,
    ) -> list[PreparedIteration]:
        rows = dataset_rows if dataset_rows else [None]
        env_context = self._build_environment_context(environment)
        env_headers_template = self._coerce_dict(environment.headers) if environment else {}
        env_base_url = environment.base_url if environment else None
        secrets_actual = decrypt_secret_mapping(environment.secrets) if environment else {}
        secrets_placeholder = {key: self._placeholder for key in secrets_actual}

        iterations: list[PreparedIteration] = []
        for index, row in enumerate(rows):
            row_data = deepcopy(row) if isinstance(row, dict) else {}
            raw_inputs = deepcopy(case.inputs or {})
            self._apply_param_mapping(raw_inputs, row_data, case.param_mapping)

            context_actual = ExecutionContext(
                variables=deepcopy(env_context.get("variables", {})),
                environment=deepcopy(env_context),
                dataset_row=deepcopy(row_data),
                secrets=deepcopy(secrets_actual),
            )
            context_masked = ExecutionContext(
                variables=deepcopy(env_context.get("variables", {})),
                environment=deepcopy(env_context),
                dataset_row=deepcopy(row_data),
                secrets=deepcopy(secrets_placeholder),
            )

            prepared_actual = self._finalize_inputs(
                render_value(raw_inputs, context_actual),
                env_headers_template,
                env_base_url,
                context_actual,
            )
            prepared_masked = self._finalize_inputs(
                render_value(raw_inputs, context_masked),
                env_headers_template,
                env_base_url,
                context_masked,
            )

            iterations.append(
                PreparedIteration(
                    index=index,
                    prepared_inputs=prepared_actual,
                    sanitized_inputs=prepared_masked,
                    context=context_actual,
                    dataset_row=row_data if row_data else None,
                )
            )
        return iterations

    def _finalize_inputs(
        self,
        inputs: dict[str, Any],
        env_headers_template: dict[str, Any],
        base_url_template: str | None,
        context: ExecutionContext,
    ) -> dict[str, Any]:
        finalized = deepcopy(inputs)
        if not isinstance(finalized, dict):
            raise ParameterizationError("Test case inputs must be an object")

        headers = self._coerce_dict(finalized.get("headers"))
        env_headers = render_value(env_headers_template, context) if env_headers_template else {}
        merged_headers = {**env_headers, **headers}
        if merged_headers:
            finalized["headers"] = merged_headers

        if base_url_template:
            resolved_base = render_value(base_url_template, context)
            if isinstance(resolved_base, str) and resolved_base:
                url_value = finalized.get("url")
                if isinstance(url_value, str) and url_value and not url_value.lower().startswith(("http://", "https://")):
                    finalized["url"] = urljoin(resolved_base.rstrip("/") + "/", url_value.lstrip("/"))

        return finalized

    def _apply_param_mapping(self, inputs: dict[str, Any], row: dict[str, Any], mapping: Any) -> None:
        if not mapping or not isinstance(mapping, dict):
            return
        for column_name, target_path in mapping.items():
            if not isinstance(column_name, str) or not isinstance(target_path, str):
                continue
            value = row.get(column_name)
            self._assign_path(inputs, target_path, value)

    def _assign_path(self, payload: dict[str, Any], path: str, value: Any) -> None:
        if not path:
            return
        segments = [segment.strip() for segment in path.split(".") if segment.strip()]
        if not segments:
            return
        current: dict[str, Any] = payload
        for segment in segments[:-1]:
            existing = current.get(segment)
            if not isinstance(existing, dict):
                existing = {}
                current[segment] = existing
            current = existing
        current[segments[-1]] = value

    def _build_environment_context(self, environment: Environment | None) -> dict[str, Any]:
        if environment is None:
            return {}
        context: dict[str, Any] = {
            "id": str(environment.id),
            "name": environment.name,
        }
        if environment.base_url:
            context["base_url"] = environment.base_url
        headers = self._coerce_dict(environment.headers)
        if headers:
            context["headers"] = headers
        variables = self._coerce_dict(environment.variables)
        if variables:
            context["variables"] = variables
            for key, value in variables.items():
                if key not in context:
                    context[key] = value
        return context

    def _coerce_dict(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        return {}


def resolve_dataset_rows(
    dataset: Dataset | None,
    *,
    loader: Callable[[Dataset], list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    if dataset is None:
        return []
    if loader is None:
        raise ParameterizationError("Dataset loader callable must be provided")
    rows = loader(dataset)
    return rows or []


__all__ = [
    "ParameterizationEngine",
    "ParameterizationError",
    "PreparedIteration",
    "resolve_dataset_rows",
]
