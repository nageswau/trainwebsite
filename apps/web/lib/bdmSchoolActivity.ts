// bdm-020 (DEC-SCOPE-089): a linked School's student development counts, as the School module reports them. Aggregates only; the API
// owns every rule (scope, which metrics are tracked).
export type SchoolActivityMetric = { key: string; label: string; tracked: boolean; completed: number | null; pending: number | null };
export type SchoolActivity = {
  linked: boolean;
  school: { name: string; school_code: string | null } | null;
  total_students: number | null;
  metrics: SchoolActivityMetric[];
};

export const schoolActivityUrl = (orgId: string) => `/api/v1/bdm/organizations/${orgId}/school-activity`;

export function isSchoolActivity(data: unknown): data is SchoolActivity {
  const d = data as Partial<SchoolActivity> | null;
  return !!d && typeof d.linked === "boolean" && Array.isArray(d.metrics);
}
