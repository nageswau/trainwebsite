// nehn-016 (DEC-SCOPE-309): a candidate's training progress, read only -- each course seat with the certificate criteria, and readiness.
import { CANDIDATES_URL } from "@/lib/recruiterCandidates";

export type TrainingSeat = {
  course: string; batch: string; trainer: string | null; starts: string; ends: string; status: string; progress: number;
  attendance_pct: number | null; attendance_marked: number; assignments_graded: number; assignments_total: number;
  assessments_passed: number; assessments_total: number; certificate: string;
};
export type CandidateTraining = {
  student: boolean;
  seats: TrainingSeat[];
  readiness: { readiness_status: string; resume_status: string; mock_interview_status: string; aptitude_status: string; available: boolean } | null;
};

export const candidateTrainingUrl = (candidateId: string) => `${CANDIDATES_URL}/${encodeURIComponent(candidateId)}/training`;

export const isCandidateTraining = (body: unknown): body is CandidateTraining =>
  typeof body === "object" && body !== null && Array.isArray((body as CandidateTraining).seats) && typeof (body as CandidateTraining).student === "boolean";
