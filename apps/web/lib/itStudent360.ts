import type { FeeAccount } from "@/components/FeeAccountSummary";
import type { StaffReview } from "@/lib/hrReviews";
import type { RiskReason } from "@/lib/itAtRisk";
import type { ItStudentNote } from "@/lib/itStudentNotes";
import type { StudentResumeVersion } from "@/lib/studentResumes";

// itc-029 (DEC-SCOPE-358): the IT student 360 -- GET /it/students/{id}/360 for the IT counselor (linked students), HR (the placement pool)
// and the IT Admin (any IT student), and the lead's timeline on .../360/lead-timeline. A section the reader may not see is left out of
// the response (HR: no fee, profile, lead, risk or notifications). API_CONTRACT §12JD.

export const PORTALS = {
  counselor: { roleLabel: "Counselor", back: "/it/counselor/students", backLabel: "my students" },
  admin: { roleLabel: "IT Administrator", back: "/it/admin/students", backLabel: "students" },
  hr: { roleLabel: "HR Team", back: "/it/hr/students", backLabel: "students" },
} as const;
export type Portal360 = keyof typeof PORTALS;

export type Enrollment360 = {
  id: string; enrollment_code: string; program: string; batch: string; trainer: string | null; status: string;
  start_date: string | null; end_date: string | null; delivery_mode: string | null; progress_percent: number;
  attendance_percent?: number | null; attendance_marked?: number; // only with `attendance.view` for HR
};

export type Student360 = {
  student: { id: string; full_name: string; student_code: string | null; active: boolean };
  viewer: Portal360;
  sections: string[];
  contact: { email: string; phone: string | null; counselor: { id: string; full_name: string } | null };
  profile?: { city: string | null; qualification: string | null; emergency_contact_name: string | null; emergency_contact_relation: string | null;
    emergency_contact_phone: string | null; calls_allowed: boolean };
  lead?: { id: string; lead_code: string; stage: string; stage_label: string; owner: string | null; created_at: string; converted_at: string | null; href: string | null } | null;
  enrollments: Enrollment360[];
  fee?: { accounts: FeeAccount[]; balance: number | null };
  risk?: { enrollment_id: string; batch: string; reasons: RiskReason[]; attendance_percent: string | number | null; assessment_percent: string | number | null;
    consecutive_absences: number; raised_at: string }[];
  feedback: { kind: "assignment" | "assessment"; title: string; score: number | null; max_score: number; feedback: string; by: string | null; at: string }[];
  resumes: { items: StudentResumeVersion[] };
  hr_review: StaffReview;
  notes: { items: ItStudentNote[]; total: number };
  notifications?: { id: string; title: string; event_type: string | null; sent_at: string; read: boolean }[];
};

export const student360Url = (studentId: string) => `/api/v1/it/students/${encodeURIComponent(studentId)}/360`;
export const leadTimelineUrl = (studentId: string) => `${student360Url(studentId)}/lead-timeline`;
/** The page of each portal: the counselor's and the IT Admin's are the student's own path; HR's student path is nehn-017's detail. */
export const student360Path = (portal: Portal360, studentId: string) =>
  `/it/${portal}/students/${encodeURIComponent(studentId)}${portal === "hr" ? "/360" : ""}`;

export const percentText = (value: number | null | undefined) => (value === null || value === undefined ? "—" : `${Number(value).toFixed(0)}%`);
