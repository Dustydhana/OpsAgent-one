const base = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");

export const apiUrl = (path: string) => `${base}/api/v1${path.startsWith("/") ? path : `/${path}`}`;

export const token = () => localStorage.getItem("opsagent_token") || "";

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
    throw new Error(detail || `Request failed (${response.status})`);
  }
  return response.json();
}
