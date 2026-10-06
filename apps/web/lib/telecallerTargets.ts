// tel-022 (DEC-SCOPE-078): daily + monthly targets -- types, KPI labels, endpoints and the date helpers behind the manager's Targets
// page and the telecaller's "My targets" card. The API decides every rule (G2 dates, T23 scope); the browser only mirrors the dates.
import type { LookupPage } from "@/lib/lookups";
import type { TelecallerTeam, TelecallerTeamRow } from "@/lib/telecaller";

export type TargetPeriod = "daily" | "monthly";
export type TargetSource = "user" | "team" | null;
export type TargetValue = { kpi: string; value: number | null; source: TargetSource };
export type Person = { id: string; full_name: string };
export type TargetsInEffect = { date: string; month: string; team: TelecallerTeam; user: Person | null; daily: TargetValue[]; monthly: TargetValue[] };
export type TargetRow = {
  id: string; scope: "team" | "user"; team: TelecallerTeam | null; user: Person | null; period: TargetPeriod; kpi: string; value: number | null;
  effective_from: string; set_by: Person; updated_at: string;
};

export const TARGETS_URL = "/api/v1/telecaller/targets";
export const EFFECTIVE_URL = "/api/v1/telecaller/targets/effective";
export const TEAM_URL = "/api/v1/telecaller/manager/team";
export const HISTORY_PAGE_SIZE = 50;
export const TARGET_MAX = 100000;

// EVID-019 §15 order (Appendix B K1-K6).
export const KPIS: { key: string; label: string }[] = [
  { key: "calls", label: "Calls" },
  { key: "connected_calls", label: "Connected calls" },
  { key: "qualified_leads", label: "Qualified leads" },
  { key: "follow_ups", label: "Follow-ups" },
  { key: "counselling_appointments", label: "Counselling appointments" },
  { key: "conversions", label: "Conversions" },
];
export const KPI_LABEL: Record<string, string> = Object.fromEntries(KPIS.map((k) => [k.key, k.label]));
export const PERIOD_LABEL: Record<TargetPeriod, string> = { daily: "Daily", monthly: "Monthly" };
export const SOURCE_LABEL: Record<"user" | "team" | "none", string> = { user: "Override", team: "Team default", none: "Not set" };
export const sourceLabel = (source: TargetSource) => SOURCE_LABEL[source ?? "none"];
export const targetText = (value: number | null) => (value === null ? "Not set" : String(value));

/** Today as an IST calendar date (YYYY-MM-DD) -- the API's day (G1). */
export const istToday = (now: Date = new Date()) => new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(now);

/** Calendar arithmetic on YYYY-MM-DD strings, in UTC so no viewer time zone can shift the day. */
function shift(iso: string, days = 0, months = 0): string {
  const d = new Date(`${iso}T00:00:00Z`);
  if (months) d.setUTCDate(1);
  d.setUTCMonth(d.getUTCMonth() + months, d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

/** G2: daily targets start tomorrow or later. */
export const earliestDaily = (today: string) => shift(today, 1);

/** G2: monthly targets start on the 1st of next month or later; the picker offers the next twelve. */
export function monthOptions(today: string, count = 12): { value: string; label: string }[] {
  const first = `${today.slice(0, 8)}01`;
  return Array.from({ length: count }, (_, i) => {
    const value = shift(first, 0, i + 1);
    const label = new Intl.DateTimeFormat("en-GB", { month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(`${value}T00:00:00Z`));
    return { value, label };
  });
}

/** The telecaller picker searches the manager's own team (T23: direct reports; super_admin: all). Inactive telecallers cannot be given
 *  targets, so they are left out. */
export async function telecallerSearch(q: string, signal: AbortSignal): Promise<LookupPage> {
  const query = new URLSearchParams({ limit: "20" });
  if (q) query.set("q", q);
  const response = await fetch(`${TEAM_URL}?${query}`, { signal });
  if (!response.ok) throw new Error(`Telecaller search failed (${response.status})`);
  const page = (await response.json()) as { items: TelecallerTeamRow[]; total: number };
  const active = page.items.filter((t) => t.active);
  return { items: active.map((t) => ({ id: t.id, label: t.full_name, detail: `${t.team === "it" ? "IT" : "Overseas"} · ${t.employee_id}` })), truncated: page.total > page.items.length };
}
