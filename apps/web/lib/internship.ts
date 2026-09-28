// ENH-021 (DEC-SCOPE-032): internship tracking fields and their client-side helpers. Deliberately NOT in lib/portfolio.ts: that
// module also holds the server loader (loadPortfolio -> serverApi -> next/headers), so a runtime import of it from a "use client"
// component breaks `next build` (guarded by tests/lib/clientBoundary.test.ts). This file has no server imports.
export type InternshipValues = {
  mentor_name?: string | null; mentor_designation?: string | null; attendance_percent?: number | null;
  completion_status?: string | null; feedback?: string | null; skills_acquired?: string[] | null;
};

export const COMPLETION_LABEL: Record<string, string> = { not_started: "Not started", in_progress: "In progress", completed: "Completed", discontinued: "Discontinued" };
export const INTERNSHIP_KEYS = ["mentor_name", "mentor_designation", "attendance_percent", "completion_status", "feedback", "skills_acquired"] as const;

export function pickInternship(values: InternshipValues | undefined): InternshipValues {
  const out: InternshipValues = {};
  for (const key of INTERNSHIP_KEYS) (out as Record<string, unknown>)[key] = values?.[key] ?? null;
  return out;
}

/** Only the tracking fields that changed, so editing title/dates never trips the Platinum-only gate (spec I6). */
export function internshipChanges(initial: InternshipValues, current: InternshipValues): InternshipValues {
  const out: InternshipValues = {};
  for (const key of INTERNSHIP_KEYS) {
    if (JSON.stringify(initial[key] ?? null) !== JSON.stringify(current[key] ?? null)) (out as Record<string, unknown>)[key] = current[key] ?? null;
  }
  return out;
}

/** The tracking fields a new entry actually has (empty ones omitted). */
export function filledInternship(values: InternshipValues): InternshipValues {
  const out: InternshipValues = {};
  for (const key of INTERNSHIP_KEYS) {
    const value = values[key];
    if (value !== null && value !== undefined && value !== "" && !(Array.isArray(value) && value.length === 0)) (out as Record<string, unknown>)[key] = value;
  }
  return out;
}
