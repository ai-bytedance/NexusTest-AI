export function safeParseJson<T = unknown>(value: string, fallback: T): T {
  try {
    if (!value.trim()) {
      return fallback;
    }
    return JSON.parse(value) as T;
  } catch (error) {
    return fallback;
  }
}

export function stringifyJson(value: unknown, space = 2): string {
  try {
    if (value === undefined) {
      return "";
    }
    return JSON.stringify(value, null, space);
  } catch (error) {
    return "";
  }
}
