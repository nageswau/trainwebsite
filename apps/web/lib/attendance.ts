// ENH-030 (DEC-SCOPE-038 D4): the four daily attendance statuses, mirroring the backend's ATTENDANCE_STATUSES. A plain module (no
// "use client"), so both the teacher's client form and server-rendered read views can import it.
export const ATTENDANCE_STATUSES = ["present", "absent", "late", "excused"] as const;
export type AttendanceStatus = (typeof ATTENDANCE_STATUSES)[number];
export const ATTENDANCE_LABEL: Record<AttendanceStatus, string> = { present: "Present", absent: "Absent", late: "Late", excused: "Excused" };
