import { LEDGER_HOME } from "@/lib/managementLedger";

// mgmt-010 (spec ME1-ME10): GET /management/expenses -- the eight §8 heads for a month and its Indian financial year to date, in
// rupees (approved manual + INR automatic expense lines). The API decides access (finance tier) and every figure.
export const EXPENSES_HOME = "/management/expenses";
export const EXPENSES_API = "/api/v1/management/expenses";

export type ExpenseHead = { key: string; label: string; month: string; year: string; share: number };
export type ExpenseCategoryRow = { label: string; group: string; month: string; year: string };
export type ExpenseDashboard = {
  month: string; year_start: string; year_label: string; groups: ExpenseHead[]; categories: ExpenseCategoryRow[];
  months: { month: string; total: string }[]; totals: { month: string; year: string }; not_counted: { currency: string; amount: string; count: number }[];
};

const MONTH = /^\d{4}-(0[1-9]|1[0-2])$/;

/** The month in the page's address; a malformed or repeated value is dropped, so the API answers with its default month. */
export function expenseMonth(search: Record<string, string | string[] | undefined>): string {
  const value = search.month;
  return typeof value === "string" && MONTH.test(value) ? value : "";
}

export function expensesUrl(month: string): string {
  return month ? `${EXPENSES_API}?month=${month}` : EXPENSES_API;
}

/** The month's expense lines, manual and automatic, in the ledger list. */
export function expensesLedgerHref(month: string): string {
  return `${LEDGER_HOME}?${new URLSearchParams({ month, kind: "expense", include: "auto" })}`;
}

/** "2026-04" -> "April 2026". */
export function formatMonth(month: string): string {
  const [year, number] = month.split("-").map(Number);
  return new Date(Date.UTC(year, number - 1, 1)).toLocaleDateString("en-IN", { month: "long", year: "numeric", timeZone: "UTC" });
}

/** The IST month of a moment ("YYYY-MM"), the latest month the month picker offers. */
export function istMonth(now: Date = new Date()): string {
  return now.toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" }).slice(0, 7);
}
