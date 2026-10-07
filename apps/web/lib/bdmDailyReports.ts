import type { BdmType } from "@/lib/bdm";
import type { PersonRef } from "@/lib/bdmTravel";

// bdm-015 (DEC-SCOPE-096): the daily activity report's types, endpoints and words. The API computes every count and decides every rule
// (window, already submitted, team scope); `can_submit` only tells the page whether to offer Submit.
export type DailyCount = { key: string; label: string; definition: string; tracked: boolean; count: number | null };
export type DailyReport = {
  report_date: string;
  bdm: PersonRef;
  bdm_type: BdmType;
  status: "draft" | "submitted";
  submitted_at: string | null;
  note: string | null;
  counts: DailyCount[];
  can_submit: boolean;
  submit_window_days: number;
  manager_comment: { text: string; by: PersonRef; at: string } | null;
};
export type GridStatus = "submitted" | "missing" | "not_started";
export type GridDay = { report_date: string; status: GridStatus; submitted_at: string | null };
export type TeamRow = { bdm: PersonRef; bdm_type: BdmType; days: GridDay[] };
export type TeamGrid = { dates: string[]; items: TeamRow[]; total: number; limit: number; offset: number };

export const NOTE_MAX = 2000;
export const COMMENT_MAX = 1000;
export const TEAM_PAGE = 50;
export const GRID_STATUS_LABEL: Record<GridStatus, string> = { submitted: "Submitted", missing: "Missing", not_started: "—" };

export const REPORTS_URL = "/api/v1/bdm/daily-reports";
export const TEAM_REPORTS_URL = "/api/v1/bdm/manager/daily-reports";
export const reportUrl = (day: string) => `${REPORTS_URL}/${day}`;
export const submitUrl = (day: string) => `${REPORTS_URL}/${day}/submit`;
export const teamReportUrl = (bdmId: string, day: string) => `${TEAM_REPORTS_URL}/${bdmId}/${day}`;
export const commentUrl = (bdmId: string, day: string) => `${teamReportUrl(bdmId, day)}/comment`;
export const teamReportHref = (bdmId: string, day: string) => `/bdm/manager/daily-reports/${bdmId}?date=${day}`;

export function isDailyReport(data: unknown): data is DailyReport {
  const d = data as Partial<DailyReport> | null;
  return !!d && typeof d.report_date === "string" && Array.isArray(d.counts) && (d.status === "draft" || d.status === "submitted");
}
