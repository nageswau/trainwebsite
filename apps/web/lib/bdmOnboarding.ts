import type { OrgPerson } from "@/lib/bdmOrganizations";

// bdm-018 (DEC-SCOPE-079): the school onboarding handover. The API owns every rule (who may request, MoU Signed/Active, one pending,
// one School per organization); these types only read its responses.
export type OnboardingStatus = "pending" | "completed" | "rejected";
export type OrgOnboarding = {
  request: { id: string; status: OnboardingStatus; created_at: string; resolved_at: string | null; reject_reason: string | null } | null;
  school: { name: string; school_code: string | null } | null;
  can_request: boolean;
};

export type OnboardingItem = {
  id: string; status: OnboardingStatus; note: string | null; created_at: string; resolved_at: string | null; resolution: "created" | "linked" | null;
  reject_reason: string | null; requested_by: { id: string; full_name: string }; assigned_bdm: OrgPerson;
  organization: {
    id: string; code: string; name: string; city: string; state: string | null; address: string | null; phone: string | null; email: string | null;
    website: string | null; board: string | null; grade_from: number | null; grade_to: number | null;
  };
  primary_contact: { name: string; email: string | null; phone: string | null } | null;
  mou: { reference: string | null; signed_on: string | null } | null;
  school: { id: string; name: string; school_code: string | null } | null;
};

export const QUEUE_URL = "/api/v1/overseas-admin/bdm-onboarding-requests";
export const QUEUE_PAGE = 20;
export const requestUrl = (orgId: string) => `/api/v1/bdm/organizations/${orgId}/onboarding-request`;

/** The 409s carry `{message, code}`; detailMessage only words strings and 422 lists. */
export function onboardingMessage(outcome: { message: string; detail?: unknown }): string {
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
