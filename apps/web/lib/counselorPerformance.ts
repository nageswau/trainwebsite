import { counselingUrl, type CounselingQuery } from "@/lib/managementCounseling";

// ccrm-036 (DEC-SCOPE-269, P1-P9): GET /counselor/performance -- the overseas counselor's own figures for an IST period (the period
// figures are mgmt-018's, without revenue) and their caseload now. The API decides access and every figure; a null percentage has nothing
// to divide. The period lives in the address (`counselingQuery`, the management counseling page's parser).
export const PERFORMANCE_HOME = "/overseas/counselor/reports";
export const PERFORMANCE_API = "/api/v1/counselor/performance";
export const PERFORMANCE_UNAVAILABLE = "Your performance figures are unavailable right now. Please try again.";

export type PerformanceFigure = { key: string; label: string; definition: string; unit: "count" | "percent"; value: number | null };
export type PerformanceCounts = { applications: number; students: number };
export type PerformanceRow = PerformanceCounts & { stage: string; stage_label: string; sub_status: string | null; sub_status_label: string };
export type CounselorPerformanceReport = {
  from: string; to: string; as_of: string; period: PerformanceFigure[]; now: PerformanceFigure[];
  applications: { rows: PerformanceRow[]; total: PerformanceCounts; definitions: { key: string; label: string; definition: string }[] };
}; // prettier-ignore

export const performanceUrl = (query: CounselingQuery): string => counselingUrl(query, PERFORMANCE_API);
