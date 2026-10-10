// upc-027 (DEC-SCOPE-169): a university's partner onboarding checklist (§29). The API owns the catalogue, the started / Lost rules, the
// overall status, the automatic course item and the Partner Activated move; these helpers only shape requests and word responses.
import { universityUrl } from "@/lib/universities";

export type OnboardingStatus = "not_started" | "in_progress" | "completed";
export type OnboardingItem = {
  kind: string; label: string; status: OnboardingStatus; completed_by: "manual" | "auto" | null; completed_on: string | null;
  owner: { id: string; full_name: string } | null; due_date: string | null; note: string | null;
};
export type OnboardingPage = {
  started: boolean; started_on: string | null; status: OnboardingStatus; completed_count: number; items: OnboardingItem[]; can_edit: boolean;
};
export type OnboardingUpdate = OnboardingPage & { stage_advanced: boolean };

export const STATUS_LABEL: Record<OnboardingStatus, string> = { not_started: "Not Started", in_progress: "In Progress", completed: "Completed" };
export const STATUSES = Object.keys(STATUS_LABEL) as OnboardingStatus[];

export const onboardingUrl = (universityId: string, kind?: string) => universityUrl(universityId, kind ? `onboarding/${kind}` : "onboarding");

/** The API's coded 409s (`onboarding_not_started`, `university_lost`) carry their own wording; null for any other detail. */
export function conflictMessage(detail: unknown): string | null {
  const d = detail as { code?: unknown; message?: unknown } | null;
  return d && typeof d === "object" && typeof d.code === "string" && typeof d.message === "string" ? d.message : null;
}

export function isOnboardingPage(data: unknown): data is OnboardingPage {
  const d = data as Partial<OnboardingPage> | null;
  return !!d && typeof d === "object" && Array.isArray(d.items) && typeof d.started === "boolean";
}
