import { CandidateImportPage } from "@/components/RecruiterCandidatePages";

// hrc-013 (DEC-SCOPE-391): candidate bulk import (`candidates.import`: recruiters and placement managers by default). pob-014
// (DEC-SCOPE-425): `?college=&permission=` imports an institution's student list under that data permission.
export default async function RecruiterCandidateImportPage({ searchParams }: { searchParams: Promise<{ college?: string; permission?: string }> }) {
  const { college, permission } = await searchParams;
  return <CandidateImportPage institution={college && permission ? { college, permission } : null} />;
}
