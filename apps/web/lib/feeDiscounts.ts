// itc-014 (DEC-SCOPE-363): discount requests and their approval (maker-checker). API_CONTRACT.md §12JI.
export const DISCOUNT_QUEUE_URL = "/api/v1/it/discount-requests";
export const discountRequestsUrl = (enrollmentId: string) => `/api/v1/it/enrollments/${encodeURIComponent(enrollmentId)}/discount-requests`;
export const decideUrl = (requestId: string, verb: "approve" | "reject") => `${DISCOUNT_QUEUE_URL}/${encodeURIComponent(requestId)}/${verb}`;

type Person = { id: string; full_name: string };
export type DiscountRequest = {
  id: string;
  enrollment_id: string;
  enrollment_code: string | null;
  student: Person;
  course: string;
  amount: number;
  reason: string;
  status: "pending" | "approved" | "rejected";
  requested_by: Person;
  created_at: string;
  decided_by: Person | null;
  decided_at: string | null;
  decision_note: string | null;
  own: boolean; // the caller asked for it, so they can never decide it
};

export const DISCOUNT_STATUS: Record<DiscountRequest["status"], { label: string; tone: string }> = {
  pending: { label: "Waiting for approval", tone: "status pending" },
  approved: { label: "Approved", tone: "status" },
  rejected: { label: "Rejected", tone: "status error" },
};
