// rec-017 (DEC-SCOPE-136): candidates on a requirement and their per-requirement status (§12) -- types, endpoints, guards and the
// candidate picker. The API decides scope and every rule (A2 transitions, the Joined gate, duplicates); each item's `allowed_statuses`
// and the list's `can_add` say what the viewer may do, so the UI never hard-codes a transition.
import type { LookupPage } from "@/lib/lookups";
import { CANDIDATES_URL, type CandidateItem } from "@/lib/recruiterCandidates";
import { REQUIREMENTS_URL } from "@/lib/recruiterRequirements";

export type StatusOption = { key: string; label: string };
export type ApplicationStatus = StatusOption & { initial: boolean };
export type RecApplication = {
  id: string; job_id: string; candidate: { id: string; code: string; name: string }; status: string; status_label: string;
  stage_changed_at: string; created_at: string; allowed_statuses: StatusOption[];
  screening_result: StatusOption | null; // rec-018: the current screening's result (the board's flag)
};
export type RequirementCandidates = { items: RecApplication[]; statuses: ApplicationStatus[]; can_add: boolean };
export type HistoryEntry = {
  from_status: string | null; from_label: string | null; to_status: string; to_label: string; note: string | null;
  changed_by: { id: string; full_name: string } | null; created_at: string;
};
export type CandidateApplication = {
  id: string; requirement: { id: string; code: string; title: string; status_label: string }; company: { id: string; name: string };
  status: string; status_label: string; stage_changed_at: string; in_scope: boolean;
};

// rec-018 (DEC-SCOPE-149): an application's screening. The API decides the status move (SC3), whether the viewer may edit (SC4/SC8)
// and every range; the form only mirrors the ranges so the browser can say so before a 422.
export type ScreeningFields = {
  qualification_verified: boolean; experience_verified: boolean; skills_verified: boolean; expected_salary: number | null;
  notice_days: number | null; location_preference: string | null; communication_rating: number | null; technical_rating: number | null;
  availability: string | null; willing_to_relocate: boolean | null; remarks: string | null; result: string;
};
export type Screening = ScreeningFields & { result_label: string; screened_by: { id: string; full_name: string }; updated_at: string };
export type ScreeningRead = { screening: Screening | null; results: StatusOption[]; can_edit: boolean };

export const NOTE_MAX = 500;
export const SCREENING_LIMITS = { salaryMax: 9_999_999_999.99, noticeMax: 365, location: 200, availability: 120, remarks: 2000 } as const;
export const requirementCandidatesUrl = (requirementId: string) => `${REQUIREMENTS_URL}/${encodeURIComponent(requirementId)}/candidates`;
export const applicationUrl = (id: string, suffix: "/status" | "/history" | "/screening") => `/api/v1/recruiter/applications/${encodeURIComponent(id)}${suffix}`;

export function isScreeningRead(data: unknown): data is ScreeningRead {
  const d = data as Partial<ScreeningRead> | null;
  return !!d && Array.isArray(d.results) && typeof d.can_edit === "boolean" && (d.screening === null || typeof d.screening?.result === "string");
}
export const candidateApplicationsUrl = (candidateId: string) => `${CANDIDATES_URL}/${encodeURIComponent(candidateId)}/applications`;

export function isRecApplication(data: unknown): data is RecApplication {
  const d = data as Partial<RecApplication> | null;
  return !!d && typeof d.id === "string" && typeof d.status === "string" && !!d.candidate && Array.isArray(d.allowed_statuses);
}

export function isApplicationBody(data: unknown): data is { application: RecApplication } {
  return !!data && isRecApplication((data as { application?: unknown }).application);
}

export function isRequirementCandidates(data: unknown): data is RequirementCandidates {
  const d = data as Partial<RequirementCandidates> | null;
  return !!d && Array.isArray(d.items) && Array.isArray(d.statuses) && typeof d.can_add === "boolean" && d.items.every(isRecApplication);
}

export function isHistory(data: unknown): data is { items: HistoryEntry[] } {
  const items = (data as { items?: unknown } | null)?.items;
  return Array.isArray(items) && items.every((h) => typeof (h as HistoryEntry).to_status === "string" && typeof (h as HistoryEntry).created_at === "string");
}

export function isCandidateApplications(data: unknown): data is { items: CandidateApplication[] } {
  const items = (data as { items?: unknown } | null)?.items;
  return Array.isArray(items) && items.every((a) => typeof (a as CandidateApplication).status_label === "string" && !!(a as CandidateApplication).requirement);
}

/** The Add candidate picker: active pool candidates by name, code or email (rec-009's list), labelled with the code. */
export function candidateSearch() {
  return async (q: string, signal: AbortSignal): Promise<LookupPage> => {
    const query = new URLSearchParams({ limit: "20" });
    if (q) query.set("q", q);
    const response = await fetch(`${CANDIDATES_URL}?${query}`, { signal });
    if (!response.ok) throw new Error(`Candidate search failed (${response.status})`);
    const page = (await response.json()) as { items: CandidateItem[]; total: number };
    return { items: page.items.map((c) => ({ id: c.id, label: c.name, detail: c.candidate_code })), truncated: page.total > page.items.length };
  };
}
