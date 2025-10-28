import client from "./client";

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
