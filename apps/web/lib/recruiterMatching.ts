// rec-016 (DEC-SCOPE-157): matching candidates for a requirement and the weighted match score. The API decides every match, every
// point and who may shortlist or edit weights (`can_shortlist`, `can_edit_weights`); the page only shows them.
import { LEVELS, type SkillLevel } from "@/lib/recruiterCandidateSkills";
import { REQUIREMENTS_URL } from "@/lib/recruiterRequirements";

// hrc-017 (DEC-SCOPE-388 T5): `min_level` -- only a candidate at that level or above counts. Optional so older fixtures still compile.
export type CriteriaSkill = {
  id: string; name: string; kind: "required" | "preferred"; weight: number; points: number; in_master: boolean; min_level?: SkillLevel | null;
};
// hrc-018 (DEC-SCOPE-390): six admin-weighted factors, optional per-job hard filters and a sentence per factor. The new keys are optional so
// older fixtures still compile; the API always sends them.
export const FACTORS = ["skills", "experience", "qualification", "location", "role", "salary"] as const;
export type FactorKey = (typeof FACTORS)[number];
export const FACTOR_LABEL: Record<FactorKey, string> = {
  skills: "Skills", experience: "Experience", qualification: "Qualification", location: "Location", role: "Role", salary: "Salary & availability",
};
export const HARD_FILTERS = ["experience", "qualification", "location", "salary"] as const;
export type HardFilterKey = (typeof HARD_FILTERS)[number];
export const HARD_FILTER_LABEL: Record<HardFilterKey, string> = {
  experience: "Minimum experience", qualification: "Qualification", location: "Location", salary: "Within the maximum salary",
};
export const HARD_FILTER_NEEDS: Record<HardFilterKey, string> = {
  experience: "Set a minimum experience on the requirement first.", qualification: "Set a qualification on the requirement first.",
  location: "Set an on-site location on the requirement first.", salary: "Set a maximum salary on the requirement first.",
};
export type Factor = { key: FactorKey; label: string; weight: number; applies: boolean; points: number };
export type HardFilters = Record<HardFilterKey, { on: boolean; available: boolean }>;
export type MatchCriteria = {
  skills: CriteriaSkill[];
  experience: { min_months: number | null; max_months: number | null; points: number } | null;
  location: { value: string; points: number } | null;
  factors?: Factor[];
  hard_filters?: HardFilters;
};
export type BreakdownItem = {
  key: string; label: string; kind: "required" | "preferred" | "experience" | "location" | "qualification" | "role" | "salary"; points: number; max: number;
  matched: boolean;
};
export type Explanation = { key: FactorKey; label: string; text: string; points: number; max: number; matched: boolean };
export type MatchRow = {
  id: string; candidate_code: string; name: string; preferred_role: string | null; current_company: string | null; experience_months: number | null;
  location: string | null; notice_days: number | null; status: string; score: number; breakdown: BreakdownItem[];
  explanation?: Explanation[];
  application: { id: string; status: string; status_label: string } | null;
};
export type Matches = {
  criteria: MatchCriteria; reason: "no_skills" | null; items: MatchRow[]; total: number; limit: number; offset: number;
  can_shortlist: boolean; can_edit_weights: boolean; disclaimer?: string;
};

export const MATCH_SETTINGS_URL = "/api/v1/recruiter/match-settings";
export type FactorWeights = Record<FactorKey, number>;
export type MatchSettings = { weights: FactorWeights; defaults: FactorWeights; can_edit: boolean };
export function isMatchSettings(data: unknown): data is MatchSettings {
  const d = data as Partial<MatchSettings> | null;
  return !!d && typeof d.can_edit === "boolean" && FACTORS.every((f) => typeof d.weights?.[f] === "number" && typeof d.defaults?.[f] === "number");
}

export const MATCH_PAGE_SIZE = 20;
export const WEIGHT_MIN = 1;
export const WEIGHT_MAX = 10;
export const matchesUrl = (requirementId: string, offset = 0) =>
  `${REQUIREMENTS_URL}/${encodeURIComponent(requirementId)}/matches?limit=${MATCH_PAGE_SIZE}&offset=${offset}`;
export const weightsUrl = (requirementId: string) => `${REQUIREMENTS_URL}/${encodeURIComponent(requirementId)}/skill-weights`;

/** "Intermediate or above"; empty for any level. */
export function minLevelText(level: SkillLevel | null | undefined): string {
  const found = LEVELS.find((l) => l.key === level);
  return found ? `${found.label} or above` : "";
}

export function isMatches(data: unknown): data is Matches {
  const d = data as Partial<Matches> | null;
  return (
    !!d && Array.isArray(d.items) && typeof d.total === "number" && !!d.criteria && Array.isArray(d.criteria.skills) &&
    typeof d.can_shortlist === "boolean" && typeof d.can_edit_weights === "boolean" &&
    d.items.every((m) => typeof m.id === "string" && typeof m.score === "number" && Array.isArray(m.breakdown))
  );
}
