import { RECORDS_URL } from "./agentStudents";

// AGN-015 (DEC-SCOPE-060): one student's step tracker and complete history (spec §4-§5).
export const journeyUrl = (id: string) => `${RECORDS_URL}/${id}/journey`;
export const timelineUrl = (id: string, limit: number, offset: number) => `${RECORDS_URL}/${id}/timeline?limit=${limit}&offset=${offset}`;

export type StepState = "not_started" | "in_progress" | "done" | "not_required" | "refunded" | "refused" | "withdrawn";
export type JourneyStep = { key: string; state: StepState };
export type JourneyApplication = { id: string; university: string | null; intake: string; status: string; steps: JourneyStep[] };
export type Journey = { student: { id: string; full_name: string | null; status: string }; steps: JourneyStep[]; applications: JourneyApplication[] };
export type TimelineItem = {
  id: string;
  at: string;
  kind: string;
  actor: string;
  application: { id: string; university: string | null } | null;
  document: { id: string; type: string } | null;
  from_status: string | null;
  to_status: string | null;
  fields: string[] | null;
  notes: string | null;
};

export const STEP_LABELS: Record<string, string> = {
  create: "Create",
  counseling: "Counseling",
  shortlist: "Shortlist",
  documents: "Documents",
  application: "Application",
  offer: "Offer",
  deposit: "Deposit",
  visa: "Visa",
  enrollment: "Enrollment",
};

export const STATE_LABELS: Record<StepState, string> = {
  not_started: "Not started",
  in_progress: "In progress",
  done: "Done",
  not_required: "Not required",
  refunded: "Refunded",
  refused: "Refused",
  withdrawn: "Withdrawn",
};

// A settled step is finished one way or another; the tracker marks the first step NOT settled as the current one.
const SETTLED: StepState[] = ["done", "not_required", "refunded", "refused", "withdrawn"];

// Every `kind` the server sends (services/agent_journey.py); anything new falls back to a humanised label.
export const KIND_LABELS: Record<string, string> = {
  student_created: "Student created",
  student_updated: "Student details edited",
  student_duplicate_override: "Saved despite a possible duplicate",
  student_assigned: "Assigned to staff",
  student_archived: "Archived",
  student_restored: "Restored",
  counseling_saved: "Counseling saved",
  shortlist_added: "University shortlisted",
  shortlist_updated: "Shortlist entry edited",
  shortlist_removed: "University removed from shortlist",
  task_added: "Task added",
  task_updated: "Task edited",
  task_completed: "Task completed",
  task_cancelled: "Task cancelled",
  application_created: "Application created",
  application_stage_changed: "Application stage changed",
  application_withdrawn: "Application withdrawn",
  application_enrolled: "Enrolled",
  application_updated: "Application updated",
  application_edited: "Application details edited",
  enrollment_updated: "Enrollment details corrected",
  visa_started: "Visa case started",
  visa_updated: "Visa details updated",
  visa_stage_changed: "Visa stage changed",
  visa_decision_recorded: "Visa decision recorded",
  deposit_set: "Deposit set",
  deposit_paid: "Deposit paid",
  deposit_remitted: "Deposit remitted",
  deposit_refunded: "Deposit refunded",
  document_uploaded: "Document uploaded",
  document_replaced: "Document replaced",
  document_verified: "Document verified",
  document_rejected: "Document rejected",
  document_changes_required: "Document changes requested",
  document_requested: "Document requested",
  document_fulfilled: "Document request fulfilled",
  document_request_cancelled: "Document request cancelled",
  document_downloaded: "Document downloaded",
};

const humanise = (value: string) => value.replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase());

export function kindLabel(kind: string): string {
  return KIND_LABELS[kind] ?? humanise(kind);
}

export function isJourney(body: unknown): body is Journey {
  const b = body as Partial<Journey> | null;
  return !!b && typeof b === "object" && !!b.student && Array.isArray(b.steps) && Array.isArray(b.applications);
}

export function currentStep(steps: JourneyStep[]): string | null {
  return steps.find((s) => !SETTLED.includes(s.state))?.key ?? null;
}

// Why the journey or history could not be shown; an expired session (401) offers sign-in instead of a retry (the AGN-021 pattern).
export type Failure = { text: string; expired: boolean };

export class LoadFailed extends Error {
  constructor(text: string, readonly expired = false) {
    super(text);
  }
}

export function failureOf(caught: unknown, fallback: string): Failure {
  // A dropped connection (TypeError) or anything unexpected reads as the generic message.
  return caught instanceof LoadFailed ? { text: caught.message, expired: caught.expired } : { text: fallback, expired: false };
}
