// ENH-013 -- client-safe helpers for the Student 360° view (docs/superpowers/specs/2026-09-23-enh-013a-student-360-view-design.md §8).
// No server imports, so "use client" components may use them (tests/lib/clientBoundary.test.ts). The server-only loader and the
// response types live in lib/student360.ts.

export const TAB_KEYS = [
  "overview", "personal_details", "academic_records", "attendance", "examination_results", "career_guidance",
  "psychometric_assessment", "skills", "foreign_languages", "english_testing", "activities", "certificates",
  "documents", "teacher_remarks", "parent_communication", "edusphere_programs",
] as const;
export type TabKey = (typeof TAB_KEYS)[number];
export type TabStatus = "has_data" | "empty" | "restricted";

export const TAB_LABELS: Record<TabKey, string> = {
  overview: "Overview", personal_details: "Personal Details", academic_records: "Academic Records", attendance: "Attendance",
  examination_results: "Examination Results", career_guidance: "Career Guidance", psychometric_assessment: "Psychometric Assessment",
  skills: "Skills", foreign_languages: "Foreign Languages", english_testing: "English Testing", activities: "Activities",
  certificates: "Certificates", documents: "Documents", teacher_remarks: "Teacher Remarks",
  parent_communication: "Parent Communication", edusphere_programs: "Edusphere Programs",
};

const ROLE_BASE: Record<string, string> = {
  school_coordinator: "/school/coordinator/students", school_principal: "/school/principal/students",
  school_teacher: "/school/teacher/students", school_parent: "/school/parent/children",
  academic_team: "/school/academic-team/students", career_counselor: "/school/career-counselor/students",
  psychometric_team: "/school/psychometric-team/students",
};

export function student360Href(role: string, studentId: string): string | null {
  const base = ROLE_BASE[role];
  return base ? `${base}/${studentId}/360` : null;
}

export function isTabKey(value: string | null | undefined): value is TabKey {
  return !!value && (TAB_KEYS as readonly string[]).includes(value);
}

// report_url is stored unvalidated upstream (SCH-005, RAID finding). Only a same-origin path or an https URL becomes a link;
// anything else (javascript:, data:, protocol-relative //host, backslash tricks, plain http) is left for the caller to show as text.
export function safeHref(value: string | null | undefined): string | null {
  if (!value) return null;
  const v = value.trim();
  if (v.startsWith("/")) return v.startsWith("//") || v.startsWith("/\\") ? null : v;
  try {
    const url = new URL(v);
    return url.protocol === "https:" ? url.toString() : null;
  } catch {
    return null;
  }
}
