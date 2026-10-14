import { isCalendarDate } from "@/lib/formatDate";

// mgmt-015 (spec CP1-CP15): EVID-017 §24's partner capital accounts. Partner-only (M13): the API refuses everyone else, so nothing here
// filters for security. Money is INR as decimal strings; every figure is the API's, never recomputed here.
export const CAPITAL_HOME = "/management/capital";
export const CAPITAL_API = "/api/v1/management/capital";
const MAX_OFFSET = 10_000; // the API's cap

export type CapitalPeriod = "month" | "quarter" | "year";
export type CapitalPerson = { id: string; full_name: string };
export type CapitalFigures = {
  invested: string; additional: string; withdrawals: string; balance: string; returns: string; share_pct: string | null;
  commitment: string | null; outstanding: string | null; profit_share: string | null;
}; // prettier-ignore
export type CapitalAccount = CapitalFigures & { partner: CapitalPerson & { active: boolean } };
export type CapitalEntry = {
  id: string; partner: CapitalPerson; entry_date: string; kind: string; amount: string; note: string | null; created_by: CapitalPerson; created_at: string;
}; // prettier-ignore
export type CapitalShare = {
  id: string; partner: CapitalPerson; effective_from: string; share_pct: string; commitment: string | null; in_force: boolean; updated_by: CapitalPerson; updated_at: string;
}; // prettier-ignore
export type Capital = {
  as_of: string; month: string; period: CapitalPeriod; label: string; net_profit: string; accounts: CapitalAccount[]; totals: CapitalFigures;
  partners: CapitalPerson[]; entries: { items: CapitalEntry[]; total: number; limit: number; offset: number }; shares: CapitalShare[];
}; // prettier-ignore
export type CapitalQuery = { month: string; period: CapitalPeriod; offset: number };

export const CAPITAL_KIND_LABEL: Record<string, string> = {
  initial: "Initial capital", additional: "Additional investment", withdrawal: "Withdrawal", profit_distribution: "Profit distribution",
};
// §24's eight figures in the source's order; the commitment is shown beside the outstanding contribution it explains.
export const CAPITAL_FIGURES: { key: keyof CapitalFigures; label: string }[] = [
  { key: "invested", label: "Capital invested" }, { key: "additional", label: "Additional investment" }, { key: "withdrawals", label: "Withdrawals" },
  { key: "share_pct", label: "Share %" }, { key: "profit_share", label: "Profit share (indicative)" }, { key: "returns", label: "Returns (profit distributions)" },
  { key: "commitment", label: "Committed capital" }, { key: "outstanding", label: "Outstanding contribution" }, { key: "balance", label: "Capital balance" },
]; // prettier-ignore

const MONTH = /^\d{4}-(0[1-9]|1[0-2])$/;
const PERIODS: readonly CapitalPeriod[] = ["month", "quarter", "year"];

/** The page's address: a malformed or repeated value is dropped, so the API answers with its defaults (financial year to date). */
export function capitalQuery(search: Record<string, string | string[] | undefined>): CapitalQuery {
  const { month, period, offset } = search;
  const start = typeof offset === "string" ? Number.parseInt(offset, 10) : 0;
  return {
    month: typeof month === "string" && MONTH.test(month) ? month : "",
    period: PERIODS.find((p) => p === period) ?? "year",
    offset: start > 0 ? Math.min(start, MAX_OFFSET) : 0,
  };
}

function params({ month, period, offset }: CapitalQuery): string {
  const query = new URLSearchParams();
  if (month) query.set("month", month);
  if (period !== "year") query.set("period", period);
  if (offset > 0) query.set("offset", String(offset));
  return query.toString();
}

export const capitalUrl = (q: CapitalQuery) => (params(q) ? `${CAPITAL_API}?${params(q)}` : CAPITAL_API);
export const capitalHref = (q: CapitalQuery) => (params(q) ? `${CAPITAL_HOME}?${params(q)}` : CAPITAL_HOME);

/** AC1 (CP7): warn, never block, whenever the shares in force do not total exactly 100%. */
export const shareTotalWarning = (total: string) => (Number(total) === 100 ? null : `Shares in force total ${total}%, not 100%.`);
export const pctText = (pct: string | null) => (pct === null ? "—" : `${pct}%`);
export const isNegative = (amount: string | null) => amount !== null && Number(amount) < 0;

const MONEY = /^\d+(\.\d{1,2})?$/;
const SHARE = /^\d{1,3}(\.\d{1,2})?$/;
type Problem<K> = { field: K; message: string } | null;

// The capital entry form (CP3): every value as typed. The API re-checks all of it; these checks only spare a round trip and name the field.
export type EntryForm = { partner_id: string; entry_date: string; kind: string; amount: string; note: string };
export const EMPTY_ENTRY_FORM: EntryForm = { partner_id: "", entry_date: "", kind: "", amount: "", note: "" };

export function entryProblem(form: EntryForm, today: string): Problem<keyof EntryForm> {
  const amount = form.amount.trim();
  if (!form.partner_id) return { field: "partner_id", message: "Choose the partner." };
  if (!isCalendarDate(form.entry_date)) return { field: "entry_date", message: "Enter the entry date." };
  if (form.entry_date > today) return { field: "entry_date", message: "The entry date can't be in the future." };
  if (form.entry_date < "2000-01-01") return { field: "entry_date", message: "The entry date can't be before 1 January 2000." };
  if (!form.kind) return { field: "kind", message: "Choose the kind of entry." };
  if (!MONEY.test(amount)) return { field: "amount", message: "Enter the amount in rupees with up to 2 decimals." };
  if (!(Number(amount) > 0)) return { field: "amount", message: "The amount must be more than ₹0." };
  return null;
}

export function entryBody(form: EntryForm) {
  return { partner_id: form.partner_id, entry_date: form.entry_date, kind: form.kind, amount: form.amount.trim(), note: form.note.trim() || null };
}

/** CP11: a withdrawal over the partner's capital balance needs a second click; the API accepts it either way. */
export function overdraw(form: EntryForm, accounts: CapitalAccount[]): { name: string; balance: string } | null {
  const account = accounts.find((a) => a.partner.id === form.partner_id);
  if (form.kind !== "withdrawal" || !account || !(Number(form.amount) > Number(account.balance))) return null;
  return { name: account.partner.full_name, balance: account.balance };
}

// The share % form (CP5/CP6): one row per active partner; a partner left blank keeps their share.
export type SharesForm = { effective_from: string; rows: Record<string, { share_pct: string; commitment: string }> };

export function sharesProblem(form: SharesForm): Problem<"effective_from" | "rows"> {
  const rows = Object.values(form.rows).map((r) => ({ pct: r.share_pct.trim(), commitment: r.commitment.trim() }));
  if (!MONTH.test(form.effective_from)) return { field: "effective_from", message: "Choose the month the shares apply from." };
  if (rows.some((r) => !r.pct && r.commitment)) return { field: "rows", message: "Enter a share % for every partner with a commitment." };
  if (!rows.some((r) => r.pct)) return { field: "rows", message: "Enter at least one partner's share %." };
  if (rows.some((r) => r.pct && (!SHARE.test(r.pct) || Number(r.pct) > 100))) return { field: "rows", message: "Enter each share as a percentage from 0 to 100 with up to 2 decimals." };
  if (rows.some((r) => r.commitment && !MONEY.test(r.commitment))) return { field: "rows", message: "Enter each commitment in rupees with up to 2 decimals." };
  return null;
}

export function sharesBody(form: SharesForm) {
  const shares = Object.entries(form.rows)
    .filter(([, r]) => r.share_pct.trim())
    .map(([partner_id, r]) => ({ partner_id, share_pct: r.share_pct.trim(), commitment: r.commitment.trim() || null }));
  return { effective_from: form.effective_from, shares };
}
