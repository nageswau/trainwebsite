// rec-011 (DEC-SCOPE-135): a candidate's skills -- types, endpoints, labels (SK1 levels, the six S2-§17 sources, the three statuses)
// and the form <-> body mapping. Labels are display only; the API decides who may write and every rule (duplicates, the Skills Master).
import { CANDIDATES_URL } from "@/lib/recruiterCandidates";
import type { SkillRef } from "@/lib/recruiterSkills";
import type { PersonRef } from "@/lib/telecallerLeads";

export type SkillLevel = "beginner" | "intermediate" | "advanced" | "expert";
export type SkillSource = "resume" | "interview_verified" | "assessment_verified" | "course_completed" | "certification" | "employer_verified";
export type SkillStatus = "claimed" | "verified" | "assessed";
export type CandidateSkill = {
  id: string; skill: SkillRef; category: { id: string; name: string }; level: SkillLevel; experience_months: number | null;
  last_used_year: number | null; source: SkillSource; status: SkillStatus; verified_by: PersonRef | null; verified_at: string | null;
  added_by: PersonRef | null; created_at: string; updated_at: string;
};
export type CandidateSkillList = { items: CandidateSkill[]; can_edit: boolean };
export type SkillForm = { skill: string; level: SkillLevel | ""; experience_months: string; last_used_year: string; source: SkillSource };

export const candidateSkillsUrl = (candidateId: string, skillId?: string, suffix = "") =>
  `${CANDIDATES_URL}/${encodeURIComponent(candidateId)}/skills${skillId ? `/${encodeURIComponent(skillId)}` : ""}${suffix}`;

export const LEVELS: { key: SkillLevel; label: string }[] = [
  { key: "beginner", label: "Beginner" }, { key: "intermediate", label: "Intermediate" }, { key: "advanced", label: "Advanced" }, { key: "expert", label: "Expert" },
];
export const SOURCES: { key: SkillSource; label: string }[] = [
  { key: "resume", label: "Resume" }, { key: "interview_verified", label: "Interview verified" },
  { key: "assessment_verified", label: "Assessment verified" }, { key: "course_completed", label: "Course completed" },
  { key: "certification", label: "Certification" }, { key: "employer_verified", label: "Employer verified" },
];
export const STATUS_LABEL: Record<SkillStatus, string> = { claimed: "Claimed", verified: "Verified", assessed: "Assessed" };
export const LEVEL_LABEL: Record<string, string> = Object.fromEntries(LEVELS.map((l) => [l.key, l.label]));
export const SOURCE_LABEL: Record<string, string> = Object.fromEntries(SOURCES.map((s) => [s.key, s.label]));

export const EMPTY_SKILL_FORM: SkillForm = { skill: "", level: "", experience_months: "", last_used_year: "", source: "resume" };

export const formOf = (s: CandidateSkill): SkillForm => ({
  skill: s.skill.name, level: s.level, experience_months: s.experience_months?.toString() ?? "", last_used_year: s.last_used_year?.toString() ?? "", source: s.source,
});

const whole = (value: string) => (value.trim() === "" ? null : Number(value.trim()));

/** A blank number is null (clears it on an edit); an edit never sends the skill -- a different skill is a remove and an add. */
export function toBody(form: SkillForm, adding: boolean): Record<string, unknown> {
  const body = { level: form.level, experience_months: whole(form.experience_months), last_used_year: whole(form.last_used_year), source: form.source };
  return adding ? { skill: form.skill, ...body } : body;
}
