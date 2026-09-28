import { serverApi } from "@/lib/api";
import type { GradePerformance, ScorecardPage, StudentDevelopment } from "@/lib/types";

// ENH-016: the three analytics sections the Coordinator and Principal reports pages share. Each is read on its own and a
// failure becomes `null` (the section shows SectionUnavailable), so one broken figure never blanks the page. Query values
// come from the URL, so they are allow-listed here before they reach the API.
export type SchoolAnalytics = {
  grade: string;
  thresholds: Record<string, string>; // the accepted at_risk_below / top_from from the URL, kept by the grid form (QA-016-12)
  thresholdError: string | null; // why the URL's thresholds were dropped (QA-016-05)
  grades: GradePerformance | null;
  development: StudentDevelopment | null;
  scorecards: ScorecardPage | null;
};

// Mirrors the API (school_analytics.py): threshold defaults (D4), their 0-100 range, and the offset bound.
const DEFAULT_AT_RISK_BELOW = 40;
const DEFAULT_TOP_FROM = 85;
const MAX_OFFSET = 10_000;
export const THRESHOLD_RANGE_ERROR = "Thresholds must be between 0 and 100. Showing the defaults.";
export const THRESHOLD_ORDER_ERROR = "At-risk must be below the top-performer threshold. Showing the defaults.";

function readThresholds(one: (key: string) => string): { thresholds: Record<string, string>; thresholdError: string | null } {
  const given: Record<string, string> = {};
  for (const key of ["at_risk_below", "top_from"]) if (one(key) !== "") given[key] = one(key);
  if (Object.values(given).some((v) => !/^\d{1,3}$/.test(v) || Number(v) > 100)) return { thresholds: {}, thresholdError: THRESHOLD_RANGE_ERROR };
  const atRisk = Number(given.at_risk_below ?? DEFAULT_AT_RISK_BELOW);
  const top = Number(given.top_from ?? DEFAULT_TOP_FROM);
  if (atRisk >= top) return { thresholds: {}, thresholdError: THRESHOLD_ORDER_ERROR };
  return { thresholds: given, thresholdError: null };
}

export async function loadSchoolAnalytics(sp: Record<string, string | string[] | undefined>): Promise<SchoolAnalytics> {
  const one = (key: string) => (typeof sp[key] === "string" ? (sp[key] as string).trim() : "");
  const grade = /^(8|9|10|11|12)$/.test(one("grade")) ? one("grade") : "";
  const offset = Math.min(MAX_OFFSET, Math.max(0, Number.parseInt(one("offset"), 10) || 0));
  const { thresholds, thresholdError } = readThresholds(one);
  const grid = new URLSearchParams({ offset: String(offset) });
  if (grade) grid.set("grade", grade);
  const [grades, development, scorecards] = await Promise.all([
    serverApi<GradePerformance>("/api/v1/school/analytics/grade-performance").catch(() => null),
    serverApi<StudentDevelopment>(`/api/v1/school/analytics/student-development?${new URLSearchParams(thresholds)}`).catch(() => null),
    serverApi<ScorecardPage>(`/api/v1/school/analytics/scorecards?${grid}`).catch(() => null),
  ]);
  return { grade, thresholds, thresholdError, grades, development, scorecards };
}
