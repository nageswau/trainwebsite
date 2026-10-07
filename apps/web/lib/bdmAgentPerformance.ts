// bdm-022 (DEC-SCOPE-109): a linked Agent organization's performance -- the agency's own aggregates, never a student or a money figure.
// The API owns every rule (scope, definitions, which steps are tracked).
export type AgentPerformanceStep = { key: string; label: string; definition: string; tracked: boolean; count: number | null };
export type AgentPerformance = {
  organization_id: string;
  linked: boolean;
  agency: { name: string; prefix: string; status: string } | null;
  steps: AgentPerformanceStep[];
  applications_by_stage: { key: string; label: string; count: number }[];
  visa_applications: number | null;
  as_of: string;
};

export const agentPerformanceUrl = (orgId: string) => `/api/v1/bdm/organizations/${orgId}/agent-performance`;

export function isAgentPerformance(data: unknown): data is AgentPerformance {
  const d = data as Partial<AgentPerformance> | null;
  return !!d && typeof d.linked === "boolean" && Array.isArray(d.steps) && Array.isArray(d.applications_by_stage);
}
