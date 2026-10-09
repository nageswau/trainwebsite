// upc-026 (DEC-SCOPE-138): the university document centre (§28) -- kinds, types, URLs and the menu list's query helpers. The API slices
// what each reader sees (the commission agreement and internal documents never reach a counselor-facing reader); nothing here filters
// for security.
import type { ManagerRef } from "@/lib/telecaller";
import { UNIVERSITIES_URL } from "@/lib/universities";

// DC1: the 12 kinds, in source order and wording.
export const DOCUMENT_KINDS: Record<string, string> = {
  mou: "MoU", partnership_agreement: "Partnership agreement", commission_agreement: "Commission agreement", brochure: "University brochure",
  course_list: "Course list", fee_structure: "Fee structure", entry_requirements: "Entry requirements",
  scholarship_information: "Scholarship information", marketing_materials: "Marketing materials", application_guidelines: "Application guidelines",
  contact_documents: "Contact documents", training_documents: "Training documents",
};
export const COMMISSION_KIND = "commission_agreement";
// DC3: shared with counsellors unless the uploader says otherwise (the API applies the same default when `shareable` is not sent).
export const SHAREABLE_BY_DEFAULT = new Set([
  "brochure", "course_list", "fee_structure", "entry_requirements", "scholarship_information", "marketing_materials", "application_guidelines",
  "training_documents",
]);

export type DocumentVersion = { version: number; file_name: string | null; content_type: string; size_bytes: number; uploaded_by: ManagerRef; uploaded_at: string };
export type UniversityDocument = {
  id: string; university: { id: string; name: string; university_code: string }; kind: string; title: string; shareable: boolean;
  current_version: number; versions: DocumentVersion[]; created_at: string; updated_at: string;
};

export const DOCUMENTS_URL = "/api/v1/partnership/documents";
export const DOCUMENTS_PATH = "/partnership/documents";
export const documentsUrl = (universityId: string) => `${UNIVERSITIES_URL}/${universityId}/documents`;
export const documentUrl = (universityId: string, documentId: string, tail = "") => `${documentsUrl(universityId)}/${documentId}${tail}`;
export const documentFileUrl = (d: Pick<UniversityDocument, "id" | "university">, version?: number) =>
  documentUrl(d.university.id, d.id, `/file${version ? `?version=${version}` : ""}`);

// DC4/DC5: what the API accepts (it decides by the bytes; `accept` only narrows the picker) and its size cap.
export const DOCUMENT_ACCEPT = [
  ".pdf", ".docx", ".xlsx", ".pptx", ".jpg", ".jpeg", ".png", "application/pdf", "image/jpeg", "image/png",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation",
].join(",");
export const DOCUMENT_MAX_BYTES = 20 * 1024 * 1024;
export const DOCUMENT_TYPES_TEXT = "PDF, Word, Excel, PowerPoint, JPEG or PNG, up to 20 MB";

export const kindLabel = (kind: string) => DOCUMENT_KINDS[kind] ?? kind;

// The menu page's filters travel in the URL; only these keys are passed on to the API.
export const DOCUMENT_FILTER_KEYS = ["kind", "q"] as const;
export type DocumentFilters = Partial<Record<(typeof DOCUMENT_FILTER_KEYS)[number] | "offset", string>>;

function filterParams(filters: DocumentFilters): URLSearchParams {
  const query = new URLSearchParams();
  for (const key of DOCUMENT_FILTER_KEYS) {
    const value = filters[key]?.trim();
    if (value) query.set(key, value);
  }
  return query;
}

export function documentListQuery(filters: DocumentFilters, limit: number, offset: number): string {
  const query = filterParams(filters);
  query.set("limit", String(limit));
  query.set("offset", String(offset));
  return query.toString();
}

export function documentPageHref(filters: DocumentFilters, offset: number): string {
  const query = filterParams(filters);
  if (offset > 0) query.set("offset", String(offset));
  const text = query.toString();
  return text ? `${DOCUMENTS_PATH}?${text}` : DOCUMENTS_PATH;
}
