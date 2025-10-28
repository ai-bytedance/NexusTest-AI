import { Tag } from "antd";
import type { ReportStatus } from "@/types/api";

interface StatusTagProps {
  status: ReportStatus | string;
}

const STATUS_COLOR_MAP: Record<string, string> = {
  pending: "default",
  running: "processing",
  passed: "success",
  failed: "error",
  error: "error",
  skipped: "warning",
};

const STATUS_LABEL_MAP: Record<string, string> = {
  pending: "Pending",
  running: "Running",
  passed: "Passed",
  failed: "Failed",
  error: "Error",
  skipped: "Skipped",
};

export function StatusTag({ status }: StatusTagProps) {
  const normalized = status?.toString().toLowerCase();
  const color = STATUS_COLOR_MAP[normalized] ?? "default";
  const label = STATUS_LABEL_MAP[normalized] ?? status;
  return <Tag color={color}>{label}</Tag>;
}

export default StatusTag;
