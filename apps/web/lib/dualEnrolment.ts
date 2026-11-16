// ENH-033 (DEC-SCOPE-441): dual enrolment -- IT <-> Overseas on one login. API_CONTRACT.md §12MH.
export type StudentDivision = "it" | "overseas";
export type DualLookup = { id: string; full_name: string; student_code: string | null; divisions: StudentDivision[] };
export type DualEnrolled = { student_id: string; division: StudentDivision; counselor_id: string; counselor_name: string };
export type RoleAssignment = { division: string; role: string; is_active: boolean };

export const DIVISION_LABEL: Record<StudentDivision, string> = { it: "IT", overseas: "Overseas" };
export const OTHER_DIVISION: Record<StudentDivision, StudentDivision> = { it: "overseas", overseas: "it" };
export const STUDENT_ROLE: Record<StudentDivision, string> = { it: "it_student", overseas: "overseas_student" };
export const ENROL_EXISTING_LABEL = "Enrol existing student";

export const dualEnrolmentApi = (division: StudentDivision) => `/api/v1/workflows/${division}/dual-enrolment`;
export const counselorPickerApi = (division: StudentDivision) => `/api/v1/lookups/${division}-counselors`;
export const studentHome = (division: StudentDivision) => `/${division}/student/dashboard`;

/** The student divisions a user holds (active rows only), IT first. */
export function heldStudentDivisions(assignments: RoleAssignment[] | undefined): StudentDivision[] {
  return (["it", "overseas"] as const).filter((d) => (assignments ?? []).some((a) => a.is_active && a.division === d && a.role === STUDENT_ROLE[d]));
}
