import { COMPANIES_URL } from "@/lib/recruiterCompanies";

// rec-030 (DEC-SCOPE-153): a company's contract / MoU. The API owns every rule (dates, fee, Expired, the document before Signed, scope);
// these helpers only shape requests and read responses. The statuses are the source's, in its order (EVID-018 §22; AC1).
export type ContractStatus = "discussion" | "proposal_sent" | "negotiation" | "contract_sent" | "signed" | "active" | "expired";
export type FeeBasis = "fixed" | "percent_of_ctc";
export type DocumentKind = "contract" | "mou";
export const CONTRACT_STATUSES: { key: ContractStatus; label: string }[] = [
  { key: "discussion", label: "Discussion" },
  { key: "proposal_sent", label: "Proposal Sent" },
  { key: "negotiation", label: "Negotiation" },
  { key: "contract_sent", label: "Contract Sent" },
  { key: "signed", label: "Signed" },
  { key: "active", label: "Active" },
  { key: "expired", label: "Expired" },
];
/** CT2: Expired is derived from the end date, never chosen. */
export const SETTABLE_CONTRACT_STATUSES = CONTRACT_STATUSES.filter((s) => s.key !== "expired");
export const FEE_BASES: { key: FeeBasis; label: string }[] = [
  { key: "fixed", label: "Fixed amount per hire (₹)" },
  { key: "percent_of_ctc", label: "Percentage of CTC" },
];
export const DOCUMENT_LABEL: Record<DocumentKind, string> = { contract: "Contract document", mou: "MoU" };

export type ContractDocument = { name: string | null; content_type: string; uploaded_at: string };
export type ContractPerson = { id: string; full_name: string; active: boolean };
export type Contract = {
  id: string; status: ContractStatus; status_label: string; status_changed_at: string; agreement_type: string | null; start_date: string | null;
  end_date: string | null; expired_on: string | null; fee_basis: FeeBasis | null; fee_value: string | null; payment_terms: string | null;
  replacement_policy: string | null; contract_document: ContractDocument | null; mou_document: ContractDocument | null; is_current: boolean;
  created_by: ContractPerson; permissions: { can_edit: boolean; can_upload: boolean; can_renew: boolean }; created_at: string; updated_at: string;
};
export type CompanyContracts = { current: Contract | null; previous: Contract[]; can_start: boolean };
export type ContractEvent = {
  id: string; kind: "created" | "status" | "updated" | "document" | "renewed"; from_status: ContractStatus | null; from_label: string | null;
  to_status: ContractStatus; to_label: string; changed: string[]; actor: ContractPerson; created_at: string;
};
export type ContractFields = {
  agreement_type: string; start_date: string; end_date: string; fee_basis: string; fee_value: string; payment_terms: string; replacement_policy: string;
};

export const CONTRACTS_URL = "/api/v1/recruiter/contracts";
export const CONTRACT_HISTORY_PAGE = 20;
export const FIELD_LABEL: Record<string, string> = {
  status: "Status", agreement_type: "Agreement type", start_date: "Contract start date", end_date: "Contract end date",
  fee_basis: "Fee basis", fee_value: "Recruitment fee", payment_terms: "Payment terms", replacement_policy: "Replacement policy",
  contract_document: "Contract document", mou_document: "MoU",
};

export const companyContractsUrl = (companyId: string) => `${COMPANIES_URL}/${companyId}/contracts`;
export const contractDocumentUrl = (contractId: string, kind: DocumentKind) => `${CONTRACTS_URL}/${contractId}/documents/${kind}`;
export const contractHistoryUrl = (contractId: string, offset = 0) => `${CONTRACTS_URL}/${contractId}/history?limit=${CONTRACT_HISTORY_PAGE}&offset=${offset}`;

/** "₹50,000 per hire" or "8.33% of CTC"; "—" when no fee is recorded. */
export function feeText(c: Pick<Contract, "fee_basis" | "fee_value">): string {
  if (c.fee_basis === null || c.fee_value === null) return "—";
  const value = Number(c.fee_value);
  if (c.fee_basis === "percent_of_ctc") return `${value.toLocaleString("en-IN", { maximumFractionDigits: 2 })}% of CTC`;
  return `₹${value.toLocaleString("en-IN", { maximumFractionDigits: 2 })} per hire`;
}

export function isContractBody(data: unknown): data is { contract: Contract } {
  const contract = (data as { contract?: { id?: unknown } } | null)?.contract;
  return !!contract && typeof contract.id === "string";
}

export function isCompanyContracts(data: unknown): data is CompanyContracts {
  const d = data as Partial<CompanyContracts> | null;
  return !!d && typeof d === "object" && "current" in d && Array.isArray(d.previous) && typeof d.can_start === "boolean";
}

/** The contract 409s that carry a code (someone changed it, it expired, it exists, the dates overlap): their message, else null. */
export function contractConflict(detail: unknown): string | null {
  const d = detail as { code?: unknown; message?: unknown } | null;
  if (!d || typeof d !== "object" || typeof d.message !== "string") return null;
  if (d.code === "contract_status_changed") return `${d.message}.`;
  if (d.code === "contract_changed") return `${d.message}. Check it and try again.`;
  return ["contract_expired", "contract_exists"].includes(String(d.code)) ? d.message : null;
}
