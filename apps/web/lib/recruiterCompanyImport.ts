// pob-006 (DEC-SCOPE-418): the company and contact import and the two merges -- endpoints, the template's column reference and the types.
// The server is the authority on every rule; the column descriptions only document the template for the person filling it in.
import type { BulkColumn } from "@/lib/bulkEntry";
import { COMPANIES_PATH, COMPANIES_URL } from "@/lib/recruiterCompanies";
import { CONTACTS_URL } from "@/lib/recruiterContacts";

export const IMPORTS_URL = "/api/v1/recruiter/company-imports";
export const PREVIEW_URL = `${IMPORTS_URL}/preview`;
export const TEMPLATE_URL = `${IMPORTS_URL}/template`;
export const IMPORT_PATH = `${COMPANIES_PATH}/import`;
export const IMPORT_MAX_BYTES = 1024 * 1024;
export const IMPORT_MAX_ROWS = 1000;
export const reportCsvUrl = (id: string) => `${IMPORTS_URL}/${encodeURIComponent(id)}/report.csv`;

const LIST = "A value from your managed list";
export const IMPORT_COLUMNS: BulkColumn[] = [
  { name: "company_name", required: true, format: "Text, up to 180 characters. Several rows may name one company", example: "Acme Technologies" },
  { name: "website", required: false, format: "A web address", example: "https://acme.example.com" },
  { name: "linkedin_url", required: false, format: "A web address", example: "https://linkedin.com/company/acme" },
  { name: "industry", required: false, format: LIST, example: "Information Technology" },
  { name: "company_size", required: false, format: LIST, example: "51-200" },
  { name: "employee_count", required: false, format: "A whole number", example: "120" },
  { name: "city", required: false, format: "Text", example: "Pune" },
  { name: "state", required: false, format: "Text", example: "Maharashtra" },
  { name: "country", required: false, format: "Text", example: "India" },
  { name: "head_office", required: false, format: "Text", example: "Baner, Pune" },
  { name: "description", required: false, format: "Text", example: "Product engineering" },
  { name: "lead_source", required: false, format: LIST, example: "Referral" },
  { name: "priority", required: false, format: "hot, warm or cold", example: "warm" },
  { name: "contact_name", required: false, format: "Needed when the row gives a contact's details", example: "Asha Verma" },
  { name: "contact_designation", required: false, format: "Text, up to 120 characters", example: "HR Manager" },
  { name: "contact_department", required: false, format: "Text, up to 120 characters", example: "Talent Acquisition" },
  { name: "contact_role", required: false, format: LIST, example: "HR" },
  { name: "contact_mobile", required: false, format: "10 digits, or + and the country code", example: "9876543210" },
  { name: "contact_email", required: false, format: "An email address", example: "asha@acme.example.com" },
  { name: "contact_linkedin", required: false, format: "A web address", example: "https://linkedin.com/in/asha" },
  { name: "contact_channel", required: false, format: "call, whatsapp, email or linkedin", example: "email" },
  { name: "contact_source", required: false, format: "LinkedIn, company website, referral, job portal, event, inbound or other", example: "LinkedIn" },
  { name: "contact_verified_on", required: false, format: "A date, YYYY-MM-DD", example: "2026-11-01" },
  { name: "contact_decision_maker", required: false, format: "Yes or No", example: "Yes" },
  { name: "contact_notes", required: false, format: "Text, up to 2000 characters", example: "Met at the job fair" },
];

export type CompanyRef = { id: string; code: string | null; name: string; in_scope: boolean };
export type ContactRef = { id: string; name: string };
type Outcome = "new" | "created" | "matched" | null;
type Counts = { total_rows: number; matched_count: number; error_count: number };

export type PreviewRow = {
  row_number: number; status: "new" | "matched" | "error"; company_name: string; contact_name: string; company: CompanyRef | null; contact: ContactRef | null;
  company_outcome: Outcome; contact_outcome: Outcome; same_as_row: number | null; reason: string | null;
};
export type Preview = Counts & { new_count: number; rows: PreviewRow[] };

export type ReportRow = { row_number: number; status: "created" | "matched" | "error"; company: CompanyRef | null; contact: ContactRef | null; company_outcome: Outcome; contact_outcome: Outcome; reason: string | null };
export type ImportSummary = Counts & {
  id: string; file_name: string; uploaded_by: { id: string; full_name: string }; created_count: number; companies_created: number; contacts_created: number; created_at: string;
};
export type ImportReport = ImportSummary & { replayed: boolean; rows: ReportRow[] };

const plural = (n: number, one: string, many: string) => `${n.toLocaleString("en-IN")} ${n === 1 ? one : many}`;
export const reportCounts = (r: Pick<ImportSummary, "companies_created" | "contacts_created" | "matched_count" | "error_count">) =>
  `${plural(r.companies_created, "company", "companies")} and ${plural(r.contacts_created, "contact", "contacts")} added, ${plural(r.matched_count, "row", "rows")} already here, ${plural(r.error_count, "error", "errors")}`;
export const previewCounts = (p: Preview) =>
  `${plural(p.new_count, "row adds", "rows add")} something new, ${plural(p.matched_count, "row is", "rows are")} already here, ${plural(p.error_count, "row has an error", "rows have errors")}`;

// --- merges ---------------------------------------------------------------------------------------------------------------------------
export const companyMergePath = (id: string, victim?: string) => `${COMPANIES_PATH}/${encodeURIComponent(id)}/merge${victim ? `?${new URLSearchParams({ victim })}` : ""}`;
export const companyMergeUrl = (id: string, victim?: string) => `${COMPANIES_URL}/${encodeURIComponent(id)}/merge${victim ? `?${new URLSearchParams({ victim })}` : ""}`;
export const contactMergePath = (companyId: string, contactId: string) => `${COMPANIES_PATH}/${encodeURIComponent(companyId)}/contacts/${encodeURIComponent(contactId)}/merge`;
export const contactMergeUrl = (id: string, victim?: string) => `${CONTACTS_URL}/${encodeURIComponent(id)}/merge${victim ? `?${new URLSearchParams({ victim })}` : ""}`;

export type MergeValues = Record<string, string | number | null>;
export type CompanySide = { id: string; code: string; name: string; assigned_recruiter: string | null; values: MergeValues };
export type CompanyPreview = { survivor: CompanySide; victim: CompanySide; fields: string[]; moved: Record<string, number>; blocked: string[] };
export type ContactSide = { id: string; name: string; status: string; is_primary: boolean; is_decision_maker: boolean; active: boolean; values: MergeValues };
export type ContactPreview = { company: { id: string; code: string; name: string }; survivor: ContactSide; victim: ContactSide; fields: string[]; moved: Record<string, number> };

export const FIELD_LABEL: Record<string, string> = {
  website: "Website", linkedin_url: "LinkedIn", industry_id: "Industry", company_size_id: "Company size", employee_count: "Employees", city: "City", state: "State", country: "Country",
  head_office: "Head office", description: "Description", lead_source_id: "Lead source", priority: "Priority", products_services: "Products and services",
  name: "Name", designation: "Designation", department: "Department", role_id: "Role", mobile: "Mobile", email: "Email", preferred_channel: "Preferred channel", notes: "Notes", source: "Found through", verified_on: "Verified on",
};
export const MOVED_LABEL: Record<string, string> = {
  contacts: "contacts", requirements: "requirements", follow_ups: "follow-ups", calls: "calls", messages: "messages", meetings: "meetings", contracts: "contracts", documents: "documents",
  shares: "profile shares", drives: "campus drives", stage_history: "stage history rows", assignment_history: "assignment history rows", job_descriptions: "job descriptions", interviews: "interviews",
  meeting_participants: "meeting invitations",
};
export const movedText = (moved: Record<string, number>) =>
  Object.entries(moved).filter(([key, n]) => n > 0 && MOVED_LABEL[key]).map(([key, n]) => `${MOVED_LABEL[key]}: ${n}`).join(", ");
