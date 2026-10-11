// rec-036 (DEC-SCOPE-179 CI7): a candidate's EVID-018 §27 journey -- lead → IT student → trained → recruiter candidate → placed.
import { CANDIDATES_URL } from "@/lib/recruiterCandidates";

export type CandidateJourney = {
  lead: { lead_code: string; source: string; created_at: string; converted_at: string | null } | null;
  enrolments: { program: string; batch: string; enrolled_on: string; status: string }[];
  certificates: { program: string; certificate_no: string; issued_on: string }[];
  candidate: { added_at: string; opted_in_at: string | null };
  applications: { count: number; first_at: string | null };
  placements: { company: string; position: string | null; joined_on: string | null }[];
};

export const candidateJourneyUrl = (candidateId: string) => `${CANDIDATES_URL}/${encodeURIComponent(candidateId)}/journey`;

export const isCandidateJourney = (body: unknown): body is CandidateJourney =>
  typeof body === "object" && body !== null && Array.isArray((body as CandidateJourney).enrolments) && typeof (body as CandidateJourney).candidate === "object";

/** "completed" → "Completed", "in_progress" → "In progress". */
export const statusLabel = (value: string) => (value.charAt(0).toUpperCase() + value.slice(1)).replace(/_/g, " ");
