// upc-003 (DEC-SCOPE-119): the Global University Master's types, words, URLs and pickers, shared by its pages and forms.
import type { LookupPage } from "@/lib/lookups";
import { PARTNERSHIP_HEAD_NAV, PARTNERSHIP_NAV, PORTAL_NAV, SUPER_ADMIN_NAV, type NavItem } from "@/lib/navigation";
import { ROLE_LABEL } from "@/lib/partnership";
import type { ManagerOption, ManagerRef } from "@/lib/telecaller";

export type UniversityPermissions = { can_edit: boolean; can_assign: boolean; can_publish: boolean; can_deactivate: boolean };
export type UniversityCountry = { id: string; name: string; iso2: string | null; region: string | null; catalogue_visible: boolean };
export type Ranking = { system: string; other_name: string | null; year: number; rank: string };
export type UniversityRow = {
  id: string; university_code: string; slug: string; name: string; institution_type: string; country: UniversityCountry; city: string;
  priority: string | null; partnership_potential: string | null; primary_manager: ManagerRef | null; backup_manager: ManagerRef | null;
  catalogue_visible: boolean; active: boolean; permissions: UniversityPermissions;
};
export type University = UniversityRow & {
  ownership_type: string | null; state_region: string | null; website: string | null; course_levels: string[]; popular_programs: string[];
  international_office: string | null; existing_relationship: string | null; overview: string; eligibility: string; rankings: Ranking[];
  application_count: number; created_at: string; updated_at: string;
};

export const UNIVERSITIES_URL = "/api/v1/partnership/universities";
export const UNIVERSITIES_PATH = "/partnership/universities";
export const universityUrl = (id: string, action?: string) => `${UNIVERSITIES_URL}/${id}${action ? `/${action}` : ""}`;
export const universityPath = (id: string, edit = false) => `${UNIVERSITIES_PATH}/${id}${edit ? "/edit" : ""}`;

// UM8: who may add a university (the API decides; this only hides the link).
export const CREATOR_ROLES = new Set(["partnership_head", "overseas_admin", "super_admin"]);

export const INSTITUTION_TYPES: Record<string, string> = {
  university: "University", college: "College", institute: "Institute", language_school: "Language School", training_institution: "Training Institution",
};
export const OWNERSHIP_TYPES: Record<string, string> = { public: "Public", private: "Private" };
export const RELATIONSHIPS: Record<string, string> = { new: "New", existing: "Existing" };
export const PRIORITIES = ["A", "B", "C"];
export const POTENTIALS: Record<string, string> = { high: "High", medium: "Medium", low: "Low" };
export const COURSE_LEVELS = ["UG", "PG", "PhD", "Diploma", "Foundation"];
export const RANKING_SYSTEMS = ["QS", "THE", "ARWU", "Other"];
export const REGIONS = ["UK", "Europe", "North America", "Latin America & Caribbean", "Middle East", "Asia", "Oceania", "Africa", "Antarctica"];

export const label = (words: Record<string, string>, key: string | null | undefined) => (key ? words[key] ?? key : "—");
export const visibilityLabel = (u: Pick<UniversityRow, "active" | "catalogue_visible">) =>
  !u.active ? "Inactive" : u.catalogue_visible ? "Public" : "Internal";
export const rankingText = (r: Ranking) => `${r.system === "Other" ? r.other_name : r.system} ${r.year}: ${r.rank}`;

/** The sidebar for whoever reads the master: each role keeps its own shell. */
export function shellFor(role: string): { nav: NavItem[]; roleLabel: string } {
  if (role === "super_admin") return { nav: SUPER_ADMIN_NAV, roleLabel: "Super Administrator" };
  if (role === "overseas_admin") return { nav: PORTAL_NAV["overseas/admin"], roleLabel: "Overseas Administrator" };
  if (role === "partnership_head") return { nav: PARTNERSHIP_HEAD_NAV, roleLabel: ROLE_LABEL.head };
  return { nav: PARTNERSHIP_NAV, roleLabel: ROLE_LABEL.manager };
}

// The list's filters travel in the page URL (shareable, no client state); only these keys are passed on to the API.
export const FILTER_KEYS = ["q", "region", "institution_type", "priority", "partnership_potential", "manager", "visibility", "include_inactive"] as const;
export type Filters = Partial<Record<(typeof FILTER_KEYS)[number] | "offset", string>>;

export function listQuery(filters: Filters, limit: number, offset: number): string {
  const query = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  for (const key of FILTER_KEYS) {
    const value = filters[key]?.trim();
    if (value) query.set(key, value);
  }
  return query.toString();
}

export function pageHref(filters: Filters, offset: number): string {
  const query = new URLSearchParams();
  for (const key of FILTER_KEYS) {
    const value = filters[key]?.trim();
    if (value) query.set(key, value);
  }
  if (offset > 0) query.set("offset", String(offset));
  const text = query.toString();
  return text ? `${UNIVERSITIES_PATH}?${text}` : UNIVERSITIES_PATH;
}

/** Every country, internal ISO rows included (upc-002's lookup): a target university may be anywhere. */
export async function countrySearch(q: string, signal: AbortSignal): Promise<LookupPage> {
  const query = new URLSearchParams({ limit: "20" });
  if (q) query.set("q", q);
  const response = await fetch(`/api/v1/lookups/countries?${query}`, { signal });
  if (!response.ok) throw new Error(`Country search failed (${response.status})`);
  return (await response.json()) as LookupPage;
}

/** The managers this caller may assign (a head's active team; every active manager for super_admin). */
export async function managerSearch(q: string, signal: AbortSignal): Promise<LookupPage> {
  const query = new URLSearchParams({ limit: "20" });
  if (q) query.set("q", q);
  const response = await fetch(`${UNIVERSITIES_URL}/manager-options?${query}`, { signal });
  if (!response.ok) throw new Error(`Manager search failed (${response.status})`);
  const page = (await response.json()) as { items: ManagerOption[]; total: number };
  return { items: page.items.map((m) => ({ id: m.id, label: m.full_name, detail: m.email })), truncated: page.total > page.items.length };
}
