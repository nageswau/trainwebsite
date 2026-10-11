import { COMPANIES_URL } from "@/lib/recruiterCompanies";
import { type FeeBasis, feeText } from "@/lib/recruiterContracts";
import { REQUIREMENTS_URL } from "@/lib/recruiterRequirements";

// rec-031 (DEC-SCOPE-175): revenue per requirement and company, invoices, payments and the receivables list. Track only (R9): the API
// computes every figure and enforces every rule (Joined only, the fee source, the over-payment cap, scope); these helpers shape requests
// and words. Amounts travel as decimal strings ("150000.00") and are shown in rupees with Indian grouping.
export type PaymentStatus = "unpaid" | "part_paid" | "paid" | "cancelled";
export type ReceivableView = "outstanding" | "overdue" | "paid" | "cancelled";
export type Ref = { id: string; code: string; name: string };
export type RequirementRef = { id: string; code: string; title: string };
export type Person = { id: string; full_name: string; active: boolean };
export type RevenueFee = {
  basis: FeeBasis | null; value: string | null; source: "requirement" | "contract" | null; contract_status_label: string | null;
  override: { basis: FeeBasis; value: string } | null;
};
export type Payment = { id: string; received_on: string; amount: string; reference: string | null; created_by: Person; created_at: string };
export type Invoice = {
  id: string; invoice_number: string; invoice_date: string; due_date: string; amount: string; note: string | null; received: string; outstanding: string;
  payment_status: PaymentStatus; payment_status_label: string; overdue: boolean; cancelled_at: string | null; cancel_reason: string | null;
  requirement: RequirementRef; company: Ref; created_by: Person; payments: Payment[]; permissions: { can_pay: boolean; can_cancel: boolean }; created_at: string;
};
export type Hire = { application_id: string; candidate: Ref; joined_on: string | null; fee: string | null };
export type RequirementRevenue = {
  requirement: RequirementRef; company: Ref; selected: number; joined: number; fee: RevenueFee; hires: Hire[]; expected_revenue: string | null;
  unpriced_hires: number; invoiced: string; received: string; outstanding: string; over_invoiced: boolean; invoices: Invoice[];
  permissions: { can_invoice: boolean; can_set_fee: boolean };
};
export type CompanyRevenueRow = {
  requirement: RequirementRef; status_label: string; selected: number; joined: number; fee: RevenueFee; expected_revenue: string | null; invoiced: string;
  received: string; outstanding: string;
};
export type Totals = { selected: number; joined: number; expected_revenue: string; invoiced: string; received: string; outstanding: string };
export type CompanyRevenue = { requirements: CompanyRevenueRow[]; totals: Totals };
export type InvoicePage = { items: Invoice[]; total: number; limit: number; offset: number; counts: Record<ReceivableView, number>; outstanding_total: string };

/** RV10: who sees revenue (the API answers 403 to anyone else, e.g. the BDM who reads the requirement). */
export const canSeeRevenue = (role: string) => ["placement_team", "placement_manager", "super_admin"].includes(role);
export const INVOICES_URL = "/api/v1/recruiter/invoices";
export const RECEIVABLES_PATH = "/recruiter/receivables";
export const RECEIVABLES_LIMIT = 50;
export const RECEIVABLE_TABS: [ReceivableView, string][] = [["outstanding", "Outstanding"], ["overdue", "Overdue"], ["paid", "Paid"], ["cancelled", "Cancelled"]];
export const requirementRevenueUrl = (id: string) => `${REQUIREMENTS_URL}/${encodeURIComponent(id)}/revenue`;
export const requirementFeeUrl = (id: string) => `${REQUIREMENTS_URL}/${encodeURIComponent(id)}/fee`;
export const companyRevenueUrl = (id: string) => `${COMPANIES_URL}/${encodeURIComponent(id)}/revenue`;
export const invoiceActionUrl = (id: string, action: "payments" | "cancel") => `${INVOICES_URL}/${encodeURIComponent(id)}/${action}`;

export function invoicesUrl(view: ReceivableView, offset = 0, companyId?: string): string {
  const params = new URLSearchParams({ view, limit: String(RECEIVABLES_LIMIT), offset: String(offset) });
  if (companyId) params.set("company_id", companyId);
  return `${INVOICES_URL}?${params}`;
}

export const isReceivableView = (value: string | null): value is ReceivableView => RECEIVABLE_TABS.some(([key]) => key === value);

/** "₹1,50,000.00"; "—" when there is no amount. */
export function inr(amount: string | number | null): string {
  if (amount === null || amount === "") return "—";
  return `₹${Number(amount).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/** RV1: the fee per hire and where it comes from. */
export function feeSourceText(fee: RevenueFee): string {
  if (fee.basis === null || fee.value === null) return "No fee set";
  const where = fee.source === "requirement" ? "set for this requirement" : `from the company contract (${fee.contract_status_label})`;
  return `${feeText({ fee_basis: fee.basis, fee_value: fee.value })} · ${where}`;
}

/** The revenue 409s carry `{message, code}`: their message (sendJson's own text for a dict detail is generic), else null. */
export function revenueConflict(detail: unknown): string | null {
  const d = detail as { code?: unknown; message?: unknown } | null;
  if (!d || typeof d !== "object" || typeof d.message !== "string" || typeof d.code !== "string") return null;
  return ["invoice_number_taken", "invoice_cancelled", "invoice_has_payments"].includes(d.code) ? d.message : null;
}

export function isRequirementRevenue(data: unknown): data is RequirementRevenue {
  const d = data as Partial<RequirementRevenue> | null;
  return !!d && typeof d.joined === "number" && Array.isArray(d.invoices) && !!d.fee && !!d.permissions;
}

export function isCompanyRevenue(data: unknown): data is CompanyRevenue {
  const d = data as Partial<CompanyRevenue> | null;
  return !!d && Array.isArray(d.requirements) && !!d.totals;
}

export function isInvoicePage(data: unknown): data is InvoicePage {
  const d = data as Partial<InvoicePage> | null;
  return !!d && Array.isArray(d.items) && typeof d.total === "number" && !!d.counts;
}
