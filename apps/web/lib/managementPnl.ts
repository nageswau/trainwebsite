// mgmt-009 (spec PL1-PL12): GET /management/pnl -- revenue, expenses, contribution and margin per business vertical, the unallocated
// shared costs and the total, for a month, its financial-year quarter or its financial year to date. The API decides access (finance
// tier) and every figure; nothing here computes money.
export const PNL_HOME = "/management/pnl";
export const PNL_API = "/api/v1/management/pnl";

export type Period = "month" | "quarter" | "year";
export type PnlFigures = { revenue: string; expenses: string; contribution: string; margin: number | null };
export type PnlRow = PnlFigures & { key: "abroad" | "it" | "recruitment" | "school" | "other" | "shared"; label: string };
export type Pnl = {
  month: string; period: Period; start: string; end: string; label: string; commission_visible: boolean;
  rows: PnlRow[]; total: PnlFigures; not_counted: { currency: string; kind: string; amount: string; count: number }[];
}; // prettier-ignore
export type PnlQuery = { month: string; period: Period };

const MONTH = /^\d{4}-(0[1-9]|1[0-2])$/;
const PERIODS: readonly Period[] = ["month", "quarter", "year"];

/** The page's address: a malformed or repeated value is dropped, so the API answers with its defaults. */
export function pnlQuery(search: Record<string, string | string[] | undefined>): PnlQuery {
  const { month, period } = search;
  return {
    month: typeof month === "string" && MONTH.test(month) ? month : "",
    period: PERIODS.find((p) => p === period) ?? "month",
  };
}

export function pnlUrl({ month, period }: PnlQuery): string {
  if (!month && period === "month") return PNL_API;
  return `${PNL_API}?${new URLSearchParams({ ...(month ? { month } : {}), period })}`;
}

export function formatMargin(margin: number | null): string {
  return margin === null ? "—" : `${margin.toFixed(1)}%`;
}

/** PL9: a negative contribution is shown in red. */
export function isLoss(amount: string): boolean {
  return Number(amount) < 0;
}
