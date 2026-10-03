import type { BdmType } from "@/lib/bdm";
import type { LookupPage } from "@/lib/lookups";

// bdm-002 (DEC-SCOPE-060): types and helpers for the Organization CRM. The API decides scope and permissions; `permissions` on each
// organization only tells the UI which actions to show.
export const ORGS_URL = "/api/v1/bdm/organizations";
export const TEAM_URL = "/api/v1/bdm/manager/team";
// Browser QA-03: the global reset makes links look like text; these are links (the AgentUniversitiesPanel convention).
export const LINK_STYLE = { color: "var(--blue)", textDecoration: "underline" } as const;
const PICKER_LIMIT = 20;
export const MAX_CONTACTS = 20; // the API's BDM_MAX_CONTACTS
// A checkbox or radio with its label: one row, a 44 px touch target (the AgentStudentsPanel "Show archived" style).
export const CHECKBOX_ROW = { display: "flex", gap: 6, alignItems: "center", minHeight: 44 } as const;

export const ORG_TYPES = ["college", "university", "agent", "school", "corporate", "training_institute", "other"] as const;
export type OrgType = (typeof ORG_TYPES)[number];
export const ORG_TYPE_LABEL: Record<OrgType, string> = {
  college: "College", university: "University", agent: "Agent", school: "School", corporate: "Corporate", training_institute: "Training Institute", other: "Other",
};
export const CONTACT_ROLES = ["principal", "dean", "hod", "placement_officer", "counselor", "management", "owner", "other"] as const;
export type ContactRole = (typeof CONTACT_ROLES)[number];
export const CONTACT_ROLE_LABEL: Record<ContactRole, string> = {
  principal: "Principal", dean: "Dean", hod: "HOD", placement_officer: "Placement Officer", counselor: "Counselor", management: "Management", owner: "Owner", other: "Other",
};

export type OrgPerson = { id: string; full_name: string; active: boolean };
export type OrgContact = { id: string; name: string; designation: string | null; role: ContactRole | null; phone: string | null; email: string | null; is_primary: boolean };
export type OrgPermissions = { can_edit: boolean; can_archive: boolean; can_restore: boolean; can_reassign: boolean };
export type OrgRow = {
  id: string; code: string; name: string; org_type: OrgType; bdm_type: BdmType; city: string; state: string | null; existing_partner: boolean;
  assigned_bdm: OrgPerson; primary_contact: { name: string; designation: string | null; phone: string | null; email: string | null } | null;
  archived: boolean; last_meeting_at: string | null; next_meeting_at: string | null; permissions: OrgPermissions;
};
export type Organization = OrgRow & {
  phone: string | null; email: string | null; website: string | null; address: string | null; courses_interested: string | null; student_count: number | null;
  profile: OrgProfile | null; contacts: OrgContact[]; created_by_name: string; archived_at: string | null; created_at: string; updated_at: string;
};
export type OrgDuplicateMatch = { id: string; code: string; name: string; city: string; archived: boolean; assigned_bdm_name: string };
export type OrgDuplicate = { message: string; matches: OrgDuplicateMatch[]; total: number };

export function orgDuplicate(detail: unknown): OrgDuplicate | null {
  const d = detail as (Partial<OrgDuplicate> & { code?: string }) | null;
  if (!d || typeof d !== "object" || d.code !== "possible_duplicate" || !Array.isArray(d.matches)) return null;
  return { message: String(d.message ?? ""), matches: d.matches, total: Number(d.total ?? d.matches.length) };
}

export function isOrganizationBody(data: unknown): data is { organization: Organization } {
  const org = (data as { organization?: { id?: unknown } } | null)?.organization;
  return !!org && typeof org.id === "string";
}

// spec §12.2 F11: a stored website becomes a link only with an http(s) scheme (the server enforces the same rule).
export function safeWebsite(url: string | null): string | null {
  return url && /^https?:\/\//i.test(url) ? url : null;
}

export function display(value: string | number | null | undefined): string {
  return value === null || value === undefined || value === "" ? "—" : String(value);
}

// The reassign picker: active BDMs of the organization's type in the manager's team, minus the current assignee (the server
// re-checks every rule).
export function teamSearch(bdmType: BdmType, excludeId?: string) {
  return async (q: string, signal: AbortSignal): Promise<LookupPage> => {
    const query = new URLSearchParams({ limit: String(PICKER_LIMIT), bdm_type: bdmType });
    if (q) query.set("q", q);
    const response = await fetch(`${TEAM_URL}?${query}`, { signal });
    if (!response.ok) throw new Error(`Team search failed (${response.status})`);
    const page = (await response.json()) as { items: { id: string; full_name: string; email: string; active: boolean; employee_id: string }[]; total: number };
    const active = page.items.filter((b) => b.active && b.id !== excludeId);
    return { items: active.map((b) => ({ id: b.id, label: b.full_name, detail: `${b.employee_id} · ${b.email}` })), truncated: page.total > page.items.length };
  };
}

// bdm-003 (DEC-SCOPE-064, spec §6.1): type-specific profiles. The API validates every value; these drive the form, labels and filters.
export type ProfileGroup = "agent" | "school" | "college";
const PROFILE_GROUP: Partial<Record<string, ProfileGroup>> = { agent: "agent", school: "school", college: "college", university: "college" };
export const profileGroup = (orgType: string): ProfileGroup | null => PROFILE_GROUP[orgType] ?? null;
export const PROFILE_GROUP_LABEL: Record<ProfileGroup, string> = { agent: "Agent", school: "School", college: "College" };
export const PROFILE_FIELDS = {
  agent: ["country", "territory", "source", "staff_count"],
  school: ["board", "school_type", "grade_from", "grade_to"],
  college: ["affiliation", "college_type", "courses"],
} as const;
export type ProfileField = (typeof PROFILE_FIELDS)[ProfileGroup][number];
export const ALL_PROFILE_FIELDS: ProfileField[] = [...PROFILE_FIELDS.agent, ...PROFILE_FIELDS.school, ...PROFILE_FIELDS.college];
export const PROFILE_LABEL: Record<ProfileField, string> = {
  country: "Country", territory: "Territory", source: "Source", staff_count: "Number of staff", board: "Board", school_type: "School type",
  grade_from: "Lowest grade", grade_to: "Highest grade", affiliation: "University / affiliation", college_type: "College type", courses: "Courses",
};
/** P10: the agent's commission is never entered here; it comes from the Agent CRM once linked (bdm-019). */
export const COMMISSION_NOTE = "Commission: Available after onboarding";
export const SOURCES = ["referral", "website", "event", "cold_call", "walk_in", "other"] as const;
export const SOURCE_LABEL: Record<string, string> = { referral: "Referral", website: "Website", event: "Event", cold_call: "Cold call", walk_in: "Walk-in", other: "Other" };
export const BOARDS = ["CBSE", "ICSE", "State", "IB", "Other"] as const;
export const BOARD_LABEL: Record<string, string> = { CBSE: "CBSE", ICSE: "ICSE", State: "State board", IB: "IB", Other: "Other" };
export const SCHOOL_TYPES = ["private", "government", "aided", "international", "other"] as const;
export const SCHOOL_TYPE_LABEL: Record<string, string> = { private: "Private", government: "Government", aided: "Aided", international: "International", other: "Other" };
export const COLLEGE_TYPES = ["engineering", "arts_science", "management", "medical", "polytechnic", "other"] as const;
export const COLLEGE_TYPE_LABEL: Record<string, string> = {
  engineering: "Engineering", arts_science: "Arts & Science", management: "Management", medical: "Medical", polytechnic: "Polytechnic", other: "Other",
};
export const GRADES = [-2, -1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12] as const;
const PRE_PRIMARY: Record<number, string> = { [-2]: "Nursery", [-1]: "LKG", 0: "UKG" };
export const gradeLabel = (grade: number): string => PRE_PRIMARY[grade] ?? String(grade);

export function gradeRange(from: number | null, to: number | null): string {
  if (from !== null && to !== null) return `${gradeLabel(from)}–${gradeLabel(to)}`;
  if (from !== null) return `From ${gradeLabel(from)}`;
  if (to !== null) return `Up to ${gradeLabel(to)}`;
  return "—";
}

/** A stored enum value as words; an unknown (newer) value is shown as it is instead of breaking the page (spec §12.2 F8). */
export const labelOf = (labels: Record<string, string>, value: string | null): string => (value === null ? "—" : (labels[value] ?? value));

const SUGGESTED_ROLES: Record<ProfileGroup, ContactRole[]> = { agent: ["owner"], school: ["principal", "management", "counselor"], college: ["principal", "dean", "hod", "placement_officer"] };
/** P8: every role stays valid on every type; the type's named people come first in the Role list. */
export function rolesFor(orgType?: string): ContactRole[] {
  const group = orgType ? profileGroup(orgType) : null;
  const first = group ? SUGGESTED_ROLES[group] : [];
  return [...first, ...CONTACT_ROLES.filter((r) => !first.includes(r))];
}

/** The fields of a `profile_not_empty` 409 (spec §5.2), or null for any other body. */
export function profileNotEmpty(detail: unknown): string[] | null {
  const d = detail as { code?: string; fields?: unknown } | null;
  return d && typeof d === "object" && d.code === "profile_not_empty" && Array.isArray(d.fields) ? d.fields.map(String) : null;
}

export const typeChangeMessage = (group: ProfileGroup, fields: string[]): string =>
  `Clear the ${PROFILE_GROUP_LABEL[group]} details before changing the type: ${fields.map((f) => PROFILE_LABEL[f as ProfileField] ?? f).join(", ")}.`;

/** The old type's details are cleared in the form but not saved yet: a type change is two saves (P4). */
export const saveClearedFirst = (group: ProfileGroup): string =>
  `Save the cleared ${PROFILE_GROUP_LABEL[group]} details first: change the type back to ${PROFILE_GROUP_LABEL[group]} and save, then change the type.`;

export type OrgProfile =
  | { kind: "agent"; country: string | null; territory: string | null; source: string | null; staff_count: number | null }
  | { kind: "school"; board: string | null; school_type: string | null; grade_from: number | null; grade_to: number | null }
  | { kind: "college"; affiliation: string | null; college_type: string | null; courses: string | null };
