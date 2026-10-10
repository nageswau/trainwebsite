// upc-001 (DEC-SCOPE-118): partnership manager types and endpoints shared by the partnership pages and the admin Partnership managers
// page. The form readers, paging and status words are tel-001's (lib/telecaller).
import type { LookupPage } from "@/lib/lookups";
import type { ManagerOption, ManagerRef } from "@/lib/telecaller";

export type PartnershipProfile = { employee_id: string; reporting_head: ManagerRef };
export type PartnershipMe = { id: string; full_name: string; email: string; phone: string | null; active: boolean; division: string; partnership_profile: PartnershipProfile };
export type PartnershipTeamRow = { id: string; full_name: string; email: string; phone: string | null; active: boolean; employee_id: string };
export type PartnershipAdminRow = PartnershipTeamRow & { reporting_head: ManagerRef; head_active: boolean };
// upc-032 (DEC-SCOPE-171 RA14): what a head's Team row carries -- the manager's primary and backup universities and open tasks.
export type PartnershipWork = { primary: number; backup: number; tasks: number };
export type PartnershipTeamMember = PartnershipTeamRow & { work: PartnershipWork };
export const REASSIGN_URL = "/api/v1/partnership/head/reassign";

export const MANAGERS_URL = "/api/v1/admin/partnership-managers";
export const HEADS_URL = "/api/v1/admin/partnership-heads";
export const ME_URL = "/api/v1/partnership/me";
export const PROFILE_URL = "/api/v1/partnership/profile";
export const TEAM_PATH = "/partnership/head/team";
export const ROLE_LABEL = { manager: "Partnership Manager", head: "Partnership Head" };
const PICKER_LIMIT = 20;

/** The reporting-head picker searches the server (SearchableSelect server mode), so every head is reachable. */
export async function headSearch(q: string, signal: AbortSignal): Promise<LookupPage> {
  const query = new URLSearchParams({ limit: String(PICKER_LIMIT) });
  if (q) query.set("q", q);
  const response = await fetch(`${HEADS_URL}?${query}`, { signal });
  if (!response.ok) throw new Error(`Head search failed (${response.status})`);
  const page = (await response.json()) as { items: ManagerOption[]; total: number };
  return { items: page.items.map((h) => ({ id: h.id, label: h.full_name, detail: h.email })), truncated: page.total > page.items.length };
}
