import { CandidateDetailPage } from "@/components/RecruiterCandidatePages";

// rec-009: one candidate -- profile, edit, archive and resumes.
// hrc-014: `?merged=CAN-…` after a merge shows the success notice.
export default async function RecruiterCandidatePage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<{ merged?: string | string[] }> }) {
  const merged = (await searchParams).merged;
  return <CandidateDetailPage id={(await params).id} merged={typeof merged === "string" ? merged.slice(0, 20) : undefined} />;
}
