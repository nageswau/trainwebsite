import { ORGS_URL } from "@/lib/bdmOrganizations";

// bdm-021 (spec §4): a College organization's funnel and revenue. An untracked stage / line has `tracked: false` and a null figure;
// `revenue` is null when the caller may not see it (B3). Amounts are decimal strings in INR.
export type BusinessStage = { key: string; label: string; definition: string; tracked: boolean; count: number | null };
export type RevenueLine = { key: string; label: string; definition: string; tracked: boolean; amount: string | null };
export type Business = { organization_id: string; currency: "INR"; funnel: BusinessStage[]; revenue: { lines: RevenueLine[] } | null };

export const orgBusinessUrl = (orgId: string) => `${ORGS_URL}/${encodeURIComponent(orgId)}/business`;

export function isBusiness(data: unknown): data is Business {
  const d = data as Partial<Business> | null;
  return !!d && typeof d === "object" && Array.isArray(d.funnel) && (d.revenue === null || Array.isArray(d.revenue?.lines));
}
