import type { CurrencyTotal } from "./types";

// AGN-018 (DEC-SCOPE-062): the agency dashboard endpoint.
export const DASHBOARD_URL = "/api/v1/workflows/overseas/agent/crm/dashboard";

// The portal's Revenue format (AGN-014 QA14-01): per currency, thousands separators like Python's `:,.0f`, a no-break space after
// the separator so a narrow card wraps between currencies; "INR 0" when there is nothing.
export function formatMoney(totals: CurrencyTotal[]): string {
  return totals.map((t) => `${t.currency} ${Math.round(t.amount).toLocaleString("en-US")}`).join(" · ") || "INR 0";
}
