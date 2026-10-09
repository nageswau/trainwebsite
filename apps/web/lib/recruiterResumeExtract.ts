// rec-012 (DEC-SCOPE-148): a resume version's extracted suggestions -- types, endpoints, the default ticks (EX6: skills not yet on the
// profile at Intermediate; a profile field only where the candidate has none) and the selection -> body mapping. The API decides every
// rule (duplicates, the Skills Master, the field limits).
import type { SkillLevel } from "@/lib/recruiterCandidateSkills";
import { resumeUrl, type CandidateDetail } from "@/lib/recruiterCandidates";
import type { SkillRef } from "@/lib/recruiterSkills";

export type SuggestedSkill = { skill: SkillRef; category: { id: string; name: string }; matched: string; on_profile: boolean };
export type Extraction = {
  version: number; no_text: boolean; truncated: boolean; text_chars: number; extracted_at: string; skills: SuggestedSkill[];
  qualification: string | null; experience_months: number | null; location: string | null;
  job_titles: string[]; certifications: string[]; industries: string[];
};
export type ProfileKey = "qualification" | "experience_months" | "location";
export type CurrentProfile = Pick<CandidateDetail, ProfileKey>;
export type Selection = { skills: Record<string, boolean>; levels: Record<string, SkillLevel>; fields: Record<ProfileKey, boolean> };
export type ApplyBody = { skills: { skill_id: string; level: SkillLevel }[]; qualification?: string; experience_months?: number; location?: string };
export type ApplyResult = { skills_added: number; fields: string[] };

export const PROFILE_KEYS: ProfileKey[] = ["qualification", "experience_months", "location"];
export const FIELD_LABEL: Record<ProfileKey, string> = { qualification: "Qualification", experience_months: "Total experience", location: "Location" };
export const DEFAULT_LEVEL: SkillLevel = "intermediate";

export const extractUrl = (candidateId: string, version: number) => `${resumeUrl(candidateId, version)}/extract`;
export const applyUrl = (candidateId: string, version: number) => `${resumeUrl(candidateId, version)}/apply`;

export function initialSelection(e: Extraction, current: CurrentProfile): Selection {
  const skills = Object.fromEntries(e.skills.filter((s) => !s.on_profile).map((s) => [s.skill.id, true]));
  const levels = Object.fromEntries(e.skills.map((s) => [s.skill.id, DEFAULT_LEVEL]));
  const fields = Object.fromEntries(PROFILE_KEYS.map((k) => [k, e[k] !== null && (current[k] === null || current[k] === "")])) as Record<ProfileKey, boolean>;
  return { skills, levels, fields };
}

/** Only ticked skills that are not already on the profile, and only ticked fields that have a suggestion. */
export function applyBody(e: Extraction, selection: Selection): ApplyBody {
  const body: ApplyBody = {
    skills: e.skills.filter((s) => !s.on_profile && selection.skills[s.skill.id]).map((s) => ({ skill_id: s.skill.id, level: selection.levels[s.skill.id] ?? DEFAULT_LEVEL })),
  };
  for (const key of PROFILE_KEYS) {
    if (selection.fields[key] && e[key] !== null) Object.assign(body, { [key]: e[key] });
  }
  return body;
}

export const hasChoice = (body: ApplyBody) => body.skills.length > 0 || PROFILE_KEYS.some((k) => k in body);

const joined = (words: string[]) => (words.length > 1 ? `${words.slice(0, -1).join(", ")} and ${words.at(-1)}` : words[0]);

export function savedMessage(result: ApplyResult): string {
  const fields = result.fields.map((f) => (FIELD_LABEL[f as ProfileKey] ?? f).toLowerCase());
  const added = result.skills_added ? `Added ${result.skills_added} skill${result.skills_added === 1 ? "" : "s"}` : "";
  if (added && fields.length) return `${added} and updated ${joined(fields)}.`;
  if (added) return `${added}.`;
  if (fields.length) return `Updated ${joined(fields)}.`;
  return "Nothing changed — the profile already had these values.";
}
