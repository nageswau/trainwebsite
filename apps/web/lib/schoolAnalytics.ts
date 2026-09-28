import { serverApi } from "@/lib/api";
import type { GradePerformance, ScorecardPage, StudentDevelopment } from "@/lib/types";

// ENH-016: the three analytics sections the Coordinator and Principal reports pages share. Each is read on its own and a
// failure becomes `null` (the section shows SectionUnavailable), so one broken figure never blanks the page. Query values
// come from the URL, so they are allow-listed here before they reach the API.
export type SchoolAnalytics = {
  grade: string;
  grades: GradePerformance | null;
  development: StudentDevelopment | null;
  scorecards: ScorecardPage | null;
};

export async function loadSchoolAnalytics(sp: Record<string, string | string[] | undefined>): Promise<SchoolAnalytics> {
  const one = (key: string) => (typeof sp[key] === "string" ? (sp[key] as string) : "");
  const grade = /^(8|9|10|11|12)$/.test(one("grade")) ? one("grade") : "";
  const offset = Math.max(0, Number.parseInt(one("offset"), 10) || 0);
  const thresholds = new URLSearchParams();
  for (const key of ["at_risk_below", "top_from"]) if (/^\d{1,3}$/.test(one(key))) thresholds.set(key, one(key));
  const grid = new URLSearchParams({ offset: String(offset) });
  if (grade) grid.set("grade", grade);
  const [grades, development, scorecards] = await Promise.all([
    serverApi<GradePerformance>("/api/v1/school/analytics/grade-performance").catch(() => null),
    serverApi<StudentDevelopment>(`/api/v1/school/analytics/student-development?${thresholds}`).catch(() => null),
    serverApi<ScorecardPage>(`/api/v1/school/analytics/scorecards?${grid}`).catch(() => null),
  ]);
  return { grade, grades, development, scorecards };
}
