# CI/CD Guide and CLI Usage / CI/CD 指南与命令行使用

This guide shows how to integrate NexusTest-AI into automation pipelines using the included Python CLI (scripts/nt_cli.py) and ready-to-use examples for GitHub Actions, Jenkins, and GitLab CI.

本文档介绍如何将 NexusTest-AI 集成到自动化流水线中，包含内置 Python CLI（scripts/nt_cli.py）的用法，以及 GitHub Actions、Jenkins 与 GitLab CI 的示例。

---

## 1) CLI (scripts/nt_cli.py)

- Authenticates, triggers a suite/case execution, optionally waits, and exits with non-zero code if pass-rate is below threshold.
- 安全登录后触发用例/套件执行，可选择等待完成；若通过率低于阈值则返回非 0 退出码。

Prerequisites / 前置条件:
- Python 3.11+
- httpx

Install / 安装:
```bash
python -m pip install --upgrade pip
python -m pip install httpx
```

Environment variables / 环境变量:
- NT_API_BASE: Backend API base URL (必填 / required)
- NT_REPORT_BASE_URL: Optional base for human links (可选)
- NT_PROJECT_ID: Target project id (必填 / required)
- NT_SUITE_ID / NT_CASE_ID / NT_TASK_ID: one of them to execute or resume
- NT_REPORT_ID: optional when resuming
- NT_API_TOKEN or NT_EMAIL + NT_PASSWORD: auth method
- NT_PASS_THRESHOLD: pass-rate threshold, fraction (0-1) or percent (0-100), default 1.0
- NT_POLL_INTERVAL: seconds between polls, default 10
- NT_TIMEOUT: max seconds to wait, default 900
- NT_VERIFY_SSL: true/false, default true
- NT_OUTPUT_FORMAT: text|markdown|json, default text
- NT_OUTPUT_FILE: optional output path
- NT_NO_WAIT: truthy to trigger and exit immediately

Example / 示例:
```bash
python scripts/nt_cli.py \
  --base-url http://localhost \
  --project-id 123e4567-e89b-12d3-a456-426614174000 \
  --suite-id 9aa9f8b0-aaaa-4a1f-9ff0-123456789abc \
  --email runner@example.com \
  --password changeme \
  --threshold 0.9
```

Exit codes / 退出码:
- 0: passed and met threshold / 通过且满足阈值
- 2: report failed/error / 报告失败或错误
- 3: below threshold / 低于阈值
- 4: skipped / 被跳过
- 1: configuration/network error / 配置或网络错误

---

## 2) GitHub Actions

- A reusable workflow is included at .github/workflows/test-on-pr.yml.
- 仓库已提供可复用工作流：.github/workflows/test-on-pr.yml

Setup / 配置:
- Repository variables: NT_API_BASE, NT_PROJECT_ID, NT_SUITE_ID (optional: NT_PASS_THRESHOLD, NT_REPORT_BASE_URL)
- Repository secrets: NT_API_TOKEN 或 NT_EMAIL + NT_PASSWORD

Reusing / 复用示例:
```yaml
jobs:
  suite:
    uses: ./.github/workflows/test-on-pr.yml
    with:
      project_id: 123e4567-e89b-12d3-a456-426614174000
      suite_id: 9aa9f8b0-aaaa-4a1f-9ff0-123456789abc
      threshold: 0.9
      base_url: https://api.example.com
    secrets:
      nt_api_token: ${{ secrets.NETTESTS_TOKEN }}
```

The workflow posts a PR comment and enforces threshold. / 该工作流会在 PR 中评论结果，并执行阈值校验。

---

## 3) Jenkins

- The Jenkinsfile in the repo demonstrates Trigger → Wait → Publish stages.
- 仓库内 Jenkinsfile 演示了三阶段：触发 → 等待 → 发布。

Credentials / 凭据:
- nt-api-user: username/password → NT_EMAIL/NT_PASSWORD
- nt-api-base, nt-project-id, nt-suite-id, nt-threshold: secret text 变量

流程 / Flow:
1) Setup 环境，安装依赖
2) Trigger 使用 --no-wait 触发并保存 nt_trigger.json
3) Wait 读取 task/report id 继续轮询，生成 nt_result.json
4) Publish 打印摘要并依据退出码判定流水线结果

---

## 4) GitLab CI

- See .gitlab-ci.yml job api-tests for a drop-in example.
- 参考 .gitlab-ci.yml 中 api-tests 任务作为直接示例。

CI variables / CI 变量:
- NT_API_BASE, NT_PROJECT_ID, NT_SUITE_ID
- NT_API_TOKEN 或 NT_EMAIL + NT_PASSWORD
- 可选: NT_PASS_THRESHOLD, NT_REPORT_BASE_URL

Artifacts keep nt_result.json for later review. / 产物将保留 nt_result.json 以便审阅。

---

## 5) Backend task support / 后端任务支持

GET /api/v1/tasks/{task_id} returns:
```json
{
  "code": "SUCCESS",
  "data": {
    "task_id": "...",
    "status": "success",
    "report_id": "...",
    "report_url": "/reports/..."
  }
}
```
CLI uses it for resuming and link building. / CLI 使用该接口恢复轮询并构建报告链接。

---

## 6) Failure criteria summary / 失败判定表

- failed/error → exit 2
- below threshold → exit 3
- skipped → exit 4
- success above threshold → exit 0
- configuration/network errors → exit 1

在 CI 中可据此进行合并阻断、告警等控制。
