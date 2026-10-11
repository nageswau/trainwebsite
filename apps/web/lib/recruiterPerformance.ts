// rec-033 (DEC-SCOPE-182, API §12CW): the recruiter performance dashboard -- types, the fifteen §24 figures and the URL rules. Every
// figure is computed by the API (services/recruiter_metrics.py, backlog Appendix B P1-P15); the page only lays it out.
import { dayParam } from "@/lib/telecallerMetrics";

export type FigureKind = "count" | "pct" | "ratio" | "days";
export const FIGURES = [
  { key: "recruiter_leads", label: "Recruiter Leads", kind: "count", hint: "Companies added" },
  { key: "active_companies", label: "Active Companies", kind: "count", hint: "With a live requirement at the period end" },
  { key: "requirements", label: "Requirements", kind: "count", hint: "Requirements added" },
  { key: "candidates_sourced", label: "Candidates Sourced", kind: "count", hint: "Added to requirements" },
  { key: "profiles_shared", label: "Profiles Shared", kind: "count", hint: "Sent to companies" },
  { key: "interviews", label: "Interviews", kind: "count", hint: "Held, with an outcome" },
  { key: "selected", label: "Selected", kind: "count", hint: "Candidates selected" },
  { key: "joined", label: "Joined", kind: "count", hint: "Candidates who joined" },
  { key: "selection_pct", label: "Selection %", kind: "pct", hint: "Selected ÷ sourced" },
  { key: "joining_pct", label: "Joining %", kind: "pct", hint: "Joined ÷ selected" },
  { key: "profile_to_interview", label: "Profile-to-Interview Ratio", kind: "ratio", hint: "Interviews ÷ profiles shared" },
  { key: "interview_to_selection", label: "Interview-to-Selection Ratio", kind: "ratio", hint: "Selected ÷ interviews" },
  { key: "selection_to_joining", label: "Selection-to-Joining Ratio", kind: "ratio", hint: "Joined ÷ selected" },
  { key: "avg_closure_days", label: "Average Closure Time", kind: "days", hint: "Requirement date to Closed" },
  { key: "requirements_closed", label: "Requirements Closed", kind: "count", hint: "Closed in the period" },
] as const satisfies readonly { key: string; label: string; kind: FigureKind; hint: string }[];
export type FigureKey = (typeof FIGURES)[number]["key"];

export type PerformanceRow = { user_id: string | null; full_name: string; active: boolean; status: string } & Record<FigureKey, number | null>;
export type Performance = {
  date_from: string; date_to: string; recruiter: { id: string; full_name: string } | null; items: PerformanceRow[]; totals: PerformanceRow;
};
export type PerformanceParams = { from?: string; to?: string; recruiter?: string };

export const PERFORMANCE_URL = "/api/v1/recruiter/performance";
export const PERFORMANCE_PATH = "/recruiter/manager/performance";
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** AC1: a ratio with a zero denominator arrives as null and shows "—". */
export function formatFigure(value: number | null, kind: FigureKind): string {
  if (value === null) return "—";
  if (kind === "pct") return `${value.toFixed(1)}%`;
  if (kind === "ratio") return value.toFixed(2);
  if (kind === "days") return `${value.toFixed(1)} ${value === 1 ? "day" : "days"}`;
  return value.toLocaleString("en-IN");
}

/** Only well-formed values reach the API, so its only 422s are the range rules, which carry a sentence to show. */
export function performanceParams(raw: Record<string, string | undefined>): PerformanceParams {
  const recruiter = raw.recruiter?.trim();
  return { from: dayParam(raw.from), to: dayParam(raw.to), recruiter: recruiter && UUID.test(recruiter) ? recruiter : undefined };
}

export function performanceQuery(params: PerformanceParams): string {
  const query = new URLSearchParams(Object.entries(params).filter((entry): entry is [string, string] => !!entry[1])).toString();
  return query ? `?${query}` : "";
}

export const csvUrl = (data: Performance) =>
  `${PERFORMANCE_URL}.csv${performanceQuery({ from: data.date_from, to: data.date_to, recruiter: data.recruiter?.id })}`;
export const csvFilename = (data: Performance) => `recruiter-performance-${data.date_from}-to-${data.date_to}.csv`;
/** The same period, narrowed to one recruiter (drill-down) or widened back to everyone. */
export const periodHref = (from: string, to: string, recruiter?: string) => PERFORMANCE_PATH + performanceQuery({ from, to, recruiter });

export const PERFORMANCE_UNAVAILABLE = "Recruiter performance is unavailable right now.";
export function performanceError(e: unknown): string {
  const { status, message } = (e ?? {}) as { status?: number; message?: unknown };
  return status === 422 && typeof message === "string" ? message : PERFORMANCE_UNAVAILABLE;
}
