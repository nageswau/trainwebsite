// tel-016 (DEC-SCOPE-095): a lead's counselling appointments -- types, endpoints and helpers shared by the lead detail section and the
// counselor's panel. Labels are display only; the API decides scope, the rules and what the viewer may do (`permissions`).
import { istInputToIso } from "@/lib/bdmAppointments";
import { formatSchoolDateTime } from "@/lib/formatDate";
import { leadUrl, type PersonRef } from "@/lib/telecallerLeads";

export type AppointmentStatus = "scheduled" | "confirmed" | "rescheduled" | "completed" | "cancelled" | "no_show";
export type AppointmentAction = "confirm" | "complete" | "no_show" | "cancel" | "reschedule";
export type AppointmentEvent = {
  from_status: AppointmentStatus | null; to_status: AppointmentStatus; old_scheduled_at: string | null; new_scheduled_at: string | null;
  reason: string | null; actor_name: string; created_at: string;
};
export type LeadAppointment = {
  id: string; code: string;
  lead: { id: string; lead_code: string; name: string; phone: string | null; email: string | null; status: string; status_label: string };
  appointment_type: string; type_label: string; counselor: PersonRef | null; booked_by: PersonRef | null; scheduled_at: string;
  duration_minutes: number; mode: string; meeting_link: string | null; location: string | null; purpose: string | null; remarks: string | null;
  status: AppointmentStatus; created_at: string; events: AppointmentEvent[];
  permissions: { can_confirm: boolean; can_complete: boolean; can_no_show: boolean; can_cancel: boolean; can_reschedule: boolean };
};
export type AppointmentOptions = { types: { key: string; label: string }[]; counselors: PersonRef[]; modes: string[]; duration_minutes: number };

// EVID-019 §9
export const STATUS_LABEL: Record<AppointmentStatus, string> = {
  scheduled: "Scheduled", confirmed: "Confirmed", rescheduled: "Rescheduled", completed: "Completed", cancelled: "Cancelled", no_show: "No show",
};
export const OPEN_STATUSES: AppointmentStatus[] = ["scheduled", "confirmed", "rescheduled"];
export const ACTION_LABEL: Record<AppointmentAction, string> = {
  confirm: "Confirm", complete: "Mark completed", no_show: "Mark no-show", cancel: "Cancel", reschedule: "Reschedule",
};

export const appointmentsUrl = (leadId: string) => leadUrl(leadId, "/appointments");
export const optionsUrl = (leadId: string) => leadUrl(leadId, "/appointment-options");
export const actionUrl = (id: string, action: AppointmentAction) => `/api/v1/lead-appointments/${encodeURIComponent(id)}/${action.replace("_", "-")}`;
export const COUNSELOR_APPOINTMENTS_URL = "/api/v1/counselor/appointments";

/** Spec §5: a meeting link is only ever an http(s) href -- anything else (a `javascript:` URL) is shown as text, never linked. */
export function safeLink(url: string | null): string | null {
  const trimmed = (url ?? "").trim();
  return /^https?:\/\//i.test(trimmed) ? trimmed : null;
}

export type BookingDraft = {
  appointment_type: string; counselor_id: string; when: string; mode: string; meeting_link: string; location: string; purpose: string; remarks: string;
};

/** The booking request: the datetime-local value is India time (+05:30, no DST); blank optional text is left out. */
export function bookingBody(draft: BookingDraft): Record<string, string> {
  const body: Record<string, string> = {
    appointment_type: draft.appointment_type, counselor_id: draft.counselor_id, scheduled_at: istInputToIso(draft.when), mode: draft.mode,
  };
  for (const key of ["meeting_link", "location", "purpose", "remarks"] as const) {
    const text = draft[key].trim();
    if (text) body[key] = text;
  }
  return body;
}

/** AP1: the 409 `counselor_busy` detail is an object (message + the clashing times); null for any other detail. */
export function clashText(detail: unknown): string | null {
  const d = detail as { code?: unknown; message?: unknown; matches?: { scheduled_at: string }[] } | null;
  if (!d || typeof d !== "object" || d.code !== "counselor_busy" || typeof d.message !== "string") return null;
  const times = (d.matches ?? []).map((m) => formatSchoolDateTime(m.scheduled_at, true)).join("; ");
  return times ? `${d.message}. Busy: ${times}.` : `${d.message}.`;
}

export const whenText = (iso: string, minutes: number) => `${formatSchoolDateTime(iso, true)} · ${minutes} min`;
