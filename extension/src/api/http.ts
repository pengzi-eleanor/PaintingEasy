export type ApiErrorCategory = "network" | "validation" | "server" | "unknown";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly category: ApiErrorCategory,
    public readonly status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function requestJson<T>(
  url: string,
  init: RequestInit,
): Promise<T> {
  let response: Response;
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 15000);
  try {
    response = await fetch(url, { ...init, signal: controller.signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError")
      throw new ApiError("服务响应时间较长，请稍后重试", "network");
    throw new ApiError("无法连接服务，请确认服务已启动", "network");
  } finally {
    window.clearTimeout(timeout);
  }

  if (!response.ok) {
    let detail = "";
    try {
      const body = (await response.json()) as {
        detail?: string | Array<{ msg?: string }>;
      };
      detail = Array.isArray(body.detail)
        ? body.detail
            .map((item) => item.msg)
            .filter(Boolean)
            .join("；")
        : typeof body.detail === "object" && body.detail
          ? ((body.detail as { message?: string }).message ?? "")
          : (body.detail ?? "");
    } catch {
      // 非 JSON 错误响应使用状态码兜底。
    }
    const category: ApiErrorCategory =
      response.status >= 500
        ? "server"
        : response.status === 422
          ? "validation"
          : "unknown";
    throw new ApiError(
      detail || `服务请求失败（${response.status}）`,
      category,
      response.status,
    );
  }

  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError(
      "搜索服务返回了无法解析的数据",
      "unknown",
      response.status,
    );
  }
}
