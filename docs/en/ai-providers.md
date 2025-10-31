English | [中文](../zh/ai-providers.md)

# AI Providers Configuration

This guide explains how to configure multi-provider AI for NexusTest-AI. The backend supports DeepSeek (default), OpenAI, Anthropic Claude, Google Gemini, Alibaba Qwen, Zhipu GLM, ByteDance Doubao, and a deterministic mock provider.

---

## Selecting a provider

- Set PROVIDER to one of: mock, deepseek, openai, anthropic, gemini, qwen, glm, zhipu, doubao
- You can also override per request with query param provider, for example:
  - POST /api/v1/ai/generate-cases?provider=openai
  - POST /api/v1/reports/{id}/summarize?provider=anthropic

When credentials are missing, the system falls back to the mock provider.

---

## Environment variables

Each provider supports an API key, optional custom base URL, and a default model that can be overridden without code changes.

| Provider | Required | Optional | Default model |
|---------|----------|----------|---------------|
| DeepSeek | DEEPSEEK_API_KEY | DEEPSEEK_BASE_URL, DEEPSEEK_MODEL | deepseek-chat |
| OpenAI | OPENAI_API_KEY | OPENAI_BASE_URL, OPENAI_MODEL | gpt-4o-mini |
| Anthropic | ANTHROPIC_API_KEY | ANTHROPIC_BASE_URL, ANTHROPIC_MODEL | claude-3-5-sonnet-20240620 |
| Gemini | GOOGLE_API_KEY | GOOGLE_BASE_URL, GEMINI_MODEL | gemini-1.5-flash |
| Qwen | QWEN_API_KEY | QWEN_BASE_URL, QWEN_MODEL | qwen-plus |
| GLM | ZHIPU_API_KEY | ZHIPU_BASE_URL, GLM_MODEL | glm-4-airx |
| Doubao | DOUBAO_API_KEY | DOUBAO_BASE_URL, DOUBAO_MODEL | doubao-pro-4k |

All providers honour REQUEST_TIMEOUT_SECONDS.

---

## Response shape & errors

- Endpoints return validated JSON with stable schemas:
  - generate-cases: { "cases": [...] }
  - generate-assertions: { "assertions": [...] }
  - mock-data: { "data": <object|array> }
  - summarize-report: { "markdown": "..." }
- Failures surface vendor-neutral error codes AI001–AI006; raw payloads are included in detail.data.

---

## Token usage metrics

Successful invocations persist model name and token counts (prompt/completion/total) in the ai_tasks table for analytics and billing.

---

## Troubleshooting

- Unexpected mock provider: missing *_API_KEY
- JSON decode errors: inspect ai_tasks.output_payload and provider error
- Rate limits: reduce concurrency or use gateways with higher quotas
- Custom gateways: set *_BASE_URL
