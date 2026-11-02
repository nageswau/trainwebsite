// itc-021 (DEC-SCOPE-349 L1): IT attendance stores "excused" and shows it as "Approved leave". School attendance keeps its own labels
// (lib/attendance.ts). A plain module, so client panels and server views can both import it.
export const IT_ATTENDANCE_STATUSES = ["present", "absent", "late", "excused"] as const;

const LABELS: Record<string, string> = { present: "Present", absent: "Absent", late: "Late", excused: "Approved leave" };

export const itAttendanceLabel = (status: string) => LABELS[status] ?? status;

// L2: how approved leave counts in the attendance %, as the IT Admin picks it on the certificate rules panel.
export const LEAVE_POLICIES = [
  { value: "attended", label: "Attended" },
  { value: "excluded", label: "Left out of the percentage" },
  { value: "absent", label: "Absent" },
] as const;
export type LeavePolicy = (typeof LEAVE_POLICIES)[number]["value"];
