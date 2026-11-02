// tel-007 (DEC-SCOPE-087): distribution rules and the manager's Lead assignment page -- types, endpoints and the shared pickers.
// Display only: the API decides who may write (DI3) and which leads are in scope (T23).
import { SOURCE_LABEL, getPage } from "@/lib/telecallerCatalogue";
import type { TelecallerTeam, TelecallerTeamRow } from "@/lib/telecaller";

export type PersonRef = { id: string; full_name: string; active: boolean };
export type Rule = {
  id: string; team: TelecallerTeam; kind: RuleKind; product: { id: string; name: string; active: boolean } | null;
  city: string | null; source?: string | null; telecaller: PersonRef; editable: boolean;
};
export type RuleKind = "product" | "city" | "source"; // itc-006: a source rule is tried first
export type QueueLead = {
  id: string; lead_code: string; name: string; division: TelecallerTeam; city: string | null; product: { id: string; name: string } | null;
  source: string; status: string; status_label: string; telecaller: PersonRef | null; created_at: string;
};

export const RULES_URL = "/api/v1/telecaller/distribution-rules";
export const UNASSIGNED_URL = "/api/v1/telecaller/leads/unassigned";
export const ASSIGNED_URL = "/api/v1/telecaller/leads/assigned";
export const ASSIGN_URL = "/api/v1/telecaller/leads/assign";
const TEAM_URL = "/api/v1/telecaller/manager/team";
const ALL = 100;

export function ruleMatch(rule: Pick<Rule, "kind" | "product" | "city" | "source">): string {
  if (rule.kind === "source") return `Source: ${SOURCE_LABEL[rule.source ?? ""] ?? rule.source}`;
  return rule.kind === "product" ? `Product: ${rule.product?.name ?? ""}${rule.product && !rule.product.active ? " (inactive)" : ""}` : `City: ${rule.city}`;
}

// itc-006 (DEC-SCOPE-339 D3): who gets a new lead that no rule matched.
export type Strategy = "round_robin" | "workload";
export type TeamStrategy = { team: TelecallerTeam; team_label: string; strategy: Strategy; editable: boolean };
export const STRATEGY_URL = "/api/v1/telecaller/distribution-strategy";
export const STRATEGY_LABEL: Record<Strategy, string> = {
  round_robin: "The next telecaller in turn (round robin)",
  workload: "The telecaller with the fewest open leads",
};

/** Who a rule or a lead can go to: an active direct report on the team (the API re-checks, AC5). */
export const assignTargets = (reports: TelecallerTeamRow[], team: TelecallerTeam) => reports.filter((r) => r.active && r.team === team);

/** Every direct report (super_admin: every telecaller), page after page, so no picker silently stops at the first 100. */
export async function myReports(signal?: AbortSignal): Promise<TelecallerTeamRow[]> {
  const items: TelecallerTeamRow[] = [];
  for (;;) {
    const page = await getPage<TelecallerTeamRow>(`${TEAM_URL}?limit=${ALL}&offset=${items.length}`, signal);
    items.push(...page.items);
    if (page.items.length === 0 || items.length >= page.total) return items;
  }
}
