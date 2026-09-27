import { serverApi } from "@/lib/api";

// ENH-012 -- Digital Portfolio: server-side loader + shared types, kept OUT of PortfolioPanel.tsx.
// PortfolioPanel.tsx is a "use client" file (see its own header comment for why); serverApi imports
// next/headers, and a "use client" module that reaches next/headers breaks the production build --
// the exact class of bug tests/lib/clientBoundary.test.ts guards against (first hit in ENH-005,
// see that test's own comment). PortfolioPanel.tsx imports only the *types* below (type-only imports
// are erased at compile time, so they carry no runtime import and stay clear of the boundary); the
// pages built in Task 10 import loadPortfolio from here directly.

// ENH-021 (DEC-SCOPE-032): internship tracking fields, present (possibly null) on every entry, filled only for section="internship".
export type InternshipValues = {
  mentor_name?: string | null; mentor_designation?: string | null; attendance_percent?: number | null;
  completion_status?: string | null; feedback?: string | null; skills_acquired?: string[] | null;
};
export type PortfolioEntry = { id: string; section: string; title: string; description: string | null; organization: string | null; date_from: string | null; date_to: string | null; created_at: string; updated_at: string }
  & InternshipValues & { has_certificate?: boolean; certificate_content_type?: string | null };

export const COMPLETION_LABEL: Record<string, string> = { not_started: "Not started", in_progress: "In progress", completed: "Completed", discontinued: "Discontinued" };
export const INTERNSHIP_KEYS = ["mentor_name", "mentor_designation", "attendance_percent", "completion_status", "feedback", "skills_acquired"] as const;

export function pickInternship(values: InternshipValues | undefined): InternshipValues {
  const out: InternshipValues = {};
  for (const key of INTERNSHIP_KEYS) (out as Record<string, unknown>)[key] = values?.[key] ?? null;
  return out;
}

/** ENH-021: only the tracking fields that changed, so editing title/dates never trips the Platinum-only gate (spec I6). */
export function internshipChanges(initial: InternshipValues, current: InternshipValues): InternshipValues {
  const out: InternshipValues = {};
  for (const key of INTERNSHIP_KEYS) {
    if (JSON.stringify(initial[key] ?? null) !== JSON.stringify(current[key] ?? null)) (out as Record<string, unknown>)[key] = current[key] ?? null;
  }
  return out;
}

/** ENH-021: the tracking fields a new entry actually has (empty ones omitted). */
export function filledInternship(values: InternshipValues): InternshipValues {
  const out: InternshipValues = {};
  for (const key of INTERNSHIP_KEYS) {
    const value = values[key];
    if (value !== null && value !== undefined && value !== "" && !(Array.isArray(value) && value.length === 0)) (out as Record<string, unknown>)[key] = value;
  }
  return out;
}
export type PortfolioData = {
  student: { id: string; full_name: string };
  completion_percentage: number;
  can_edit: boolean;
  profile_complete: boolean;
  academic_achievements: { id: string; term: string; subject: string; grade: string | null; published_at: string }[];
  psychometric_report: { id: string; assessment_type: string; report_url: string | null; created_at: string }[];
  career_guidance: { id: string; record_type: string; notes: string; created_at: string }[];
  languages: { id: string; language: string; level: string | null; certification_status: string; created_at: string }[];
  entries: Record<string, PortfolioEntry[]>;
  personal_statement: string | null;
};

export async function loadPortfolio(studentId: string): Promise<PortfolioData> {
  return serverApi<PortfolioData>(`/api/v1/school/students/${studentId}/portfolio`);
}
