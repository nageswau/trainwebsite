// nehn-017 (DEC-SCOPE-310): the shapes of GET /hr/students and GET /hr/students/{id} (apps/api/app/api/hr_students.py).
export const HR_STUDENTS_API = "/api/v1/hr/students";
export const HR_STUDENTS_PATH = "/it/hr/students";

export type HrStudentRow = { id: string; student_code: string | null; full_name: string; courses: number; completed: number };
export type HrStudentList = { items: HrStudentRow[]; total: number; page: number; page_size: number };
export type HrAttendance = { marked: number; present: number; absent: number; late: number; excused: number; attendance_pct: number | null };
export type HrSeat = {
  course: string; batch: string; trainer: string | null; status: string; progress: number | null; completed: boolean; certificate: string;
  attendance?: HrAttendance;
};
export type HrDocument = { id: string; document_type: string; original_filename: string | null; uploaded_at: string };
export type HrStudentDetail = {
  student: { id: string; student_code: string | null; full_name: string };
  seats: HrSeat[];
  documents?: HrDocument[];
  can: { attendance: boolean; documents: boolean; download: boolean };
};

/** "75%" or "—" when nothing is marked (null), never "0%". */
export const percent = (value: number | null | undefined) => (value === null || value === undefined ? "—" : `${value}%`);

/** QA17-02: each status named, not "10 / 0 / 0 / 2 of 12". QA17-05: the parts, so a narrow cell wraps between them, never inside one. */
export const classesParts = (a: HrAttendance) =>
  a.marked === 0 ? ["No classes marked yet"] : [`Present ${a.present}`, `Late ${a.late}`, `Excused ${a.excused}`, `Absent ${a.absent} (${a.marked} marked)`];

export const statusLabel = (status: string) => status.replaceAll("_", " ").replace(/^\w/, (c) => c.toUpperCase());

/** "?q=…&page=…" (or "") -- the same query for the API call and the page links. */
export function hrStudentsQuery(q: string, page: number): string {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (page > 1) params.set("page", String(page));
  const query = params.toString();
  return query ? `?${query}` : "";
}
