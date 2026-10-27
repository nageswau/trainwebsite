import { type DateRange, reportQuery } from "./agentCommissionReport";
import { isCalendarDate } from "./formatDate";
import type { CurrencyTotal } from "./types";

// AGN-018 (DEC-SCOPE-062): the agency dashboard endpoint.
export const DASHBOARD_URL = "/api/v1/workflows/overseas/agent/crm/dashboard";
export const DASHBOARD_PAGE = "/overseas/agent/dashboard";

// nehn-038 (DEC-SCOPE-306): the referral-date range lives in the page address (?from=&to=, the AGN-014/019 keys), so refresh, Back
// and a shared link keep it. Only well-formed YYYY-MM-DD values are read; the first of a repeated key wins; anything else is no bound.
export function dashboardRange(query?: Record<string, string | string[] | undefined>): DateRange {
  const pick = (key: "from" | "to") => {
    const raw = query?.[key];
    const value = (Array.isArray(raw) ? raw[0] : raw) ?? "";
    return isCalendarDate(value) ? value : "";
  };
  return { from: pick("from"), to: pick("to") };
}

export function dashboardUrl(range: DateRange): string {
  return `${DASHBOARD_URL}${reportQuery(range.from, range.to)}`;
}

// The portal's Revenue format (AGN-014 QA14-01): per currency, thousands separators like Python's `:,.0f`, a no-break space after
// the separator so a narrow card wraps between currencies; "INR 0" when there is nothing.
export function formatMoney(totals: CurrencyTotal[]): string {
  return totals.map((t) => `${t.currency} ${Math.round(t.amount).toLocaleString("en-US")}`).join(" · ") || "INR 0";
}
