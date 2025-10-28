import client from "./client";
import type { ExecutionTrigger, TestSuite } from "@/types/api";

export interface CreateSuitePayload {
  name: string;
  description?: string | null;
  steps?: unknown[];
  variables?: Record<string, unknown>;
}

export interface UpdateSuitePayload extends Partial<CreateSuitePayload> {}

export async function listTestSuites(projectId: string): Promise<TestSuite[]> {
  return client.get<TestSuite[]>(`/v1/projects/${projectId}/test-suites`);
}

export async function createTestSuite(
  projectId: string,
  payload: CreateSuitePayload
): Promise<TestSuite> {
  return client.post<TestSuite>(`/v1/projects/${projectId}/test-suites`, payload);
}

export async function updateTestSuite(
  projectId: string,
  suiteId: string,
  payload: UpdateSuitePayload
): Promise<TestSuite> {
  return client.patch<TestSuite>(
    `/v1/projects/${projectId}/test-suites/${suiteId}`,
    payload
  );
}

export async function deleteTestSuite(
  projectId: string,
  suiteId: string
): Promise<{ id: string; deleted: boolean }> {
  return client.delete<{ id: string; deleted: boolean }>(
    `/v1/projects/${projectId}/test-suites/${suiteId}`
  );
}

export async function runTestSuite(
  projectId: string,
  suiteId: string
): Promise<ExecutionTrigger> {
  return client.post<ExecutionTrigger>(
    `/v1/projects/${projectId}/execute/suite/${suiteId}`,
    {}
  );
}
