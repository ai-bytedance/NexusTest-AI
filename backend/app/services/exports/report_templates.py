from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class ReportTemplateDefinition:
    key: str
    label: str
    description: str
    markdown_template: str
    pdf_template: str


REPORT_TEMPLATE_REGISTRY: Dict[str, ReportTemplateDefinition] = {
    "default": ReportTemplateDefinition(
        key="default",
        label="Default",
        description="Balanced layout with full summary, steps, assertions, and payload excerpts.",
        markdown_template="default.md.j2",
        pdf_template="default.html.j2",
    ),
    "compact": ReportTemplateDefinition(
        key="compact",
        label="Compact",
        description="Focused layout emphasising high-level metrics and failures only.",
        markdown_template="compact.md.j2",
        pdf_template="compact.html.j2",
    ),
    "detailed": ReportTemplateDefinition(
        key="detailed",
        label="Detailed",
        description="Extended layout including full payloads, metrics, and assertion breakdowns.",
        markdown_template="detailed.md.j2",
        pdf_template="detailed.html.j2",
    ),
}


def get_template_definition(key: str) -> ReportTemplateDefinition | None:
    return REPORT_TEMPLATE_REGISTRY.get(key)


__all__ = [
    "ReportTemplateDefinition",
    "REPORT_TEMPLATE_REGISTRY",
    "get_template_definition",
]
