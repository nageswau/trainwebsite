// upc-018 (DEC-SCOPE-153): the §17 student opportunity funnel and the §18 university performance ranking. The API counts every figure
// and decides who reads and which universities are in scope; a null count is a step the CRM does not track (U8: Leads, Counselling,
// Profiles eligible). Counts only -- no student is named and no commission is shown (upc-019 adds it for the commission roles).
export type StepKey = "leads" | "counselling" | "interested" | "eligible" | "applications" | "offers" | "deposits" | "visas" | "enrolled";
export type PerformanceStep = { key: StepKey; label: string; tracked: boolean };
export type PerformanceCounts = Record<StepKey, number | null>;
export type PerformanceUniversity = { id: string; university_code: string; name: string; country: string; stage: string; stage_label: string; partner: boolean };
export type Period = { from: string; to: string };
export type UniversityPerformance = Period & { steps: PerformanceStep[]; university: PerformanceUniversity; counts: PerformanceCounts };
export type PerformanceRow = { rank: number; university: PerformanceUniversity; counts: PerformanceCounts };
export type PerformancePage = Period & { steps: PerformanceStep[]; totals: PerformanceCounts; items: PerformanceRow[]; total: number; limit: number; offset: number };

export const PERFORMANCE_URL = "/api/v1/partnership/performance";
export const PERFORMANCE_PATH = "/partnership/performance";
export const OPPORTUNITIES_PATH = "/partnership/opportunities";
export const PERFORMANCE_READERS = new Set(["partnership_manager", "partnership_head", "overseas_admin", "super_admin"]);
export const PAGE_SIZE = 25;
const MAX_DAYS = 366;
const DAY = /^\d{4}-\d{2}-\d{2}$/;

export const periodQuery = (period: Period, extra: Record<string, string> = {}) => new URLSearchParams({ ...period, ...extra }).toString();
export const universityPerformanceUrl = (id: string, period: Period) => `/api/v1/partnership/universities/${id}/performance?${periodQuery(period)}`;
export const opportunitiesHref = (universityId: string) => `${OPPORTUNITIES_PATH}?${new URLSearchParams({ university_id: universityId })}`;

/** Today in IST (the API's day), as YYYY-MM-DD. */
export function istToday(now = Date.now()): string {
  return new Date(now + 330 * 60_000).toISOString().slice(0, 10);
}

const realDay = (value: string) => DAY.test(value) && new Date(`${value}T00:00:00Z`).toISOString().slice(0, 10) === value;
const days = (from: string, to: string) => (Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / 86_400_000 + 1;

/** PF1: the period in the URL, or this IST month to date. A bad value falls back with a note instead of an error page. */
export function chosenPeriod(from: string | undefined, to: string | undefined, today = istToday()): { period: Period; note: string | null } {
  const fallback = { from: `${today.slice(0, 8)}01`, to: today };
  if (!from && !to) return { period: fallback, note: null };
  const period = { from: from || fallback.from, to: to || fallback.to };
  if (!realDay(period.from) || !realDay(period.to)) return { period: fallback, note: "That isn't a valid date — showing this month." };
  if (period.from > period.to) return { period: fallback, note: "The period must start on or before its end — showing this month." };
  if (days(period.from, period.to) > MAX_DAYS) return { period: fallback, note: `A period can be at most ${MAX_DAYS} days — showing this month.` };
  return { period, note: null };
}

export function periodLabel({ from, to }: Period): string {
  const day = (value: string) => new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }).format(new Date(`${value}T00:00:00Z`));
  return from === to ? day(from) : `${day(from)} – ${day(to)}`;
}

export const countText = (value: number | null) => (value === null ? "Not tracked" : value.toLocaleString("en-IN"));
