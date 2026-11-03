// itc-031 (DEC-SCOPE-358): the derived IT student lifecycle -- GET /{counselor|admin}/it/students/{id}/lifecycle (the 360), PUT
// /admin/it/students/{id}/enrollments/{eid}/lifecycle-override (IT Admin: "not_placed" / "closed" with a reason, null clears). Labels
// come from the API (itc-005 renames them there). API_CONTRACT §12JD.

export type LifecycleStage = { stage: string; stage_label: string };

export type LifecycleHistoryRow = {
  from_stage: string | null;
  from_label: string | null;
  to_stage: string;
  to_label: string;
  cause: string;
  actor: string | null;
  created_at: string;
};

export type LifecycleEnrollment = LifecycleStage & {
  enrollment_id: string;
  enrollment_code: string;
  program: string;
  batch: string;
  components: { fee: LifecycleStage | null; training: LifecycleStage | null; placement: LifecycleStage | null };
  override: (LifecycleStage & { reason: string | null }) | null;
  history: LifecycleHistoryRow[];
};

export type LifecycleResponse = { enrollments: LifecycleEnrollment[] };

export const lifecycleUrl = (portal: "counselor" | "admin", studentId: string) => `/api/v1/${portal}/it/students/${encodeURIComponent(studentId)}/lifecycle`;
export const lifecycleOverrideUrl = (studentId: string, enrollmentId: string) =>
  `/api/v1/admin/it/students/${encodeURIComponent(studentId)}/enrollments/${encodeURIComponent(enrollmentId)}/lifecycle-override`;

export const OVERRIDE_CHOICES = [
  { value: "not_placed", label: "Not placed" },
  { value: "closed", label: "Closed" },
] as const;

export const CAUSE_LABELS: Record<string, string> = {
  enrolment: "Enrolment change", fee: "Fee payment", certificate: "Certificate issued", hr_review: "HR review", placement: "Placement",
  override: "Set by the IT Admin", daily_check: "Daily check",
};

export const COMPONENT_LABELS = { fee: "Fee", training: "Training", placement: "Placement" } as const;

/** The status pill's tone; the label is always shown too, so colour is never the only signal. */
export function stageTone(stage: string): string {
  if (stage === "at_risk" || stage === "not_placed") return "status error";
  if (stage === "closed") return "status closed";
  if (stage === "enrolled" || stage === "fee_pending" || stage === "partially_paid") return "status pending";
  return "status";
}
