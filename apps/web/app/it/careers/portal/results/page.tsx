import CandidatePortalSection from "@/components/CandidatePortalSection";
import MyResultsCard from "@/components/MyResultsCard";

// hrc-031 (DEC-SCOPE-412): released results only (hrc-030 R9).
export default function CandidateResultsPage() {
  return <CandidatePortalSection header={{ title: "My Results", subtitle: "Your interview results, once the company has published them." }} lead={<MyResultsCard />} />;
}
