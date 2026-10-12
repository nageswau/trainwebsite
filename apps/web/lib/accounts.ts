// mgmt-013 (spec AD1-AD14): the accounts dashboard's types, links and the balances form's request body. The API decides access (finance
// tier only) and every rule; this module only shapes what the page sends and shows.
import { rupees } from "@/lib/investments";

export const ACCOUNTS_HOME = "/management/accounts";
export const ACCOUNTS_API = "/api/v1/management/accounts";

export type AccountsHead = { key: string; label: string; amount: string; parts: { label: string; amount: string }[] };
export type AccountsSection = { heads: AccountsHead[]; total: string };
export type NotCounted = { currency: string; kind: string; amount: string; count: number };
export const BALANCE_FIELDS = ["cash_bank", "payables", "tax_liabilities"] as const;
export type BalanceField = (typeof BALANCE_FIELDS)[number];
export type AccountsMonth = {
  month: string; current_month: string; as_of: string; income: AccountsSection; expenses: AccountsSection; profit: string; not_counted: NotCounted[];
  receivables: { total: string; overdue: string; fees: string; recruitment: string; university: string; not_counted: NotCounted[] };
  pending_invoices: { count: number; amount: string };
  balances: Record<BalanceField, string | null> & { updated_at: string | null; updated_by: { id: string; full_name: string } | null };
};
export type BalancesDraft = Record<BalanceField, string>;

export const BALANCE_LABEL: Record<BalanceField, string> = { cash_bank: "Cash/bank", payables: "Payables", tax_liabilities: "Tax liabilities" };

export const accountsHref = (month: string) => `${ACCOUNTS_HOME}?month=${month}`;
export const accountsUrl = (month: string) => (month ? `${ACCOUNTS_API}?month=${month}` : ACCOUNTS_API);
export const balancesUrl = (month: string) => `${ACCOUNTS_API}/balances?month=${month}`;

/** Rupees with the sign in front (an overdraft reads "-₹2,500.50"); a figure never entered reads "Not entered" (AD9), never ₹0. */
export function amountText(amount: string | null): string {
  if (amount === null) return "Not entered";
  return amount.startsWith("-") ? `-${rupees(amount.slice(1))}` : rupees(amount);
}

/** AD8: a blank field is null (not entered); anything typed is sent as written, so the API's 422 names the field. */
export function balancesBody(draft: BalancesDraft): Record<BalanceField, string | null> {
  return Object.fromEntries(BALANCE_FIELDS.map((f) => [f, draft[f].trim() || null])) as Record<BalanceField, string | null>;
}

/** The API's 422 items placed on their fields (`loc: ["body", field]`). */
export function fieldErrors(detail: unknown): Partial<Record<BalanceField, string>> {
  if (!Array.isArray(detail)) return {};
  const out: Partial<Record<BalanceField, string>> = {};
  for (const item of detail as { loc?: unknown[]; msg?: string }[]) {
    const [where, field] = item.loc ?? [];
    if (where === "body" && BALANCE_FIELDS.includes(field as BalanceField)) out[field as BalanceField] = String(item.msg);
  }
  return out;
}
