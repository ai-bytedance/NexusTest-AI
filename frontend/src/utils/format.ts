import dayjs from "dayjs";

export function formatDateTime(value?: string | null, fallback = "-"): string {
  if (!value) {
    return fallback;
  }
  const parsed = dayjs(value);
  if (!parsed.isValid()) {
    return fallback;
  }
  return parsed.format("YYYY-MM-DD HH:mm:ss");
}

export function formatDate(value?: string | null, fallback = "-"): string {
  if (!value) {
    return fallback;
  }
  const parsed = dayjs(value);
  if (!parsed.isValid()) {
    return fallback;
  }
  return parsed.format("YYYY-MM-DD");
}

export function formatDuration(durationMs?: number | null): string {
  if (durationMs === undefined || durationMs === null) {
    return "-";
  }
  if (durationMs < 1000) {
    return `${durationMs} ms`;
  }
  const seconds = durationMs / 1000;
  if (seconds < 60) {
    return `${seconds.toFixed(2)} s`;
  }
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  if (minutes < 60) {
    return `${minutes}m ${remainingSeconds.toFixed(0)}s`;
  }
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return `${hours}h ${remainingMinutes}m`;
}

export function formatPassRate(value?: number | null): string {
  if (value === undefined || value === null) {
    return "-";
  }
  return `${Math.round(value * 100)}%`;
}
