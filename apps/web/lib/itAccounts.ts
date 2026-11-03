// itc-017 (DEC-SCOPE-368): the IT accounts workspace -- five read-only reports over IT enrolment fees (API §12JN). The filters live in the
// address (a GET form), so refresh, Back and a shared link keep the view; anything unknown in the address is dropped here.

const IT_ACCOUNTS_API = "/api/v1/it/accounts/reports";
export const IT_ADMIN_ACCOUNTS = "/it/admin/accounts";
export const MANAGEMENT_IT_ACCOUNTS = "/management/it-accounts";
const ACCOUNTS_PAGE_SIZE = 50;

export type AccountsReport = "collections" | "outstanding" | "overdue" | "receipts" | "adjustments";
export const ACCOUNTS_TABS: { key: AccountsReport; label: string; about: string }[] = [
  { key: "collections", label: "Collections", about: "Confirmed fee payments, by the India (IST) day, month or course they were paid in." },
  { key: "outstanding", label: "Outstanding", about: "Active enrolments that still owe fees today, with the overdue part and a total per course." },
  { key: "overdue", label: "Overdue installments", about: "Installments still owed after their due date (India time), with the reminders sent." },
  { key: "receipts", label: "Receipts register", about: "Every receipt issued for an IT enrolment fee. A receipt of a corrected payment is shown but not added up." },
  { key: "adjustments", label: "Refunds & adjustments", about: "Credit notes, write-offs, refunds and payment corrections recorded on fee accounts." },
];

export const MODE_LABEL: Record<string, string> = { cash: "Cash", upi: "UPI", card: "Card", bank_transfer: "Bank transfer", cheque: "Cheque", razorpay: "Razorpay" };
export const KIND_LABEL: Record<string, string> = { credit_note: "Credit note", write_off: "Write-off", refund: "Refund", reversal: "Payment correction" };
export const STATE_LABEL: Record<string, string> = { enrolled_pending_payment: "Nothing paid yet", partially_paid: "Partly paid", overdue: "Has overdue installments" };
export const GROUP_LABEL: Record<string, string> = { day: "Day", month: "Month", course: "Course" };
const STATUS_LABEL: Record<string, string> = { paid: "Paid", succeeded: "Paid", reversed: "Corrected" };

const FILTERS = ["program_id", "batch_id", "date_from", "date_to", "group", "mode", "kind", "state"] as const;
type FilterKey = (typeof FILTERS)[number];
export type AccountsParams = Partial<Record<FilterKey, string>> & { offset?: number };

// Which filters each report takes (the API ignores the rest; the form never shows them).
const DATED: AccountsReport[] = ["collections", "receipts", "adjustments"];
export const takes = (report: AccountsReport, key: FilterKey): boolean =>
  key === "program_id" || key === "batch_id" ||
  ((key === "date_from" || key === "date_to") && DATED.includes(report)) ||
  (key === "group" && report === "collections") ||
  (key === "mode" && (report === "collections" || report === "receipts")) ||
  (key === "kind" && report === "adjustments") ||
  (key === "state" && report === "outstanding");

export function accountsReport(value: string | string[] | undefined): AccountsReport {
  return ACCOUNTS_TABS.some((t) => t.key === value) ? (value as AccountsReport) : "collections";
}

/** The report's filters from the page's search params: known keys only, one value each; a negative or malformed offset reads as 0. */
export function accountsParams(report: AccountsReport, search: Record<string, string | string[] | undefined>): AccountsParams {
  const out: AccountsParams = {};
  for (const key of FILTERS) {
    const value = search[key];
    if (typeof value === "string" && value && takes(report, key)) out[key] = value;
  }
  const offset = Number.parseInt(typeof search.offset === "string" ? search.offset : "", 10);
  if (offset > 0) out.offset = offset;
  return out;
}

function query(params: AccountsParams, extra: Record<string, string> = {}): string {
  const q = new URLSearchParams(extra);
  for (const key of FILTERS) if (params[key]) q.set(key, params[key]!);
  return q.toString();
}

export const accountsUrl = (report: AccountsReport, params: AccountsParams) =>
  `${IT_ACCOUNTS_API}/${report}?${query(params, { limit: String(ACCOUNTS_PAGE_SIZE), offset: String(params.offset ?? 0) })}`;
export const exportUrl = (report: AccountsReport, params: AccountsParams) => {
  const q = query(params);
  return `${IT_ACCOUNTS_API}/${report}/export${q ? `?${q}` : ""}`;
};
/** A page or tab of the workspace: the course and batch carry across tabs; the date range too where the next report takes one. */
export function accountsHref(basePath: string, report: AccountsReport, params: AccountsParams, offset = 0): string {
  const kept: AccountsParams = {};
  for (const key of FILTERS) if (params[key] && takes(report, key)) kept[key] = params[key];
  const q = query(kept, { report });
  return `${basePath}?${q}${offset > 0 ? `&offset=${offset}` : ""}`;
}

export type AccountsRow = Record<string, string | number | null>;
export type AccountsPage = {
  report: AccountsReport; items: AccountsRow[]; total: number; limit: number; offset: number;
  totals: Record<string, number>; by_course?: { program_id: string; title: string; enrolments: number; balance: number }[];
  filters: Record<FilterKey, string | null>; courses: { id: string; title: string }[]; batches: { id: string; name: string; program_id: string }[];
};

const INR = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const inr = (value: number | string | null | undefined) => (value === null || value === undefined || value === "" ? "—" : INR.format(Number(value)));

/** "2026-10-15" -> "15 Oct 2026" (a calendar day: no time zone shift). */
export function day(value: string | number | null | undefined): string {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return "—";
  const [y, m, d] = value.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" });
}

type Column = { key: string; label: string; show: (v: string | number | null) => string; num?: boolean };
const text = (v: string | number | null) => (v === null || v === "" ? "—" : String(v));
const money = (key: string, label: string): Column => ({ key, label, show: inr, num: true });
const STUDENT: Column[] = [
  { key: "student_name", label: "Student", show: text }, { key: "student_code", label: "Student ID", show: text },
  { key: "enrollment_code", label: "Enrolment", show: text }, { key: "course", label: "Course", show: text }, { key: "batch", label: "Batch", show: text },
];
export const ACCOUNTS_COLUMNS: Record<AccountsReport, Column[]> = {
  collections: [{ key: "label", label: "Period or course", show: text }, { key: "payments", label: "Payments", show: text, num: true }, money("amount", "Amount")],
  outstanding: [
    ...STUDENT, money("total_payable", "Total payable"), money("paid_confirmed", "Paid"), money("balance", "Balance"), money("overdue_amount", "Overdue"),
    { key: "next_due_date", label: "Next due", show: day }, { key: "state", label: "State", show: (v) => STATE_LABEL[String(v)] ?? text(v) },
  ],
  overdue: [
    ...STUDENT, { key: "installment_no", label: "Installment", show: text, num: true }, { key: "due_date", label: "Due date", show: day },
    { key: "days_overdue", label: "Days overdue", show: text, num: true }, money("amount", "Amount"), { key: "reminders", label: "Reminders sent", show: text, num: true },
  ],
  receipts: [
    { key: "receipt_no", label: "Receipt", show: text }, { key: "issued_on", label: "Issued on", show: day }, ...STUDENT, money("amount", "Amount"),
    { key: "payment_mode", label: "Mode", show: (v) => MODE_LABEL[String(v)] ?? text(v) }, { key: "reference", label: "Reference", show: text },
    { key: "status", label: "Status", show: (v) => STATUS_LABEL[String(v)] ?? text(v) },
  ],
  adjustments: [
    { key: "document_no", label: "Document", show: text }, { key: "created_on", label: "Date", show: day },
    { key: "kind", label: "Kind", show: (v) => KIND_LABEL[String(v)] ?? text(v) }, ...STUDENT, money("amount", "Amount"),
    { key: "payment_mode", label: "Mode", show: (v) => MODE_LABEL[String(v)] ?? text(v) }, { key: "reference", label: "Reference", show: text },
    { key: "reason", label: "Reason", show: text },
  ],
};

/** The headline figures of the whole filtered list (not just the page), as label/value pairs. */
export function accountsTotals(report: AccountsReport, totals: Record<string, number>): { label: string; value: string }[] {
  switch (report) {
    case "collections": return [{ label: "Collected", value: inr(totals.amount) }, { label: "Payments", value: String(totals.payments) }];
    case "outstanding": return [{ label: "Outstanding", value: inr(totals.balance) }, { label: "Of which overdue", value: inr(totals.overdue_amount) }, { label: "Enrolments owing", value: String(totals.enrolments) }];
    case "overdue": return [{ label: "Overdue", value: inr(totals.amount) }, { label: "Installments", value: String(totals.installments) }];
    case "receipts": return [{ label: "Receipted", value: inr(totals.amount) }, { label: "Receipts", value: String(totals.receipts) }];
    case "adjustments": return [
      { label: "Credit notes", value: inr(totals.credit_note) }, { label: "Write-offs", value: inr(totals.write_off) },
      { label: "Refunds", value: inr(totals.refund) }, { label: "Entries", value: String(totals.count) },
    ];
  }
}
