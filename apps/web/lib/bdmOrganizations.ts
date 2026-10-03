import type { BdmType } from "@/lib/bdm";
import type { LookupPage } from "@/lib/lookups";

// bdm-002 (DEC-SCOPE-058): types and helpers for the Organization CRM. The API decides scope and permissions; `permissions` on each
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
  phone: string | null; email: string | null; website: string | null; courses_interested: string | null; student_count: number | null;
  contacts: OrgContact[]; created_by_name: string; archived_at: string | null; created_at: string; updated_at: string;
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
