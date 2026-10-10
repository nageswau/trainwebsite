// upc-019 (DEC-SCOPE-161): the commission ledger of one university -- Expected (computed from enrolled applications x the commission
// terms), Received (recorded receipts) and Outstanding, per currency with no FX. RESTRICTED (U2): the API answers 403 to every other role
// and records only for the partnership head / super_admin (Q-20). Nothing here filters for security.
import type { ManagerRef } from "@/lib/telecaller";
import { universityUrl } from "@/lib/universities";

export { CURRENCIES } from "@/lib/agentStudents"; // models.COMMISSION_CURRENCIES

export type LedgerTotal = { currency: string; expected: string; received: string; outstanding: string };
export type LedgerStatus = "counted" | "awaiting_visa" | "trigger_not_tracked" | "no_term" | "tuition_unknown" | "date_unknown";
export type LedgerApplication = {
  id: string; course: string | null; intake: string; reference: string | null; enrolled_on: string | null; status: LedgerStatus; status_label: string;
  term_id: string | null; currency: string | null; amount: string | null;
};
export type CommissionReceipt = {
  id: string; amount: string; currency: string; received_on: string; reference: string; note: string | null; application_ids: string[];
  created_by: ManagerRef; created_at: string;
};
export type CommissionLedger = {
  university: { id: string; name: string; university_code: string }; totals: LedgerTotal[]; applications: LedgerApplication[];
  applications_total: number; receipts: CommissionReceipt[]; receipts_total: number; permissions: { can_record: boolean };
};
export type CurrencyAmount = { currency: string; amount: string };
export type PerformanceCommission = { expected: CurrencyAmount[]; received: CurrencyAmount[] };

export const ledgerUrl = (universityId: string) => universityUrl(universityId, "commission");
export const receiptsUrl = (universityId: string, receiptId?: string) => `${ledgerUrl(universityId)}/receipts${receiptId ? `/${receiptId}` : ""}`;

/** "GBP 2,700.00"; a negative outstanding keeps its sign ("-GBP 300.00"). */
export function moneyText(currency: string, amount: string): string {
  const n = Number(amount);
  const text = Math.abs(n).toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return `${n < 0 ? "-" : ""}${currency} ${text}`;
}

/** "GBP 5,400.00 · USD 50.00", or an em dash when nothing is due or received (F10 / F11 cells). */
export const amountsText = (amounts: CurrencyAmount[]) => (amounts.length ? amounts.map((a) => moneyText(a.currency, a.amount)).join(" · ") : "—");

/** A short, non-identifying label for an enrolled application (CL14: no student name anywhere). */
export const applicationLabel = (a: Pick<LedgerApplication, "id" | "course" | "intake" | "reference">) =>
  `${a.reference ?? `#${a.id.slice(0, 8)}`} · ${a.course ?? "No programme"} · ${a.intake}`;
