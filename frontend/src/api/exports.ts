import client from "./client";

export interface PytestExportPayload {
  project_id: string;
  case_ids: string[];
}

export async function exportPytestSuite(payload: PytestExportPayload): Promise<Blob> {
  const response = await client.post<Blob>("/v1/exports/pytest", payload, {
    responseType: "blob",
  });
  return response;
}
