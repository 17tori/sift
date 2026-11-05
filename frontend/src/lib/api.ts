import { initData } from "./telegram";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details: Record<string, unknown> = {}) {
    super(message);
  }
}

type Body = FormData | Record<string, unknown> | unknown[] | undefined;

async function request<T>(method: string, path: string, body?: Body, headers: Record<string, string> = {}): Promise<T> {
  const h: Record<string, string> = { Authorization: `tma ${initData()}`, ...headers };
  let payload: BodyInit | undefined;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) {
    h["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  let res: Response;
  try {
    res = await fetch(path, { method, headers: h, body: payload });
  } catch {
    throw new ApiError(0, "network", "Нет соединения. Проверьте интернет и попробуйте снова.");
  }
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const e = (data as { error?: { code?: string; message?: string } }).error ?? {};
    throw new ApiError(res.status, e.code ?? "error", e.message ?? "Что-то пошло не так.", e as Record<string, unknown>);
  }
  return data as T;
}

export const api = {
  get: <T>(p: string) => request<T>("GET", p),
  post: <T>(p: string, b?: Body, h?: Record<string, string>) => request<T>("POST", p, b, h),
  patch: <T>(p: string, b?: Body) => request<T>("PATCH", p, b),
  put: <T>(p: string, b?: Body) => request<T>("PUT", p, b),
  del: <T>(p: string) => request<T>("DELETE", p),
};

export function qs(params: Record<string, string | number | null | undefined>): string {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== null && v !== undefined && v !== "") u.set(k, String(v));
  const s = u.toString();
  return s ? `?${s}` : "";
}
