import { isCalendarDate } from "@/lib/formatDate";

// mgmt-014 (DEC-SCOPE-189 MI1-MI14): EVID-017 §23's investment register. Partner-only (M13): the API refuses everyone else, so nothing
// here filters for security. Money is INR, sent and received as decimal strings; ROI is the API's (MI7), never recomputed here.
export const MANAGEMENT_INVESTMENTS = "/management/investments";
export const INVESTMENTS_PAGE_SIZE = 25;
const MAX_OFFSET = 10_000; // the API's cap (browser QA-01: past it the page showed the API's 422 list as "[object Object]")

export const INVESTMENT_STATUS_LABEL: Record<string, string> = { planned: "Planned", active: "Active", completed: "Completed", cancelled: "Cancelled" };
export const INVESTMENT_VERTICAL_LABEL: Record<string, string> = {
  abroad: "Abroad Education", it: "IT Training", recruitment: "Recruitment & Placement", school: "Schools", shared: "Company-wide", other: "Other",
};

export type InvestmentPerson = { id: string; full_name: string };
export type Investment = {
  id: string; code: string; invested_on: string; investor_kind: "partner" | "company"; investor: InvestmentPerson | null; amount: string;
  purpose: string; vertical: string; expected_return: string | null; actual_return: string | null; roi: string | null; status: string;
  notes: string | null; created_by: InvestmentPerson; updated_by: InvestmentPerson; created_at: string; updated_at: string;
};
export type InvestmentTotals = { count: number; invested: string; actual_return: string; roi: string | null };
export type InvestmentPage = { items: Investment[]; total: number; limit: number; offset: number; totals: InvestmentTotals; investors: InvestmentPerson[] };
export type InvestmentFilters = { date_from: string; date_to: string; vertical: string; status: string; offset: number };

/** "₹5,00,000.00"; a dash when there is no figure. */
export function rupees(amount: string | null): string {
  return amount === null ? "—" : `₹${Number(amount).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/** "260.00%", or a dash while the actual return is not known (backlog edge case). */
export const roiText = (roi: string | null) => (roi === null ? "—" : `${roi}%`);

/** The register's filters from the page's search params; anything unknown, malformed or repeated is dropped. */
export function investmentFilters(search: Record<string, string | string[] | undefined>): InvestmentFilters {
  const one = (key: string) => (typeof search[key] === "string" ? (search[key] as string) : "");
  const day = (key: string) => (isCalendarDate(one(key)) ? one(key) : "");
  const known = (key: string, labels: Record<string, string>) => (one(key) in labels ? one(key) : "");
  const offset = Number.parseInt(one("offset"), 10);
  return {
    date_from: day("date_from"), date_to: day("date_to"), vertical: known("vertical", INVESTMENT_VERTICAL_LABEL),
    status: known("status", INVESTMENT_STATUS_LABEL), offset: offset > 0 ? Math.min(offset, MAX_OFFSET) : 0,
  };
}

function filterQuery(filters: InvestmentFilters): URLSearchParams {
  const query = new URLSearchParams();
  for (const key of ["date_from", "date_to", "vertical", "status"] as const) if (filters[key]) query.set(key, filters[key]);
  if (filters.offset > 0) query.set("offset", String(filters.offset));
  return query;
}

export function investmentsHref(filters: InvestmentFilters): string {
  const query = filterQuery(filters).toString();
  return query ? `${MANAGEMENT_INVESTMENTS}?${query}` : MANAGEMENT_INVESTMENTS;
}

export function investmentsUrl(filters: InvestmentFilters): string {
  const query = filterQuery(filters);
  query.set("limit", String(INVESTMENTS_PAGE_SIZE));
  return `/api/v1${MANAGEMENT_INVESTMENTS}?${query}`;
}

export const investmentUrl = (id?: string) => `/api/v1${MANAGEMENT_INVESTMENTS}${id ? `/${id}` : ""}`;

// The add/edit form: every value as typed. The API re-checks all of it; these checks only spare a round trip and name the field.
export type InvestmentForm = {
  invested_on: string; investor_kind: "partner" | "company"; investor_user_id: string; amount: string; purpose: string; vertical: string;
  expected_return: string; actual_return: string; status: string; notes: string;
};
export const EMPTY_INVESTMENT_FORM: InvestmentForm = {
  invested_on: "", investor_kind: "company", investor_user_id: "", amount: "", purpose: "", vertical: "", expected_return: "", actual_return: "",
  status: "active", notes: "",
};

export function investmentFormFrom(i: Investment): InvestmentForm {
  return {
    invested_on: i.invested_on, investor_kind: i.investor_kind, investor_user_id: i.investor?.id ?? "", amount: i.amount, purpose: i.purpose,
    vertical: i.vertical, expected_return: i.expected_return ?? "", actual_return: i.actual_return ?? "", status: i.status, notes: i.notes ?? "",
  };
}

const MONEY = /^\d+(\.\d{1,2})?$/;

export function investmentProblem(form: InvestmentForm): { field: keyof InvestmentForm; message: string } | null {
  const amount = form.amount.trim();
  if (!isCalendarDate(form.invested_on)) return { field: "invested_on", message: "Enter the investment date." };
  if (form.investor_kind === "partner" && !form.investor_user_id) return { field: "investor_user_id", message: "Choose the partner who invested." };
  if (!MONEY.test(amount)) return { field: "amount", message: "Enter the amount in rupees with up to 2 decimals." };
  if (!(Number(amount) > 0)) return { field: "amount", message: "The amount must be more than ₹0." };
  if (form.purpose.trim().length < 2) return { field: "purpose", message: "Enter the purpose (at least 2 characters)." };
  if (!form.vertical) return { field: "vertical", message: "Choose the business vertical." };
  for (const [field, label] of [["expected_return", "expected return"], ["actual_return", "actual return"]] as const) {
    if (form[field].trim() && !MONEY.test(form[field].trim())) return { field, message: `Enter the ${label} in rupees with up to 2 decimals.` };
  }
  return null;
}

export function investmentBody(form: InvestmentForm) {
  const blank = (value: string) => value.trim() || null;
  return {
    invested_on: form.invested_on, investor_kind: form.investor_kind, investor_user_id: form.investor_kind === "partner" ? form.investor_user_id : null,
    amount: form.amount.trim(), purpose: form.purpose.trim(), vertical: form.vertical, expected_return: blank(form.expected_return),
    actual_return: blank(form.actual_return), status: form.status, notes: blank(form.notes),
  };
}
