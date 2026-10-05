import { cookies } from "next/headers";

const internalBase = process.env.BACKEND_INTERNAL_URL || "http://localhost:8000";

// Carries the HTTP status so a caller can tell "the API said 401" (signed out) from "the API is erroring". It is still an
// Error with the same message as before, so every existing caller keeps working unchanged. A network failure is NOT an
// ApiError (there was no HTTP answer) and propagates as the TypeError fetch threw.
export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export async function serverApi<T>(path: string, init?: RequestInit): Promise<T> {
  const jar = await cookies();
  const cookieHeader = jar.toString();
  const res = await fetch(`${internalBase}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(cookieHeader ? {cookie: cookieHeader} : {}), ...(init?.headers || {}) },
    cache: "no-store"
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try { const data = await res.json(); detail = data.detail || detail; } catch {}
    throw new ApiError(detail, res.status);
  }
  return res.json() as Promise<T>;
}

export async function publicApi<T>(path: string): Promise<T> {
  const res = await fetch(`${internalBase}${path}`, { next: { revalidate: 60 } });
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json() as Promise<T>;
}
