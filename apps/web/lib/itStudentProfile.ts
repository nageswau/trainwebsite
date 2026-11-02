// itc-012 (DEC-SCOPE-345): the IT student record -- GET/PATCH /it/me/profile (the student), /counselor/it/students/{id}/profile (their
// itc-003 counselor) and /admin/it/students/{id}/profile (the IT Admin); PATCH .../enrollments/{id} sets the date and mode overrides
// (staff only). API_CONTRACT §12IQ.

export type ItStudentProfile = {
  exists: boolean;
  date_of_birth: string | null;
  address: string | null;
  city: string | null;
  qualification: string | null;
  graduation_year: number | null;
  emergency_contact_name: string | null;
  emergency_contact_relation: string | null;
  emergency_contact_phone: string | null;
  updated_at: string | null;
  updated_by_name: string | null;
};

export type ItEnrollment = {
  id: string;
  enrollment_code: string;
  program: string;
  batch: string;
  status: string;
  start_date: string;
  end_date: string;
  delivery_mode: string;
  start_date_override: string | null;
  end_date_override: string | null;
  delivery_mode_override: string | null;
  batch_start_date: string;
  batch_end_date: string;
  batch_mode: string;
};

export type ItStudentProfileResponse = {
  student: { id: string; full_name: string; student_code: string | null };
  profile: ItStudentProfile;
  enrollments: ItEnrollment[];
};

export const IT_DELIVERY_MODES = ["Online", "Offline", "Hybrid"] as const;
export const MY_IT_PROFILE_URL = "/api/v1/it/me/profile";
export const itStudentProfileUrl = (portal: "counselor" | "admin", id: string) => `/api/v1/${portal}/it/students/${encodeURIComponent(id)}/profile`;
export const itEnrollmentsUrl = (portal: "counselor" | "admin", id: string) => `/api/v1/${portal}/it/students/${encodeURIComponent(id)}/enrollments`;

export const IT_PROFILE_FIELD_LABELS: Record<string, string> = {
  date_of_birth: "Date of birth", address: "Address", city: "City", qualification: "Highest qualification", graduation_year: "Graduation year",
  emergency_contact_name: "Emergency contact name", emergency_contact_relation: "Relation", emergency_contact_phone: "Emergency contact phone",
  start_date: "Start date", end_date: "End date", delivery_mode: "Delivery mode",
};

/** The PATCH body: every profile field (blank text -> null, the year as a number). */
export function toPatchBody(p: ItStudentProfile) {
  const text = (v: string | null) => (v && v.trim() ? v.trim() : null);
  const year = p.graduation_year === null || String(p.graduation_year).trim() === "" ? null : Number(p.graduation_year);
  return {
    date_of_birth: p.date_of_birth || null, address: text(p.address), city: text(p.city), qualification: text(p.qualification), graduation_year: year,
    emergency_contact_name: text(p.emergency_contact_name), emergency_contact_relation: text(p.emergency_contact_relation),
    emergency_contact_phone: text(p.emergency_contact_phone),
  };
}
