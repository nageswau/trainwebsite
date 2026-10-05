// tel-001 (DEC-SCOPE-073): telecaller types, labels and endpoints shared by the telecaller pages and the admin Telecallers page.
import type { LookupPage } from "@/lib/lookups";

export type TelecallerTeam = "it" | "overseas";
export type ManagerRef = { id: string; full_name: string; active: boolean };
export type TelecallerProfile = { team: TelecallerTeam; employee_id: string; reporting_manager: ManagerRef };
export type TelecallerMe = { id: string; full_name: string; email: string; phone: string | null; active: boolean; division: string; telecaller_profile: TelecallerProfile };
export type TelecallerTeamRow = { id: string; full_name: string; email: string; phone: string | null; active: boolean; team: TelecallerTeam; employee_id: string };
export type TelecallerAdminRow = TelecallerTeamRow & { reporting_manager: ManagerRef; manager_active: boolean };
export type ManagerOption = { id: string; full_name: string; email: string };

export const TEAM_LABEL: Record<TelecallerTeam, string> = { it: "IT", overseas: "Overseas" };
export const teamRoleLabel = (team: TelecallerTeam) => `${TEAM_LABEL[team]} Telecaller`;
// Display only -- the API decides (services/telecaller.CREATOR_TEAMS).
const CREATOR_TEAMS: Record<string, TelecallerTeam[]> = { super_admin: ["it", "overseas"], it_admin: ["it"], overseas_admin: ["overseas"] };
export const creatableTeams = (role: string): TelecallerTeam[] => CREATOR_TEAMS[role] ?? [];
export const statusLabel = (active: boolean) => (active ? "Active" : "Inactive");

// Form readers: trimmed text, and "" sent as null.
export const formText = (form: FormData, name: string) => String(form.get(name) ?? "").trim();
export const formOptional = (form: FormData, name: string) => formText(form, name) || null;

export const TELECALLERS_URL = "/api/v1/admin/telecallers";
export const MANAGERS_URL = "/api/v1/admin/telecaller-managers";
export const USERS_URL = "/api/v1/admin/users";
export const PROFILE_URL = "/api/v1/telecaller/profile";
export const PAGE_SIZE = 50;
/** A list page's `?offset=`: a positive whole number, anything else is the first page. */
export function pageOffset(raw: string | undefined): number {
  const n = Number.parseInt(raw ?? "0", 10);
  return Number.isFinite(n) && n > 0 ? n : 0;
}
const PICKER_LIMIT = 20;

/** The reporting-manager picker searches the server (SearchableSelect server mode), so every manager is reachable. */
export async function managerSearch(q: string, signal: AbortSignal): Promise<LookupPage> {
  const query = new URLSearchParams({ limit: String(PICKER_LIMIT) });
  if (q) query.set("q", q);
  const response = await fetch(`${MANAGERS_URL}?${query}`, { signal });
  if (!response.ok) throw new Error(`Manager search failed (${response.status})`);
  const page = (await response.json()) as { items: ManagerOption[]; total: number };
  return { items: page.items.map((m) => ({ id: m.id, label: m.full_name, detail: m.email })), truncated: page.total > page.items.length };
}
