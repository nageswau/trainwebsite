import { COMPANIES_URL } from "@/lib/recruiterCompanies";
import type { PaymentStatus, Person, Ref, RequirementRef } from "@/lib/recruiterRevenue";

// pob-012 (DEC-SCOPE-433): vendor bills (payables / receivables), their payments, and vendor performance. The API computes every figure
// and enforces every rule (the grant, scope, over-payment cap); these helpers shape URLs and words. A null rate is "—", never 0%.
export type BillKind = "payable" | "receivable";
export type VendorBillPayment = { id: string; paid_on: string; amount: string; reference: string | null; created_by: Person; created_at: string };
export type VendorBill = {
  id: string; kind: BillKind; kind_label: string; bill_number: string; bill_date: string; due_date: string; amount: string; milestone: string | null;
  note: string | null; paid: string; outstanding: string; payment_status: PaymentStatus; payment_status_label: string; overdue: boolean;
  cancelled_at: string | null; cancel_reason: string | null; requirement: RequirementRef | null; created_by: Person; payments: VendorBillPayment[];
  permissions: { can_pay: boolean; can_cancel: boolean }; created_at: string;
};
export type MoneyTotals = { billed: string; paid: string; outstanding: string; last_paid_on: string | null };
export type VendorBillList = { items: VendorBill[]; totals: Record<BillKind, MoneyTotals>; can_edit: boolean };
export type VendorMetrics = {
  requirements: number; responded_requirements: number; avg_response_hours: string | null; submitted: number; interviewed: number; placed: number;
  joined: number; interview_rate: string | null; joining_rate: string | null; payments: Record<BillKind, MoneyTotals>;
};
export type VendorPerformanceRow = { vendor: Ref; vendor_status_label: string | null; metrics: VendorMetrics };
export type VendorPerformancePage = { items: VendorPerformanceRow[]; total: number; limit: number; offset: number };
export type VendorRequirementRow = { requirement: RequirementRef; created_at: string; first_submission_at: string | null; response_hours: string | null };
export type VendorSubmissionRow = {
  application_id: string; candidate: Ref; requirement: RequirementRef; submitted_at: string; interviewed: boolean; placed: boolean; joined: boolean;
};
export type VendorPerformanceDetail = VendorPerformanceRow & { requirements: VendorRequirementRow[]; submissions: VendorSubmissionRow[] };

export const BILL_KINDS: { key: BillKind; label: string }[] = [{ key: "payable", label: "We owe the vendor" }, { key: "receivable", label: "The vendor owes us" }];
export const VENDOR_BILLS_URL = "/api/v1/recruiter/vendor-bills";
export const VENDOR_PERFORMANCE_URL = "/api/v1/recruiter/vendors/performance";
export const VENDOR_PERFORMANCE_PATH = "/recruiter/vendors/performance";
export const PERFORMANCE_LIMIT = 50;
export const vendorBillsUrl = (companyId: string) => `${COMPANIES_URL}/${encodeURIComponent(companyId)}/vendor-bills`;
export const billActionUrl = (id: string, action: "payments" | "cancel") => `${VENDOR_BILLS_URL}/${encodeURIComponent(id)}/${action}`;
export const vendorPerformanceUrl = (id: string) => `/api/v1/recruiter/vendors/${encodeURIComponent(id)}/performance`;
export const vendorPerformancePath = (id: string) => `/recruiter/vendors/${encodeURIComponent(id)}/performance`;
export const performancePageUrl = (offset = 0) => `${VENDOR_PERFORMANCE_URL}?limit=${PERFORMANCE_LIMIT}&offset=${offset}`;

/** "75.0%", or "—" when there is nothing to divide by (the backlog's +/−/E). */
export const rateText = (rate: string | null) => (rate === null ? "—" : `${rate}%`);
/** "6.0 h", or "—" when no requirement has been shared with the vendor yet. */
export const hoursText = (hours: string | null) => (hours === null ? "—" : `${hours} h`);

export function isVendorBillList(data: unknown): data is VendorBillList {
  const d = data as Partial<VendorBillList> | null;
  return !!d && Array.isArray(d.items) && !!d.totals && typeof d.can_edit === "boolean";
}

export function isVendorPerformancePage(data: unknown): data is VendorPerformancePage {
  const d = data as Partial<VendorPerformancePage> | null;
  return !!d && Array.isArray(d.items) && typeof d.total === "number";
}

export function isVendorPerformanceDetail(data: unknown): data is VendorPerformanceDetail {
  const d = data as Partial<VendorPerformanceDetail> | null;
  return !!d && !!d.metrics && Array.isArray(d.requirements) && Array.isArray(d.submissions);
}
