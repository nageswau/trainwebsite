// upc-005 (DEC-SCOPE-127): University CSV import -- endpoints, the template's column reference and the report types.
// The server is the authority on every rule; the column descriptions only document the template for the person filling it in.
import type { BulkColumn } from "@/lib/bulkEntry";
import { UNIVERSITIES_PATH, UNIVERSITIES_URL } from "@/lib/universities";

export const IMPORT_URL = `${UNIVERSITIES_URL}/import`;
export const IMPORTS_URL = `${UNIVERSITIES_URL}/imports`;
export const IMPORT_TEMPLATE_URL = `${IMPORTS_URL}/template`;
export const IMPORT_PATH = `${UNIVERSITIES_PATH}/import`;
export const IMPORT_MAX_BYTES = 1024 * 1024;
export const IMPORT_MAX_ROWS = 5000;
export const reportCsvUrl = (id: string) => `${IMPORTS_URL}/${id}/report.csv`;

const LIST = "Items separated by ;";
export const IMPORT_COLUMNS: BulkColumn[] = [
  { name: "name", required: true, format: "Text, up to 200 characters", example: "ABC University" },
  { name: "country", required: true, format: "ISO code or country name", example: "GB" },
  { name: "city", required: true, format: "Text, up to 120 characters", example: "London" },
  { name: "institution_type", required: true, format: "University, College, Institute, Language School or Training Institution", example: "University" },
  { name: "ownership_type", required: false, format: "Public or Private", example: "Public" },
  { name: "state_region", required: false, format: "Text, up to 120 characters", example: "Greater London" },
  { name: "website", required: false, format: "A web address", example: "abc.ac.uk" },
  { name: "course_levels", required: false, format: `UG, PG, PhD, Diploma, Foundation. ${LIST}`, example: "UG; PG" },
  { name: "popular_programs", required: false, format: `Up to 80 characters each. ${LIST}`, example: "Business; Engineering" },
  { name: "international_office", required: false, format: "Contact text, up to 1000 characters", example: "intl@abc.ac.uk" },
  { name: "existing_relationship", required: false, format: "New or Existing", example: "New" },
  { name: "priority", required: false, format: "A, B or C", example: "A" },
  { name: "partnership_potential", required: false, format: "High, Medium or Low", example: "High" },
  { name: "overview", required: false, format: "Catalogue text, up to 5000 characters", example: "A research university in London." },
];

export type ImportRowStatus = "created" | "duplicate" | "invalid";
export type ImportRow = {
  row_number: number; status: ImportRowStatus; name: string; country: string; university_id: string | null; university_code: string | null;
  matches: string[]; reason: string | null;
};
type ImportCounts = { total_rows: number; created_count: number; duplicate_count: number; invalid_count: number };
export type ImportSummary = ImportCounts & { id: string; uploaded_by: { id: string; full_name: string }; created_at: string };
export type ImportReport = ImportSummary & { rows: ImportRow[] };

export const RESULT_LABEL: Record<ImportRowStatus, string> = { created: "Created", duplicate: "Duplicate", invalid: "Invalid" };

/** "980 created, 15 duplicates, 5 invalid" -- the counts every import shows, in the report and the history. */
export function importCounts(r: ImportCounts): string {
  return `${r.created_count} created, ${r.duplicate_count} ${r.duplicate_count === 1 ? "duplicate" : "duplicates"}, ${r.invalid_count} invalid`;
}
