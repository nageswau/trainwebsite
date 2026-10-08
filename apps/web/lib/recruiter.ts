// rec-001 (DEC-SCOPE-116): recruiter types and endpoints shared by the /recruiter pages and the admin Recruiter Staff page. The
// telecaller module's generic helpers (form readers, paging, status label) are reused rather than copied.
import type { LookupPage } from "@/lib/lookups";
import type { ManagerOption, ManagerRef } from "@/lib/telecaller";

export type RecruiterProfile = { employee_id: string | null; reporting_manager: ManagerRef | null };
export type RecruiterMe = { id: string; full_name: string; email: string; phone: string | null; active: boolean; division: string; recruiter_profile: RecruiterProfile };
export type RecruiterTeamRow = { id: string; full_name: string; email: string; phone: string | null; active: boolean; employee_id: string | null };
export type RecruiterAdminRow = RecruiterTeamRow & { reporting_manager: ManagerRef | null };

export const RECRUITERS_URL = "/api/v1/admin/recruiters";
export const PLACEMENT_MANAGERS_URL = "/api/v1/admin/placement-managers";
export const RECRUITER_PROFILE_URL = "/api/v1/recruiter/profile";
export const RECRUITER_ROLE_LABEL = "Recruiter";
export const PLACEMENT_MANAGER_LABEL = "Placement Manager";

/** "Name" or "Name (inactive)"; null when a backfilled recruiter has no manager yet (AC5). */
export const managerLabel = (m: ManagerRef | null) => (m ? `${m.full_name}${m.active ? "" : " (inactive)"}` : null);

/** The reporting-manager picker searches the server (SearchableSelect server mode), so every active placement manager is reachable. */
export async function placementManagerSearch(q: string, signal: AbortSignal): Promise<LookupPage> {
  const query = new URLSearchParams({ limit: "20" });
  if (q) query.set("q", q);
  const response = await fetch(`${PLACEMENT_MANAGERS_URL}?${query}`, { signal });
  if (!response.ok) throw new Error(`Manager search failed (${response.status})`);
  const page = (await response.json()) as { items: ManagerOption[]; total: number };
  return { items: page.items.map((m) => ({ id: m.id, label: m.full_name, detail: m.email })), truncated: page.total > page.items.length };
}
