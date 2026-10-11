const base = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");

export const apiUrl = (path: string) => `${base}/api/v1${path.startsWith("/") ? path : `/${path}`}`;

export const token = () => localStorage.getItem("opsagent_token") || "";

export function apiErrorMessage(detail: unknown, fallback = "Request failed") {
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const messages = detail.map((item) => {
      if (!item || typeof item !== "object") return String(item);
      const error = item as { loc?: unknown[]; msg?: unknown };
      const field = (error.loc || []).filter((part) => part !== "body").join(" ");
      const message = typeof error.msg === "string" ? error.msg : "Invalid value";
      return field ? `${field}: ${message}` : message;
    }).filter(Boolean);
    if (messages.length) return messages.join(" · ");
  }
  if (detail && typeof detail === "object") {
    const message = (detail as { message?: unknown }).message;
    if (typeof message === "string" && message.trim()) return message;
  }
  return fallback;
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(apiUrl(path), {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token()}`,
      ...options.headers,
    },
  });
  if (!response.ok) {
    const detail = (await response.json().catch(() => null))?.detail;
    if (response.status === 401) {
      localStorage.removeItem("opsagent_token");
      window.dispatchEvent(new Event("opsagent:unauthorized"));
    }
    throw new Error(apiErrorMessage(detail, `Request failed (${response.status})`));
  }
  return response.json();
}
