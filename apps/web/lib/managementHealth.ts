import { formatInr } from "@/lib/managementLedger";

// mgmt-030 (EVID-017 §30, spec BH1-BH14): GET /management/health -- the overall business health score and its factors for one month
// against the month before. The API decides access (operational tier), which factors a caller gets (super_admin: the operational six)
// and every score; this file only writes the figures as words.
export const HEALTH_HOME = "/management/health";
const HEALTH_API = "/api/v1/management/health";

export type HealthRag = "green" | "amber" | "red";
export type HealthFactor = {
  key: string; label: string; tier: "finance" | "operational"; weight: number; unit: "inr" | "count" | "percent";
  current: string | null; previous: string | null; change: number | null; score: number | null; rag: HealthRag | null;
  points: number | null; note: string | null;
}; // prettier-ignore
export type BusinessHealth = {
  month: string; previous_month: string; partial: boolean; scope: "business" | "operational"; score: number | null; rag: HealthRag | null;
  factors: HealthFactor[];
}; // prettier-ignore
export type HealthQuery = { month: string };

export const RAG_LABEL: Record<HealthRag, string> = { green: "Green", amber: "Amber", red: "Red" };
const MONTH = /^\d{4}-(0[1-9]|1[0-2])$/;

/** The page's address: a malformed or repeated month is dropped, so the API answers with the last complete month. */
export function healthQuery(search: Record<string, string | string[] | undefined>): HealthQuery {
  const { month } = search;
  return { month: typeof month === "string" && MONTH.test(month) ? month : "" };
}

export function healthUrl({ month }: HealthQuery): string {
  return month ? `${HEALTH_API}?${new URLSearchParams({ month })}` : HEALTH_API;
}

const signed = (value: number) => `${value < 0 ? "−" : "+"}${Math.abs(value).toFixed(1)}`;

function amount(factor: HealthFactor, value: string): string {
  return factor.unit === "inr" ? formatInr(value) : String(Number(value));
}

/** BH11: one factor's measure in words; a factor that is not available gives the API's reason. */
export function measureText(factor: HealthFactor): string {
  if (factor.score === null || factor.current === null) return factor.note ?? "Not available";
  if (factor.key === "profit") return `Margin ${factor.current}%${factor.previous !== null ? ` (${factor.previous}% the month before)` : ""}`;
  if (factor.key === "marketing_roi") return `ROI ${factor.current}%`;
  const now = `${amount(factor, factor.current)}${factor.key === "productivity" ? " per head" : ""}`;
  const against = `${now} against ${amount(factor, factor.previous ?? "0")}`;
  if (factor.key === "expenses") return `${against}: grew ${Math.abs(factor.change ?? 0).toFixed(1)} points ${(factor.change ?? 0) > 0 ? "faster" : "slower"} than revenue`;
  return `${against} (${factor.change === null ? "new this month" : `${signed(factor.change)}%`})`;
}
