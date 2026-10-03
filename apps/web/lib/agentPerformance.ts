// AGN-019 (DEC-SCOPE-063): the staff performance payload's shape and URL, shared by the panel and its tests. Mirrors
// AgentPerformanceOut (apps/api/app/schemas.py); the server remains the authority.

export const PERFORMANCE_URL = "/api/v1/workflows/overseas/agent/crm/performance";

export type AgentFunnel = { students: number; applications: number; submitted: number; offers: number; visa: number; enrolled: number };
export type AgentPerformanceCounts = {
  students: number;
  applications: number;
  offers: number;
  visa_applications: number;
  visa_approvals: number;
  enrollments: number;
  funnel: AgentFunnel;
};
export type AgentPerformanceRow = AgentPerformanceCounts & { code: string; name: string; active: boolean };
export type AgentPerformance = {
  date_from: string | null;
  date_to: string | null;
  rows: AgentPerformanceRow[];
  unassigned: AgentPerformanceCounts | null;
  total: AgentPerformanceCounts; // rows + unassigned
  as_of: string;
};
export type FunnelStage = { key: keyof AgentFunnel; label: string; count: number; percent: number | null };

const STAGES: [keyof AgentFunnel, string][] = [
  ["students", "Students"],
  ["applications", "Applications"],
  ["submitted", "Submitted"],
  ["offers", "Offers"],
  ["visa", "Visa"],
  ["enrolled", "Enrolled"],
];

// Each stage with its share of the Students stage; null (shown as "—") when there are no students, never NaN.
export function funnelStages(f: AgentFunnel): FunnelStage[] {
  return STAGES.map(([key, label]) => ({ key, label, count: f[key], percent: f.students > 0 ? Math.round((f[key] / f.students) * 100) : null }));
}

export function isPerformance(body: unknown): body is AgentPerformance {
  const b = body as Partial<AgentPerformance> | null;
  return typeof b === "object" && b !== null && Array.isArray(b.rows) && "unassigned" in b && typeof b.total?.funnel?.students === "number";
}
