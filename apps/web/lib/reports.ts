// nehn-009 (DEC-SCOPE-303): the report library -- types and addresses. Every report, column, label and option comes from the API
// (apps/api/app/services/reports); the browser only lays them out, so the screen and the downloads always agree.

export type ReportColumn = { key: string; label: string };
export type ReportRow = Record<string, string | number | null>;
export type Choice = { value: string; label: string };
export type ReportOptions = Partial<Record<"courses" | "batches" | "trainers" | "recruiters" | "statuses", Choice[]>>;
export type CatalogueItem = { id: string; title: string; description: string; filters: string[]; can_download: boolean };
export type Report = {
  id: string; title: string; description: string; columns: ReportColumn[]; items: ReportRow[]; total: number; page: number;
  page_size: number; filters: string[]; applied: Record<string, string>; options: ReportOptions;
};
export type ReportParams = Record<string, string>;

export const REPORTS_API = "/api/v1/reports";

// The standard filters, in the form's order, with the labels the API's 422 messages use.
export const FILTER_LABELS: Record<string, string> = {
  from: "From", to: "To", course_id: "Course", batch_id: "Batch", trainer_id: "Trainer", recruiter_id: "Recruiter", student: "Student",
  status: "Status", latest: "Latest", completion_from: "Completion from", completion_to: "Completion to", attendance_below: "Attendance below %",
};

/** The address's values for the report's declared filters and the page (anything else, empty or repeated, is ignored). */
export function reportParams(search: Record<string, string | string[] | undefined>, declared: string[]): ReportParams {
  return Object.fromEntries(
    [...declared, "page"].flatMap((key) => (typeof search[key] === "string" && search[key] ? [[key, search[key] as string]] : [])),
  );
}

function query(params: ReportParams, withPage: boolean): string {
  const text = new URLSearchParams(Object.entries(params).filter(([key, value]) => value && (withPage || key !== "page"))).toString();
  return text ? `?${text}` : "";
}

export const reportUrl = (id: string, params: ReportParams) => `${REPORTS_API}/${encodeURIComponent(id)}${query(params, true)}`;
export const csvUrl = (id: string, params: ReportParams) => `${REPORTS_API}/${encodeURIComponent(id)}.csv${query(params, false)}`;

/** The library page for one report and page; page 1 is the bare address. */
export function pageHref(basePath: string, id: string, params: ReportParams, page: number): string {
  const search = new URLSearchParams({ report: id });
  for (const [key, value] of Object.entries(params)) if (key !== "page" && value) search.set(key, value);
  if (page > 1) search.set("page", String(page));
  return `${basePath}?${search.toString()}`;
}
