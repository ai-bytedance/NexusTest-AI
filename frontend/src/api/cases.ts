import client from "./client";
import type { ExecutionTrigger, TestCase } from "@/types/api";

export interface CreateCasePayload {
  api_id: string;
  name: string;
  inputs?: Record<string, unknown>;
  expected?: Record<string, unknown>;
  assertions?: Record<string, unknown>;
  enabled?: boolean;
}

export interface UpdateCasePayload extends Partial<CreateCasePayload> {}

export async function listTestCases(projectId: string): Promise<TestCase[]> {
  return client.get<TestCase[]>(`/projects/${projectId}/test-cases`);
}

export async function createTestCase(
  projectId: string,
  payload: CreateCasePayload
): Promise<TestCase> {
  return client.post<TestCase>(`/projects/${projectId}/test-cases`, payload);
}

export async function updateTestCase(
  projectId: string,
  caseId: string,
  payload: UpdateCasePayload
): Promise<TestCase> {
  return client.patch<TestCase>(
    `/projects/${projectId}/test-cases/${caseId}`,
    payload
  );
}

export async function deleteTestCase(
  projectId: string,
  caseId: string
): Promise<{ id: string; deleted: boolean }> {
  return client.delete<{ id: string; deleted: boolean }>(
    `/projects/${projectId}/test-cases/${caseId}`
  );
}

export async function runTestCase(
  projectId: string,
  caseId: string
): Promise<ExecutionTrigger> {
  return client.post<ExecutionTrigger>(
    `/projects/${projectId}/execute/case/${caseId}`,
    {}
  );
}
