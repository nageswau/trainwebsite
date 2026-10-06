// tel-006 (DEC-SCOPE-091, IM1): CSV lead import per campaign -- endpoints, the template's column reference and the report types.
// The server is the authority on every rule; the column descriptions only document the template for the person filling it in.
import type { BulkColumn } from "@/lib/bulkEntry";
import type { TelecallerTeam } from "@/lib/telecaller";

export const IMPORTS_URL = "/api/v1/telecaller/imports";
export const IMPORT_TEMPLATE_URL = `${IMPORTS_URL}/template`;
export const IMPORT_MAX_BYTES = 1024 * 1024;
export const IMPORT_MAX_ROWS = 500;

const TEXT = "Text, up to 120 characters";
export const IMPORT_COLUMNS: BulkColumn[] = [
  { name: "name", required: true, format: "Text, up to 160 characters", example: "Rahul Kumar" },
  { name: "phone", required: true, format: "A valid mobile; 10 digits get +91", example: "98765 43210" },
  { name: "email", required: false, format: "An email address", example: "rahul@example.com" },
  { name: "whatsapp_number", required: false, format: "Up to 40 characters", example: "+91 98765 43210" },
  { name: "city", required: false, format: TEXT, example: "Pune" },
  { name: "state", required: false, format: TEXT, example: "Maharashtra" },
  { name: "qualification", required: false, format: TEXT, example: "B.Tech" },
  { name: "passing_year", required: false, format: "Year from 1950 to 2100", example: "2025" },
  { name: "institution", required: false, format: "Text, up to 200 characters", example: "COEP" },
  { name: "priority", required: false, format: "hot, warm or cold (default warm)", example: "warm" },
  { name: "subject", required: false, format: "Up to 180 characters (default: the campaign's product)", example: "Weekend batch" },
  { name: "message", required: false, format: "Notes, up to 5000 characters", example: "Call after 6 pm" },
];

export type ImportRowStatus = "created" | "attached" | "rejected";
export type ImportRow = { row_number: number; status: ImportRowStatus; lead_id: string | null; lead_code: string | null; error: string | null };
type ImportCounts = { total_rows: number; created_count: number; attached_count: number; rejected_count: number };
type ImportBatch = ImportCounts & { id: string; campaign: { id: string; name: string }; division: TelecallerTeam; created_at: string };
export type ImportReport = ImportBatch & { rows: ImportRow[] };
export type ImportSummary = ImportBatch & { uploaded_by: { id: string; full_name: string } };

export const RESULT_LABEL: Record<ImportRowStatus, string> = { created: "Created", attached: "Added to existing lead", rejected: "Rejected" };

/** "3 created, 1 added to existing leads, 2 rejected" -- the counts every import shows, in the report and the history. */
export function importCounts(r: ImportCounts): string {
  return `${r.created_count} created, ${r.attached_count} added to existing leads, ${r.rejected_count} rejected`;
}
