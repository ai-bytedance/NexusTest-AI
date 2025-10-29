import client from "./client";
import type {
  AIChatMessage,
  AIChatSummary,
  ChatCompletion,
  ChatDetail,
  ChatTool,
  TestCase,
} from "@/types/api";

export interface GenerateCasesPayload {
  project_id: string;
  api_spec: Record<string, unknown> | string;
}

export interface GenerateAssertionsPayload {
  project_id: string;
  example_response: Record<string, unknown> | string;
}

export interface GenerateMockDataPayload {
  project_id: string;
  json_schema: Record<string, unknown>;
}

export interface SummarizeReportPayload {
  project_id: string;
  report_id?: string;
  report?: Record<string, unknown>;
}

export interface ChatMessageInput {
  role: "user" | "assistant" | "system";
  content: string;
}

export interface ChatContextPayload {
  api_id?: string;
  openapi_spec?: Record<string, unknown>;
  example_response?: Record<string, unknown>;
  json_schema?: Record<string, unknown>;
  report_id?: string;
  report?: Record<string, unknown>;
  examples?: Record<string, unknown> | Record<string, unknown>[];
}

export interface ChatRequestPayload {
  project_id: string;
  chat_id?: string;
  messages: ChatMessageInput[];
  tools?: ChatTool[];
  context?: ChatContextPayload;
}

export interface SaveGeneratedCasesPayload {
  project_id: string;
  message_id: string;
  api_id: string;
}

export async function generateCases(payload: GenerateCasesPayload): Promise<Record<string, unknown>> {
  return client.post<Record<string, unknown>>("/v1/ai/generate-cases", payload);
}

export async function generateAssertions(
  payload: GenerateAssertionsPayload
): Promise<Record<string, unknown>> {
  return client.post<Record<string, unknown>>("/v1/ai/generate-assertions", payload);
}

export async function generateMockData(
  payload: GenerateMockDataPayload
): Promise<Record<string, unknown>> {
  return client.post<Record<string, unknown>>("/v1/ai/mock-data", payload);
}

export async function summarizeReportWithAI(
  payload: SummarizeReportPayload
): Promise<Record<string, unknown>> {
  return client.post<Record<string, unknown>>("/v1/ai/summarize-report", payload);
}

export async function chatWithAssistant(
  payload: ChatRequestPayload,
  provider?: string
): Promise<ChatCompletion> {
  const suffix = provider ? `?provider=${provider}` : "";
  return client.post<ChatCompletion>(`/v1/ai/chat${suffix}`, payload);
}

export async function listChats(projectId: string): Promise<AIChatSummary[]> {
  return client.get<AIChatSummary[]>("/v1/ai/chats", { params: { project_id: projectId } });
}

export async function getChat(projectId: string, chatId: string): Promise<ChatDetail> {
  return client.get<ChatDetail>(`/v1/ai/chats/${chatId}`, { params: { project_id: projectId } });
}

export async function saveGeneratedCases(
  chatId: string,
  payload: SaveGeneratedCasesPayload
): Promise<{ cases: TestCase[]; message: AIChatMessage }> {
  return client.post<{ cases: TestCase[]; message: AIChatMessage }>(
    `/v1/ai/chats/${chatId}/save-test-cases`,
    payload
  );
}
