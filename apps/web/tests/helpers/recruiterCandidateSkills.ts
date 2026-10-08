import type { CandidateSkill } from "@/lib/recruiterCandidateSkills";

// rec-011: one candidate skill as the API returns it, for the lib and component tests.
export const candidateSkill = (over: Partial<CandidateSkill> = {}): CandidateSkill => ({
  id: "S1", skill: { id: "K-java", name: "Java", active: true }, category: { id: "G1", name: "Programming" }, level: "advanced",
  experience_months: 36, last_used_year: 2026, source: "resume", status: "claimed", verified_by: null, verified_at: null,
  added_by: { id: "r1", full_name: "Riya Recruiter" }, created_at: "2026-10-08T05:00:00Z", updated_at: "2026-10-08T05:00:00Z", ...over,
});
