// ccrm-026 (DEC-SCOPE-252): mirrors apps/api/app/visa_status.py -- a visa case's Appendix A status and the moves allowed from it.
export const VISA_STATUSES = [
  "not_started",
  "preparing",
  "appointment_booked",
  "submitted",
  "additional_info_requested",
  "decision_pending",
  "approved",
  "refused",
  "withdrawn",
] as const;
export type VisaStatus = (typeof VISA_STATUSES)[number];
export const VISA_DECISION_STATUSES: readonly VisaStatus[] = ["approved", "refused", "withdrawn"];
export const VISA_STATUS_LABELS: Record<VisaStatus, string> = {
  not_started: "Not started",
  preparing: "Preparing",
  appointment_booked: "Appointment booked",
  submitted: "Submitted",
  additional_info_requested: "Additional information requested",
  decision_pending: "Decision pending",
  approved: "Approved",
  refused: "Refused",
  withdrawn: "Withdrawn",
};

export const visaStatusLabel = (status: string | null | undefined) => (status ? VISA_STATUS_LABELS[status as VisaStatus] ?? status : "");

export const isVisaDecided = (status: string | null | undefined) => VISA_DECISION_STATUSES.includes(status as VisaStatus);

/** VC4: forward only, except Additional information requested <-> Decision pending; Withdrawn from any open status. A decided case
 *  offers the other decisions only (the Overseas Admin's correction, VC1). */
export function nextVisaStatuses(current: string): VisaStatus[] {
  if (isVisaDecided(current)) return VISA_DECISION_STATUSES.filter((s) => s !== current);
  const index = VISA_STATUSES.indexOf(current as VisaStatus);
  return VISA_STATUSES.filter((s, i) => i > index || (current === "decision_pending" && s === "additional_info_requested"));
}
