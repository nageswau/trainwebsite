// rec-016 (DEC-SCOPE-157): matching candidates for a requirement and the weighted match score. The API decides every match, every
// point and who may shortlist or edit weights (`can_shortlist`, `can_edit_weights`); the page only shows them.
import { REQUIREMENTS_URL } from "@/lib/recruiterRequirements";

export type CriteriaSkill = { id: string; name: string; kind: "required" | "preferred"; weight: number; points: number; in_master: boolean };
export type MatchCriteria = {
  skills: CriteriaSkill[];
  experience: { min_months: number | null; max_months: number | null; points: number } | null;
  location: { value: string; points: number } | null;
};
export type BreakdownItem = { key: string; label: string; kind: "required" | "preferred" | "experience" | "location"; points: number; max: number; matched: boolean };
export type MatchRow = {
  id: string; candidate_code: string; name: string; preferred_role: string | null; current_company: string | null; experience_months: number | null;
  location: string | null; notice_days: number | null; status: string; score: number; breakdown: BreakdownItem[];
  application: { id: string; status: string; status_label: string } | null;
};
export type Matches = {
  criteria: MatchCriteria; reason: "no_skills" | null; items: MatchRow[]; total: number; limit: number; offset: number;
  can_shortlist: boolean; can_edit_weights: boolean;
};

export const MATCH_PAGE_SIZE = 20;
export const WEIGHT_MIN = 1;
export const WEIGHT_MAX = 10;
export const matchesUrl = (requirementId: string, offset = 0) =>
  `${REQUIREMENTS_URL}/${encodeURIComponent(requirementId)}/matches?limit=${MATCH_PAGE_SIZE}&offset=${offset}`;
export const weightsUrl = (requirementId: string) => `${REQUIREMENTS_URL}/${encodeURIComponent(requirementId)}/skill-weights`;

export function isMatches(data: unknown): data is Matches {
  const d = data as Partial<Matches> | null;
  return (
    !!d && Array.isArray(d.items) && typeof d.total === "number" && !!d.criteria && Array.isArray(d.criteria.skills) &&
    typeof d.can_shortlist === "boolean" && typeof d.can_edit_weights === "boolean" &&
    d.items.every((m) => typeof m.id === "string" && typeof m.score === "number" && Array.isArray(m.breakdown))
  );
}
