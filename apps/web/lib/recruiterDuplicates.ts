import type { PersonRef } from "@/lib/telecallerLeads";
import { CANDIDATES_PATH, candidateUrl, type CandidateStatus } from "@/lib/recruiterCandidates";

// hrc-014 (DEC-SCOPE-377): the probable-duplicate review queue and the candidate merge screen.
export const DUPLICATES_URL = "/api/v1/recruiter/candidate-duplicates";
export const DUPLICATES_PATH = `${CANDIDATES_PATH}/duplicates`;
export const mergePath = (survivorId: string, victimCode: string) =>
  `${CANDIDATES_PATH}/${encodeURIComponent(survivorId)}/merge?${new URLSearchParams({ victim: victimCode })}`;
export const mergeUrl = (survivorId: string, victimCode?: string) =>
  candidateUrl(survivorId, victimCode === undefined ? "/merge" : `/merge?${new URLSearchParams({ victim: victimCode })}`);

export type DuplicateStatus = "open" | "dismissed" | "merged";
export const DUPLICATE_STATUSES: { key: DuplicateStatus; label: string }[] = [
  { key: "open", label: "To review" }, { key: "dismissed", label: "Not the same person" }, { key: "merged", label: "Merged" },
];
export const SIGNAL_LABEL: Record<string, string> = {
  name_location_college: "Same name, location and college",
  phone_variant: "Same mobile number written differently",
};

export type DuplicateSide = { id: string; candidate_code: string; name: string; location: string | null; college: string | null; status: CandidateStatus; archived: boolean };
export type DuplicatePair = {
  id: string; signals: string[]; status: DuplicateStatus; created_at: string; decided_at: string | null; decided_by: PersonRef | null;
  candidate: DuplicateSide; other: DuplicateSide;
};

// The fields the merge may take from the duplicate (candidate_merge.FIELDS), in the API's order.
export type MergeField = "name" | "location" | "qualification" | "college" | "passing_year" | "experience_months" | "current_company" | "notice_days" | "preferred_role" | "linkedin";
export const MERGE_FIELD_LABEL: Record<MergeField, string> = {
  name: "Name", location: "Location", qualification: "Qualification", college: "College", passing_year: "Passing year",
  experience_months: "Total experience (months)", current_company: "Current company", notice_days: "Notice period (days)",
  preferred_role: "Preferred role", linkedin: "LinkedIn",
};
export type MergeSide = Record<MergeField, string | number | null> & {
  id: string; candidate_code: string; status: CandidateStatus; created_at: string; mobile: string | null; email: string | null;
  current_salary?: string | null; expected_salary?: string | null;
};
export type MergeConflict = { application_id: string; job_id: string; job_title: string; status: string; blocking: boolean };
export type MergeMoved = Record<"applications" | "share_items" | "calls" | "messages" | "consents" | "documents" | "document_requests" | "career_applications" | "skills" | "resumes", number>;
export type MergePreview = { survivor: MergeSide; victim: MergeSide; fields: MergeField[]; conflicts: MergeConflict[]; moved: MergeMoved };
export const MOVED_LABEL: [keyof MergeMoved, string][] = [
  ["applications", "requirements"], ["share_items", "profile shares"], ["calls", "calls"], ["messages", "messages"],
  ["skills", "skills"], ["resumes", "resumes"], ["documents", "documents"], ["document_requests", "document requests"], ["consents", "consent records"],
  ["career_applications", "website applications"], // hrc-023 W10
];

export function isMergePreview(data: unknown): data is MergePreview {
  const d = data as Partial<MergePreview> | null;
  return !!d && typeof d === "object" && !!d.survivor && !!d.victim && Array.isArray(d.fields) && Array.isArray(d.conflicts) && !!d.moved;
}
