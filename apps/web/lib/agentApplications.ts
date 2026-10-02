// AGN-008 (DEC-SCOPE-050): an agency's applications -- the shapes, labels and stage rules the list, detail and forms share. The
// server is the authority (forward-only, enrolled, stale, archived); these only keep the screens from offering a refused action.

export const APPLICATIONS_URL = "/api/v1/workflows/overseas/agent/crm/applications";

const STAGES = ["enquiry", "eligibility_evaluation", "university_selection", "offer", "visa_documentation", "status_tracking", "enrolled"] as const;
const AGENT_MAX_STAGE = "status_tracking";

// Every stage, `withdrawn` and a legacy value (QA8-11, e.g. "University review"): underscores to spaces, first letter capital.
export function stageLabel(status: string): string {
  const words = status.replaceAll("_", " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export const STATUS_GROUPS = ["all", "draft", "submitted", "offer", "visa", "enrolled", "withdrawn"] as const;
export type StatusGroup = (typeof STATUS_GROUPS)[number];
export const GROUP_LABELS: Record<StatusGroup, string> = {
  all: "All applications",
  draft: "Draft",
  submitted: "Submitted",
  offer: "Offer received",
  visa: "Visa",
  enrolled: "Enrolled",
  withdrawn: "Withdrawn",
};

export function parseGroup(value: string | null | undefined): StatusGroup {
  return (STATUS_GROUPS as readonly string[]).includes(value ?? "") ? (value as StatusGroup) : "all";
}

// The stages an agent may move to next: every later stage up to status_tracking (skips allowed, as counselor /advance allows).
export function nextStages(current: string): string[] {
  if (current === "withdrawn" || current === "enrolled") return [];
  const at = (STAGES as readonly string[]).indexOf(current); // a legacy value counts as before the first stage (-1)
  return STAGES.slice(at + 1, STAGES.indexOf(AGENT_MAX_STAGE) + 1);
}

export function canWithdraw(current: string): boolean {
  return current !== "withdrawn" && current !== "enrolled";
}

// AGN-013 E6: a Master confirms enrollment from an offer onwards (the server is the authority).
const ENROLLABLE_STAGES: readonly string[] = STAGES.slice(STAGES.indexOf("offer"), STAGES.indexOf(AGENT_MAX_STAGE) + 1);
export function canConfirmEnrollment(status: string): boolean {
  return ENROLLABLE_STAGES.includes(status);
}
export type EnrollmentCheck = "after_intake" | "intake_unrecognised" | null;
export const ENROLLMENT_CHECK_TEXT: Record<Exclude<EnrollmentCheck, null>, string> = {
  after_intake: "The enrollment date is in the future and after the intake month. Check the date.",
  intake_unrecognised: "The intake is not a month and year, so the enrollment date was not checked against it.",
};

export type NearestDeadline = { kind: "application" | "offer"; date: string } | null;

export function deadlineText(nearest: NearestDeadline, today: string): string | null {
  if (!nearest) return null;
  const label = nearest.kind === "offer" ? "Offer deadline" : "Application deadline";
  const days = Math.round((Date.parse(nearest.date) - Date.parse(today)) / 86_400_000);
  if (days < 0) return `${label} ${nearest.date} (past)`;
  if (days === 0) return `${label} ${nearest.date} (today)`;
  if (days <= 7) return `${label} ${nearest.date} (in ${days} day${days === 1 ? "" : "s"})`;
  return `${label} ${nearest.date}`;
}

export function todayIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export type AgentApplicationItem = {
  id: string;
  agent_student_id: string | null;
  student: string;
  has_login: boolean;
  university: string;
  course: string | null;
  intake: string;
  status: string;
  application_reference: string | null;
  submitted_on: string | null;
  application_deadline: string | null;
  offer_deadline: string | null;
  nearest_deadline: NearestDeadline;
  next_action: string | null;
  updated_at: string;
};
export type HistoryEntry = { from_status: string | null; to_status: string; next_action: string | null; notes: string | null; changed_by: string | null; created_at: string };
export type AgentApplicationDetail = AgentApplicationItem & {
  university_id: string;
  university_slug: string;
  course_id: string | null;
  created_at: string;
  read_only_reason: "withdrawn" | "archived" | null;
  enrollment_date: string | null;
  university_student_id: string | null;
  enrollment_confirmed_at: string | null;
  enrollment_check: EnrollmentCheck;
  history: HistoryEntry[];
  offer: AgentOffer | null;
  offer_letters: OfferLetterOption[];
  // AGN-011: optional so a detail from before the deposit existed (or a test fixture) still renders.
  deposit?: AgentDeposit | null;
  payment_available?: boolean;
};

// AGN-011 (DEC-SCOPE-057): the university deposit, paid through EduSphere Razorpay by a Master or Staff member. INR only (D1); amounts
// arrive as 2-decimal strings. Only the server moves it to paid (webhook/verify) and only an Overseas Admin to remitted/refunded.
export type DepositStatus = "not_required" | "pending" | "paid" | "remitted" | "refunded";
export const DEPOSIT_STATUS_LABELS: Record<DepositStatus, string> = {
  not_required: "Not required",
  pending: "Awaiting payment",
  paid: "Paid",
  remitted: "Remitted to the university",
  refunded: "Refunded",
};
export type AgentDeposit = {
  id: string;
  required: boolean;
  amount: string | null;
  currency: string;
  due_date: string | null;
  status: DepositStatus;
  paid_at: string | null;
  paid_by: string | null;
  receipt_available: boolean;
  remitted_at: string | null;
  remittance_reference: string | null;
  refunded_at: string | null;
  refund_amount: string | null;
  refund_reason: string | null;
  checkout_in_progress: boolean;
};
export const depositUrl = (id: string) => `${APPLICATIONS_URL}/${id}/deposit`;
export const PAYMENT_UNAVAILABLE = "Online payment is unavailable right now. Nothing has been charged.";
const INR = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" });
export const formatInr = (amount: string) => INR.format(Number(amount));

// AGN-010 (DEC-SCOPE-056): one current offer per application; its deadline is the application's `offer_deadline` (O2) and its letter
// an AGN-009 document of type "Offer letter" attached to this application (O3). The server checks every rule again.
export type OfferType = "conditional" | "unconditional";
export const OFFER_TYPE_LABELS: Record<OfferType, string> = { conditional: "Conditional", unconditional: "Unconditional" };
export type OfferLetterOption = { id: string; name: string; verification_status: string };
export type AgentOffer = { type: OfferType; date: string; deadline: string | null; conditions: string | null; document: OfferLetterOption | null };
export const offerUrl = (id: string) => `${APPLICATIONS_URL}/${id}/offer`;

export const READ_ONLY_TEXT: Record<"withdrawn" | "archived", string> = {
  withdrawn: "This application is withdrawn, so it can no longer be changed.",
  archived: "This student is archived. Unarchive them on the Students page to change this application.",
};
