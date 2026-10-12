// mgmt-004 (spec ML1-ML16): the management ledger's types, filters, links and labels. The API decides access (finance tier only) and
// every rule; this module only shapes what the pages send and show.
export const LEDGER_HOME = "/management/ledger";
export const LEDGER_API = "/api/v1/management/ledger";
export const LEDGER_PAGE_SIZE = 25;

export type LedgerKind = "income" | "expense";
export type LedgerStatus = "draft" | "submitted" | "approved" | "rejected";
export type LedgerPerson = { id: string; full_name: string };
export type LedgerNamed = { id: string; name: string };
export type LedgerCategory = { id: string; kind: LedgerKind; nature: "fixed" | "variable" | null; name: string; active: boolean };
export type LedgerEvent = { id: string; at: string; actor: LedgerPerson | null; event: string; from_status: string | null; to_status: string | null; fields: string[]; reason: string | null };
export type LedgerEntry = {
  source?: "manual"; id: string; entry_date: string; kind: LedgerKind; category: { id: string; name: string; active: boolean }; amount: string; description: string;
  vertical: string; channel: string | null; program: LedgerNamed | null; batch: LedgerNamed | null; status: LedgerStatus; reversal_of_id: string | null;
  reversed_by_id: string | null; receipt: { name: string | null; content_type: string } | null; created_by: LedgerPerson | null;
  updated_by: LedgerPerson | null; decided_by: LedgerPerson | null; submitted_at: string | null; decided_at: string | null;
  rejection_reason: string | null; created_at: string; updated_at: string; can: { edit: boolean; submit: boolean; decide: boolean; reverse: boolean };
};
export type LedgerEntryDetail = LedgerEntry & { events: LedgerEvent[] };
// mgmt-005 (MA1-MA11): a read-only line computed from another module's money row (`include=auto`); `id` is that row's id.
export type LedgerSource = "payment" | "agent_commission" | "trip_expense" | "recruiter_payment" | "university_commission";
export type LedgerAutoLine = {
  source: LedgerSource; id: string; entry_date: string; kind: LedgerKind; vertical: string; category_label: string; amount: string; currency: string;
  description: string; counted: boolean;
};
export type LedgerNotCounted = { currency: string; kind: LedgerKind; amount: string; count: number };
export type LedgerTotals = { income: string; expense: string; net: string; not_counted?: LedgerNotCounted[] };
export type LedgerPage = { items: (LedgerEntry | LedgerAutoLine)[]; total: number; limit: number; offset: number; totals: LedgerTotals };

export function isAutoLine(item: LedgerEntry | LedgerAutoLine): item is LedgerAutoLine {
  return item.source !== undefined && item.source !== "manual";
}
export type LedgerChoice = { value: string; label: string };
export type LedgerOptions = { categories: LedgerCategory[]; channels: LedgerChoice[]; verticals: LedgerChoice[]; programs: (LedgerNamed & { batches: LedgerNamed[] })[] };
export type LedgerFilters = { month: string; kind: string; category: string; vertical: string; status: string; include: string; offset: number };

export const KIND_LABEL: Record<LedgerKind, string> = { income: "Income", expense: "Expense" };
export const STATUS_LABEL: Record<LedgerStatus, string> = { draft: "Draft", submitted: "Awaiting approval", approved: "Approved", rejected: "Rejected" };
export const VERTICAL_LABEL: Record<string, string> = {
  abroad: "Abroad Education", it: "IT Training", recruitment: "Recruitment", school: "School projects", other: "Other", shared: "Shared (company-wide)",
};
export const EVENT_LABEL: Record<string, string> = {
  created: "Created", updated: "Changed", submitted: "Submitted for approval", approved: "Approved", rejected: "Rejected", reversed: "Reversal requested", receipt: "Receipt attached",
};

export const SOURCE_LABEL: Record<LedgerSource, string> = {
  payment: "Student payment", agent_commission: "Agent commission", trip_expense: "BDM trip expense", recruiter_payment: "Recruiter payment",
  university_commission: "University commission",
};

const FILTER_KEYS = ["month", "kind", "category", "vertical", "status", "include"] as const;
const SHAPES: Record<(typeof FILTER_KEYS)[number], RegExp> = {
  month: /^\d{4}-(0[1-9]|1[0-2])$/,
  kind: /^(income|expense)$/,
  category: /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i,
  vertical: /^(abroad|it|recruitment|school|other|shared)$/,
  status: /^(draft|submitted|approved|rejected)$/,
  include: /^auto$/,
};

/** The filters from the page's search params. A malformed or repeated value only comes from a hand-edited address and is dropped, so
 * the API never answers the page with a 422. */
export function ledgerFilters(search: Record<string, string | string[] | undefined>): LedgerFilters {
  const one = (key: string) => (typeof search[key] === "string" ? (search[key] as string) : "");
  const kept = Object.fromEntries(FILTER_KEYS.map((key) => [key, SHAPES[key].test(one(key)) ? one(key) : ""])) as Omit<LedgerFilters, "offset">;
  const offset = Number.parseInt(one("offset"), 10);
  return { ...kept, offset: offset > 0 && offset <= 10_000 ? offset : 0 };
}

function query(filters: LedgerFilters): URLSearchParams {
  const params = new URLSearchParams();
  for (const key of FILTER_KEYS) if (filters[key]) params.set(key, filters[key]);
  if (filters.offset > 0) params.set("offset", String(filters.offset));
  return params;
}

export function ledgerHref(filters: LedgerFilters): string {
  const text = query(filters).toString();
  return text ? `${LEDGER_HOME}?${text}` : LEDGER_HOME;
}

export function ledgerUrl(filters: LedgerFilters): string {
  const params = query(filters);
  params.set("limit", String(LEDGER_PAGE_SIZE));
  return `${LEDGER_API}?${params}`;
}

const INR = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** "120000.00" -> "₹1,20,000.00" (the API sends amounts as decimal strings). */
export function formatInr(amount: string): string {
  return INR.format(Number(amount));
}

/** An automatic line in another currency (MA8) is shown in its own money: "300.00", "GBP" -> "£300.00". */
export function formatMoney(amount: string, currency: string): string {
  return currency === "INR" ? formatInr(amount) : new Intl.NumberFormat("en-IN", { style: "currency", currency, minimumFractionDigits: 2 }).format(Number(amount));
}

export function statusClass(status: LedgerStatus): string {
  return { draft: "badge", submitted: "status pending", approved: "status", rejected: "status error" }[status];
}
