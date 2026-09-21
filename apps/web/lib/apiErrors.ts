// ENH-005: the two API-error shapes every School screen already handles -- a string `detail` (403/409/429) or FastAPI's
// list (422) -- in one place for the new transfer components. (The same helper is copy-pasted inside three older
// components; those are deliberately left untouched.)
export function detailMessage(detail: unknown, fallback = "Something went wrong."): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item?.msg || "Invalid input").join("; ");
  return fallback;
}

export type Page<T> = { items: T[]; total: number; limit: number; offset: number };

// A 200 is only trusted if it has the shape of a page. A proxy login page or an empty body must not crash the screen.
export function isPage<T = unknown>(data: unknown): data is Page<T> {
  const d = data as Partial<Page<T>> | null;
  return !!d && typeof d === "object" && Array.isArray(d.items) && typeof d.total === "number" && typeof d.limit === "number" && typeof d.offset === "number";
}
