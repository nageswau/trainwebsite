import type { OrgPerson } from "@/lib/bdmOrganizations";

// bdm-018 (DEC-SCOPE-085): the school onboarding handover. The API owns every rule (who may request, MoU Signed/Active, one pending,
// one School per organization); these types only read its responses.
// bdm-019 (DEC-SCOPE-107): Agent organizations hand over the same way and are linked to an Agent Organization by its code; the BDM sees
// that agency as aggregates only (A7).
export type OnboardingStatus = "pending" | "completed" | "rejected";
export type OnboardingKind = "school" | "agent";
export type AgentLink = {
  name: string; prefix: string; status: string; master_login: boolean; staff_count: number;
  counts: { students: number; applications: number; enrollments: number };
};
export type OrgOnboarding = {
  request: { id: string; status: OnboardingStatus; created_at: string; resolved_at: string | null; reject_reason: string | null } | null;
  school: { name: string; school_code: string | null } | null;
  agent?: AgentLink | null;
  can_request: boolean;
};

/** The linked agency's AGN-001 status, worded for the BDM (who only reads it). */
export const AGENCY_STATUS: Record<string, string> = { pending: "Pending approval", active: "Active", suspended: "Suspended", rejected: "Rejected" };

export type OnboardingItem = {
  id: string; kind: OnboardingKind; status: OnboardingStatus; note: string | null; created_at: string; resolved_at: string | null; resolution: "created" | "linked" | null;
  reject_reason: string | null; requested_by: { id: string; full_name: string }; assigned_bdm: OrgPerson;
  organization: {
    id: string; code: string; name: string; city: string; state: string | null; address: string | null; phone: string | null; email: string | null;
    website: string | null; board: string | null; grade_from: number | null; grade_to: number | null;
  };
  primary_contact: { name: string; email: string | null; phone: string | null } | null;
  mou: { reference: string | null; signed_on: string | null } | null;
  school: { id: string; name: string; school_code: string | null } | null;
  agent_org: { id: string; name: string; prefix: string; status: string } | null;
};

export const QUEUE_URL = "/api/v1/overseas-admin/bdm-onboarding-requests";
export const QUEUE_PAGE = 20;
export const requestUrl = (orgId: string) => `/api/v1/bdm/organizations/${orgId}/onboarding-request`;

export const UNCONFIRMED = "The request could not be confirmed. Reload the page to check before trying again.";

/** The 409s carry `{message, code}`; detailMessage only words strings and 422 lists. A 5xx can fail after the commit, so its outcome is
 * unknown (QA18-01, the QA-023-04 rule). */
export function onboardingMessage(outcome: { message: string; status?: number; detail?: unknown }): string {
  if ((outcome.status ?? 0) >= 500) return UNCONFIRMED;
  const d = outcome.detail as { message?: unknown } | null | undefined;
  return d && typeof d === "object" && typeof d.message === "string" ? d.message : outcome.message;
}

export function isOnboardingItem(data: unknown): data is OnboardingItem {
  const d = data as Partial<OnboardingItem> | null;
  return !!d && typeof d.id === "string" && typeof d.status === "string" && !!d.organization;
}

/** The organization's grade range ("1-12") as the School's free-text "Grades available" prefill. */
export function gradesText(from: number | null, to: number | null): string {
  if (from === null && to === null) return "";
  return from !== null && to !== null ? `${from}-${to}` : String(from ?? to);
}
