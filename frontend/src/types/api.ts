export interface ApiResponse<T> {
  code: string;
  message: string;
  data: T;
}

export interface Pagination {
  page: number;
  page_size: number;
  total: number;
}

export interface PaginatedResult<T> {
  items: T[];
  pagination: Pagination;
}

export interface Project {
  id: string;
  name: string;
  key: string;
  description: string | null;
  created_at: string;
  updated_at: string;
  created_by: string;
}

export type ProjectRole = "admin" | "member";

export interface ProjectMemberUser {
  id: string;
  email: string;
}

export interface ProjectMember {
  id: string;
  project_id: string;
  user_id: string;
  role: ProjectRole;
  created_at: string;
  updated_at: string;
  user: ProjectMemberUser;
}

export interface ProjectWithMembers extends Project {
  members: ProjectMember[];
}

export type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export interface ApiDefinition {
  id: string;
  project_id: string;
  name: string;
  method: HttpMethod;
  path: string;
  version: string;
  group_name: string | null;
  headers: Record<string, unknown>;
  params: Record<string, unknown>;
  body: Record<string, unknown>;
  mock_example: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface TestCase {
  id: string;
  project_id: string;
  api_id: string;
  name: string;
  inputs: Record<string, unknown>;
  expected: Record<string, unknown>;
  assertions: Record<string, unknown>;
  enabled: boolean;
  created_at: string;
  updated_at: string;
  created_by: string;
}

export interface TestSuite {
  id: string;
  project_id: string;
  name: string;
  description: string | null;
  steps: unknown[];
  variables: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  created_by: string;
}

export type ReportEntityType = "case" | "suite";

export type ReportStatus =
  | "pending"
  | "running"
  | "passed"
  | "failed"
  | "error"
  | "skipped";

export interface ReportSummary {
  id: string;
  project_id: string;
  entity_type: ReportEntityType;
  entity_id: string;
  status: ReportStatus;
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  created_at: string;
  updated_at: string;
  summary: string | null;
  failure_signature: string | null;
  failure_excerpt: string | null;
  is_flaky: boolean;
  flakiness_score: number | null;
  assertions_total: number;
  assertions_passed: number;
  pass_rate: number;
  response_size: number;
  response_payload_truncated: boolean;
  request_payload_truncated: boolean;
}

export interface ReportDetail extends ReportSummary {
  request_payload: Record<string, unknown> | null;
  response_payload: Record<string, unknown> | null;
  assertions_result: AssertionsResult | null;
  metrics: Record<string, unknown> | null;
  response_payload_note?: string;
  request_payload_note?: string;
  redacted_fields?: string[];
}

export interface AssertionsResult {
  results?: AssertionItem[];
  [key: string]: unknown;
}

export interface AssertionItem {
  name?: string;
  target?: string;
  passed?: boolean;
  message?: string;
  expected?: unknown;
  actual?: unknown;
  [key: string]: unknown;
}

export interface ExecutionTrigger {
  task_id: string;
  report_id: string;
}

export interface MetricsSeriesPoint {
  date: string;
  passed: number;
  failed: number;
  error: number;
  success_rate: number;
}

export interface DashboardSummary {
  project_id: string;
  from: string;
  to: string;
  days: number;
  series: MetricsSeriesPoint[];
}

export interface SummaryActionResponse {
  report_id: string;
  summary: string;
  task_id: string | null;
  updated: boolean;
}

export interface ExportMarkdownResponse {
  report_id: string;
  format: "markdown";
  filename: string;
  content_type: string;
  content: string;
}

export interface ImportSummary {
  created: number;
  updated: number;
  skipped: number;
  details: string[];
}

export interface OpenAPIImportResponse {
  summary: ImportSummary;
}

export interface PostmanImportResponse {
  summary: ImportSummary;
}

export interface TaskStatusPayload {
  task_id: string;
  status: string;
  report_id: string | null;
}

export type ReportProgressEventType =
  | "task_queued"
  | "started"
  | "step_progress"
  | "assertion_result"
  | "finished";

export interface ReportProgressEvent {
  type: ReportProgressEventType;
  report_id: string;
  step_alias?: string | null;
  payload?: Record<string, unknown> | null;
  timestamp?: string;
  truncated?: boolean;
}

export type ChatTool =
  | "generate_cases"
  | "generate_assertions"
  | "generate_mock"
  | "summarize";

export interface GeneratedCaseOutput {
  name: string;
  description?: string | null;
  request: Record<string, unknown>;
  expected: Record<string, unknown>;
  assertions: Record<string, unknown>[];
  metadata?: Record<string, unknown> | null;
}

export interface AIChatMessageContent {
  kind: "text" | "cases" | "assertions" | "mock" | "summary" | "system";
  text?: string | null;
  cases?: GeneratedCaseOutput[];
  assertions?: Record<string, unknown>[];
  mock?: Record<string, unknown> | null;
  summary?: Record<string, unknown> | null;
  tool?: ChatTool | null;
  saved_case_ids?: string[] | null;
}

export interface AIChatMessage {
  id: string;
  chat_id: string;
  role: "user" | "assistant" | "system";
  sequence: number;
  content: AIChatMessageContent;
  tool_invoked?: ChatTool | null;
  result_ref?: string | null;
  author_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface AIChat {
  id: string;
  project_id: string;
  title: string;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface AIChatSummary extends AIChat {
  last_message_at?: string | null;
  message_count: number;
}

export interface ChatCompletion {
  chat: AIChat;
  messages: AIChatMessage[];
  tool?: ChatTool | null;
  usage?: Record<string, number> | null;
}

export interface ChatDetail {
  chat: AIChat;
  messages: AIChatMessage[];
}
