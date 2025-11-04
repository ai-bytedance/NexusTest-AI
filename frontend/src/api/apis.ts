import client from "./client";
import type {
  ApiDefinition,
  HttpMethod,
  OpenAPIImportResponse,
  PostmanImportResponse,
} from "@/types/api";

export interface ApiPayload {
  name: string;
  method: HttpMethod;
  path: string;
  version?: string;
  group_name?: string | null;
  headers?: Record<string, unknown>;
  params?: Record<string, unknown>;
  body?: Record<string, unknown>;
  mock_example?: Record<string, unknown>;
}

export interface ApiUpdatePayload extends Partial<ApiPayload> {}

export interface OpenApiImportPayload {
  url?: string;
  json?: Record<string, unknown>;
  dry_run?: boolean;
}

export interface PostmanImportPayload {
  collection: Record<string, unknown>;
  dry_run?: boolean;
}

export async function listApis(projectId: string): Promise<ApiDefinition[]> {
  return client.get<ApiDefinition[]>(`/projects/${projectId}/apis`);
}

export async function createApi(
  projectId: string,
  payload: ApiPayload
): Promise<ApiDefinition> {
  return client.post<ApiDefinition>(`/projects/${projectId}/apis`, payload);
}

export async function updateApi(
  projectId: string,
  apiId: string,
  payload: ApiUpdatePayload
): Promise<ApiDefinition> {
  return client.patch<ApiDefinition>(`/projects/${projectId}/apis/${apiId}`, payload);
}

export async function deleteApi(
  projectId: string,
  apiId: string
): Promise<{ id: string; deleted: boolean }> {
  return client.delete<{ id: string; deleted: boolean }>(
    `/projects/${projectId}/apis/${apiId}`
  );
}

export async function importOpenApi(
  projectId: string,
  payload: OpenApiImportPayload
): Promise<OpenAPIImportResponse> {
  return client.post<OpenAPIImportResponse>(
    `/projects/${projectId}/import/openapi`,
    payload
  );
}

export async function importPostmanCollection(
  projectId: string,
  payload: PostmanImportPayload
): Promise<PostmanImportResponse> {
  return client.post<PostmanImportResponse>(
    `/projects/${projectId}/import/postman`,
    payload
  );
}
