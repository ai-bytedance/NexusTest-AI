[English](../en/ai-providers.md) | 中文

# 人工智能提供商配置

本指南介绍如何在 NexusTest-AI 中配置多家 AI 提供商。后端支持 DeepSeek（默认）、OpenAI、Anthropic Claude、Google Gemini、阿里通义千问（Qwen）、智谱 GLM、字节 Doubao，以及一个可重复结果的 Mock 提供商。

---

## 选择提供商

- 将 PROVIDER 设置为以下之一：mock、deepseek、openai、anthropic、gemini、qwen、glm、zhipu、doubao
- 也可在请求级别用 provider 查询参数临时覆盖，例如：
  - POST /api/v1/ai/generate-cases?provider=openai
  - POST /api/v1/reports/{id}/summarize?provider=anthropic

如缺少凭据，系统会自动回退到 Mock 提供商。

---

## 环境变量

每个提供商均支持 API Key、可选的自定义 Base URL 以及默认模型（可通过环境变量覆盖）。

| 提供商 | 必填 | 可选 | 默认模型 |
|---------|----------|----------|---------------|
| DeepSeek | DEEPSEEK_API_KEY | DEEPSEEK_BASE_URL, DEEPSEEK_MODEL | deepseek-chat |
| OpenAI | OPENAI_API_KEY | OPENAI_BASE_URL, OPENAI_MODEL | gpt-4o-mini |
| Anthropic | ANTHROPIC_API_KEY | ANTHROPIC_BASE_URL, ANTHROPIC_MODEL | claude-3-5-sonnet-20240620 |
| Gemini | GOOGLE_API_KEY | GOOGLE_BASE_URL, GEMINI_MODEL | gemini-1.5-flash |
| Qwen | QWEN_API_KEY | QWEN_BASE_URL, QWEN_MODEL | qwen-plus |
| GLM | ZHIPU_API_KEY | ZHIPU_BASE_URL, GLM_MODEL | glm-4-airx |
| Doubao | DOUBAO_API_KEY | DOUBAO_BASE_URL, DOUBAO_MODEL | doubao-pro-4k |

所有提供商均遵循 REQUEST_TIMEOUT_SECONDS 超时配置。

---

## 响应结构与错误

- 各端点返回经校验的稳定 JSON 结构：
  - generate-cases：{ "cases": [...] }
  - generate-assertions：{ "assertions": [...] }
  - mock-data：{ "data": <object|array> }
  - summarize-report：{ "markdown": "..." }
- 失败时返回统一错误码（AI001–AI006），并在 detail.data 中包含原始错误信息。

---

## 令牌用量指标

成功调用会在 ai_tasks 表中记录模型名称与令牌用量（提示/生成/总计），便于分析和计费。

---

## 故障排查

- 意外使用 Mock：缺少对应的 *_API_KEY
- JSON 解析失败：检查 ai_tasks.output_payload 及提供商返回
- 触发限流：降低并发或使用更高配额的网关
- 使用网关：设置对应的 *_BASE_URL
