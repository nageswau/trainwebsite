// ccrm-018 (DEC-SCOPE-248): document checklist templates. The server (api/document_checklists.py) is the authority on every rule; these
// mirror app/document_checklists.py and the upload type list (lib/agentDocuments.ts) for the Overseas Admin editor.
import type { LookupPage } from "@/lib/lookups";

export type ChecklistKind = "admission" | "visa";
export type GateMode = "block" | "warn";
export type CourseLevel = "UG" | "PG" | "PhD" | "Diploma" | "Foundation";

export const CHECKLISTS_URL = "/api/v1/overseas-admin/checklists";
export const KIND_LABELS: Record<ChecklistKind, string> = { admission: "Admission", visa: "Visa" };
export const GATE_LABELS: Record<GateMode, string> = { block: "Block until complete", warn: "Warn (override with a reason)" };
export const COURSE_LEVELS: CourseLevel[] = ["UG", "PG", "PhD", "Diploma", "Foundation"];
export const CHECKLIST_DOCUMENT_TYPES = ["Passport", "Academic certificates", "Transcripts", "English test", "CV", "SOP", "LOR", "Financial documents", "Offer letter", "Other"] as const;
export type ChecklistDocumentType = (typeof CHECKLIST_DOCUMENT_TYPES)[number];

export const STANDARD_STATUSES = ["pending", "requested", "uploaded", "under_review", "verified", "incomplete", "reupload_required", "expired", "not_required"] as const;
export const DRAFTING_STATUSES = ["draft", "review", "approved"] as const;
export type ItemStatus = (typeof STANDARD_STATUSES)[number] | (typeof DRAFTING_STATUSES)[number];
export const STATUS_LABELS: Record<ItemStatus, string> = {
  pending: "Pending", requested: "Requested", uploaded: "Uploaded", under_review: "Under review", verified: "Verified", incomplete: "Incomplete",
  reupload_required: "Re-upload required", expired: "Expired", not_required: "Not required", draft: "Draft", review: "Review", approved: "Approved",
};
export const MAX_ITEMS = 50;

// ccrm-021 (DEC-SCOPE-251): a stored document status as words. `pending` on a document is an upload awaiting review (S1); history rows
// written before migration 0174 still carry the old outcomes.
const LEGACY_LABELS: Record<string, string> = { rejected: "Rejected", changes_required: "Changes required" };
export function documentStatusLabel(status: string): string {
  if (status === "pending") return "Pending review";
  const label = STATUS_LABELS[status as ItemStatus] ?? LEGACY_LABELS[status] ?? status.replaceAll("_", " ");
  return label.charAt(0).toUpperCase() + label.slice(1);
}
// What a counselor / Overseas Admin may set (app/document_checklists.REVIEW_STATUSES); Draft/Review/Approved on CV / SOP only (S6).
export const REVIEW_STATUSES = ["verified", "under_review", "incomplete", "reupload_required", "not_required"] as const;
// Free-text types match by whole words, as the server does ("QA Passport", "SOP draft"; browser QA-01).
function named(documentType: string, names: string[]): boolean {
  const words = ` ${(documentType.toLowerCase().match(/[a-z]+/g) ?? []).join(" ")} `;
  return names.some((name) => words.includes(` ${name} `));
}
export function reviewStatusesFor(documentType: string): ItemStatus[] {
  return named(documentType, ["cv", "resume", "sop", "statement of purpose"]) ? [...REVIEW_STATUSES, ...DRAFTING_STATUSES] : [...REVIEW_STATUSES];
}
export const needsExpiry = (documentType: string) => named(documentType, ["passport"]);
/** A status that asks the uploader for something (shown in the error colour). */
export const NEEDS_ACTION = new Set(["incomplete", "reupload_required", "expired", "rejected", "changes_required"]);

// ccrm-022 (DEC-SCOPE-262 SD1): sensitivity classes and the words that class a type (app/document_checklists.py type_sensitivity).
export type Sensitivity = "standard" | "identity" | "financial";
export const SENSITIVITY_LABELS: Record<Sensitivity, string> = { standard: "Standard", identity: "Identity", financial: "Financial" };
const IDENTITY_TYPES = ["passport", "aadhaar", "aadhar", "national id", "identity", "id card", "birth certificate"];
const FINANCIAL_TYPES = ["financial", "finance", "bank", "sponsor", "sponsorship", "loan", "income", "salary", "tax", "itr", "affidavit"];
export function typeSensitivity(documentType: string, label?: string | null): Sensitivity {
  const words = `${documentType} ${label ?? ""}`;
  if (named(words, FINANCIAL_TYPES)) return "financial";
  return named(words, IDENTITY_TYPES) ? "identity" : "standard";
}
/** "Sensitive · Financial" for an identity/financial document or item; null for a standard one. */
export const sensitivityBadge = (sensitivity: string | null | undefined) =>
  sensitivity === "identity" || sensitivity === "financial" ? `Sensitive · ${SENSITIVITY_LABELS[sensitivity]}` : null;

export type ChecklistItem = { document_type: ChecklistDocumentType; label: string | null; required: boolean; allowed_statuses: ItemStatus[]; notes: string | null; sensitivity: Sensitivity };
type Scope = {
  name: string;
  kind: ChecklistKind;
  country_id: string;
  country_name: string | null;
  university_id: string | null;
  university_name: string | null;
  course_level: CourseLevel | null;
  intake: string | null;
  gate_mode: GateMode;
  version: number;
  active: boolean;
  updated_at: string;
};
export type ChecklistSummary = Scope & { id: string; item_count: number };
export type ChecklistTemplate = Scope & { id: string; notes: string | null; items: (ChecklistItem & { id: string; position: number })[] };

/** "United Kingdom · University X · PG · September 2027", the unset parts left out. */
export function scopeText(t: Pick<Scope, "country_name" | "university_name" | "course_level" | "intake">): string {
  return [t.country_name, t.university_name ?? "Any university", t.course_level ?? "Any level", t.intake ?? "Any intake"].filter(Boolean).join(" · ");
}

/** The universities of one country, from the university master (Overseas Admin reads it, upc-003). */
export function universitySearch(countryId: string) {
  return async (q: string, signal: AbortSignal): Promise<LookupPage> => {
    const query = new URLSearchParams({ limit: "20", country_id: countryId });
    if (q) query.set("q", q);
    const response = await fetch(`/api/v1/partnership/universities?${query}`, { signal });
    if (!response.ok) throw new Error(`University search failed (${response.status})`);
    const page = (await response.json()) as { items: { id: string; name: string; city?: string | null }[]; total: number };
    return { items: page.items.map((u) => ({ id: u.id, label: u.name, detail: u.city || null })), truncated: page.total > page.items.length };
  };
}
