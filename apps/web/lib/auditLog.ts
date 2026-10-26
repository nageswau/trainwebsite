import { isCalendarDate } from "@/lib/formatDate";

// nehn-042 (DEC-SCOPE-289 A1-A8): the admin Audit log page's filters, links and API address. One page for the three admin portals; the
// API scopes a division admin to their own division (in SQL), so the page never filters rows itself.

export const AUDIT_PAGE_SIZE = 50;
export const AUDIT_DIVISIONS = [{ value: "it", label: "IT" }, { value: "overseas", label: "Overseas" }, { value: "global", label: "Global" }];

export type AuditFilters = {
  actor: string; action: string; entity_type: string; entity_id: string; division: string; date_from: string; date_to: string; offset: number;
};
export type AuditActor = { id: string; full_name: string; email: string; division: string };
export type AuditRow = {
  id: string; user_id: string | null; actor: AuditActor | null; action: string; entity_type: string; entity_id: string | null; outcome: string;
  created_at: string;
};

const TEXT_KEYS = ["actor", "action", "entity_type", "entity_id", "division", "date_from", "date_to"] as const;
const UUID_SHAPE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** The filters from the page's search params, trimmed. A repeated param, an impossible date or an unknown division only comes from a
 *  hand-edited address and is dropped. The actor is kept as typed, so a mistyped reference is explained (auditFilterError), not ignored. */
export function auditFilters(search: Record<string, string | string[] | undefined>): AuditFilters {
  const one = (key: string) => (typeof search[key] === "string" ? (search[key] as string).trim() : "");
  const day = (key: string) => (isCalendarDate(one(key)) ? one(key) : "");
  const offset = Number.parseInt(one("offset"), 10);
  return {
    actor: one("actor"), action: one("action"), entity_type: one("entity_type"), entity_id: one("entity_id"),
    division: AUDIT_DIVISIONS.some((d) => d.value === one("division")) ? one("division") : "",
    date_from: day("date_from"), date_to: day("date_to"), offset: offset > 0 ? offset : 0,
  };
}

/** What the API would refuse, in words; "" when the filters are fine. */
export function auditFilterError(filters: AuditFilters): string {
  if (filters.actor && !UUID_SHAPE.test(filters.actor)) return "“Done by” must be a user reference (as shown in the User reference column).";
  if (filters.date_from && filters.date_to && filters.date_to < filters.date_from) return "The end date must be on or after the start date.";
  return "";
}

function query(filters: AuditFilters): URLSearchParams {
  const params = new URLSearchParams();
  for (const key of TEXT_KEYS) if (filters[key]) params.set(key, filters[key]);
  if (filters.offset > 0) params.set("offset", String(filters.offset));
  return params;
}

/** The page link for these filters (paging links reuse it with another offset). */
export function auditHref(base: string, filters: AuditFilters): string {
  const params = query(filters).toString();
  return params ? `${base}?${params}` : base;
}

/** One row more than a page, so the page knows whether a next page exists without counting the whole log. */
export function auditUrl(filters: AuditFilters): string {
  const params = query(filters);
  params.set("limit", String(AUDIT_PAGE_SIZE + 1));
  return `/api/v1/admin/audit?${params}`;
}

/** A1/A8: one entity's whole history -- the History view for a payment, lead or student. */
export function entityHistoryHref(base: string, entityType: string, entityId: string): string {
  return `${base}?${new URLSearchParams({ entity_type: entityType, entity_id: entityId })}`;
}

/** A8: everything one person did. */
export function actorHistoryHref(base: string, actorId: string): string {
  return `${base}?${new URLSearchParams({ actor: actorId })}`;
}
