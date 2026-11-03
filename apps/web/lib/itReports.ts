// itc-032 (DEC-SCOPE-369): the management IT reports -- six read-only tabs with the same five filters (API §12JO). The filters live in
// the address (a GET form), so refresh, Back and a shared link keep the view; anything unknown in the address is dropped here.
import { isCalendarDate } from "@/lib/formatDate";
import { inr } from "@/lib/itAccounts";

const IT_REPORTS_API = "/api/v1/management/it/reports";
export const MANAGEMENT_IT_REPORTS = "/management/it-reports";
export const IT_ADMIN_IT_REPORTS = "/it/admin/management-reports";
const PAGE_SIZE = 50;

export type ItReport = "funnel" | "conversions" | "revenue" | "training" | "placement" | "activity";
export const IT_REPORTS: { key: ItReport; about: string }[] = [
  { key: "funnel", about: "IT leads created in the period, by course and source, and the stage each one is at now." },
  { key: "conversions", about: "Of the leads created in the period, how many converted to a student, by course." },
  { key: "revenue", about: "What the period's enrolments were billed, what they have paid and what active ones still owe today." },
  { key: "training", about: "Attendance and completion of the enrolments taken in the period." },
  { key: "placement", about: "Where the period's enrolments stand on placement, from the student lifecycle." },
  { key: "activity", about: "Calls, completed follow-ups and conversions on IT leads in the period, per staff member." },
];
const LEAD_REPORTS: ItReport[] = ["funnel", "conversions", "activity"];
export const isLeadReport = (report: ItReport) => LEAD_REPORTS.includes(report);

const FILTERS = ["program_id", "batch_id", "owner_id", "date_from", "date_to", "status"] as const;
type FilterKey = (typeof FILTERS)[number];
export type ItReportParams = Partial<Record<FilterKey, string>> & { offset?: number };

export function itReport(value: string | string[] | undefined, allowed: ItReport[]): ItReport | null {
  if (typeof value === "string" && allowed.includes(value as ItReport)) return value as ItReport;
  return allowed[0] ?? null;
}

const UUID_SHAPE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const isId = (value: string) => UUID_SHAPE.test(value);
const WELL_FORMED: Partial<Record<FilterKey, (value: string) => boolean>> = {
  program_id: isId, batch_id: isId, owner_id: isId, date_from: isCalendarDate, date_to: isCalendarDate,
};

/** The filters from the page's search params: known keys only, one value each; a negative or malformed offset reads as 0. A malformed id or
 * an impossible date only comes from a hand-edited address and is dropped too (QA-01), so the API's only 422s are its own worded ones. */
export function itReportParams(search: Record<string, string | string[] | undefined>): ItReportParams {
  const out: ItReportParams = {};
  for (const key of FILTERS) {
    const value = search[key];
    if (typeof value === "string" && value && (WELL_FORMED[key]?.(value) ?? true)) out[key] = value;
  }
  const offset = Number.parseInt(typeof search.offset === "string" ? search.offset : "", 10);
  if (offset > 0) out.offset = offset;
  return out;
}

function query(params: ItReportParams, extra: Record<string, string> = {}): string {
  const q = new URLSearchParams(extra);
  for (const key of FILTERS) if (params[key]) q.set(key, params[key]!);
  return q.toString();
}

export const itReportsIndexUrl = IT_REPORTS_API;
export const itReportUrl = (report: ItReport, params: ItReportParams) =>
  `${IT_REPORTS_API}/${report}?${query(params, { limit: String(PAGE_SIZE), offset: String(params.offset ?? 0) })}`;
export const itReportExportUrl = (report: ItReport, params: ItReportParams) => {
  const q = query(params);
  return `${IT_REPORTS_API}/${report}/export${q ? `?${q}` : ""}`;
};

/** A tab or page of the reports: course, batch, owner and dates carry across tabs; the status only within its family (lead / enrolment). */
export function itReportHref(basePath: string, report: ItReport, params: ItReportParams, from: ItReport, offset = 0): string {
  const kept: ItReportParams = { ...params, offset: undefined };
  if (isLeadReport(report) !== isLeadReport(from)) delete kept.status;
  const q = query(kept, { report });
  return `${basePath}?${q}${offset > 0 ? `&offset=${offset}` : ""}`;
}

export type ItReportRow = Record<string, string | number | boolean | null>;
export type ItReportPage = {
  report: ItReport; items: ItReportRow[]; total: number; limit: number; offset: number;
  totals: Record<string, number | null | { stage: string; label: string; count: number }[]>;
  groups: ItReportRow[]; definitions: { key: string; label: string; definition: string }[];
  filters: Record<FilterKey, string | null>;
  options: {
    courses: { id: string; title: string }[]; batches: { id: string; name: string; program_id: string }[];
    owners: { id: string; name: string }[]; statuses: { value: string; label: string }[];
  };
};

type Show = (v: ItReportRow[string]) => string;
export type ItColumn = { key: string; label: string; show: Show; num?: boolean };
const text: Show = (v) => (v === null || v === undefined || v === "" ? "—" : String(v));
const count: Show = (v) => (v === null || v === undefined ? "0" : String(v));
const pct: Show = (v) => (v === null || v === undefined ? "—" : `${v}%`);
const yes: Show = (v) => (v === true ? "Yes" : v === false ? "No" : text(v));
const money = (key: string, label: string): ItColumn => ({ key, label, show: (v) => inr(v as number), num: true });
const num = (key: string, label: string, show: Show = count): ItColumn => ({ key, label, show, num: true });

/** "2026-10-15" -> "15 Oct 2026" (a calendar day: no time zone shift). */
export function calendarDay(value: ItReportRow[string]): string {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return "—";
  const [y, m, d] = value.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" });
}

const LEAD: ItColumn[] = [
  { key: "lead_code", label: "Lead", show: text }, { key: "course", label: "Course", show: text }, { key: "source", label: "Source", show: text },
  { key: "owner", label: "Owner", show: text }, { key: "stage", label: "Stage", show: text }, { key: "created_on", label: "Created on", show: calendarDay },
];
const SEAT: ItColumn[] = [
  { key: "enrollment_code", label: "Enrolment", show: text }, { key: "student_code", label: "Student ID", show: text }, { key: "course", label: "Course", show: text },
  { key: "batch", label: "Batch", show: text }, { key: "counselor", label: "Counselor", show: text }, { key: "enrolled_on", label: "Enrolled on", show: calendarDay },
  { key: "stage", label: "Stage", show: text },
];
const OUTCOME_COLUMNS: ItColumn[] = [
  num("placed", "Placed"), num("interview", "Interview"), num("hr_screening", "HR screening"), num("resume_submitted", "Resume submitted"),
  num("not_placed", "Not placed"), num("not_started", "Not started"),
];
const REVENUE_MONEY = [money("billed", "Billed"), money("collected", "Collected"), money("outstanding", "Outstanding"), money("overdue", "Overdue")];
const COURSE: ItColumn = { key: "course", label: "Course", show: text };

/** The drill-down rows of each report. */
export const ROW_COLUMNS: Record<ItReport, ItColumn[]> = {
  funnel: [...LEAD, { key: "converted_on", label: "Converted on", show: calendarDay }],
  conversions: [...LEAD, { key: "converted_on", label: "Converted on", show: calendarDay }, num("days_to_convert", "Days to convert")],
  activity: [
    { key: "at", label: "When (IST)", show: text }, { key: "kind", label: "Activity", show: text }, { key: "connected", label: "Connected", show: text },
    { key: "staff", label: "Staff", show: text }, { key: "lead_code", label: "Lead", show: text }, COURSE, { key: "stage", label: "Lead stage", show: text },
  ],
  revenue: [...SEAT, ...REVENUE_MONEY],
  training: [...SEAT, num("attended", "Attended"), num("counted", "Counted"), num("attendance_pct", "Attendance", pct), num("progress", "Progress", pct), { key: "completed", label: "Completed", show: yes }],
  placement: [...SEAT, { key: "outcome_label", label: "Placement outcome", show: text }],
};

/** The groups table of each report (its first column is the row header). */
export const GROUP_COLUMNS: Record<ItReport, ItColumn[]> = {
  funnel: [COURSE, { key: "source", label: "Source", show: text }, num("leads", "Leads"), num("open", "Open"), num("nurture", "Nurture"), num("converted", "Converted"), num("closed", "Closed")],
  conversions: [COURSE, num("leads", "Leads"), num("converted", "Converted"), num("conversion_pct", "Conversion rate", pct)],
  activity: [{ key: "staff", label: "Staff member", show: text }, num("calls", "Calls"), num("connected_calls", "Connected calls"), num("follow_ups", "Follow-ups completed"), num("conversions", "Conversions")],
  revenue: [COURSE, num("enrolments", "Enrolments"), ...REVENUE_MONEY],
  training: [COURSE, num("enrolments", "Enrolments"), num("attendance_pct", "Attendance", pct), num("completed", "Completed"), num("completion_pct", "Completion", pct)],
  placement: [COURSE, num("enrolments", "Enrolments"), ...OUTCOME_COLUMNS],
};

/** The headline figures of the whole filtered report, as label/value pairs. */
export function itReportTotals(report: ItReport, totals: ItReportPage["totals"]): { label: string; value: string }[] {
  const n = (key: string) => count(totals[key] as number);
  const p = (key: string) => pct(totals[key] as number | null);
  const m = (key: string) => inr(totals[key] as number);
  switch (report) {
    case "funnel": return [{ label: "Leads", value: n("leads") }, { label: "Open", value: n("open") }, { label: "Nurture", value: n("nurture") }, { label: "Converted", value: n("converted") }, { label: "Closed", value: n("closed") }];
    case "conversions": return [{ label: "Leads", value: n("leads") }, { label: "Converted", value: n("converted") }, { label: "Conversion rate", value: p("conversion_pct") }];
    case "activity": return [{ label: "Calls", value: n("calls") }, { label: "Connected calls", value: n("connected_calls") }, { label: "Follow-ups completed", value: n("follow_ups") }, { label: "Conversions", value: n("conversions") }];
    case "revenue": return [{ label: "Enrolments", value: n("enrolments") }, { label: "Billed", value: m("billed") }, { label: "Collected", value: m("collected") }, { label: "Outstanding", value: m("outstanding") }, { label: "Overdue", value: m("overdue") }];
    case "training": return [{ label: "Enrolments", value: n("enrolments") }, { label: "Attendance", value: p("attendance_pct") }, { label: "Completed", value: n("completed") }, { label: "Completion", value: p("completion_pct") }];
    case "placement": return [{ label: "Enrolments", value: n("enrolments") }, { label: "Placed", value: n("placed") }, { label: "Interview", value: n("interview") }, { label: "HR screening", value: n("hr_screening") }, { label: "Not placed", value: n("not_placed") }, { label: "Not started", value: n("not_started") }];
  }
}
