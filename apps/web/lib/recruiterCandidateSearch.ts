// rec-013 (DEC-SCOPE-151): Find Candidates -- types, the URL <-> search state <-> request body mapping, and the facet / card labels. The
// API resolves every skill (aliases, related skills), applies the pool and decides who may search; nothing here filters for security.
// rec-014 (DEC-SCOPE-154): the resume search text rides along as `q` <-> `text`; a card's snippet arrives as plain-text segments.
import type { LookupPage } from "@/lib/lookups";
import { CANDIDATES_URL, STATUSES, type CandidateStatus, type SourceRef } from "@/lib/recruiterCandidates";
import { REQUIREMENTS_URL, type RequirementRow } from "@/lib/recruiterRequirements";

export type Band = "immediate" | "d15" | "d30" | "d31_59" | "d60_plus";
export type ExperienceKey = "y0_1" | "y1_3" | "y3_5" | "y5_plus";
export type CardSkill = { name: string; level: string; status: "claimed" | "verified" | "assessed"; matched: boolean };
export type SnippetSegment = { text: string; hit: boolean };
export type CandidateCard = {
  id: string; candidate_code: string; name: string; preferred_role: string | null; current_company: string | null; experience_months: number | null;
  location: string | null; notice_days: number | null; expected_salary: string | null; source: SourceRef; source_detail: string | null;
  status: CandidateStatus; skills: CardSkill[]; snippet?: SnippetSegment[] | null;
};
export type Facet = { key: string; count: number };
export type SearchResult = {
  items: CandidateCard[]; total: number; limit: number; offset: number;
  facets: { experience: Facet[]; availability: Facet[]; location: { value: string | null; count: number }[] };
  terms: { term: string; skill: { id: string; name: string }; also: string[] }[];
  notice?: string | null;
};
export type SearchState = {
  text: string; all: string[]; any: string[][]; verified: boolean; expMin: string; expMax: string; location: string; availability: Band[]; qualification: string;
  salMin: string; salMax: string; sourceId: string; status: string; offset: number;
};

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
  sourceId: "", status: "", offset: 0,
};

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
    offset: Number.isInteger(offset) && offset > 0 ? offset : 0,
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
  ];
  for (const [key, value] of single) if (value) params.set(key, value);
  state.availability.forEach((band) => params.append("avail", band));
  if (state.offset > 0) params.set("offset", String(state.offset));
  return params;
}

const rupees = (lakhs: string) => Math.round(Number(lakhs) * 100000);

/** The POST body (years → months, a maximum year counting in full; lakhs → rupees), or null with neither a skill nor resume words. */
export function searchBody(state: SearchState): Record<string, unknown> | null {
  const any = state.any.filter((group) => group.length);
  if (!state.all.length && !any.length && !state.text) return null;
  const body: Record<string, unknown> = {};
  if (state.text) body.text = state.text;
  if (state.all.length) body.all = state.all;
  if (any.length) body.any = any;
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
