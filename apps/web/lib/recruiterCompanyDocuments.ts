// pob-003 (DEC-SCOPE-406 D6-D8): a company's document store -- types, endpoints and labels. The API scopes every row, decides
// `can_upload` / `can_upload_agreement` / `can_download`, sniffs the bytes and audits every upload and download.
import { COMPANIES_URL, type Person } from "@/lib/recruiterCompanies";

export const DOCUMENT_KINDS = ["company_profile", "vendor_onboarding_form", "recruitment_agreement", "job_description", "meeting_notes", "nda"] as const;
export type DocumentKind = (typeof DOCUMENT_KINDS)[number];
export const KIND_LABEL: Record<DocumentKind, string> = {
  company_profile: "Company profile",
  vendor_onboarding_form: "Vendor onboarding form",
  recruitment_agreement: "Recruitment agreement",
  job_description: "Job description",
  meeting_notes: "Meeting notes",
  nda: "Signed NDA",
};
export const AGREEMENT: DocumentKind = "recruitment_agreement";

export type CompanyDocument = {
  id: string; kind: DocumentKind; name: string | null; content_type: string; size_bytes: number;
  meeting: { id: string; code: string; starts_at: string } | null; uploaded_by: Person; created_at: string; can_download: boolean;
};
export type DocumentPage = { items: CompanyDocument[]; total: number; limit: number; offset: number; can_upload: boolean; can_upload_agreement: boolean };

export const documentsUrl = (companyId: string) => `${COMPANIES_URL}/${companyId}/documents`;
export const downloadUrl = (documentId: string) => `${COMPANIES_URL}/documents/${documentId}/download`;

export function isDocumentPage(data: unknown): data is DocumentPage {
  const page = data as Partial<DocumentPage> | null;
  return !!page && Array.isArray(page.items) && typeof page.can_upload === "boolean";
}

export function fileSize(bytes: number): string {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
