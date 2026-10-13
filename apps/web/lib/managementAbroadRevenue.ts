import { LEDGER_HOME } from "@/lib/managementLedger";

// mgmt-006 (spec MR1-MR12): GET /management/revenue/abroad -- Abroad Education revenue by kind and by country / university / intake /
// agency (each with an Unattributed figure), the Abroad expenses and the gross contribution, for a month and its Indian financial year
// to date, in rupees. The API decides access (finance tier), whether university commission is in the figures (partners only) and every
// figure. The month in the address is read with mgmt-010's `expenseMonth`.
export const ABROAD_REVENUE_HOME = "/management/revenue/abroad";
export const ABROAD_REVENUE_API = "/api/v1/management/revenue/abroad";

export type MonthYear = { month: string; year: string };
export type AbroadRevenueRow = MonthYear & { label: string };
export type AbroadRevenue = {
  month: string; year_start: string; year_label: string; commission_visible: boolean;
  kinds: (AbroadRevenueRow & { key: string })[]; revenue: MonthYear; agent_generated: MonthYear;
  breakdowns: { key: string; label: string; rows: AbroadRevenueRow[]; unattributed: MonthYear }[];
  expenses: AbroadRevenueRow[]; expense_total: MonthYear; shared_expenses: MonthYear; contribution: MonthYear;
  not_counted: { currency: string; kind: string; amount: string; count: number }[];
}; // prettier-ignore

export function abroadRevenueUrl(month: string): string {
  return month ? `${ABROAD_REVENUE_API}?month=${month}` : ABROAD_REVENUE_API;
}

/** The month's Abroad lines, manual and automatic, in the ledger list. */
export function abroadLedgerHref(month: string): string {
  return `${LEDGER_HOME}?${new URLSearchParams({ month, vertical: "abroad", include: "auto" })}`;
}

/** A row's share of the annual revenue for its bar, one decimal place, held to 0-100 (0 when revenue is not positive). */
export function revenueShare(amount: string, total: string): number {
  const whole = Number(total);
  if (!(whole > 0)) return 0;
  return Math.round(Math.min(Math.max(Number(amount) / whole, 0), 1) * 1000) / 10;
}
