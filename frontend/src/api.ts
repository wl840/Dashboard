import type {
  ChatResponse,
  DashboardData,
  DashboardFilters,
  Metadata,
} from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

async function request<T>(
  path: string,
  init?: RequestInit,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, { ...init, signal });
  if (!response.ok) {
    let message = `请求失败（${response.status}）`;
    try {
      const payload = (await response.json()) as { detail?: string };
      if (payload.detail) message = payload.detail;
    } catch {
      // Keep the status-based fallback when the body is not JSON.
    }
    throw new Error(message);
  }
  return (await response.json()) as T;
}

export function fetchMetadata(signal?: AbortSignal): Promise<Metadata> {
  return request<Metadata>("/api/meta", undefined, signal);
}

export function fetchDashboard(
  filters: DashboardFilters,
  signal?: AbortSignal,
): Promise<DashboardData> {
  const params = new URLSearchParams({
    start_date: filters.startDate,
    end_date: filters.endDate,
  });
  if (filters.storeId) params.set("store_id", filters.storeId);
  return request<DashboardData>(`/api/dashboard?${params}`, undefined, signal);
}

export function sendChat(
  message: string,
  context: Record<string, unknown>,
): Promise<ChatResponse> {
  return request<ChatResponse>("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, context }),
  });
}
