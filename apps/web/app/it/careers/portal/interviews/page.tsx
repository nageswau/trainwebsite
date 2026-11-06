import CandidatePortalSection from "@/components/CandidatePortalSection";
import { CANDIDATE_API } from "@/lib/candidatePortal";

// hrc-031 (DEC-SCOPE-412 P1): the candidate's interviews, the student portal's schedule table.
export default function CandidateInterviewsPage() {
  return <CandidatePortalSection url={`${CANDIDATE_API}/interviews`} emptyText="No interviews are scheduled yet." />;
}
