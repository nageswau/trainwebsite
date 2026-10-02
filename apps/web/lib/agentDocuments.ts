// AGN-009 (DEC-SCOPE-052): an agency's documents and document requests -- the shapes, labels and §6 review rules the Documents
// page shares. The server is the authority (scope, matrix, reasons, states); these only keep the screens from offering a refused action.
import { detailMessage } from "@/lib/apiErrors";
import type { User } from "@/lib/types";

export const DOCUMENTS_URL = "/api/v1/workflows/overseas/agent/crm/documents";
export const REQUESTS_URL = "/api/v1/workflows/overseas/agent/crm/document-requests";
export const downloadUrl = (id: string) => `/api/v1/workflows/overseas/documents/${id}/download`;
export const reviewUrl = (id: string) => `/api/v1/workflows/overseas/documents/${id}/verify`;

// EVID-015 §5 Step 4 (G3); "Other" needs a description. Mirrors the API's AgentDocumentType.
export const DOCUMENT_TYPES = ["Passport", "Academic certificates", "Transcripts", "English test", "CV", "SOP", "LOR", "Financial documents", "Other"] as const;
export const OTHER = "Other";
// AGN-010 (DEC-SCOPE-056 O3): uploads also take an offer letter, which must name its application; requests keep DOCUMENT_TYPES.
export const OFFER_LETTER = "Offer letter";
export const UPLOAD_DOCUMENT_TYPES = [...DOCUMENT_TYPES, OFFER_LETTER] as const;

// Download uses the scoped OVS-005 route: the presigned link is fetched on demand and never stored. Returns an error message, or null
// once the file has been opened in a new tab.
export async function openDocument(id: string): Promise<string | null> {
  try {
    const response = await fetch(downloadUrl(id));
    const data = await response.json().catch(() => ({}));
    if (!response.ok || typeof data.url !== "string") return detailMessage(data.detail, "The document could not be opened.");
    window.open(data.url, "_blank", "noreferrer");
    return null;
  } catch {
    return "Couldn't reach the server. Check your connection and try again.";
  }
}
export const FILE_ACCEPT = "application/pdf,image/jpeg,image/png,.pdf,.jpg,.jpeg,.png";

export const VIEWS = ["pending", "uploaded", "additional"] as const;
export type View = (typeof VIEWS)[number];
export const VIEW_LABELS: Record<View, string> = { pending: "Pending review", uploaded: "Uploaded documents", additional: "Additional documents" };
export const VIEW_NAV_LABELS: Record<View, string> = { pending: "Pending", uploaded: "Uploaded", additional: "Additional" };

export function parseView(value: string | null | undefined): View {
  return (VIEWS as readonly string[]).includes(value ?? "") ? (value as View) : "pending";
}

export type ReviewDecision = "verified" | "rejected" | "changes_required";
const STATUS_LABELS: Record<string, string> = { pending: "Pending review", verified: "Verified", rejected: "Rejected", changes_required: "Changes required" };

export function statusLabel(status: string): string {
  const label = STATUS_LABELS[status] ?? status.replaceAll("_", " ");
  return label.charAt(0).toUpperCase() + label.slice(1);
}

export function documentName(doc: { document_type: string; document_label: string | null }): string {
  return doc.document_type === OTHER && doc.document_label ? doc.document_label : doc.document_type;
}

// §6 (DEC-SCOPE-044 P1/P6): a Master decides all three; staff with Verify only verify; staff without it review nothing.
export function reviewDecisions(user: User): ReviewDecision[] {
  if (user.agent_member_role !== "staff") return ["verified", "rejected", "changes_required"];
  return user.agent_permissions?.can_verify_documents ? ["verified"] : [];
}

export type AgentDocumentItem = {
  id: string;
  agent_student_id: string | null;
  student: string;
  has_login: boolean;
  document_type: string;
  document_label: string | null;
  verification_status: string;
  reviewer_notes: string | null;
  application_id: string | null;
  university: string | null;
  original_filename: string | null;
  content_type: string | null;
  file_size: number | null;
  uploaded_by: string | null;
  fulfils_request_id: string | null;
  created_at: string;
  updated_at: string;
  replaceable: boolean;
};

export type DocumentRequestItem = {
  id: string;
  agent_student_id: string;
  student: string;
  document_type: string;
  document_label: string | null;
  note: string | null;
  status: "open" | "fulfilled" | "cancelled";
  requested_by: string | null;
  fulfilled_by_document_id: string | null;
  created_at: string;
  closed_at: string | null;
};

export type HistoryEvent = { id: string; event: string; actor: string | null; from_status: string | null; to_status: string | null; notes: string | null; created_at: string };

const EVENT_LABELS: Record<string, string> = {
  uploaded: "Uploaded",
  replaced: "File replaced",
  verified: "Verified",
  rejected: "Rejected",
  changes_required: "Changes requested",
  requested: "Requested",
  fulfilled: "Request fulfilled",
  cancelled: "Request cancelled",
  downloaded: "Downloaded",
};

export function eventLabel(event: string): string {
  return EVENT_LABELS[event] ?? statusLabel(event);
}

export function formatSize(bytes: number | null): string | null {
  if (bytes == null) return null;
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
