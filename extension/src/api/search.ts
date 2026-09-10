import type { SearchAssistResponse } from "../types/search";
import type {
  ImageAnalyzeResponse,
  ImageUploadResponse,
} from "../types/search";
import { requestJson } from "./http";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
export const analyticsSessionId = `s_${crypto.randomUUID()}`;
export async function track(
  event_name: string,
  payload: Record<string, unknown> = {},
) {
  try {
    await requestJson(`${API_BASE_URL}/api/analytics/events`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        event_name,
        session_id: analyticsSessionId,
        payload,
      }),
    });
  } catch {
    /* telemetry never blocks UX */
  }
}

export async function assistSearch(
  query: string,
  language = "auto",
  persona?: string,
  platforms?: string[],
): Promise<SearchAssistResponse> {
  return requestJson<SearchAssistResponse>(
    `${API_BASE_URL}/api/v1/search/assist`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, language, persona, platforms }),
    },
  );
}
export async function uploadImage(file: File): Promise<ImageUploadResponse> {
  const form = new FormData();
  form.append("file", file);
  return requestJson(`${API_BASE_URL}/api/images/upload`, {
    method: "POST",
    body: form,
  });
}
export async function analyzeImage(
  imageId: string,
  persona?: string,
  platform?: string,
): Promise<ImageAnalyzeResponse> {
  const params = new URLSearchParams();
  if (persona) params.set("persona", persona);
  if (platform) params.set("platform", platform);
  return requestJson(
    `${API_BASE_URL}/api/images/${imageId}/analyze${params.size ? `?${params}` : ""}`,
    { method: "POST" },
  );
}
