// dtu-001 (DEC-SCOPE-209): what EduSphere pays an agent Master per university. Sent only to super_admin, overseas_admin and Masters.
export type AgentCommission = { percent: string | null; amount: string | null; currency: string | null; note: string | null };
export const AGENT_COMMISSION_EDITORS = new Set(["super_admin", "overseas_admin"]);
export const AGENT_COMMISSION_CURRENCIES = ["INR", "USD", "GBP", "EUR", "CAD", "AUD", "NZD", "AED"];
export const agentCommissionUrl = (universityId: string) => `/api/v1/partnership/universities/${universityId}/agent-commission`;
export function formatAgentCommission(c: AgentCommission | null | undefined): string {
  if (!c) return "—";
  if (c.percent) return `${c.percent}%`;
  return `${c.currency} ${Number(c.amount).toLocaleString("en-GB", { minimumFractionDigits: 2 })}`;
}
