import { TalentPoolPage } from "@/components/RecruiterCandidatePages";

// rec-015: one talent pool -- its rule and its members, computed on read.
export default async function RecruiterTalentPoolPage({ params }: { params: Promise<{ id: string }> }) {
  return <TalentPoolPage id={(await params).id} />;
}
