// bdm-001 (DEC-SCOPE-055): BDM types, labels and endpoints shared by the BDM pages and the admin BDM page.
import type { LookupPage } from "@/lib/lookups";

export type BdmType = "agent" | "school" | "college";
export type BdmManagerRef = { id: string; full_name: string; active: boolean };
export type BdmProfile = { bdm_type: BdmType; employee_id: string; designation: string | null; department: string | null; territory: string | null; reporting_manager: BdmManagerRef };
export type BdmMe = { id: string; full_name: string; email: string; phone: string | null; active: boolean; division: string; bdm_profile: BdmProfile };
export type BdmTeamRow = {
  id: string; full_name: string; email: string; phone: string | null; active: boolean; bdm_type: BdmType;
  employee_id: string; designation: string | null; department: string | null; territory: string | null;
};
export type BdmAdminRow = BdmTeamRow & { reporting_manager: BdmManagerRef; manager_active: boolean };
// QA-03 (owner, 2026-10-02): the picker carries email so same-name managers can be told apart.
export type BdmManagerOption = { id: string; full_name: string; email: string };

export const BDM_TYPE_LABEL: Record<BdmType, string> = { agent: "Agent", school: "School", college: "College" };
// Display only -- the API decides (services/bdm.CREATOR_TYPES, D10).
const CREATOR_TYPES: Record<string, BdmType[]> = { super_admin: ["agent", "school", "college"], it_admin: ["college"], overseas_admin: ["agent", "school"] };
export const creatableTypes = (role: string): BdmType[] => CREATOR_TYPES[role] ?? [];
export const statusLabel = (active: boolean) => (active ? "Active" : "Inactive");

// Form readers shared by the create form and the row editor: trimmed text, and "" sent as null (clears an optional field).
export const formText = (form: FormData, name: string) => String(form.get(name) ?? "").trim();
export const formOptional = (form: FormData, name: string) => formText(form, name) || null;

export const BDMS_URL = "/api/v1/admin/bdms";
export const MANAGERS_URL = "/api/v1/admin/bdm-managers";
export const USERS_URL = "/api/v1/admin/users";
export const PAGE_SIZE = 50;
/** A list page's `?offset=`: a positive whole number, anything else (missing, junk, negative) is the first page. */
export function pageOffset(raw: string | undefined): number {
  const n = Number.parseInt(raw ?? "0", 10);
  return Number.isFinite(n) && n > 0 ? n : 0;
}
const PICKER_LIMIT = 20;

/** QA-02: the reporting-manager picker searches the server (SearchableSelect server mode), so every manager is reachable.
 * bdm-025: `excludeId` drops the manager being deactivated from their own replacement list. */
export async function managerSearch(q: string, signal: AbortSignal, excludeId?: string): Promise<LookupPage> {
  const query = new URLSearchParams({ limit: String(PICKER_LIMIT) });
  if (q) query.set("q", q);
  const response = await fetch(`${MANAGERS_URL}?${query}`, { signal });
  if (!response.ok) throw new Error(`Manager search failed (${response.status})`);
  const page = (await response.json()) as { items: BdmManagerOption[]; total: number };
  const items = page.items.filter((m) => m.id !== excludeId);
  return { items: items.map((m) => ({ id: m.id, label: m.full_name, detail: m.email })), truncated: page.total > page.items.length };
}

// --- bdm-025 (DEC-SCOPE-081): deactivation with a handover choice, later handover, BDM manager deactivation ---
export type BdmPortfolio = { organizations: number; appointments: number; tasks: number; trips: number };
export type BdmManagerRow = BdmManagerOption & { bdm_count: number };
export const portfolioUrl = (bdmId: string) => `${BDMS_URL}/${bdmId}/portfolio`;
export const deactivateUrl = (bdmId: string) => `${BDMS_URL}/${bdmId}/deactivate`;
export const handoverUrl = (bdmId: string) => `${BDMS_URL}/${bdmId}/handover`;
export const managerDeactivateUrl = (managerId: string) => `${MANAGERS_URL}/${managerId}/deactivate`;

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
/** "3 organizations, 1 appointment and 2 follow-ups/tasks" -- the server's notification wording. */
export function portfolioText(p: Pick<BdmPortfolio, "organizations" | "appointments" | "tasks">): string {
  return `${plural(p.organizations, "organization", "organizations")}, ${plural(p.appointments, "appointment", "appointments")} and ${plural(p.tasks, "follow-up/task", "follow-ups/tasks")}`;
}
export const hasOpenWork = (p: BdmPortfolio) => p.organizations + p.appointments + p.tasks > 0;
export const bdmCountText = (n: number) => plural(n, "BDM", "BDMs");

/** The handover target picker: active BDMs of the same module, minus the BDM handing over (the server re-checks every rule). */
export function bdmSearch(bdmType: BdmType, excludeId: string) {
  return async (q: string, signal: AbortSignal): Promise<LookupPage> => {
    const query = new URLSearchParams({ limit: String(PICKER_LIMIT), bdm_type: bdmType, active: "true" });
    if (q) query.set("q", q);
    const response = await fetch(`${BDMS_URL}?${query}`, { signal });
    if (!response.ok) throw new Error(`BDM search failed (${response.status})`);
    const page = (await response.json()) as { items: BdmAdminRow[]; total: number };
    const items = page.items.filter((b) => b.id !== excludeId);
    return { items: items.map((b) => ({ id: b.id, label: b.full_name, detail: `${b.employee_id} · ${b.email}` })), truncated: page.total > page.items.length };
  };
}
