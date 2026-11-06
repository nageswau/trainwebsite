// hrc-015 (DEC-SCOPE-379): candidate documents, document requests and the short-lived signed links every resume/document download or
// preview goes through. The API decides file types by their bytes; the accept lists below only help the file picker.
import { detailMessage } from "@/lib/apiErrors";
import type { PersonRef } from "@/lib/telecallerLeads";

export type PreviewStatus = "pending" | "ready" | "failed" | null;
export type DocumentType = "certificate" | "education" | "experience_letter" | "relieving_letter" | "payslip" | "id_proof" | "other";
export const DOCUMENT_TYPES: { value: DocumentType; label: string }[] = [
  { value: "certificate", label: "Certificate" },
  { value: "education", label: "Education (degree or marksheet)" },
  { value: "experience_letter", label: "Experience letter" },
  { value: "relieving_letter", label: "Relieving letter" },
  { value: "payslip", label: "Payslip" },
  { value: "id_proof", label: "ID proof" },
  { value: "other", label: "Other" },
];
export const documentTypeLabel = (value: string) => DOCUMENT_TYPES.find((t) => t.value === value)?.label ?? value;
/** A document's title, else its type label. */
export const documentName = (d: { title: string | null; document_type: string }) => d.title || documentTypeLabel(d.document_type);

export type CandidateDocument = {
  id: string; document_type: DocumentType; title: string | null; file_name: string | null; content_type: string; size_bytes: number;
  preview_status: PreviewStatus; request_id: string | null; uploaded_by: PersonRef | "you" | "placement_team" | null; created_at: string;
};
export type DocumentRequestStatus = "pending" | "received" | "cancelled";
export type DocumentRequest = {
  id: string; document_type: DocumentType; note: string | null; due_date: string | null; status: DocumentRequestStatus; created_at: string;
  received_at: string | null; cancelled_at: string | null; document_id: string | null; requested_by?: PersonRef | null;
};
export type DocumentsState = { documents: CandidateDocument[]; requests: DocumentRequest[] };
export const REQUEST_STATUS_LABELS: Record<DocumentRequestStatus, string> = { pending: "Pending", received: "Received", cancelled: "Cancelled" };
/** hrc-031 (DEC-SCOPE-412 P5): "1 of 2 requested documents received"; cancelled requests do not count, and nothing asked for says nothing. */
export function documentCompletion(requests: DocumentRequest[]): string | null {
  const asked = requests.filter((r) => r.status !== "cancelled");
  if (asked.length === 0) return null;
  return `${asked.filter((r) => r.status === "received").length} of ${asked.length} requested documents received`;
}

export const DOCUMENT_ACCEPT = ".pdf,.doc,.docx,.png,.jpg,.jpeg,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,image/png,image/jpeg";
export const DOCUMENT_MAX_BYTES = 5 * 1024 * 1024;
export const MY_DOCUMENTS_URL = "/api/v1/account/candidate-documents";

export type LinkMode = "download" | "preview";
export type LinkOutcome = { ok: true; url: string } | { ok: false; status: number; message: string };
const NOT_COMPLETED = "Couldn't open the file. Check your connection and try again.";

/** A 300-second signed link for one file. 409 = the preview is still being prepared; 422 = no preview, download instead. */
export async function fetchLink(linkUrl: string, mode: LinkMode): Promise<LinkOutcome> {
  let response: Response;
  try {
    response = await fetch(`${linkUrl}?mode=${mode}`, { cache: "no-store" });
  } catch {
    return { ok: false, status: 0, message: NOT_COMPLETED };
  }
  const data = await response.json().catch(() => null);
  if (!response.ok || typeof data?.url !== "string") return { ok: false, status: response.status, message: detailMessage(data?.detail, NOT_COMPLETED) };
  return { ok: true, url: data.url };
}

export const isImage = (contentType: string) => contentType === "image/png" || contentType === "image/jpeg";
