import client from "./client";
import type {
  DashboardSummary,
  ExportMarkdownResponse,
  PaginatedResult,
  ReportDetail,
  ReportEntityType,
  ReportStatus,
  ReportSummary,
  SummaryActionResponse,
  TaskStatusPayload,
} from "@/types/api";

export interface ReportListParams {
  projectId: string;
  entityType?: ReportEntityType;
  status?: ReportStatus;
  dateFrom?: string;
  dateTo?: string;
  orderBy?: string;
  orderDirection?: "asc" | "desc";
  page?: number;
  pageSize?: number;
}

function buildQuery(params: Record<string, string | number | undefined | null>): string {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") {
      return;
    }
    query.append(key, String(value));
  });
  const queryString = query.toString();
  return queryString ? `?${queryString}` : "";
}

export async function listReports(params: ReportListParams): Promise<PaginatedResult<ReportSummary>> {
  const {
    projectId,
    entityType,
    status,
    dateFrom,
    dateTo,
    orderBy,
    orderDirection,
    page,
    pageSize,
  } = params;
  const query = buildQuery({
    project_id: projectId,
    entity_type: entityType,
    status,
    date_from: dateFrom,
    date_to: dateTo,
    order_by: orderBy,
    order_direction: orderDirection,
    page,
    page_size: pageSize,
  });
  return client.get<PaginatedResult<ReportSummary>>(`/v1/reports${query}`);
}

export async function getReport(reportId: string): Promise<ReportDetail> {
  return client.get<ReportDetail>(`/v1/reports/${reportId}`);
}

export async function summarizeReport(
  reportId: string,
  overwrite = false
): Promise<SummaryActionResponse> {
  return client.post<SummaryActionResponse>(`/v1/reports/${reportId}/summarize`, {
    overwrite,
  });
}

export async function exportReport(
  reportId: string,
  format: "markdown" = "markdown"
): Promise<ExportMarkdownResponse> {
  return client.get<ExportMarkdownResponse>(`/v1/reports/${reportId}/export`, {
    params: { format },
  });
}

export async function getDashboardSummary(
  projectId: string,
  days = 14
): Promise<DashboardSummary> {
  return client.get<DashboardSummary>("/v1/metrics/reports/summary", {
    params: {
      project_id: projectId,
      days,
    },
  });
}

export async function getTaskStatus(taskId: string): Promise<TaskStatusPayload> {
  return client.get<TaskStatusPayload>(`/v1/tasks/${taskId}`);
}
