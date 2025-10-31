[English](../en/ci-cd.md) | 中文

# CI/CD 指南与命令行使用

本文档介绍如何将 NexusTest-AI 集成到自动化流水线中，包含内置 Python CLI（scripts/nt_cli.py）的用法，以及 GitHub Actions、Jenkins 与 GitLab CI 的示例。

---

## 1) CLI（scripts/nt_cli.py）

- 安全登录后触发用例/套件执行，可选择等待完成；若通过率低于阈值则返回非 0 退出码。

前置条件：
- Python 3.11+
- httpx

安装：
```bash
python -m pip install --upgrade pip
python -m pip install httpx
```

环境变量：
- NT_API_BASE：后端 API 基础地址（必填）
- NT_REPORT_BASE_URL：用于人类可读链接的基础地址（可选）
- NT_PROJECT_ID：目标项目 id（必填）
- NT_SUITE_ID / NT_CASE_ID / NT_TASK_ID：三者之一用于执行或恢复
- NT_REPORT_ID：恢复时可选
- NT_API_TOKEN 或 NT_EMAIL + NT_PASSWORD：认证方式
- NT_PASS_THRESHOLD：通过率阈值，分数（0-1）或百分比（0-100），默认 1.0
- NT_POLL_INTERVAL：轮询间隔秒数，默认 10
- NT_TIMEOUT：最大等待秒数，默认 900
- NT_VERIFY_SSL：true/false，默认 true
- NT_OUTPUT_FORMAT：text|markdown|json，默认 text
- NT_OUTPUT_FILE：可选输出文件路径
- NT_NO_WAIT：为真时触发后立即退出

示例：
```bash
python scripts/nt_cli.py \
  --base-url http://localhost \
  --project-id 123e4567-e89b-12d3-a456-426614174000 \
  --suite-id 9aa9f8b0-aaaa-4a1f-9ff0-123456789abc \
  --email runner@example.com \
  --password changeme \
  --threshold 0.9
```

退出码：
- 0：通过且满足阈值
- 2：报告失败/错误
- 3：低于阈值
- 4：被跳过
- 1：配置或网络错误

---

## 2) GitHub Actions

- 仓库已提供可复用工作流：.github/workflows/test-on-pr.yml

配置：
- 仓库变量：NT_API_BASE，NT_PROJECT_ID，NT_SUITE_ID（可选：NT_PASS_THRESHOLD，NT_REPORT_BASE_URL）
- 仓库密钥：NT_API_TOKEN 或 NT_EMAIL + NT_PASSWORD

复用示例：
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

该工作流会在 PR 中评论结果，并执行阈值校验。

---

## 3) Jenkins

- 仓库内 Jenkinsfile 演示了三阶段：触发 → 等待 → 发布。

凭据：
- nt-api-user：用户名/密码 → NT_EMAIL/NT_PASSWORD
- nt-api-base、nt-project-id、nt-suite-id、nt-threshold：Secret Text 变量

流程：
1) 准备环境并安装依赖
2) 使用 --no-wait 触发并保存 nt_trigger.json
3) 读取 task/report id 持续轮询，生成 nt_result.json
4) 打印摘要并依据退出码判定流水线结果

---

## 4) GitLab CI

- 参考 .gitlab-ci.yml 中 api-tests 任务作为直接示例。

CI 变量：
- NT_API_BASE、NT_PROJECT_ID、NT_SUITE_ID
- NT_API_TOKEN 或 NT_EMAIL + NT_PASSWORD
- 可选：NT_PASS_THRESHOLD、NT_REPORT_BASE_URL

产物会保留 nt_result.json 以便审阅。

---

## 5) 后端任务支持

GET /api/v1/tasks/{task_id} 返回：
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
CLI 使用该接口恢复轮询并构建报告链接。

---

## 6) 失败判定表

- failed/error → 退出码 2
- below threshold → 退出码 3
- skipped → 退出码 4
- success above threshold → 退出码 0
- configuration/network errors → 退出码 1
