import { isCalendarDate } from "@/lib/formatDate";

// mgmt-021 (EVID-017 §17, spec AN1-AN14): GET /management/agents -- the §17 agent network figures and every approved agency ranked along
// Agent → Staff → Student → Application → Enrollment → Revenue. The API decides access, the order and every figure: `commission` and
// `revenue` are null unless `money_visible` (partners), and then the chain has no revenue step.
export const AGENTS_HOME = "/management/agents";
export const AGENTS_API = "/api/v1/management/agents";

export type AgentCountKey = "staff" | "students" | "applications" | "offers" | "visa" | "enrollments";
export type AgentMoneyKey = "commission" | "revenue";
export type AgentFigureKey = "agents" | "new_agents" | "active_agents" | "inactive_agents" | AgentCountKey | AgentMoneyKey;
export type AgentFigure = { key: AgentFigureKey; label: string; definition: string };
type AgentCounts = Record<AgentCountKey, number> & Record<AgentMoneyKey, string | null>;
export type AgentTotals = AgentCounts & { agents: number; new_agents: number; active_agents: number; inactive_agents: number };
export type AgencyRow = AgentCounts & { id: string; name: string; prefix: string; status: "active" | "suspended"; new: boolean };
export type AgentChainStep = { key: "agents" | AgentCountKey | "revenue"; label: string; value: number | string };
export type AgentsDashboard = {
  from: string; to: string; as_of: string; money_visible: boolean; figures: AgentFigure[];
  totals: AgentTotals; chain: AgentChainStep[]; agencies: AgencyRow[];
}; // prettier-ignore
export type AgentsQuery = { from: string; to: string };

/** The page's address: an impossible date or a repeated value is dropped, so the API answers with this month. */
export function agentsQuery(search: Record<string, string | string[] | undefined>): AgentsQuery {
  const day = (key: string) => (typeof search[key] === "string" && isCalendarDate(search[key] as string) ? (search[key] as string) : "");
  return { from: day("from"), to: day("to") };
}

export function agentsUrl({ from, to }: AgentsQuery): string {
  const params = new URLSearchParams({ ...(from ? { from } : {}), ...(to ? { to } : {}) }).toString();
  return params ? `${AGENTS_API}?${params}` : AGENTS_API;
}
