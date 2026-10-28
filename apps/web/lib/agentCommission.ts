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

// ccrm-050: the editor's entry, shared by AgentCommissionCard and the Add/Edit University form (AgentCommissionFields).
export type AgentCommissionDraft = { kind: "percent" | "fixed"; percent: string; amount: string; currency: string; note: string };
export const agentCommissionDraft = (c: AgentCommission | null | undefined): AgentCommissionDraft => ({
  kind: c && !c.percent && c.amount ? "fixed" : "percent", percent: c?.percent ?? "", amount: c?.amount ?? "", currency: c?.currency ?? "", note: c?.note ?? "",
});
// The API body ({percent} or {amount, currency}, plus a note), null when no rate is entered, or the message for an incomplete entry.
export function agentCommissionBody(d: AgentCommissionDraft): { body: Record<string, string> | null } | { error: string } {
  const rate = d.kind === "percent" ? d.percent.trim() : d.amount.trim();
  if (!rate) return { body: null };
  if (d.kind === "fixed" && !d.currency) return { error: "Choose the currency." };
  const body: Record<string, string> = d.kind === "percent" ? { percent: rate } : { amount: rate, currency: d.currency };
  if (d.note.trim()) body.note = d.note.trim();
  return { body };
}
