import type { BdmType } from "@/lib/bdm";
import { ORGS_URL, TEAM_URL } from "@/lib/bdmOrganizations";
import type { ApprovalStatus, TravelStatus } from "@/lib/bdmTravel";
import { formatSchoolDateTime, SCHOOL_TIME_ZONE } from "@/lib/formatDate";
import type { LookupPage } from "@/lib/lookups";

// bdm-006 (DEC-SCOPE-068): types, catalogues and helpers for BDM appointments. The catalogues are display copies of the API's
// (models.BDM_APPOINTMENT_*); the API validates every value and `permissions` only tells the UI which actions to show.
export const APPOINTMENTS_URL = "/api/v1/bdm/appointments";
const PICKER_LIMIT = 20;

export const STATUSES = ["scheduled", "confirmed", "rescheduled", "completed", "cancelled", "no_show"] as const;
export type AppointmentStatus = (typeof STATUSES)[number];
export const STATUS_LABEL: Record<AppointmentStatus, string> = {
  scheduled: "Scheduled", confirmed: "Confirmed", rescheduled: "Rescheduled", completed: "Completed", cancelled: "Cancelled", no_show: "No show",
};
// R-F2: always text in the existing pills; colour only reinforces it.
export const STATUS_CLASS: Record<AppointmentStatus, string> = {
  scheduled: "status pending", rescheduled: "status pending", confirmed: "status", completed: "status", cancelled: "status error", no_show: "status error",
};

const COMMON_TYPES = ["college_meeting", "agent_meeting", "school_meeting", "mou_discussion", "student_institution_meeting", "seminar_workshop", "corporate_meeting", "other"];
const MODULE_TYPES: Record<BdmType, string[]> = {
  agent: ["agent_meeting", "new_agent_presentation", "product_training", "agreement_discussion", "performance_review", "agent_onboarding", "agent_visit", "commission_discussion", "business_review"],
  school: ["principal_meeting", "management_meeting", "career_guidance_presentation", "psychometric_presentation", "profile_building_presentation", "parent_orientation", "teacher_orientation", "seminar", "workshop", "mou_discussion", "renewal_meeting"],
  college: ["principal_meeting", "hod_meeting", "placement_cell_meeting", "course_promotion", "it_training_presentation", "student_seminar", "workshop", "internship_discussion", "placement_discussion", "mou_discussion", "corporate_connect", "faculty_meeting"],
};
export const TYPE_LABEL: Record<string, string> = {
  college_meeting: "College Meeting", agent_meeting: "Agent Meeting", school_meeting: "School Meeting", mou_discussion: "MoU Discussion",
  student_institution_meeting: "Student / Institution Meeting", seminar_workshop: "Seminar / Workshop", corporate_meeting: "Corporate Meeting", other: "Other",
  new_agent_presentation: "New Agent Presentation", product_training: "Product Training", agreement_discussion: "Agreement Discussion",
  performance_review: "Performance Review", agent_onboarding: "Agent Onboarding", agent_visit: "Agent Visit", commission_discussion: "Commission Discussion",
  business_review: "Business Review", principal_meeting: "Principal Meeting", management_meeting: "Management Meeting",
  career_guidance_presentation: "Career Guidance Presentation", psychometric_presentation: "Psychometric Presentation",
  profile_building_presentation: "Student Profile Building Presentation", parent_orientation: "Parent Orientation", teacher_orientation: "Teacher Orientation",
  seminar: "Seminar", workshop: "Workshop", renewal_meeting: "Renewal Meeting", hod_meeting: "HOD Meeting", placement_cell_meeting: "Placement Cell Meeting",
  course_promotion: "Course Promotion", it_training_presentation: "IT Training Presentation", student_seminar: "Student Seminar",
  internship_discussion: "Internship Discussion", placement_discussion: "Placement Discussion", corporate_connect: "Corporate Connect", faculty_meeting: "Faculty Meeting",
};
export const ALL_TYPES = Object.keys(TYPE_LABEL);
export const appointmentTypes = (t: BdmType): string[] => [...new Set([...COMMON_TYPES, ...MODULE_TYPES[t]])];

const COMMON_OUTCOMES = ["interested", "mou_discussion_required", "student_leads_expected", "course_promotion_interested", "follow_up_required", "commercial_discussion", "not_interested", "reschedule", "other"];
const AGENT_OUTCOMES = ["interested", "agreement_required", "product_training_required", "follow_up", "documents_required", "onboarding_required", "active_business_expected", "not_interested"];
export const OUTCOME_LABEL: Record<string, string> = {
  interested: "Interested", mou_discussion_required: "MoU Discussion Required", student_leads_expected: "Student Leads Expected",
  course_promotion_interested: "Course Promotion Interested", follow_up_required: "Follow-up Required", commercial_discussion: "Commercial Discussion",
  not_interested: "Not Interested", reschedule: "Reschedule", other: "Other", agreement_required: "Agreement Required",
  product_training_required: "Product Training Required", follow_up: "Follow-up", documents_required: "Documents Required",
  onboarding_required: "Onboarding Required", active_business_expected: "Active Business Expected",
};
export const appointmentOutcomes = (t: BdmType): string[] => (t === "agent" ? AGENT_OUTCOMES : COMMON_OUTCOMES);
export const DURATIONS = [15, 30, 45, 60, 90, 120, 180, 240, 360, 480, 720]; // R-F6; the API accepts any 15-720
// The duration choices, plus an off-list value an appointment already has (so a select never hides it).
export const durationOptions = (current: number): number[] => (DURATIONS.includes(current) ? DURATIONS : [...DURATIONS, current].sort((a, b) => a - b));

export type AppointmentPermissions = { can_edit: boolean; can_confirm: boolean; can_reschedule: boolean; can_cancel: boolean; can_no_show: boolean; can_complete: boolean; can_edit_report: boolean };
export type AppointmentRow = {
  id: string; code: string; starts_at: string; duration_minutes: number; appointment_type: string; status: AppointmentStatus;
  organization: { id: string; code: string; name: string; archived: boolean }; contact_name: string; bdm: { id: string; full_name: string; active: boolean };
  outcome_pending: boolean; // bdm-007 AC5: open and past its start, no meeting report yet
};
export type AppointmentEvent = { from_status: AppointmentStatus | null; to_status: AppointmentStatus; old_starts_at: string | null; new_starts_at: string | null; reason: string | null; actor_name: string; created_at: string };
// bdm-011: the trip this appointment is linked to (BdmAppointmentTripRef).
export type AppointmentTrip = {
  id: string; code: string; from_place: string; to_place: string; travel_date: string; return_date: string;
  approval_status: ApprovalStatus; travel_status: TravelStatus;
};
export type Appointment = AppointmentRow & {
  trip: AppointmentTrip | null;
  contact_id: string | null; contact_designation: string | null; contact_phone: string | null; contact_email: string | null;
  location: string | null; purpose: string | null; remarks: string | null; outcome: string | null; next_follow_up_on: string | null;
  report: MeetingReport | null; follow_up: FollowUp | null;
  expected_leads: number | null; expected_revenue: string | null; events: AppointmentEvent[]; permissions: AppointmentPermissions;
  created_at: string; updated_at: string;
};
// bdm-007 (spec §5.3): the meeting report filed on completion; outcome and follow-up date stay on the appointment.
export type MeetingReport = {
  discussion: string | null; requirements: string | null; opportunity: string | null; next_action: string | null;
  responsible_person: string | null; legacy: boolean; author: { id: string; full_name: string; active: boolean };
  submitted_at: string; updated_at: string;
};
export type FollowUp = { id: string; due_on: string; status: "open" | "done" | "cancelled" };
export type ReportBody = {
  outcome: string; discussion: string; requirements: string | null; opportunity: string | null; next_action: string | null;
  responsible_person: string | null; next_follow_up_on: string | null;
};
export const REPORT_LIMITS = { discussion: 4000, requirements: 2000, opportunity: 2000, next_action: 1000, responsible_person: 200 } as const;
export const REPORT_FIELD_LABEL: Record<keyof typeof REPORT_LIMITS, string> = {
  discussion: "Discussion", requirements: "Requirements", opportunity: "Opportunity", next_action: "Next action", responsible_person: "Responsible person",
};
export type OverlapMatch = { id: string; code: string; starts_at: string; duration_minutes: number; organization_name: string };
export type Overlap = { message: string; matches: OverlapMatch[]; total: number };

// The API's possible_overlap 409 body ({message, code, matches, total} -- services/bdm_appointments.overlap_conflict); anything else is null.
export function overlap(detail: unknown): Overlap | null {
  const d = detail as (Overlap & { code?: string }) | null;
  return d && typeof d === "object" && d.code === "possible_overlap" && Array.isArray(d.matches) ? d : null;
}

export function isAppointmentBody(data: unknown): data is { appointment: Appointment } {
  const a = (data as { appointment?: { id?: unknown } } | null)?.appointment;
  return !!a && typeof a.id === "string";
}

// India has one fixed offset (+05:30, no DST), so a datetime-local value is sent with it and read back in Asia/Kolkata.
const IST_PARTS = new Intl.DateTimeFormat("en-CA", { timeZone: SCHOOL_TIME_ZONE, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
export function isoToIstInput(iso: string): string {
  const p = Object.fromEntries(IST_PARTS.formatToParts(new Date(iso)).map((part) => [part.type, part.value]));
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`;
}
export const istInputToIso = (value: string): string => `${value}:00+05:30`;
export const nowIstInput = (): string => isoToIstInput(new Date().toISOString());
export const todayIst = (): string => nowIstInput().slice(0, 10);

export function formatMinutes(n: number): string {
  if (n < 60) return `${n} min`;
  return n % 60 ? `${Math.floor(n / 60)} h ${n % 60} min` : `${n / 60} h`;
}
export const whenText = (startsAt: string, minutes: number): string => `${formatSchoolDateTime(startsAt, true)} · ${formatMinutes(minutes)}`;
export function formatInr(value: string | null): string {
  return value === null ? "—" : `₹${Number(value).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

// The booking picker: the caller's own, active organizations (assigned=me; archived are excluded by the list's default).
export function myOrganizationSearch() {
  return async (q: string, signal: AbortSignal): Promise<LookupPage> => {
    const query = new URLSearchParams({ limit: String(PICKER_LIMIT), assigned: "me" });
    if (q) query.set("q", q);
    const response = await fetch(`${ORGS_URL}?${query}`, { signal });
    if (!response.ok) throw new Error(`Organization search failed (${response.status})`);
    const page = (await response.json()) as { items: { id: string; code: string; name: string; city: string }[]; total: number };
    return { items: page.items.map((o) => ({ id: o.id, label: o.name, detail: `${o.code} · ${o.city}` })), truncated: page.total > page.items.length };
  };
}

// The manager's BDM filter: their team (super_admin: everyone).
export function teamMemberSearch() {
  return async (q: string, signal: AbortSignal): Promise<LookupPage> => {
    const query = new URLSearchParams({ limit: String(PICKER_LIMIT) });
    if (q) query.set("q", q);
    const response = await fetch(`${TEAM_URL}?${query}`, { signal });
    if (!response.ok) throw new Error(`Team search failed (${response.status})`);
    const page = (await response.json()) as { items: { id: string; full_name: string; employee_id: string; bdm_type: BdmType }[]; total: number };
    return { items: page.items.map((b) => ({ id: b.id, label: b.full_name, detail: `${b.employee_id} · ${b.bdm_type}` })), truncated: page.total > page.items.length };
  };
}
