// rec-003 (DEC-SCOPE-120): the recruiter company master -- types, endpoints and the pure helpers its list, form and detail share. The
// API scopes every row and decides every permission; nothing here filters for security.
import type { LookupPage } from "@/lib/lookups";
import { BDM_NAV, RECRUITER_MANAGER_NAV, RECRUITER_NAV, SUPER_ADMIN_NAV, type NavItem } from "@/lib/navigation";
import { PLACEMENT_MANAGER_LABEL, RECRUITER_ROLE_LABEL } from "@/lib/recruiter";

export type Ref = { id: string; name: string; active: boolean };
export type Person = { id: string; full_name: string; active: boolean };
export type Priority = "hot" | "warm" | "cold";
export type CompanyPermissions = { can_edit: boolean; can_archive: boolean; can_restore: boolean; can_reassign: boolean };
export type CompanyRow = {
  id: string; code: string; name: string; city: string | null; priority: Priority | null; industry: Ref | null; lead_source: Ref | null;
  assigned_recruiter: Person | null; archived: boolean; permissions: CompanyPermissions;
};
export type Assignment = { from_user: Person | null; to_user: Person; changed_by: Person; created_at: string };
export type Company = CompanyRow & {
  website: string | null; linkedin_url: string | null; company_size: Ref | null; employee_count: number | null; state: string | null;
  country: string | null; head_office: string | null; branches: string | null; description: string | null; campaign: Ref | null;
  assigned_bdm: Person | null; owner_type: string; created_by: Person | null; assignment_history: Assignment[]; archived_at: string | null;
  created_at: string; updated_at: string;
};
export type DuplicateMatch = { id: string; code: string; name: string; city: string | null; archived: boolean };
export type Duplicate = { message: string; matches: DuplicateMatch[]; total: number };

export const COMPANIES_URL = "/api/v1/recruiter/companies";
export const COMPANIES_PATH = "/recruiter/companies";
export const RECRUITER_SIGN_IN = "/it/login";
export const PRIORITIES: Priority[] = ["hot", "warm", "cold"];
export const PRIORITY_LABEL: Record<Priority, string> = { hot: "Hot", warm: "Warm", cold: "Cold" };
export const CREATOR_ROLES = ["placement_team", "placement_manager", "super_admin"];

/** The shell a company page renders in: the recruiter's or the manager's workspace (super admin keeps their own menu). */
export function companyShell(role: string): { nav: NavItem[]; roleLabel: string } {
  if (role === "super_admin") return { nav: SUPER_ADMIN_NAV, roleLabel: "Super Administrator" };
  if (role === "placement_manager") return { nav: RECRUITER_MANAGER_NAV, roleLabel: PLACEMENT_MANAGER_LABEL };
  if (role === "bdm") return { nav: BDM_NAV, roleLabel: "BDM" }; // R10: an assigned BDM reads the companies linked to them (QA-04)
  return { nav: RECRUITER_NAV, roleLabel: RECRUITER_ROLE_LABEL };
}

/** The form's text fields, in screen order (EVID-018 §2/§3, company side). */
export const TEXT_FIELDS = ["name", "website", "linkedin_url", "city", "state", "country", "head_office", "branches", "description", "employee_count"] as const;
export const PICK_FIELDS = ["industry_id", "company_size_id", "lead_source_id", "campaign_id", "priority", "assigned_bdm_user_id"] as const;
export type FormField = (typeof TEXT_FIELDS)[number] | (typeof PICK_FIELDS)[number];
export type FormValues = Record<FormField, string>;

export function valuesOf(c?: Company): FormValues {
  const text = (v: string | number | null | undefined) => (v == null ? "" : String(v));
  return {
    name: text(c?.name), website: text(c?.website), linkedin_url: text(c?.linkedin_url), city: text(c?.city), state: text(c?.state),
    country: text(c?.country), head_office: text(c?.head_office), branches: text(c?.branches), description: text(c?.description),
    employee_count: text(c?.employee_count), industry_id: text(c?.industry?.id), company_size_id: text(c?.company_size?.id),
    lead_source_id: text(c?.lead_source?.id), campaign_id: text(c?.campaign?.id), priority: text(c?.priority),
    assigned_bdm_user_id: text(c?.assigned_bdm?.id),
  };
}

/** A form value as the API expects it: blank is null (clears on edit), the employee count a number when it is one (else the server's
 * 422 names it). */
export function wire(key: FormField, value: string): unknown {
  const trimmed = value.trim();
  if (trimmed === "") return null;
  if (key === "employee_count" && /^\d+$/.test(trimmed)) return Number(trimmed);
  return trimmed;
}

/** Create: every filled field. Edit: only the fields that changed. */
export function companyBody(values: FormValues, original?: FormValues): Record<string, unknown> {
  const keys = [...TEXT_FIELDS, ...PICK_FIELDS].filter((k) => (original ? values[k] !== original[k] : values[k].trim() !== ""));
  return Object.fromEntries(keys.map((k) => [k, wire(k, values[k])]));
}

export function duplicateOf(detail: unknown): Duplicate | null {
  const d = detail as (Partial<Duplicate> & { code?: string }) | null;
  if (!d || typeof d !== "object" || d.code !== "possible_duplicate" || !Array.isArray(d.matches)) return null;
  return { message: String(d.message ?? ""), matches: d.matches, total: Number(d.total ?? d.matches.length) };
}

export function isCompanyBody(data: unknown): data is { company: Company } {
  const company = (data as { company?: { id?: unknown } } | null)?.company;
  return !!company && typeof company.id === "string";
}

/** A stored link becomes an anchor only with an http(s) scheme (the server enforces the same rule; old employer rows predate it). */
export const safeLink = (url: string | null) => (url && /^https?:\/\//i.test(url) ? url : null);

export const personName = (p: Person | null, none = "Unassigned") => (p ? `${p.full_name}${p.active ? "" : " (inactive)"}` : none);

/** The Assigned BDM picker searches the server, so every active BDM is reachable. */
export async function bdmSearch(q: string, signal: AbortSignal): Promise<LookupPage> {
  const query = new URLSearchParams({ limit: "20" });
  if (q) query.set("q", q);
  const response = await fetch(`${COMPANIES_URL}/bdm-options?${query}`, { signal });
  if (!response.ok) throw new Error(`BDM search failed (${response.status})`);
  const page = (await response.json()) as { items: { id: string; full_name: string }[]; total: number };
  return { items: page.items.map((b) => ({ id: b.id, label: b.full_name })), truncated: page.total > page.items.length };
}

/** The reassign picker searches the manager's direct reports (super admin: every recruiter) on the server; inactive recruiters and the
 * current assignee are left out (the server refuses them anyway). */
export function recruiterSearch(exclude: string | null) {
  return async (q: string, signal: AbortSignal): Promise<LookupPage> => {
    const query = new URLSearchParams({ limit: "20" });
    if (q) query.set("q", q);
    const response = await fetch(`/api/v1/recruiter/manager/team?${query}`, { signal });
    if (!response.ok) throw new Error(`Recruiter search failed (${response.status})`);
    const page = (await response.json()) as { items: { id: string; full_name: string; email: string; active: boolean }[]; total: number };
    const items = page.items.filter((r) => r.active && r.id !== exclude).map((r) => ({ id: r.id, label: r.full_name, detail: r.email }));
    return { items, truncated: page.total > page.items.length };
  };
}
