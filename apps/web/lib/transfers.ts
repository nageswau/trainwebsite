// ENH-005 -- shapes of the transfer API (docs/superpowers/specs/2026-09-21-enh-005-student-school-transfer-design.md §5.2-5.3)
// and how a status is shown. Status is always a text label plus a class, never colour alone.

export type TransferStatus = "pending" | "approved" | "rejected" | "cancelled";
export type TransferDirection = "outgoing" | "incoming";
export type SchoolRef = { id: string; name: string };

/** A coordinator's row. A not-yet-approved incoming row has student_id, student_name and from_school set to null. */
export type TransferRequest = {
  id: string;
  direction: TransferDirection;
  status: TransferStatus;
  student_id: string | null;
  student_code: string;
  student_name: string | null;
  from_school: SchoolRef | null;
  to_school: SchoolRef;
  reason: string | null;
  decision_note: string | null;
  created_at: string;
  decided_at: string | null;
};

export type TransferOutcome = { parents_moved: number; parents_kept: number; results_withdrawn: number; teacher_cleared: boolean; pending_parent_email_cleared: boolean };
export type TransferPreview = { linked_parents: number; in_flight_results: number; to_school_has_portfolio_staff: boolean };

/** The admin's row: always complete. */
export type AdminTransferRequest = {
  id: string;
  direction: TransferDirection;
  status: TransferStatus;
  student_id: string;
  student_code: string;
  student_name: string;
  from_school: SchoolRef;
  to_school: SchoolRef;
  filed_by_school: SchoolRef;
  requester: { id: string; name: string };
  reason: string | null;
  decision_note: string | null;
  decided_by: { id: string; name: string } | null;
  outcome: TransferOutcome | null;
  preview: TransferPreview | null;
  created_at: string;
  decided_at: string | null;
};

export const STATUS_LABEL: Record<TransferStatus, string> = {
  pending: "Pending review",
  approved: "Approved",
  rejected: "Rejected",
  cancelled: "Cancelled",
};

// The global `.status` classes: default, `.pending`, `.error`.
export const STATUS_CLASS: Record<TransferStatus, string> = {
  pending: "status pending",
  approved: "status",
  rejected: "status error",
  cancelled: "status",
};
