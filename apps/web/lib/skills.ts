// ENH-011 -- shapes of the skills-tracker API (docs/superpowers/specs/2026-09-22-enh-011-skills-tracker-design.md §5) and how a
// status is shown. Status is always a text label plus a class, never colour alone. Safe for client components (no server imports).

import { detailMessage, NOT_COMPLETED } from "@/lib/apiErrors";
import { formatDate } from "@/lib/formatDate";
import type { SchoolRef } from "@/lib/transfers";

export type SkillModule = "soft_skills" | "digital_skills";
export type SkillBatchStatus = "open" | "closed";
export const ENROLMENT_STATUSES = ["enrolled", "completed", "certified", "withdrawn"] as const;
export type SkillEnrollmentStatus = (typeof ENROLMENT_STATUSES)[number];

export type SkillAttendanceSummary = { present: number; marked: number };

export type SkillBatch = {
  id: string;
  school: SchoolRef;
  module_type: SkillModule;
  title: string;
  topic: string | null;
  trainer_name: string | null;
  start_date: string;
  end_date: string | null;
  status: SkillBatchStatus;
  enrolled_count: number;
  created_at: string;
};

export type SkillEnrollment = {
  id: string;
  batch_id: string;
  school_student_id: string;
  student_name: string;
  status: SkillEnrollmentStatus;
  frozen: boolean;
  completed_at: string | null;
  certified_at: string | null;
  created_at: string;
  attendance: SkillAttendanceSummary;
  scores: { assessment_id: string; score: number; remarks: string | null }[];
};

export type SkillSession = { id: string; session_date: string; topic: string | null; attendance: { enrollment_id: string; present: boolean }[] };
export type SkillAssessment = { id: string; name: string; max_score: number };
export type SkillBatchDetail = SkillBatch & { enrollments: SkillEnrollment[]; sessions: SkillSession[]; assessments: SkillAssessment[] };

/** One portfolio student as `GET /school/portfolio-students` returns it (SCH-004). */
export type PortfolioStudent = { id: string; full_name: string; school_id: string; school_name: string };

export const MODULE_LABEL: Record<SkillModule, string> = { soft_skills: "Soft Skills", digital_skills: "Digital Skills" };

export const ENROLMENT_LABEL: Record<SkillEnrollmentStatus, string> = { enrolled: "Enrolled", completed: "Completed", certified: "Certified", withdrawn: "Withdrawn" };
// `.status` is the positive tone; `.status.pending` the neutral one (globals.css).
export const ENROLMENT_CLASS: Record<SkillEnrollmentStatus, string> = { enrolled: "status pending", completed: "status", certified: "status", withdrawn: "status pending" };

/** Mirrors the API's TRANSITIONS (app/api/school_skills.py): the UI never offers a change the API would refuse. */
export const TRANSITIONS: Record<SkillEnrollmentStatus, SkillEnrollmentStatus[]> = {
  enrolled: ["completed", "certified", "withdrawn"],
  completed: ["certified", "enrolled"],
  withdrawn: ["enrolled"],
  certified: [],
};

export function attendanceText({ present, marked }: SkillAttendanceSummary): string {
  if (marked === 0) return "No attendance yet";
  return `Attended ${present} of ${marked} session${marked === 1 ? "" : "s"}`;
}

/** Attendance and scores are taken only for a live enrolment of a student still at the batch's school. */
export function canMark(enrolment: Pick<SkillEnrollment, "status" | "frozen">): boolean {
  return !enrolment.frozen && (enrolment.status === "enrolled" || enrolment.status === "completed");
}

// Browser QA-10: a 5xx is not the counselor's mistake; say nothing was saved and that trying again is safe.
export const SERVER_FAILED = "The change was not saved because of a problem on our side. Your entry is kept; please try again in a moment.";
// Browser QA-05/06: the batch form's own checks, in plain words, so a server message never has to explain a field name or a parser.
const END_BEFORE_START = "The end date must be on or after the start date";

/** A batch's dates: the range when it has an end, otherwise just the start. Callers add their own "from"/"From". */
export function dateRange(start: string, end: string | null): string {
  return end ? `${formatDate(start)} – ${formatDate(end)}` : formatDate(start);
}

/** Field errors for a batch's title and dates, keyed like the API's fields. Empty when the draft may be sent. */
export function batchDraftErrors(draft: { title: string; start_date: string; end_date: string }): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!draft.title.trim()) errors.title = "Enter a title";
  if (!draft.start_date) errors.start_date = "Choose a start date";
  else if (draft.end_date && draft.end_date < draft.start_date) errors.end_date = END_BEFORE_START;
  return errors;
}

export type SendFailure = { ok: false; message: string; fields: Record<string, string>; expired?: boolean };
export type SendResult<T> = { ok: true; data: T } | SendFailure;

/** FastAPI's 422 list keyed by field name (the last string in `loc`), worded like `detailMessage`. */
function fieldErrors(detail: unknown): Record<string, string> {
  if (!Array.isArray(detail)) return {};
  const fields: Record<string, string> = {};
  for (const item of detail as { loc?: unknown[] }[]) {
    const name = [...(item?.loc ?? [])].reverse().find((part) => typeof part === "string" && part !== "body");
    if (typeof name === "string" && !fields[name]) fields[name] = detailMessage([item]);
  }
  return fields;
}

/** Every skills write goes through here, so the counselor screens share one reading of 401, 4xx/422, a dropped connection and a
 * 2xx that is not JSON (a proxy page must not read as saved). */
export async function send<T>(url: string, method: "GET" | "POST" | "PATCH" | "PUT", body?: unknown): Promise<SendResult<T>> {
  let response: Response;
  try {
    response = await fetch(url, body === undefined ? { method } : { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  } catch {
    return { ok: false, message: NOT_COMPLETED, fields: {} };
  }
  const data = await response.json().catch(() => null);
  if (response.status === 401) return { ok: false, expired: true, message: "Your session has expired.", fields: {} };
  if (response.status >= 500) return { ok: false, message: SERVER_FAILED, fields: {} };
  if (!response.ok) return { ok: false, message: detailMessage(data?.detail), fields: fieldErrors(data?.detail) };
  if (data === null || typeof data !== "object") return { ok: false, message: "The change could not be confirmed. Reload the page to see where it stands.", fields: {} };
  return { ok: true, data: data as T };
}
