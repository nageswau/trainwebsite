import type { MonthStatus, TargetKpi } from "@/lib/bdmTargets";
import type { PersonRef } from "@/lib/bdmTravel";

// upc-021 (DEC-SCOPE-144): monthly partnership targets vs actual (§21). The API computes actuals and percent and decides every rule (who
// reads, who sets, which months are editable); `editable` only tells the page whether to offer inputs. The month helpers are bdm-016's.
export type TargetKpiDef = { key: string; label: string; definition: string; tracked: boolean };
export type TargetValue = { key: string; target: number | null; achieved: number | null; percent: number | null };
export type ManagerTargetRow = { manager: PersonRef; active: boolean; kpis: TargetValue[] };
export type TeamTargets = { month: string; month_status: MonthStatus; editable: boolean; kpis: TargetKpiDef[]; managers: ManagerTargetRow[]; team: TargetValue[] };
export type ManagerTargetSheet = { month: string; month_status: MonthStatus; editable: boolean; manager: PersonRef; kpis: TargetKpi[] };

export const TARGETS_URL = "/api/v1/partnership/targets";
export const TARGETS_PATH = "/partnership/targets";
export const TARGET_READERS = new Set(["partnership_manager", "partnership_head", "super_admin"]);
export const managerTargetUrl = (managerId: string, month: string) => `${TARGETS_URL}/${managerId}?month=${month}`;
export const managerTargetHref = (managerId: string, month: string) => `${TARGETS_PATH}/${managerId}?month=${month}`;

/** One comparison cell: "actual / target", plus the achievement when there is one. Untracked or not-started actuals never read as 0. */
export function cellText(kpi: TargetKpiDef, value: TargetValue, status: MonthStatus): string {
  const actual = !kpi.tracked ? "Not tracked" : status === "future" ? "Not started" : String(value.achieved ?? "—");
  const base = `${actual} / ${value.target ?? "—"}`;
  return value.percent === null ? base : `${base} · ${value.percent}%`;
}
