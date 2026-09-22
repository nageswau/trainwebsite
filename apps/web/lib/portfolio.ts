import { serverApi } from "@/lib/api";

// ENH-012 -- Digital Portfolio: server-side loader + shared types, kept OUT of PortfolioPanel.tsx.
// PortfolioPanel.tsx is a "use client" file (see its own header comment for why); serverApi imports
// next/headers, and a "use client" module that reaches next/headers breaks the production build --
// the exact class of bug tests/lib/clientBoundary.test.ts guards against (first hit in ENH-005,
// see that test's own comment). PortfolioPanel.tsx imports only the *types* below (type-only imports
// are erased at compile time, so they carry no runtime import and stay clear of the boundary); the
// pages built in Task 10 import loadPortfolio from here directly.

export type PortfolioEntry = { id: string; section: string; title: string; description: string | null; organization: string | null; date_from: string | null; date_to: string | null; created_at: string; updated_at: string };
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
