// ENH-005: the two API-error shapes every School screen already handles -- a string `detail` (403/409/429) or FastAPI's
// list (422) -- in one place for the new transfer components. (The same helper is copy-pasted inside three older
// components; those are deliberately left untouched.)
export function detailMessage(detail: unknown, fallback = "Something went wrong."): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => readable(item?.msg) || "Invalid input").join("; ");
  return fallback;
}

// Pydantic words a failed custom validator as "Value error, <our message>"; the prefix means nothing to a coordinator (browser QA N1).
// Only the 422 list is cleaned: a string `detail` is our own wording and is shown as written.
function readable(msg: string | undefined): string {
  const text = (msg ?? "").replace(/^Value error,\s*/, "");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

// A 200 (or 201) is only a success if it carries the request it is about: a proxy login page, an empty body or `{}` must not be reported as
// "filed", "cancelled" or "decided" (browser QA N2). The check is the id only, because that is all the screens rely on beyond the status.
export function isRequestBody(data: unknown): data is { id: string } {
  return !!data && typeof data === "object" && !Array.isArray(data) && typeof (data as { id?: unknown }).id === "string";
}

// What both request forms say when the network drops mid-submit. The entry is kept, so the coordinator can simply try again.
export const NOT_COMPLETED = "The request did not complete. Check your connection and try again; your entry is kept.";

export type Page<T> = { items: T[]; total: number; limit: number; offset: number };

// A 200 is only trusted if it has the shape of a page. A proxy login page or an empty body must not crash the screen.
export function isPage<T = unknown>(data: unknown): data is Page<T> {
  const d = data as Partial<Page<T>> | null;
  return !!d && typeof d === "object" && Array.isArray(d.items) && typeof d.total === "number" && typeof d.limit === "number" && typeof d.offset === "number";
}

// `status` is the HTTP status of a failed response (absent when the network dropped), so a screen can word its own 401/5xx (QA27-03/-04).
// `detail` is the server's raw detail, so a form can put a 422 on its field (AGN-013 QA13-09).
export type SendOutcome = { ok: true; data: Record<string, unknown> } | { ok: false; message: string; status?: number; detail?: unknown };

// ENH-022: one JSON write for the older School panels. Never throws: a dropped network is NOT_COMPLETED (the entry is kept), and
// any error response carries the server's `detail` -- e.g. a partnership-tier 403 -- worded by detailMessage.
export async function sendJson(url: string, method: "POST" | "PATCH" | "PUT", body: unknown): Promise<SendOutcome> {
  return sendRequest(url, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}

// sendJson's contract for any request body (AGN-009 multipart uploads pass a FormData; the browser sets the boundary).
export async function sendRequest(url: string, init: RequestInit): Promise<SendOutcome> {
  let response: Response;
  try {
    response = await fetch(url, init);
  } catch {
    return { ok: false, message: NOT_COMPLETED };
  }
  const data = await response.json().catch(() => null);
  if (!response.ok) return { ok: false, message: detailMessage(data?.detail), status: response.status, detail: data?.detail };
  return { ok: true, data: data && typeof data === "object" ? data : {} };
}
