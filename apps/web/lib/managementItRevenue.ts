// mgmt-007 (spec IR1-IR12): GET /management/revenue/it -- IT Training revenue, costs and new enrolments per course and batch for a
// month or its Indian financial year to date -- and /payments, the payments behind one course, batch or the "Not linked" row. The API
// decides access (finance tier) and every figure; nothing here computes money.
export const IT_REVENUE_HOME = "/management/revenue/it";
export const IT_REVENUE_API = "/api/v1/management/revenue/it";
export const PAGE_SIZE = 25;

export type Period = "month" | "year";
export type Money = { revenue: string; costs: string };
export type ItRevenueBatch = Money & { batch_id: string; name: string; enrolments: number };
export type ItRevenueCourse = Money & { program_id: string; title: string; enrolments: number; contribution: string; batches: ItRevenueBatch[]; unbatched: Money };
export type ItRevenue = {
  month: string; period: Period; start: string; end: string; label: string;
  totals: Money & { contribution: string; enrolments: number };
  income: { key: string; label: string; amount: string }[]; costs: { key: string; label: string; amount: string }[];
  courses: ItRevenueCourse[]; unlinked: Money; placement: null; not_counted: { currency: string; amount: string; count: number }[];
};
export type ItRevenuePayment = {
  id: string; entry_date: string; kind: string; amount: string; currency: string; installment_no: number | null; receipt_no: string | null;
  enrollment_code: string | null; course: string | null; batch: string | null;
};
export type ItRevenuePaymentPage = { items: ItRevenuePayment[]; total: number; limit: number; offset: number };

/** Whose payments are listed: one course, one batch, or the payments not linked to a course (IR11). */
export type Scope = { program: string } | { batch: string } | { unlinked: true };
export type Range = { month: string; period: Period };
export type ItRevenueQuery = Range & { scope: Scope | null; page: number };

const MONTH = /^\d{4}-(0[1-9]|1[0-2])$/;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
type Search = Record<string, string | string[] | undefined>;

function one(search: Search, key: string, pattern: RegExp): string {
  const value = search[key];
  return typeof value === "string" && pattern.test(value) ? value : "";
}

/** The page's address: a malformed or repeated value is dropped, so the API answers with its defaults; two scopes mean none. */
export function itRevenueQuery(search: Search): ItRevenueQuery {
  const program = one(search, "program", UUID);
  const batch = one(search, "batch", UUID);
  const unlinked = search.unlinked === "1";
  const scopes: Scope[] = [...(program ? [{ program }] : []), ...(batch ? [{ batch }] : []), ...(unlinked ? [{ unlinked: true as const }] : [])];
  const page = Number(one(search, "page", /^[1-9]\d{0,5}$/) || 1);
  return { month: one(search, "month", MONTH), period: search.period === "year" ? "year" : "month", scope: scopes.length === 1 ? scopes[0] : null, page };
}

function rangeParams({ month, period }: Range): URLSearchParams {
  return new URLSearchParams({ ...(month ? { month } : {}), period });
}

export function itRevenueUrl(range: Range): string {
  return range.month || range.period === "year" ? `${IT_REVENUE_API}?${rangeParams(range)}` : IT_REVENUE_API;
}

export function itRevenuePaymentsUrl(query: ItRevenueQuery): string {
  const params = rangeParams(query);
  const scope = query.scope!;
  if ("program" in scope) params.set("program_id", scope.program);
  else if ("batch" in scope) params.set("batch_id", scope.batch);
  else params.set("unlinked", "true");
  params.set("limit", String(PAGE_SIZE));
  params.set("offset", String((query.page - 1) * PAGE_SIZE));
  return `${IT_REVENUE_API}/payments?${params}`;
}

/** This page with `scope`'s payments listed (page `page`), scrolled to them. */
export function itRevenueHref(range: Range, scope: Scope, page = 1): string {
  const params = rangeParams(range);
  if ("program" in scope) params.set("program", scope.program);
  else if ("batch" in scope) params.set("batch", scope.batch);
  else params.set("unlinked", "1");
  if (page > 1) params.set("page", String(page));
  return `${IT_REVENUE_HOME}?${params}#payments`;
}
