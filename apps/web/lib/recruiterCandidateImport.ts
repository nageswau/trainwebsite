// hrc-013 (DEC-SCOPE-391): candidate bulk import -- endpoints, the template's column reference and the preview / report types.
// The server is the authority on every rule; the column descriptions only document the template for the person filling it in.
import type { BulkColumn } from "@/lib/bulkEntry";
import { CANDIDATES_PATH } from "@/lib/recruiterCandidates";

export const IMPORTS_URL = "/api/v1/recruiter/candidate-imports";
export const PREVIEW_URL = `${IMPORTS_URL}/preview`;
export const TEMPLATE_URL = `${IMPORTS_URL}/template`;
export const IMPORT_PATH = `${CANDIDATES_PATH}/import`;
export const IMPORT_MAX_BYTES = 1024 * 1024;
export const IMPORT_MAX_ROWS = 1000;
export const reportCsvUrl = (id: string) => `${IMPORTS_URL}/${encodeURIComponent(id)}/report.csv`;

const LIST = "Items separated by ;";
export const IMPORT_COLUMNS: BulkColumn[] = [
  { name: "name", required: true, format: "Text, up to 160 characters", example: "Asha Verma" },
  { name: "mobile", required: false, format: "10 digits, or + and the country code. A mobile or an email is required", example: "9876543210" },
  { name: "email", required: false, format: "An email address. A mobile or an email is required", example: "asha@example.com" },
  { name: "source_detail", required: false, format: "Text, up to 200 characters", example: "Campus fair, Nov 2026" },
  { name: "location", required: false, format: "Text, up to 120 characters (filled from city, state, country when given)", example: "Pune" },
  { name: "country", required: false, format: "Text, up to 80 characters", example: "India" },
  { name: "state", required: false, format: "Text, up to 80 characters", example: "Maharashtra" },
  { name: "city", required: false, format: "Text, up to 80 characters", example: "Pune" },
  { name: "qualification", required: false, format: "Text, up to 120 characters", example: "B.Tech" },
  { name: "college", required: false, format: "Text, up to 200 characters", example: "ABC College" },
  { name: "passing_year", required: false, format: "A year, 1950-2100", example: "2025" },
  { name: "experience_months", required: false, format: "Whole months, 0-600", example: "18" },
  { name: "relevant_experience_months", required: false, format: "Whole months, 0-600", example: "12" },
  { name: "current_company", required: false, format: "Text, up to 200 characters", example: "Infosys" },
  { name: "notice_days", required: false, format: "Whole days, 0-365", example: "30" },
  { name: "preferred_role", required: false, format: "Text, up to 120 characters", example: "Java Developer" },
  { name: "preferred_locations", required: false, format: LIST, example: "Pune; Bengaluru" },
  { name: "tools", required: false, format: `Up to 20. ${LIST}`, example: "Git; Jira" },
  { name: "languages", required: false, format: `Up to 20. ${LIST}`, example: "English; Hindi" },
  { name: "linkedin", required: false, format: "A web address", example: "https://linkedin.com/in/asha" },
  { name: "available_from", required: false, format: "A date, YYYY-MM-DD", example: "2026-12-01" },
  { name: "willing_to_relocate", required: false, format: "Yes or No", example: "Yes" },
];

export type CandidateRef = { id: string; candidate_code: string; name: string };
type Counts = { total_rows: number; matched_count: number; error_count: number };

export type PreviewRow = {
  row_number: number; status: "new" | "matched" | "error"; name: string; candidate: CandidateRef | null; same_as_row: number | null; reason: string | null;
};
export type Preview = Counts & { new_count: number; rows: PreviewRow[] };

export type ReportRow = { row_number: number; status: "created" | "matched" | "error"; candidate: CandidateRef | null; reason: string | null };
export type ImportSummary = Counts & {
  id: string; file_name: string; source: { id: string; name: string }; uploaded_by: { id: string; full_name: string }; created_count: number; created_at: string;
};
export type ImportReport = ImportSummary & { replayed: boolean; rows: ReportRow[] };

const plural = (n: number, one: string, many: string) => `${n.toLocaleString("en-IN")} ${n === 1 ? one : many}`;
export const reportCounts = (r: Pick<ImportSummary, "created_count" | "matched_count" | "error_count">) =>
  `${plural(r.created_count, "added", "added")}, ${plural(r.matched_count, "already a candidate", "already candidates")}, ${plural(r.error_count, "error", "errors")}`;
export const previewCounts = (p: Preview) =>
  `${plural(p.new_count, "new candidate", "new candidates")}, ${plural(p.matched_count, "already a candidate", "already candidates")}, ${plural(p.error_count, "row with an error", "rows with errors")}`;
