import { serverApi } from "@/lib/api";
import type { InternshipValues } from "@/lib/internship";

// ENH-012 -- Digital Portfolio: server-side loader + shared types, kept OUT of PortfolioPanel.tsx.
// PortfolioPanel.tsx is a "use client" file (see its own header comment for why); serverApi imports
// next/headers, and a "use client" module that reaches next/headers breaks the production build --
// the exact class of bug tests/lib/clientBoundary.test.ts guards against (first hit in ENH-005,
// see that test's own comment). PortfolioPanel.tsx imports only the *types* below (type-only imports
// are erased at compile time, so they carry no runtime import and stay clear of the boundary); the
// pages built in Task 10 import loadPortfolio from here directly.
// ENH-021: the internship runtime helpers therefore live in lib/internship.ts, never here.

// ENH-024: the API always sends the four Skill India fields (null on every other entry); optional here so older-shaped values stay valid.
export type CertificationFields = { certification_type?: string | null; certification_status?: string | null; certificate_number?: string | null; issued_on?: string | null };
// ENH-021 (DEC-SCOPE-032): internship tracking fields, present (possibly null) on every entry, filled only for section="internship".
export type PortfolioEntry = { id: string; section: string; title: string; description: string | null; organization: string | null; date_from: string | null; date_to: string | null; created_at: string; updated_at: string }
  & InternshipValues & { has_certificate?: boolean; certificate_content_type?: string | null } & CertificationFields;
export type PortfolioData = {
  student: { id: string; full_name: string };
  completion_percentage: number;
  can_edit: boolean;
  // ENH-021 QA-08: false when this writer's school lacks Platinum `internships`; absent on an older API (treated as available).
  can_track_internships?: boolean;
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
