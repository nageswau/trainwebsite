// ccrm-020 (DEC-SCOPE-265): a counselor's / Overseas Admin's document requests to a direct student. The server
// (api/student_document_requests.py) owns every rule -- scope, due date, duplicates, overdue, reopen on rejection; this shapes responses.

export const staffRequestsUrl = (studentId: string) => `/api/v1/counselor/students/${studentId}/document-requests`;
export const MY_REQUESTS_URL = "/api/v1/overseas/me/document-requests";
export const uploadUrl = (requestId: string) => `${MY_REQUESTS_URL}/${requestId}/upload`;

export type RequestStatus = "open" | "fulfilled" | "cancelled";
export type DocumentRequest = {
  id: string;
  document_type: string;
  document_label: string | null;
  name: string;
  note: string | null;
  review_note?: string | null; // why an open request is open again: the counselor's note on the rejected upload (R1)
  status: RequestStatus;
  due_date: string | null;
  overdue: boolean;
  application_id: string | null;
  application_code: string | null;
  university: string | null;
  checklist_item_id: string | null;
  requested_by: string | null;
  created_at: string;
  closed_at: string | null;
  document: { id: string; original_filename: string | null; verification_status: string; status_label: string } | null;
};
export type RequestPage = { items: DocumentRequest[]; total: number; limit: number; offset: number };

export const REQUEST_STATUS_LABELS: Record<RequestStatus, string> = { open: "Open", fulfilled: "Uploaded", cancelled: "Cancelled" };

/** Today in India (the server's due-date calendar), as yyyy-mm-dd for a date input's `min`. */
export function todayInIndia(now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata", year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
}
