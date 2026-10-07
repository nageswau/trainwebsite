import type { BdmType } from "@/lib/bdm";
import type { PersonRef } from "@/lib/bdmTravel";
import { indiaToday } from "@/lib/bdmTravel";

// bdm-016 (DEC-SCOPE-100): monthly targets' types, endpoints and words. The API computes achieved and percent and decides every rule
// (which months are editable, team scope, the type's KPIs); `editable` only tells the page whether to offer inputs.
export type MonthStatus = "past" | "current" | "future";
export type TargetKpi = { key: string; label: string; definition: string; tracked: boolean; target: number | null; achieved: number | null; percent: number | null };
export type TargetSheet = { month: string; month_status: MonthStatus; editable: boolean; bdm: PersonRef; bdm_type: BdmType; kpis: TargetKpi[] };
export type TeamTargetRow = { bdm: PersonRef; bdm_type: BdmType; targets_set: number; kpi_count: number };
export type TeamTargets = { month: string; month_status: MonthStatus; editable: boolean; items: TeamTargetRow[]; total: number; limit: number; offset: number };

export const TARGET_MAX = 100_000;
export const TEAM_PAGE = 50;
export const TARGETS_URL = "/api/v1/bdm/targets";
export const TEAM_TARGETS_URL = "/api/v1/bdm/manager/targets";
export const COPY_URL = `${TEAM_TARGETS_URL}/copy`;
export const MANAGER_TARGETS_PATH = "/bdm/manager/targets";
export const teamTargetUrl = (bdmId: string, month: string) => `${TEAM_TARGETS_URL}/${bdmId}?month=${month}`;
export const teamTargetHref = (bdmId: string, month: string) => `${MANAGER_TARGETS_PATH}/${bdmId}?month=${month}`;

const MONTH = /^\d{4}-(0[1-9]|1[0-2])$/;
export const currentMonth = () => indiaToday().slice(0, 7);

/** The month in the URL, or this IST month with a note when it is malformed (the activities-page rule). */
export function chosenMonth(raw: string | undefined, current: string): { month: string; note: string | null } {
  if (!raw) return { month: current, note: null };
  return MONTH.test(raw) ? { month: raw, note: null } : { month: current, note: "That isn't a valid month — showing this month." };
}

function shift(month: string, by: number): string {
  const index = Number(month.slice(0, 4)) * 12 + Number(month.slice(5, 7)) - 1 + by;
  return `${Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, "0")}`;
}

export const previousMonth = (month: string) => shift(month, -1);

export const monthLabel = (month: string) =>
  new Intl.DateTimeFormat("en-GB", { month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(`${month}-01T00:00:00Z`));

/** The month picker: a year back to a year ahead (a select works in every browser; `<input type="month">` does not). */
export function monthOptions(current: string): { value: string; label: string }[] {
  return Array.from({ length: 25 }, (_, i) => shift(current, i - 12)).map((value) => ({ value, label: monthLabel(value) }));
}

export function achievedText(kpi: TargetKpi, status: MonthStatus): string {
  if (!kpi.tracked) return "Not tracked";
  if (status === "future") return "Month not started";
  return String(kpi.achieved ?? "—");
}

export const percentText = (kpi: TargetKpi) => (kpi.percent === null ? "—" : `${kpi.percent}%`);

/** A target input: blank clears the target; otherwise a whole number 0–100000. */
export function parseTarget(text: string): { ok: true; value: number | null } | { ok: false } {
  const trimmed = text.trim();
  if (trimmed === "") return { ok: true, value: null };
  if (!/^\d+$/.test(trimmed) || Number(trimmed) > TARGET_MAX) return { ok: false };
  return { ok: true, value: Number(trimmed) };
}

export function isTargetSheet(data: unknown): data is TargetSheet {
  const d = data as Partial<TargetSheet> | null;
  return !!d && typeof d.month === "string" && typeof d.month_status === "string" && Array.isArray(d.kpis);
}
