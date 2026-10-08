import { CandidateDetailPage } from "@/components/RecruiterCandidatePages";

// rec-009: one candidate -- profile, edit, archive and resumes.
export default async function RecruiterCandidatePage({ params }: { params: Promise<{ id: string }> }) {
  return <CandidateDetailPage id={(await params).id} />;
}
