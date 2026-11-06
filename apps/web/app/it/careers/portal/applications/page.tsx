import CandidatePortalSection from "@/components/CandidatePortalSection";
import StudentOffersCard from "@/components/StudentOffersCard";
import { CANDIDATE_API } from "@/lib/candidatePortal";

// hrc-031 (DEC-SCOPE-412 P1/P6): the candidate's applications -- stage, date, next action -- and their offers.
export default function CandidateApplicationsPage() {
  return <CandidatePortalSection url={`${CANDIDATE_API}/applications`} lead={<StudentOffersCard />} emptyText="You haven't applied to any jobs yet." />;
}
