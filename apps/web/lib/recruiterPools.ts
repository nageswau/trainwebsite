// rec-015 (DEC-SCOPE-159): talent pools -- types, the rule's plain-English summary, the form <-> body mapping (experience in whole years,
// as on Find Candidates) and the Find Candidates link. The API resolves the skills, computes the members and decides who may change a
// pool; nothing here filters for security.
import type { CandidateCard } from "@/lib/recruiterCandidateSearch";
import { distinctTerms, EMPTY_SEARCH, FIND_PATH, GROUP_TERMS, MAX_GROUPS, paramsOf } from "@/lib/recruiterCandidateSearch";

export type Pool = {
  id: string; name: string; all: string[]; any: string[][]; experience_min_months: number | null; experience_max_months: number | null;
  active: boolean; members: number; unavailable: string[]; created_by: { id: string; name: string } | null; updated_at: string;
};
export type PoolList = { items: Pool[]; can_manage: boolean };
export type PoolMembers = { pool: Pool; items: CandidateCard[]; total: number; limit: number; offset: number; can_manage: boolean };
export type PoolForm = { name: string; all: string[]; any: string[][]; expMin: string; expMax: string; active: boolean };

export const POOLS_URL = "/api/v1/recruiter/pools";
export const POOLS_PATH = "/recruiter/pools";
export const MEMBERS_PAGE = 50;
export const poolUrl = (id: string) => `${POOLS_URL}/${encodeURIComponent(id)}`;
export const poolPath = (id: string) => `${POOLS_PATH}/${encodeURIComponent(id)}`;
export const membersUrl = (id: string, offset: number) => `${poolUrl(id)}/candidates?limit=${MEMBERS_PAGE}&offset=${offset}`;

export const EMPTY_POOL: PoolForm = { name: "", all: [], any: [], expMin: "", expMax: "", active: true };
const YEARS = /^\d{1,2}$/;

/** P2: a maximum year covers the whole year ("0" = up to 11 months), the Find Candidates rule. */
const fromYears = (min: string, max: string) => ({
  experience_min_months: min ? Number(min) * 12 : null,
  experience_max_months: max ? Math.min(600, Number(max) * 12 + 11) : null,
});

/** Months back to the whole years the form holds: a minimum rounds up, a maximum covers its last whole year (11 → 0, 23 → 1). */
function years(months: number | null, isMax: boolean): string {
  if (months === null) return "";
  return String(isMax ? Math.max(0, Math.floor((months - 11) / 12)) : Math.ceil(months / 12));
}

export function formOf(pool: Pool): PoolForm {
  return {
    name: pool.name, all: [...pool.all], any: pool.any.map((g) => [...g]), active: pool.active,
    expMin: years(pool.experience_min_months, false), expMax: years(pool.experience_max_months, true),
  };
}

/** The POST / PATCH body. A blank year clears that bound; empty "at least one of" groups are dropped. */
export function poolBody(form: PoolForm, includeActive: boolean): Record<string, unknown> {
  const body: Record<string, unknown> = {
    name: form.name.replace(/\s+/g, " ").trim(),
    all: distinctTerms(form.all),
    any: form.any.map((g) => distinctTerms(g, GROUP_TERMS)).filter((g) => g.length).slice(0, MAX_GROUPS),
    ...fromYears(form.expMin, form.expMax),
  };
  if (includeActive) body.active = form.active;
  return body;
}

/** A year field the API would refuse, worded for the form; null when the years are fine. */
export function yearsProblem(form: PoolForm): string | null {
  if ((form.expMin && !YEARS.test(form.expMin)) || (form.expMax && !YEARS.test(form.expMax))) return "Enter experience as whole years (0–50).";
  if (form.expMin && form.expMax && Number(form.expMin) > Number(form.expMax)) return "The minimum experience cannot be above the maximum.";
  return null;
}

const yearWord = (n: string) => (n === "1" ? "year" : "years");

/** The band in the form's whole years: "Under 1 year", "1+ year", "Up to 3 years", "2–5 years" (of experience). */
function experienceText(min: number | null, max: number | null): string | null {
  if (min === null && max === null) return null;
  const low = years(min, false);
  const high = years(max, true);
  if (high === "0") return "Under 1 year of experience";
  if (!high) return `${low}+ ${yearWord(low)} of experience`;
  if (!low || low === "0") return `Up to ${high} ${yearWord(high)} of experience`;
  return `${low}–${high} years of experience`;
}

/** The rule in one line: "Java and Spring · AWS or Azure · Under 1 year of experience". */
export function ruleText(pool: Pick<Pool, "all" | "any" | "experience_min_months" | "experience_max_months">): string {
  const parts = [
    pool.all.join(" and "),
    ...pool.any.map((g) => (g.length > 1 ? `${g.slice(0, -1).join(", ")} or ${g[g.length - 1]}` : g[0])),
    experienceText(pool.experience_min_months, pool.experience_max_months),
  ].filter(Boolean);
  return parts.join(" · ");
}

/** Find Candidates with the pool's skills and band filled in, to refine and shortlist. A skill no longer in the Skills Master is left out
 *  (Find would refuse it, QA-03). Null for a pool without skills (Find needs one) or one that matches nobody (an unavailable "all" skill,
 *  or an "at least one of" group with nothing left). */
export function findHref(pool: Pool): string | null {
  const gone = new Set(pool.unavailable.map((t) => t.toLowerCase()));
  const live = (terms: string[]) => terms.filter((t) => !gone.has(t.toLowerCase()));
  const any = pool.any.map(live);
  if (live(pool.all).length < pool.all.length || any.some((g) => !g.length) || (!pool.all.length && !any.length)) return null;
  const form = formOf(pool);
  return `${FIND_PATH}?${paramsOf({ ...EMPTY_SEARCH, all: pool.all, any, expMin: form.expMin, expMax: form.expMax })}`;
}

export function isPool(data: unknown): data is Pool {
  const d = data as Partial<Pool> | null;
  return !!d && typeof d.id === "string" && typeof d.name === "string" && Array.isArray(d.all) && Array.isArray(d.any) && typeof d.members === "number";
}

export function isPoolList(data: unknown): data is PoolList {
  const d = data as Partial<PoolList> | null;
  return !!d && Array.isArray(d.items) && typeof d.can_manage === "boolean";
}

export function isPoolMembers(data: unknown): data is PoolMembers {
  const d = data as Partial<PoolMembers> | null;
  return !!d && isPool(d.pool) && Array.isArray(d.items) && typeof d.total === "number" && typeof d.can_manage === "boolean";
}
