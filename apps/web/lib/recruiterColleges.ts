// pob-013 (DEC-SCOPE-410): a college's placement profile, kept by the placement team beside the BDM-owned organization (API §12LD).
export const COLLEGES_URL = "/api/v1/recruiter/colleges";
export const COLLEGES_PATH = "/recruiter/colleges";
export const collegeUrl = (id: string, ...rest: string[]) => [COLLEGES_URL, encodeURIComponent(id), ...rest.map(encodeURIComponent)].join("/");

export const EVENT_KINDS = ["pre_placement_talk", "campus_drive", "assessment", "interview", "exam", "holiday", "other"] as const;
export const EVENT_KIND_LABEL: Record<string, string> = {
  pre_placement_talk: "Pre-placement talk", campus_drive: "Campus drive", assessment: "Assessment", interview: "Interviews", exam: "Exams",
  holiday: "Holiday", other: "Other",
};
export const CHANNELS = ["meeting", "call", "email", "whatsapp", "visit", "other"] as const;
export const CHANNEL_LABEL: Record<string, string> = { meeting: "Meeting", call: "Call", email: "Email", whatsapp: "WhatsApp", visit: "Visit", other: "Other" };
export const CONTACT_METHODS = ["email", "phone", "whatsapp", "in_person", "linkedin"] as const;
export const CONTACT_METHOD_LABEL: Record<string, string> = { email: "Email", phone: "Phone", whatsapp: "WhatsApp", in_person: "In person", linkedin: "LinkedIn" };

export type CollegeRow = {
  id: string; code: string; name: string; org_type: string; city: string; state: string | null; assigned_bdm_name: string; course_count: number;
  next_pass_out_year: number | null; archived: boolean;
};
export type PlacementContact = {
  id: string; name: string; designation: string | null; role: string | null; phone: string | null; email: string | null; is_primary: boolean;
  office_details: string | null; preferred_contact_method: string | null;
};
export type Course = { id: string; department: string | null; course: string };
export type Batch = { id: string; course_id: string | null; course: string | null; pass_out_year: number; pass_out_date: string | null; student_count: number | null; notes: string | null };
export type CalendarEntry = { id: string; title: string; kind: string; starts_on: string; ends_on: string | null; notes: string | null };
export type Interaction = {
  id: string; channel: string; occurred_at: string; contact_id: string | null; contact_name: string | null; summary: string; next_step: string | null; logged_by_name: string;
};
export type CollegeDrive = { id: string; drive_code: string; drive_date: string; job_role: string; status: string };
export type College = {
  id: string; code: string; name: string; org_type: string; city: string; state: string | null; website: string | null; student_count: number | null;
  affiliation: string | null; college_type: string | null; courses_note: string | null; relationship_stage: string; assigned_bdm_name: string; archived: boolean;
  permissions: { can_edit: boolean };
  profile: { drive_process: string | null; eligibility_rules: string | null; updated_at: string | null; updated_by_name: string | null };
  contacts: PlacementContact[]; courses: Course[]; batches: Batch[]; calendar: CalendarEntry[]; interactions: Interaction[]; interaction_total: number;
  drives: CollegeDrive[];
};

export function isCollegeBody(data: unknown): data is { college: College } {
  const college = (data as { college?: Partial<College> } | null)?.college;
  return !!college && typeof college.id === "string" && Array.isArray(college.batches) && Array.isArray(college.contacts);
}

/** P2: only a college-module college or university has a placement profile. */
export const hasPlacementProfile = (org: { org_type: string; bdm_type: string }) => org.bdm_type === "college" && (org.org_type === "college" || org.org_type === "university");

/** "2026-12-01" -> "1 Dec 2026", read as a calendar date (never shifted by the time zone). */
export function dayText(value: string | null): string {
  if (!value) return "—";
  const [y, m, d] = value.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}
