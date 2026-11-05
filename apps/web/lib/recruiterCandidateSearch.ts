// rec-013 (DEC-SCOPE-151): Find Candidates -- types, the URL <-> search state <-> request body mapping, and the facet / card labels. The
// API resolves every skill (aliases, related skills), applies the pool and decides who may search; nothing here filters for security.
// rec-014 (DEC-SCOPE-154): the resume search text rides along as `q` <-> `text`; a card's snippet arrives as plain-text segments.
// hrc-019 (DEC-SCOPE-399): the §8 filter groups are one table (FILTERS) that drives the URL, the body, the panel and the active-filter
// chips; `pref` (nice-to-have skills) and `sort` sit beside the skills and the results.
import { DOCUMENT_TYPES } from "@/lib/candidateDocuments";
import type { LookupPage } from "@/lib/lookups";
import { LEVELS } from "@/lib/recruiterCandidateSkills";
import {
  CANDIDATES_URL, EMPLOYMENT_TYPES, ENGAGEMENTS, engagementOf, STATUSES, WORK_MODES, type CandidateEngagement, type CandidateStatus, type SourceRef,
} from "@/lib/recruiterCandidates";
import { REQUIREMENTS_URL, type RequirementRow } from "@/lib/recruiterRequirements";

export type Band = "immediate" | "d15" | "d30" | "d31_59" | "d60_plus";
export type ExperienceKey = "y0_1" | "y1_3" | "y3_5" | "y5_plus";
export type CardSkill = { name: string; level: string; status: "claimed" | "verified" | "assessed"; matched: boolean };
export type SnippetSegment = { text: string; hit: boolean };
export type CandidateCard = {
  id: string; candidate_code: string; name: string; preferred_role: string | null; current_company: string | null; experience_months: number | null;
  location: string | null; notice_days: number | null; expected_salary?: string | null; expected_annual_inr?: string | null; source: SourceRef; source_detail: string | null;
  status: CandidateStatus; skills: CardSkill[]; snippet?: SnippetSegment[] | null;
  engagement?: CandidateEngagement | null; // hrc-021
  match?: { required: MatchLine[]; preferred: MatchLine[] }; // hrc-019 S11
};
export type MatchLine = { term: string; skill: string | null; held: boolean };
export type Facet = { key: string; count: number };
export type SearchResult = {
  items: CandidateCard[]; total: number; limit: number; offset: number;
  facets: { experience: Facet[]; availability: Facet[]; location: { value: string | null; count: number }[] };
  terms: { term: string; skill: { id: string; name: string }; also: string[] }[];
  notice?: string | null;
};
export type SearchState = {
  text: string; all: string[]; any: string[][]; verified: boolean; expMin: string; expMax: string; location: string; availability: Band[]; qualification: string;
  salMin: string; salMax: string; sourceId: string; status: string; engagement: string; offset: number;
  preferred: string[]; more: Record<string, string[]>; sort: SortKey; // hrc-019: `more` is keyed by FILTERS[].param
};
export type SortKey = "relevance" | "match" | "experience" | "package" | "registered" | "activity" | "completeness";

export const SEARCH_URL = `${CANDIDATES_URL}/search`;
export const FIND_PATH = "/recruiter/find-candidates";
export const PAGE_SIZE = 50;
export const MAX_TERMS = 20;
export const MAX_GROUPS = 5;
export const GROUP_TERMS = 10;
export const OTHER_LOCATION = "__other__";
export const TEXT_MAX = 200;

export const BANDS: { key: Band; label: string }[] = [
  { key: "immediate", label: "Immediate" }, { key: "d15", label: "15 days" }, { key: "d30", label: "30 days" },
  { key: "d31_59", label: "31–59 days" }, { key: "d60_plus", label: "60+ days" },
];
export const EXPERIENCE_LABEL: Record<string, string> = { y0_1: "0–1 year", y1_3: "1–3 years", y3_5: "3–5 years", y5_plus: "5+ years", none: "Not recorded" };
export const BAND_LABEL: Record<string, string> = { ...Object.fromEntries(BANDS.map((b) => [b.key, b.label])), none: "Not recorded" };
// F1 in whole years, as the year fields hold them (a maximum year covers the whole year: "2" = up to 2 yr 11 mo).
const EXPERIENCE_YEARS: Record<ExperienceKey, [string, string]> = { y0_1: ["0", "0"], y1_3: ["1", "2"], y3_5: ["3", "4"], y5_plus: ["5", ""] };

export const EMPTY_SEARCH: SearchState = {
  text: "", all: [], any: [], verified: false, expMin: "", expMax: "", location: "", availability: [], qualification: "", salMin: "", salMax: "",
  sourceId: "", status: "", engagement: "", offset: 0, preferred: [], more: {}, sort: "relevance",
};

// --- hrc-019 (S3-S10) --------------------------------------------------------------------------------------------------------------
export const PREFERRED_MAX = 10;
export const CATEGORIES_MAX = 10;
export type FilterGroup = "skills" | "education" | "experience" | "location" | "preferences" | "package" | "recruitment" | "records";
type Kind = "text" | "years" | "lakhs" | "year" | "cgpa" | "flag" | "yesno" | "multi" | "choice" | "date" | "category";
type Option = { key: string; label: string };
export type FilterSpec = {
  param: string; body: string; label: string; group: FilterGroup; kind: Kind; options?: Option[];
  max?: boolean; // a "to" year bound covers the whole year (rec-013's rule)
  package?: boolean; // S9: shown and sent only with the compensation grant
};
export const APPLICATION_STAGES: Option[] = [
  { key: "sourced", label: "Sourced" }, { key: "screened", label: "Screened" }, { key: "shortlisted", label: "Shortlisted" },
  { key: "profile_shared", label: "Profile shared" }, { key: "interview", label: "Interview" }, { key: "selected", label: "Selected" },
  { key: "joined", label: "Joined" }, { key: "rejected", label: "Rejected" }, { key: "withdrawn", label: "Withdrawn" },
];
const f = (param: string, body: string, label: string, group: FilterGroup, kind: Kind, extra: Partial<FilterSpec> = {}): FilterSpec =>
  ({ param, body, label, group, kind, ...extra });
export const FILTERS: FilterSpec[] = [
  f("cat", "category_ids", "Skill category", "skills", "category"),
  f("level", "min_level", "Minimum skill level", "skills", "choice", { options: LEVELS }),
  f("skill_yrs", "skill_min_months", "Years on each skill", "skills", "years"),
  f("degree", "degree", "Degree", "education", "text"),
  f("spec", "specialisation", "Specialisation", "education", "text"),
  f("inst", "institution", "Institution", "education", "text"),
  f("year_min", "passing_year_min", "Passing year from", "education", "year"),
  f("year_max", "passing_year_max", "Passing year to", "education", "year"),
  f("cgpa_min", "cgpa_min", "CGPA from", "education", "cgpa"),
  f("cgpa_max", "cgpa_max", "CGPA to", "education", "cgpa"),
  f("fresher", "fresher", "Freshers only", "experience", "flag"),
  f("rel_min", "relevant_min_months", "Relevant experience from (years)", "experience", "years"),
  f("rel_max", "relevant_max_months", "Relevant experience to (years)", "experience", "years", { max: true }),
  f("designation", "designation", "Designation", "experience", "text"),
  f("industry", "industry", "Industry", "experience", "text"),
  f("emp_type", "employment_types", "Employment type", "experience", "multi", { options: EMPLOYMENT_TYPES }),
  f("country", "country", "Country", "location", "text"),
  f("state", "state", "State", "location", "text"),
  f("city", "city", "City", "location", "text"),
  f("pref_loc", "preferred_location", "Preferred location", "location", "text"),
  f("relocate", "willing_to_relocate", "Willing to relocate", "location", "flag"),
  f("work_mode", "work_modes", "Work mode", "location", "multi", { options: WORK_MODES }),
  f("pref_role", "preferred_role", "Preferred role", "preferences", "text"),
  f("pref_emp", "preferred_employment_types", "Preferred employment type", "preferences", "multi", { options: EMPLOYMENT_TYPES }),
  f("owner", "owner", "Primary recruiter", "recruitment", "choice", { options: [{ key: "me", label: "Me" }, { key: "unassigned", label: "Nobody yet" }] }),
  f("reg_from", "registered_from", "Registered from", "recruitment", "date"),
  f("reg_to", "registered_to", "Registered to", "recruitment", "date"),
  f("resume", "has_resume", "Resume", "records", "yesno", { options: [{ key: "1", label: "Has a resume" }, { key: "0", label: "No resume" }] }),
  f("doc", "document_types", "Has document", "records", "multi", { options: DOCUMENT_TYPES.map((d) => ({ key: d.value, label: d.label })) }),
  f("app", "application_statuses", "Application stage", "records", "multi", { options: APPLICATION_STAGES }),
  f("interviewed", "interviewed", "Has been interviewed", "records", "flag"),
  f("cur_min", "current_min", "Current salary from (₹ lakhs a year)", "package", "lakhs", { package: true }),
  f("cur_max", "current_max", "Current salary to (₹ lakhs a year)", "package", "lakhs", { package: true }),
  f("min_min", "minimum_min", "Minimum acceptable from (₹ lakhs a year)", "package", "lakhs", { package: true }),
  f("min_max", "minimum_max", "Minimum acceptable to (₹ lakhs a year)", "package", "lakhs", { package: true }),
  f("sal_unknown", "package_unknown", "Include unknown salary", "package", "flag", { package: true }),
];
export const SORTS: { key: SortKey; label: string; package?: boolean }[] = [
  { key: "relevance", label: "Relevance" }, { key: "match", label: "Most matching skills" }, { key: "experience", label: "Most experience" },
  { key: "package", label: "Lowest expected salary", package: true }, { key: "registered", label: "Newest registration" },
  { key: "activity", label: "Most recent activity" }, { key: "completeness", label: "Most complete profile" },
];
export const sortOptions = (compensation: boolean) => SORTS.filter((s) => compensation || !s.package);

const DATE = /^\d{4}-\d{2}-\d{2}$/;
const CGPA = /^\d{1,2}(\.\d{1,2})?$/;
/** One URL value of a filter, or "" when the API would refuse it (a hand-edited URL is dropped, rec-013's rule). */
function valid(spec: FilterSpec, raw: string): string {
  const value = raw.trim();
  switch (spec.kind) {
    case "text": return value.replace(/\s+/g, " ").slice(0, 120);
    case "years": return pick(value, YEARS);
    case "lakhs": return pick(value, LAKHS);
    case "year": return /^\d{4}$/.test(value) && Number(value) >= 1950 && Number(value) <= 2100 ? value : "";
    case "cgpa": return CGPA.test(value) && Number(value) <= 10 ? value : "";
    case "flag": return value === "1" ? value : "";
    case "date": return DATE.test(value) && !Number.isNaN(Date.parse(value)) ? value : "";
    case "category": return pick(value, UUID);
    default: return spec.options?.some((o) => o.key === value) ? value : "";
  }
}
const many = (spec: FilterSpec) => spec.kind === "multi" || spec.kind === "category";

function moreOf(params: URLSearchParams): Record<string, string[]> {
  const out: Record<string, string[]> = {};
  for (const spec of FILTERS) {
    const values = [...new Set(params.getAll(spec.param).map((v) => valid(spec, v)).filter(Boolean))];
    const kept = many(spec) ? values.slice(0, CATEGORIES_MAX) : values.slice(0, 1);
    if (kept.length) out[spec.param] = kept;
  }
  return out;
}

function bodyValue(spec: FilterSpec, values: string[]): unknown {
  const [value] = values;
  switch (spec.kind) {
    case "multi": case "category": return values;
    case "years": return spec.max ? Math.min(600, Number(value) * 12 + 11) : Number(value) * 12;
    case "lakhs": return rupees(value);
    case "year": case "cgpa": return Number(value);
    case "flag": return true;
    case "yesno": return value === "1";
    default: return value;
  }
}

/** S11: the card's "why matched" line. */
export function matchSummary(match: CandidateCard["match"]): { matched: string[]; missing: string[] } | null {
  if (!match || (!match.required.length && !match.preferred.length)) return null;
  const name = (m: MatchLine) => m.skill ?? m.term;
  return { matched: [...match.required, ...match.preferred].filter((m) => m.held).map(name), missing: match.preferred.filter((m) => !m.held).map(name) };
}

export type ActiveFilter = { key: string; label: string; clear: (state: SearchState) => SearchState };
const short = (label: string) => label.replace(/ \(.*\)$/, "");

/** AC2: one removable chip per active filter (skills and resume words have their own chips); clearing one goes back to page 1. */
export function activeFilters(state: SearchState, lookup: { categories: Record<string, string>; sources?: Record<string, string> }): ActiveFilter[] {
  const out: ActiveFilter[] = [];
  const own = (key: string, label: string, changes: Partial<SearchState>) => out.push({ key, label, clear: (s) => ({ ...s, ...changes, offset: 0 }) });
  if (state.verified) own("verified", "Verified skills only", { verified: false });
  if (state.expMin) own("exp_min", `Experience from: ${state.expMin} yr`, { expMin: "" });
  if (state.expMax) own("exp_max", `Experience to: ${state.expMax} yr`, { expMax: "" });
  if (state.location) own("location", `Location: ${state.location}`, { location: "" });
  if (state.qualification) own("qualification", `Qualification: ${state.qualification}`, { qualification: "" });
  for (const band of state.availability) {
    out.push({ key: `avail:${band}`, label: `Availability: ${BAND_LABEL[band]}`, clear: (s) => ({ ...s, availability: s.availability.filter((b) => b !== band), offset: 0 }) });
  }
  if (state.salMin) own("sal_min", `Expected salary from: ₹${state.salMin} L`, { salMin: "" });
  if (state.salMax) own("sal_max", `Expected salary to: ₹${state.salMax} L`, { salMax: "" });
  if (state.sourceId) own("source_id", `Source: ${lookup.sources?.[state.sourceId] ?? "Selected source"}`, { sourceId: "" });
  if (state.status) own("status", `Status: ${STATUSES.find((s) => s.key === state.status)?.label ?? state.status}`, { status: "" });
  if (state.engagement) own("engagement", `Engagement: ${ENGAGEMENTS.find((e) => e.key === state.engagement)?.label ?? state.engagement}`, { engagement: "" });
  for (const spec of FILTERS) {
    for (const value of state.more[spec.param] ?? []) {
      const shown = spec.kind === "category" ? lookup.categories[value] ?? "Selected category"
        : spec.options ? spec.options.find((o) => o.key === value)?.label ?? value
        : spec.kind === "years" ? `${value} yr` : spec.kind === "lakhs" ? `₹${value} L` : value;
      out.push({
        key: `${spec.param}:${value}`, label: spec.kind === "flag" ? spec.label : `${short(spec.label)}: ${shown}`,
        clear: (s) => {
          const rest = (s.more[spec.param] ?? []).filter((v) => v !== value);
          const more = { ...s.more };
          if (rest.length) more[spec.param] = rest;
          else delete more[spec.param];
          return { ...s, more, offset: 0 };
        },
      });
    }
  }
  return out;
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const YEARS = /^\d{1,2}$/;
const LAKHS = /^\d{1,7}(\.\d{1,2})?$/;

/** The API's own rule for the resume search: whitespace collapsed and trimmed, at most TEXT_MAX characters. */
export const searchText = (raw: string) => raw.replace(/\s+/g, " ").trim().slice(0, TEXT_MAX);

/** Trimmed, blank-free and case-insensitively distinct, capped -- the API's own rule for one list of skills. */
export function distinctTerms(values: string[], cap = MAX_TERMS): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of values) {
    const term = raw.replace(/\s+/g, " ").trim().slice(0, 120);
    if (term && !seen.has(term.toLowerCase()) && out.length < cap) {
      seen.add(term.toLowerCase());
      out.push(term);
    }
  }
  return out;
}

const pick = (value: string | null, test: RegExp) => (value && test.test(value) ? value : "");

/** The search held in the URL (refresh and Back keep it). A hand-edited value the API would refuse is dropped. */
export function stateOf(params: URLSearchParams): SearchState {
  const any: string[][] = [];
  for (let n = 1; n <= MAX_GROUPS; n++) {
    const group = distinctTerms(params.getAll(`any${n}`), GROUP_TERMS);
    if (group.length) any.push(group);
  }
  const offset = Number(params.get("offset"));
  return {
    text: searchText(params.get("q") ?? ""),
    all: distinctTerms(params.getAll("all"), MAX_TERMS),
    any,
    verified: params.get("verified") === "1",
    expMin: pick(params.get("exp_min"), YEARS),
    expMax: pick(params.get("exp_max"), YEARS),
    location: (params.get("location") ?? "").trim().slice(0, 120),
    availability: BANDS.map((b) => b.key).filter((key) => params.getAll("avail").includes(key)),
    qualification: (params.get("qualification") ?? "").trim().slice(0, 120),
    salMin: pick(params.get("sal_min"), LAKHS),
    salMax: pick(params.get("sal_max"), LAKHS),
    sourceId: pick(params.get("source_id"), UUID),
    status: STATUSES.some((s) => s.key === params.get("status")) ? params.get("status")! : "",
    engagement: engagementOf(params.get("engagement")), // hrc-021
    offset: Number.isInteger(offset) && offset > 0 ? offset : 0,
    preferred: distinctTerms(params.getAll("pref"), PREFERRED_MAX), // hrc-019
    more: moreOf(params),
    sort: SORTS.find((s) => s.key === params.get("sort"))?.key ?? "relevance",
  };
}

export function paramsOf(state: SearchState): URLSearchParams {
  const params = new URLSearchParams();
  if (state.text) params.set("q", state.text);
  state.all.forEach((term) => params.append("all", term));
  state.any.filter((group) => group.length).forEach((group, i) => group.forEach((term) => params.append(`any${i + 1}`, term)));
  if (state.verified) params.set("verified", "1");
  const single: [string, string][] = [
    ["exp_min", state.expMin], ["exp_max", state.expMax], ["location", state.location], ["qualification", state.qualification],
    ["sal_min", state.salMin], ["sal_max", state.salMax], ["source_id", state.sourceId], ["status", state.status],
    ["engagement", state.engagement],
  ];
  for (const [key, value] of single) if (value) params.set(key, value);
  state.availability.forEach((band) => params.append("avail", band));
  state.preferred.forEach((term) => params.append("pref", term)); // hrc-019
  for (const spec of FILTERS) (state.more[spec.param] ?? []).forEach((value) => params.append(spec.param, value));
  if (state.sort !== "relevance") params.set("sort", state.sort);
  if (state.offset > 0) params.set("offset", String(state.offset));
  return params;
}

const rupees = (lakhs: string) => Math.round(Number(lakhs) * 100000);

/** The POST body (years → months, a maximum year counting in full; lakhs → rupees), or null with neither a skill nor resume words. */
export function searchBody(state: SearchState): Record<string, unknown> | null {
  const any = state.any.filter((group) => group.length);
  if (!state.all.length && !any.length && !state.text && !state.preferred.length && !state.more.cat?.length) return null; // hrc-019 S3
  const body: Record<string, unknown> = {};
  if (state.text) body.text = state.text;
  if (state.all.length) body.all = state.all;
  if (any.length) body.any = any;
  if (state.preferred.length) body.preferred = state.preferred;
  for (const spec of FILTERS) if (state.more[spec.param]?.length) body[spec.body] = bodyValue(spec, state.more[spec.param]);
  if (state.sort !== "relevance") body.sort = state.sort;
  if (state.verified) body.verified_only = true;
  if (state.expMin) body.experience_min_months = Number(state.expMin) * 12;
  if (state.expMax) body.experience_max_months = Math.min(600, Number(state.expMax) * 12 + 11);
  if (state.location) body.location = state.location;
  if (state.availability.length) body.availability = state.availability;
  if (state.qualification) body.qualification = state.qualification;
  if (state.salMin) body.salary_min = rupees(state.salMin);
  if (state.salMax) body.salary_max = rupees(state.salMax);
  if (state.sourceId) body.source_id = state.sourceId;
  if (state.status) body.status = state.status;
  if (state.engagement) body.engagement = state.engagement;
  return body;
}

export function experienceBand(key: string): { expMin: string; expMax: string } | null {
  const years = EXPERIENCE_YEARS[key as ExperienceKey];
  return years ? { expMin: years[0], expMax: years[1] } : null;
}

export function availabilityOf(days: number | null): string {
  if (days === null || days === undefined) return "—";
  return days === 0 ? "Immediate" : `${days} days`;
}

/** Expected salary per year in lakhs (₹8 LPA), the S2-§19 card wording. */
export function salaryText(inr: string | null): string {
  if (inr === null || inr === undefined || inr === "") return "—";
  const lakhs = Math.round((Number(inr) / 100000) * 100) / 100;
  return `₹${lakhs} LPA`;
}

/** FS3: the 422 detail of a term that is no skill, with the API's suggestions; null for any other detail. */
export function unknownSkill(detail: unknown): { term: string; suggestions: string[] } | null {
  const d = detail as { code?: unknown; term?: unknown; suggestions?: unknown } | null;
  if (!d || typeof d !== "object" || d.code !== "unknown_skill" || typeof d.term !== "string") return null;
  return { term: d.term, suggestions: Array.isArray(d.suggestions) ? d.suggestions.filter((s): s is string => typeof s === "string") : [] };
}

export function isSearchResult(data: unknown): data is SearchResult {
  const d = data as Partial<SearchResult> | null;
  return !!d && Array.isArray(d.items) && typeof d.total === "number" && !!d.facets && Array.isArray(d.terms);
}

/** The "Shortlist into" picker: the caller's live requirements (rec-007 scope), closed and cancelled ones left out. */
export async function requirementSearch(q: string, signal: AbortSignal): Promise<LookupPage> {
  const query = new URLSearchParams({ limit: "20" });
  if (q) query.set("q", q);
  const response = await fetch(`${REQUIREMENTS_URL}?${query}`, { signal });
  if (!response.ok) throw new Error(`Requirement search failed (${response.status})`);
  const page = (await response.json()) as { items: RequirementRow[]; total: number };
  const live = page.items.filter((r) => r.status !== "closed" && r.status !== "cancelled");
  return { items: live.map((r) => ({ id: r.id, label: `${r.title} — ${r.company.name}`, detail: r.code })), truncated: page.total > page.items.length };
}
