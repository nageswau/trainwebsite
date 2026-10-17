// AGN-024 (DEC-SCOPE-224): the three KYC documents an education agent uploads at signup (K1), their numbers (K2: only the last 4
// Aadhaar digits) and the 5 MB PDF/JPG/PNG rule (K8). The server re-checks everything; these checks only give fast feedback.
export type KycDocType = "pan" | "aadhaar" | "business_license";
export type KycStatus = "pending" | "verified" | "rejected";
export type KycDocSpec = {
  type: KycDocType; label: string; numberField: string; numberLabel: string; fileField: string;
  pattern: string; maxLength: number; inputMode?: "numeric"; hint?: string;
};
type KycDocBase = { id: string; doc_type: KycDocType; label: string; status: KycStatus; rejection_reason: string | null; original_filename: string | null; content_type: string; file_size: number; updated_at: string };
export type AgentKycDoc = KycDocBase & { doc_number_display: string };
export type AdminKycDoc = KycDocBase & { doc_number: string; reviewed_at: string | null };

export const KYC_DOCS: readonly KycDocSpec[] = [
  { type: "pan", label: "PAN card", numberField: "pan_number", numberLabel: "PAN number", fileField: "pan_file", pattern: "[A-Za-z]{5}[0-9]{4}[A-Za-z]", maxLength: 10, hint: "Format: ABCDE1234F." },
  { type: "aadhaar", label: "Aadhaar card", numberField: "aadhaar_last4", numberLabel: "Aadhaar (last 4 digits)", fileField: "aadhaar_file", pattern: "[0-9]{4}", maxLength: 4, inputMode: "numeric", hint: "Only the last 4 digits are stored." },
  { type: "business_license", label: "Business licence", numberField: "license_number", numberLabel: "Business licence number", fileField: "license_file", pattern: "[A-Za-z0-9/\-. ]{3,64}", maxLength: 64 },
];
export const KYC_MAX_BYTES = 5 * 1024 * 1024;
export const KYC_ACCEPT = ".pdf,.jpg,.jpeg,.png";
export const REGISTRATION_URL = "/api/v1/agent/registration";
export const REGISTRATION_STATUS_PATH = "/overseas/agent/registration-status";
export const adminKycUrl = (orgId: string) => `/api/v1/overseas-admin/agent-orgs/${orgId}/kyc-documents`;
export const STATUS_LABEL: Record<KycStatus, string> = { pending: "Pending review", verified: "Verified", rejected: "Rejected" };

export function checkKycFile(label: string, file: File | null): string | null {
  if (!file || !file.size) return `${label}: choose a file.`;
  if (!/\.(pdf|jpe?g|png)$/i.test(file.name)) return `${label}: upload a PDF, JPG or PNG file.`;
  if (file.size > KYC_MAX_BYTES) return `${label}: the file must be at most 5 MB.`;
  return null;
}
