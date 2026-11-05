// hrc-027 (DEC-SCOPE-398): the open jobs a candidate or an IT student may see, in three views, and applying to one. The server decides
// visibility, scores and who may apply; this file only names the views and builds addresses.
export const CANDIDATE_JOBS_URL = "/api/v1/candidate/jobs";
export const applyUrl = (jobId: string) => `${CANDIDATE_JOBS_URL}/${encodeURIComponent(jobId)}/apply`;
export const PAGE_SIZE = 20;

export type JobView = "recommended" | "matching" | "all";
export const VIEWS: { key: JobView; label: string; empty: string }[] = [
  { key: "recommended", label: "Recommended for you", empty: "No jobs are recommended for you yet." },
  { key: "matching", label: "Matching your skills", empty: "No open job lists one of your skills yet." },
  { key: "all", label: "All open jobs", empty: "There are no open jobs right now." },
];

export type ExplanationLine = { key: string; label: string; text: string; matched: boolean };
export type JobCard = {
  id: string;
  title: string;
  company: string;
  location: string;
  work_mode: string | null;
  employment_type: string | null;
  required_skills: string[];
  preferred_skills: string[];
  experience_min_months: number | null;
  experience_max_months: number | null;
  closes_on: string | null;
  match: { score: number; explanation: ExplanationLine[] } | null;
  skills_text: string;
  matches_skills: boolean;
  recommended: boolean;
  application: { code: string; status_label: string } | null;
  can_apply: boolean;
  blocked: string[];
};
export type JobsPage = {
  view: JobView;
  q: string | null;
  items: JobCard[];
  total: number;
  limit: number;
  offset: number;
  counts: Record<JobView, number>;
  reason: "no_skills" | null;
  disclaimer: string;
  threshold: number;
};

export function parseView(value: unknown): JobView {
  return VIEWS.some((v) => v.key === value) ? (value as JobView) : "recommended";
}

export function parseOffset(value: unknown): number {
  const n = typeof value === "string" ? Number(value) : 0;
  return Number.isInteger(n) && n > 0 ? n : 0;
}

// The page's own address for a view, a search and a page: an empty search and the first page are left out.
export function pageHref(base: string, view: JobView, q: string, offset = 0): string {
  const params = new URLSearchParams({ view });
  if (q.trim()) params.set("q", q.trim());
  if (offset > 0) params.set("offset", String(offset));
  return `${base}?${params.toString()}`;
}

export function apiPath(view: JobView, q: string, offset: number): string {
  const params = new URLSearchParams({ view, limit: String(PAGE_SIZE), offset: String(offset) });
  if (q.trim()) params.set("q", q.trim().slice(0, 100));
  return `${CANDIDATE_JOBS_URL}?${params.toString()}`;
}

function years(months: number): string {
  if (months < 12) return `${months} mo${months === 1 ? "" : "s"}`;
  const value = Math.round((months / 12) * 10) / 10;
  return `${value} yr${value === 1 ? "" : "s"}`;
}

export function experienceText(min: number | null, max: number | null): string | null {
  if (min != null && max != null) return `${years(min)} – ${years(max)}`;
  if (min != null) return `${years(min)}+`;
  if (max != null) return `Up to ${years(max)}`;
  return null;
}

const WORK_MODES: Record<string, string> = { remote: "Remote", onsite: "On-site", hybrid: "Hybrid" };
export function workModeLabel(mode: string | null): string | null {
  return mode ? (WORK_MODES[mode] ?? mode) : null;
}

export function employmentLabel(kind: string | null): string | null {
  return kind ? kind.charAt(0).toUpperCase() + kind.slice(1).replaceAll("_", " ") : null;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
// A calendar date ("2026-12-01") as written, never moved by the reader's time zone.
export function dayText(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return `${d} ${MONTHS[m - 1]} ${y}`;
}
