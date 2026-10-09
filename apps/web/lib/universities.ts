// upc-003 (DEC-SCOPE-120): the Global University Master's types, words, URLs and pickers, shared by its pages and forms.
import type { UniversityFollowUpData } from "@/lib/partnershipTasks";
import type { LookupPage } from "@/lib/lookups";
import type { UniversityPipeline } from "@/lib/partnershipPipeline";
import { PARTNERSHIP_HEAD_NAV, PARTNERSHIP_NAV, PORTAL_NAV, SUPER_ADMIN_NAV, type NavItem } from "@/lib/navigation";
import { ROLE_LABEL } from "@/lib/partnership";
import type { ManagerOption, ManagerRef } from "@/lib/telecaller";

export type UniversityPermissions = {
  can_edit: boolean; can_assign: boolean; can_publish: boolean; can_deactivate: boolean; can_edit_contacts: boolean; can_manage_documents: boolean; can_move_stage: boolean;
  can_reopen: boolean;
};
export type UniversityCountry = { id: string; name: string; iso2: string | null; region: string | null; catalogue_visible: boolean };
export type Ranking = { system: string; other_name: string | null; year: number; rank: string };
export type UniversityRow = {
  id: string; university_code: string; slug: string; name: string; institution_type: string; country: UniversityCountry; city: string;
  priority: string | null; partnership_potential: string | null; relationship_strength: string | null; primary_manager: ManagerRef | null; backup_manager: ManagerRef | null;
  catalogue_visible: boolean; active: boolean; stage: string; stage_label: string; lost: boolean; permissions: UniversityPermissions;
};
export type University = UniversityRow & {
  ownership_type: string | null; state_region: string | null; website: string | null; course_levels: string[]; popular_programs: string[];
  international_office: string | null; existing_relationship: string | null; overview: string; eligibility: string; rankings: Ranking[];
  application_count: number; linked_bdm_organizations: LinkedBdmOrganization[]; created_at: string; updated_at: string; pipeline: UniversityPipeline;
  follow_up: UniversityFollowUpData; // upc-020 TK14/TK15
};
// upc-004: a BDM University organization linked to this master record (text only: partnership roles cannot open BDM records).
export type LinkedBdmOrganization = { id: string; code: string; name: string; city: string; bdm_type: string; assigned_bdm_name: string; archived: boolean };
// upc-004 UD5: the duplicate panel's fields, the same for the master forms and the BDM create form.
export type UniversityMatch = {
  id: string; university_code: string; name: string; country: { id: string; name: string }; city: string; active: boolean; catalogue_visible: boolean;
  existing_relationship: string | null; primary_manager: ManagerRef | null; backup_manager: ManagerRef | null;
};
export type UniversityMatchPage = { items: UniversityMatch[]; total: number };
export type UniversityDuplicate = { message: string; matches: UniversityMatch[]; total: number; can_override: boolean };

export const UNIVERSITIES_URL = "/api/v1/partnership/universities";
export const UNIVERSITIES_PATH = "/partnership/universities";
export const universityUrl = (id: string, action?: string) => `${UNIVERSITIES_URL}/${id}${action ? `/${action}` : ""}`;
export const universityPath = (id: string, edit = false) => `${UNIVERSITIES_PATH}/${id}${edit ? "/edit" : ""}`;

/** upc-004 UD6: search before adding. `excludeId` leaves out the university being edited. */
export function duplicatesUrl(name: string, countryId: string, excludeId?: string): string {
  const query = new URLSearchParams({ name, country_id: countryId });
  if (excludeId) query.set("exclude_id", excludeId);
  return `${UNIVERSITIES_URL}/duplicates?${query}`;
}

/** The 409 a save into an existing name + country answers (UD2), or null for any other detail. */
export function universityDuplicate(detail: unknown): UniversityDuplicate | null {
  const d = detail as (Partial<UniversityDuplicate> & { code?: string }) | null;
  if (!d || typeof d !== "object" || d.code !== "university_duplicate" || !Array.isArray(d.matches)) return null;
  return { message: String(d.message ?? ""), matches: d.matches, total: Number(d.total ?? d.matches.length), can_override: d.can_override === true };
}

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
// upc-006 (DEC-SCOPE-123): §11's relationship status exactly (CT4) and the channels a contact record holds (CT3).
export const RELATIONSHIP_STRENGTHS: Record<string, string> = {
  new: "New", developing: "Developing", good: "Good", strong: "Strong", strategic: "Strategic", at_risk: "At Risk", dormant: "Dormant",
};
export const CONTACT_CHANNELS: Record<string, string> = { email: "Email", phone: "Phone", whatsapp: "WhatsApp", linkedin: "LinkedIn" };
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
export const FILTER_KEYS = [
  "q", "region", "institution_type", "priority", "partnership_potential", "relationship_strength", "manager", "visibility", "include_inactive",
] as const;
export type Filters = Partial<Record<(typeof FILTER_KEYS)[number] | "offset", string>>;

function filterParams(filters: Filters): URLSearchParams {
  const query = new URLSearchParams();
  for (const key of FILTER_KEYS) {
    const value = filters[key]?.trim();
    if (value) query.set(key, value);
  }
  return query;
}

export function listQuery(filters: Filters, limit: number, offset: number): string {
  const query = filterParams(filters);
  query.set("limit", String(limit));
  query.set("offset", String(offset));
  return query.toString();
}

export function pageHref(filters: Filters, offset: number): string {
  const query = filterParams(filters);
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

// --- upc-006: a university's contacts (§10). `notes` is null for readers outside the partnership team (CT14).
export type ContactRole = { code: string; label: string };
export type UniversityContact = {
  id: string; university_id: string; name: string; designation: string | null; department: string | null; role: ContactRole | null;
  email: string | null; phone: string | null; whatsapp: string | null; linkedin: string | null; preferred_channel: string | null;
  relationship_strength: string | null; notes: string | null; is_primary: boolean; shareable: boolean; created_at: string; updated_at: string;
};
export const MAX_CONTACTS = 50;
export const CONTACT_ROLES_URL = "/api/v1/partnership/contact-roles";
export const contactsUrl = (universityId: string) => universityUrl(universityId, "contacts");
export const contactUrl = (contactId: string) => `/api/v1/partnership/contacts/${contactId}`;
