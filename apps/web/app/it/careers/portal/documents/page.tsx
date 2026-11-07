import CandidatePortalSection from "@/components/CandidatePortalSection";
import StudentCandidateDocumentsCard from "@/components/StudentCandidateDocumentsCard";

// hrc-031 (DEC-SCOPE-412 P4/P5): what the recruitment team asked for and how far along it is.
export default function CandidateDocumentsPage() {
  return <CandidatePortalSection header={{ title: "Documents", subtitle: "What the recruitment team asked you for, and the documents you shared." }} lead={<StudentCandidateDocumentsCard candidate />} />;
}
