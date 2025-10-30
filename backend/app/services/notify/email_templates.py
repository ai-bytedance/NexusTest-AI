from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, Tuple

from jinja2 import Environment, DictLoader, TemplateNotFound, select_autoescape


@dataclass(frozen=True)
class EmailTemplateDefinition:
    name: str
    language: str
    subject_key: str
    html_key: str
    text_key: str


@dataclass(slots=True)
class RenderedEmailTemplate:
    template: str
    language: str
    subject: str
    html: str
    text: str


_TEMPLATE_SOURCES: Dict[str, str] = {
    # Run finished (English)
    "run_finished/en.subject": "[{{ project_name or 'Project' }}] {{ entity_type|capitalize }} {{ entity_name or 'Run' }} {{ status|upper }}",
    "run_finished/en.html": (
        "<h2>Run finished in {{ project_name or 'your project' }}</h2>\n"
        "<p>{{ entity_type|capitalize }} <strong>{{ entity_name or 'Run' }}</strong> completed with status <strong>{{ status|upper }}</strong>.</p>\n"
        "<ul>\n"
        "  <li>Pass rate: {{ pass_rate|percent }}</li>\n"
        "  <li>Assertions: {{ summary.assertions_passed or 0 }}/{{ summary.assertions_total or 0 }}</li>\n"
        "  <li>Duration: {{ (summary.duration_ms or duration_ms)|duration }}</li>\n"
        "  <li>Finished at: {{ finished_at|timestamp }}</li>\n"
        "</ul>\n"
        "{% if environment.name or environment.slug %}"
        "<p>Environment: <strong>{{ environment.name or environment.slug }}</strong></p>\n"
        "{% endif %}"
        "{% if failures %}\n"
        "<h3>Failures</h3>\n"
        "<ul>\n"
        "{% for failure in failures %}\n"
        "  <li><strong>{{ failure.name or ('Failure ' ~ loop.index) }}</strong>: {{ failure.message or failure.description or 'See report for details.' }}</li>\n"
        "{% endfor %}\n"
        "</ul>\n"
        "{% endif %}\n"
        "{% if report_url %}<p><a href=\"{{ report_url }}\">View detailed report</a></p>{% endif %}"
    ),
    "run_finished/en.txt": (
        "Run finished in {{ project_name or 'your project' }}\n"
        "{{ entity_type|capitalize }} {{ entity_name or 'Run' }} completed with status {{ status|upper }}.\n"
        "Pass rate: {{ pass_rate|percent }}\n"
        "Assertions: {{ summary.assertions_passed or 0 }}/{{ summary.assertions_total or 0 }}\n"
        "Duration: {{ (summary.duration_ms or duration_ms)|duration }}\n"
        "Finished at: {{ finished_at|timestamp }}\n"
        "{% if environment.name or environment.slug %}Environment: {{ environment.name or environment.slug }}\n{% endif %}"
        "{% if failures %}Failures:\n{% for failure in failures %}- {{ failure.name or ('Failure ' ~ loop.index) }}: {{ failure.message or failure.description or 'See report for details.' }}\n{% endfor %}{% endif %}"
        "{% if report_url %}Report: {{ report_url }}{% endif %}"
    ),
    # Run finished (Chinese)
    "run_finished/zh.subject": "【{{ project_name or '项目' }}】{{ entity_name or '执行' }}已{{ status|status_label_zh }}",
    "run_finished/zh.html": (
        "<h2>{{ project_name or '您的项目' }}执行完成</h2>\n"
        "<p>{{ entity_type|entity_type_label_zh }} <strong>{{ entity_name or '执行' }}</strong> 已{{ status|status_label_zh }}。</p>\n"
        "<ul>\n"
        "  <li>通过率：{{ pass_rate|percent }}</li>\n"
        "  <li>断言：{{ summary.assertions_passed or 0 }}/{{ summary.assertions_total or 0 }}</li>\n"
        "  <li>耗时：{{ (summary.duration_ms or duration_ms)|duration }}</li>\n"
        "  <li>完成时间：{{ finished_at|timestamp }}</li>\n"
        "</ul>\n"
        "{% if environment.name or environment.slug %}"
        "<p>环境：<strong>{{ environment.name or environment.slug }}</strong></p>\n"
        "{% endif %}"
        "{% if failures %}\n"
        "<h3>失败详情</h3>\n"
        "<ul>\n"
        "{% for failure in failures %}\n"
        "  <li><strong>{{ failure.name or ('失败 ' ~ loop.index) }}</strong>：{{ failure.message or failure.description or '请查看报告获取详情。' }}</li>\n"
        "{% endfor %}\n"
        "</ul>\n"
        "{% endif %}\n"
        "{% if report_url %}<p><a href=\"{{ report_url }}\">查看完整报告</a></p>{% endif %}"
    ),
    "run_finished/zh.txt": (
        "{{ project_name or '项目' }}执行完成\n"
        "{{ entity_type|entity_type_label_zh }} {{ entity_name or '执行' }} 已{{ status|status_label_zh }}。\n"
        "通过率：{{ pass_rate|percent }}\n"
        "断言：{{ summary.assertions_passed or 0 }}/{{ summary.assertions_total or 0 }}\n"
        "耗时：{{ (summary.duration_ms or duration_ms)|duration }}\n"
        "完成时间：{{ finished_at|timestamp }}\n"
        "{% if environment.name or environment.slug %}环境：{{ environment.name or environment.slug }}\n{% endif %}"
        "{% if failures %}失败列表：\n{% for failure in failures %}- {{ failure.name or ('失败 ' ~ loop.index) }}：{{ failure.message or failure.description or '请查看报告获取详情。' }}\n{% endfor %}{% endif %}"
        "{% if report_url %}报告链接：{{ report_url }}{% endif %}"
    ),
    # Import diff ready templates
    "import_diff_ready/en.subject": "[{{ project_name or 'Project' }}] Import diff ready for review",
    "import_diff_ready/en.html": (
        "<p>An import diff for <strong>{{ import_source or 'source' }}</strong> is ready for review.</p>\n"
        "<p>Summary: {{ diff_summary or 'No diff summary provided.' }}</p>\n"
        "{% if diff_url %}<p><a href=\"{{ diff_url }}\">Review changes</a></p>{% endif %}"
    ),
    "import_diff_ready/en.txt": (
        "Import diff ready for {{ import_source or 'source' }}\n"
        "Summary: {{ diff_summary or 'No diff summary provided.' }}\n"
        "{% if diff_url %}Review: {{ diff_url }}{% endif %}"
    ),
    "import_diff_ready/zh.subject": "【{{ project_name or '项目' }}】导入差异已准备审阅",
    "import_diff_ready/zh.html": (
        "<p><strong>{{ import_source or '导入来源' }}</strong> 的差异已准备好，请及时审阅。</p>\n"
        "<p>概览：{{ diff_summary or '暂无差异详情。' }}</p>\n"
        "{% if diff_url %}<p><a href=\"{{ diff_url }}\">查看差异</a></p>{% endif %}"
    ),
    "import_diff_ready/zh.txt": (
        "导入差异已准备好\n"
        "来源：{{ import_source or '导入来源' }}\n"
        "概览：{{ diff_summary or '暂无差异详情。' }}\n"
        "{% if diff_url %}链接：{{ diff_url }}{% endif %}"
    ),
    # Import applied templates
    "import_applied/en.subject": "[{{ project_name or 'Project' }}] Import applied successfully",
    "import_applied/en.html": (
        "<p>Import <strong>{{ import_source or 'source' }}</strong> was applied successfully.</p>\n"
        "{% if applied_changes %}<p>Changes:</p><ul>{% for change in applied_changes %}<li>{{ change }}</li>{% endfor %}</ul>{% endif %}"
    ),
    "import_applied/en.txt": (
        "Import {{ import_source or 'source' }} applied successfully.\n"
        "{% if applied_changes %}Changes:\n{% for change in applied_changes %}- {{ change }}\n{% endfor %}{% endif %}"
    ),
    "import_applied/zh.subject": "【{{ project_name or '项目' }}】导入已应用",
    "import_applied/zh.html": (
        "<p>导入 <strong>{{ import_source or '导入来源' }}</strong> 已成功应用。</p>\n"
        "{% if applied_changes %}<p>变更内容：</p><ul>{% for change in applied_changes %}<li>{{ change }}</li>{% endfor %}</ul>{% endif %}"
    ),
    "import_applied/zh.txt": (
        "导入 {{ import_source or '导入来源' }} 已成功应用。\n"
        "{% if applied_changes %}变更内容：\n{% for change in applied_changes %}- {{ change }}\n{% endfor %}{% endif %}"
    ),
    # Import failed templates
    "import_failed/en.subject": "[{{ project_name or 'Project' }}] Import failed",
    "import_failed/en.html": (
        "<p>Import <strong>{{ import_source or 'source' }}</strong> failed.</p>\n"
        "<p>Error: {{ error_message or 'Unknown error.' }}</p>\n"
        "{% if retry_hint %}<p>Next steps: {{ retry_hint }}</p>{% endif %}"
    ),
    "import_failed/en.txt": (
        "Import {{ import_source or 'source' }} failed.\n"
        "Error: {{ error_message or 'Unknown error.' }}\n"
        "{% if retry_hint %}Next steps: {{ retry_hint }}{% endif %}"
    ),
    "import_failed/zh.subject": "【{{ project_name or '项目' }}】导入失败",
    "import_failed/zh.html": (
        "<p>导入 <strong>{{ import_source or '导入来源' }}</strong> 失败。</p>\n"
        "<p>错误信息：{{ error_message or '未知错误。' }}</p>\n"
        "{% if retry_hint %}<p>处理建议：{{ retry_hint }}</p>{% endif %}"
    ),
    "import_failed/zh.txt": (
        "导入 {{ import_source or '导入来源' }} 失败。\n"
        "错误信息：{{ error_message or '未知错误。' }}\n"
        "{% if retry_hint %}处理建议：{{ retry_hint }}{% endif %}"
    ),
    # Issue created templates
    "issue_created/en.subject": "[{{ project_name or 'Project' }}] Issue created: {{ issue_title or 'New issue' }}",
    "issue_created/en.html": (
        "<p>A new issue was created and linked to report {{ report_id or 'N/A' }}.</p>\n"
        "<p>{{ issue_title or 'Issue' }} — {{ issue_description or 'No description provided.' }}</p>\n"
        "{% if issue_url %}<p><a href=\"{{ issue_url }}\">View issue</a></p>{% endif %}"
    ),
    "issue_created/en.txt": (
        "New issue linked to report {{ report_id or 'N/A' }}\n"
        "Title: {{ issue_title or 'Issue' }}\n"
        "{{ issue_description or 'No description provided.' }}\n"
        "{% if issue_url %}Link: {{ issue_url }}{% endif %}"
    ),
    "issue_created/zh.subject": "【{{ project_name or '项目' }}】新建缺陷：{{ issue_title or '新缺陷' }}",
    "issue_created/zh.html": (
        "<p>已创建新的缺陷并关联到报告 {{ report_id or 'N/A' }}。</p>\n"
        "<p>{{ issue_title or '缺陷' }} — {{ issue_description or '暂无描述。' }}</p>\n"
        "{% if issue_url %}<p><a href=\"{{ issue_url }}\">查看缺陷</a></p>{% endif %}"
    ),
    "issue_created/zh.txt": (
        "已新建缺陷并关联到报告 {{ report_id or 'N/A' }}\n"
        "标题：{{ issue_title or '缺陷' }}\n"
        "{{ issue_description or '暂无描述。' }}\n"
        "{% if issue_url %}链接：{{ issue_url }}{% endif %}"
    ),
    # Issue closed templates
    "issue_closed/en.subject": "[{{ project_name or 'Project' }}] Issue closed: {{ issue_title or 'Issue' }}",
    "issue_closed/en.html": (
        "<p>The linked issue {{ issue_title or 'Issue' }} has been resolved.</p>\n"
        "{% if resolution %}<p>Resolution: {{ resolution }}</p>{% endif %}\n"
        "{% if issue_url %}<p><a href=\"{{ issue_url }}\">View issue</a></p>{% endif %}"
    ),
    "issue_closed/en.txt": (
        "Linked issue {{ issue_title or 'Issue' }} has been resolved.\n"
        "{% if resolution %}Resolution: {{ resolution }}\n{% endif %}"
        "{% if issue_url %}Link: {{ issue_url }}{% endif %}"
    ),
    "issue_closed/zh.subject": "【{{ project_name or '项目' }}】缺陷已关闭：{{ issue_title or '缺陷' }}",
    "issue_closed/zh.html": (
        "<p>关联缺陷 {{ issue_title or '缺陷' }} 已完成处理。</p>\n"
        "{% if resolution %}<p>处理结果：{{ resolution }}</p>{% endif %}\n"
        "{% if issue_url %}<p><a href=\"{{ issue_url }}\">查看缺陷</a></p>{% endif %}"
    ),
    "issue_closed/zh.txt": (
        "关联缺陷 {{ issue_title or '缺陷' }} 已关闭。\n"
        "{% if resolution %}处理结果：{{ resolution }}\n{% endif %}"
        "{% if issue_url %}链接：{{ issue_url }}{% endif %}"
    ),
}

_TEMPLATE_DEFINITIONS: Tuple[EmailTemplateDefinition, ...] = tuple(
    EmailTemplateDefinition(
        name=name,
        language=language,
        subject_key=f"{name}/{language}.subject",
        html_key=f"{name}/{language}.html",
        text_key=f"{name}/{language}.txt",
    )
    for name, language in [
        ("run_finished", "en"),
        ("run_finished", "zh"),
        ("import_diff_ready", "en"),
        ("import_diff_ready", "zh"),
        ("import_applied", "en"),
        ("import_applied", "zh"),
        ("import_failed", "en"),
        ("import_failed", "zh"),
        ("issue_created", "en"),
        ("issue_created", "zh"),
        ("issue_closed", "en"),
        ("issue_closed", "zh"),
    ]
)

_TEMPLATE_INDEX: Dict[Tuple[str, str], EmailTemplateDefinition] = {
    (definition.name, definition.language): definition for definition in _TEMPLATE_DEFINITIONS
}

_ENV = Environment(
    loader=DictLoader(_TEMPLATE_SOURCES),
    autoescape=select_autoescape(enabled_extensions=("html", "htm")),
    trim_blocks=True,
    lstrip_blocks=True,
)


def _format_percent(value: Any) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "N/A"
    if numeric <= 1:
        numeric *= 100
    return f"{numeric:.1f}%"


def _format_duration(value: Any) -> str:
    try:
        millis = float(value)
    except (TypeError, ValueError):
        return "N/A"
    if millis < 1000:
        return f"{int(millis)} ms"
    seconds = millis / 1000
    if seconds < 60:
        return f"{seconds:.1f} s"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{int(minutes)} min {int(sec)} s"
    hours, minutes = divmod(minutes, 60)
    return f"{int(hours)} h {int(minutes)} m"


def _format_timestamp(value: Any) -> str:
    if not value:
        return "N/A"
    if isinstance(value, datetime):
        return value.isoformat()
    try:
        return datetime.fromisoformat(str(value)).isoformat()
    except ValueError:
        return str(value)


def _status_label_zh(value: Any) -> str:
    mapping = {
        "passed": "完成",
        "failed": "失败",
        "error": "错误",
    }
    if not value:
        return "完成"
    key = str(value).lower()
    return mapping.get(key, "完成")


def _entity_type_label_zh(value: Any) -> str:
    mapping = {
        "suite": "测试套件",
        "case": "测试用例",
    }
    if not value:
        return "执行"
    key = str(value).lower()
    return mapping.get(key, "执行")


_ENV.filters.update(
    {
        "percent": _format_percent,
        "duration": _format_duration,
        "timestamp": _format_timestamp,
        "status_label_zh": _status_label_zh,
        "entity_type_label_zh": _entity_type_label_zh,
    }
)


def list_templates() -> Iterable[EmailTemplateDefinition]:
    return _TEMPLATE_DEFINITIONS


def render_email_template(name: str, language: str, context: dict[str, Any]) -> RenderedEmailTemplate:
    key = (name, language)
    definition = _TEMPLATE_INDEX.get(key)
    if not definition:
        raise TemplateNotFound(f"Template '{name}' with language '{language}' is not registered")

    template_context = context or {}

    subject = _ENV.get_template(definition.subject_key).render(template_context).strip()
    html = _ENV.get_template(definition.html_key).render(template_context).strip()
    text = _ENV.get_template(definition.text_key).render(template_context).strip()

    return RenderedEmailTemplate(template=name, language=language, subject=subject, html=html, text=text)


def sample_context(name: str) -> dict[str, Any]:
    samples: Dict[str, dict[str, Any]] = {
        "run_finished": {
            "project_name": "Acme Payments",
            "entity_type": "suite",
            "entity_name": "Regression",
            "status": "failed",
            "pass_rate": 0.78,
            "summary": {
                "assertions_total": 120,
                "assertions_passed": 94,
                "duration_ms": 42563,
                "pass_rate": 0.78,
            },
            "failures": [
                {
                    "name": "Checkout flow",
                    "message": "Expected status 200 but received 500",
                }
            ],
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "environment": {"name": "staging"},
            "report_url": "https://app.example.com/projects/acme/reports/123",
        },
        "import_diff_ready": {
            "project_name": "Acme Payments",
            "import_source": "OpenAPI",
            "diff_summary": "5 endpoints updated, 1 removed",
            "diff_url": "https://app.example.com/projects/acme/imports/last",
        },
        "import_applied": {
            "project_name": "Acme Payments",
            "import_source": "Postman",
            "applied_changes": [
                "Created 3 new test cases",
                "Updated 2 existing suites",
            ],
        },
        "import_failed": {
            "project_name": "Acme Payments",
            "import_source": "Swagger",
            "error_message": "Schema validation failed",
            "retry_hint": "Fix the schema issues and retry the import.",
        },
        "issue_created": {
            "project_name": "Acme Payments",
            "issue_title": "Checkout failure",
            "issue_description": "Payment gateway returns HTTP 500 for valid cards.",
            "issue_url": "https://tracker.example.com/ISSUE-123",
            "report_id": "report-123",
        },
        "issue_closed": {
            "project_name": "Acme Payments",
            "issue_title": "Checkout failure",
            "resolution": "Hotfix deployed to production",
            "issue_url": "https://tracker.example.com/ISSUE-123",
        },
    }
    return samples.get(name, {})


__all__ = [
    "EmailTemplateDefinition",
    "RenderedEmailTemplate",
    "list_templates",
    "render_email_template",
    "sample_context",
]
