// rec-035 (DEC-SCOPE-183, API §12CX): the management dashboard -- types, the seven §26 totals and the URL rules. Every figure is computed by the API
// (services/recruiter_metrics.py, backlog Appendix B M1-M9); the page only lays it out.
import { dayParam } from "@/lib/telecallerMetrics";

export const TOTALS = [
  { key: "companies", label: "Companies", hint: "Past New Lead, not archived" },
  { key: "active_recruiters", label: "Active Recruiters", hint: "Active contacts at active companies" },
  { key: "open_requirements", label: "Open Requirements", hint: "Not on hold, closed or cancelled" },
  { key: "candidates_in_pipeline", label: "Candidates in Pipeline", hint: "With a live application" },
  { key: "interviews", label: "Interviews", hint: "Scheduled in the period" },
  { key: "selected", label: "Selected", hint: "Selected in the period" },
  { key: "joined", label: "Joined", hint: "Joined in the period" },
] as const;
export type TotalKey = (typeof TOTALS)[number]["key"];

export type Management = {
  date_from: string;
  date_to: string;
  totals: Record<TotalKey, number>;
  top_companies: { id: string; name: string; joined: number }[];
  top_categories: { id: string; name: string; open_requirements: number }[];
};
export type ManagementParams = { from?: string; to?: string };

export const MANAGEMENT_URL = "/api/v1/recruiter/management";
export const MANAGEMENT_PATH = "/recruiter/manager/business";

/** Only well-formed dates reach the API, so its only 422s are the range rules, which carry a sentence to show. */
export function managementParams(raw: Record<string, string | undefined>): ManagementParams {
  return { from: dayParam(raw.from), to: dayParam(raw.to) };
}

export { performanceQuery as managementQuery } from "@/lib/recruiterPerformance"; // the same rule: blank values left out

export const count = (value: number) => value.toLocaleString("en-IN");

export const MANAGEMENT_UNAVAILABLE = "The management dashboard is unavailable right now.";
export function managementError(e: unknown): string {
  const { status, message } = (e ?? {}) as { status?: number; message?: unknown };
  return status === 422 && typeof message === "string" ? message : MANAGEMENT_UNAVAILABLE;
}
