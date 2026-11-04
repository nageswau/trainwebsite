import { CandidateMergePage } from "@/components/RecruiterCandidatePages";

// hrc-014 (DEC-SCOPE-377): merge the duplicate `?victim=CAN-…` into this candidate, side by side.
export default async function RecruiterCandidateMergeRoute({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<{ victim?: string | string[] }> }) {
  const victim = (await searchParams).victim;
  return <CandidateMergePage id={(await params).id} victim={typeof victim === "string" ? victim.trim().slice(0, 20) : ""} />;
}
