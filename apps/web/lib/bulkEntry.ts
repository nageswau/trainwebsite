// ENH-028 -- what each bulk-entry module uploads (docs/superpowers/specs/2026-10-01-enh-028-bulk-data-entry-design.md §6).
// The server is the authority on every rule; these descriptions only document the template for the person filling it in.

export type BulkColumn = { name: string; required: boolean; format: string; example: string };
export type BulkTarget = { id: string; title: string; noun: string; templateUrl: string; uploadUrl: string; columns: BulkColumn[] };

const BASE = "/api/v1/school";
const STUDENT_COLUMNS: BulkColumn[] = [
  { name: "student_code", required: true, format: "The 8-character Student ID — already filled in", example: "A1B2C3D4" },
  { name: "student_name", required: false, format: "For reference only — not read back", example: "Asha Rao" },
  { name: "school_name", required: false, format: "For reference only — not read back", example: "Sunrise Public School" },
];
const LIST = "Items separated by ; (up to 20)";
const DATE = "YYYY-MM-DD";

export const BULK_RESULTS: BulkTarget = {
  id: "bulk-results",
  title: "Bulk entry — results (CSV)",
  noun: "results",
  templateUrl: `${BASE}/academic-team/results/bulk-template`,
  uploadUrl: `${BASE}/academic-team/results/bulk-upload`,
  columns: [
    ...STUDENT_COLUMNS,
    { name: "academic_year", required: true, format: "Text, up to 20 characters", example: "2026-27" },
    { name: "term", required: true, format: "Text, up to 40 characters", example: "Term 1" },
    { name: "subject", required: true, format: "Text, up to 80 characters", example: "Mathematics" },
    { name: "max_marks", required: true, format: "Number above 0, at most 9999.99", example: "100" },
    { name: "marks_obtained", required: true, format: "Number from 0 up to max_marks", example: "88" },
    { name: "grade", required: false, format: "Up to 10 characters", example: "A" },
    { name: "teacher_remarks", required: false, format: "Up to 2000 characters", example: "Steady improvement" },
  ],
};

export const BULK_PSYCHOMETRIC: BulkTarget = {
  id: "bulk-psychometric",
  title: "Bulk entry — assessments (CSV)",
  noun: "assessments",
  templateUrl: `${BASE}/psychometric-team/records/bulk-template`,
  uploadUrl: `${BASE}/psychometric-team/records/bulk-upload`,
  columns: [
    ...STUDENT_COLUMNS,
    { name: "assessment_type", required: true, format: "Text, up to 120 characters", example: "Aptitude Test" },
    { name: "report_url", required: false, format: "http:// or https:// link; marks the assessment completed", example: "https://reports.example/asha.pdf" },
    { name: "test_date", required: false, format: DATE, example: "2026-09-01" },
    { name: "strengths", required: false, format: LIST, example: "Logic; Mathematics" },
    { name: "interest_areas", required: false, format: LIST, example: "Engineering; Design" },
    { name: "personality_indicators", required: false, format: LIST, example: "Analytical" },
    { name: "recommended_careers", required: false, format: LIST, example: "Civil Engineer" },
    { name: "recommended_stream", required: false, format: LIST, example: "Science" },
    { name: "counsellor_remarks", required: false, format: "Up to 4000 characters", example: "Strong foundation" },
    { name: "parent_discussion_on", required: false, format: DATE, example: "2026-09-10" },
    { name: "parent_discussion_notes", required: false, format: "Up to 2000 characters", example: "Discussed options" },
    { name: "follow_up_on", required: false, format: DATE, example: "2026-12-01" },
  ],
};

export const BULK_TEST_PREP: BulkTarget = {
  id: "bulk-test-prep",
  title: "Bulk entry — test preparation (CSV)",
  noun: "test preparation",
  templateUrl: `${BASE}/academic-team/test-prep-records/bulk-template`,
  uploadUrl: `${BASE}/academic-team/test-prep-records/bulk-upload`,
  columns: [
    ...STUDENT_COLUMNS,
    { name: "test_type", required: true, format: "ielts or sat", example: "ielts" },
    { name: "target_score", required: false, format: "Up to 20 characters", example: "7.5" },
  ],
};

export const BULK_LANGUAGE: BulkTarget = {
  id: "bulk-language",
  title: "Bulk entry — language classes (CSV)",
  noun: "language classes",
  templateUrl: `${BASE}/academic-team/language-records/bulk-template`,
  uploadUrl: `${BASE}/academic-team/language-records/bulk-upload`,
  columns: [
    ...STUDENT_COLUMNS,
    { name: "language", required: true, format: "Text, up to 60 characters", example: "French" },
    { name: "level", required: false, format: "Up to 30 characters", example: "A1" },
  ],
};
