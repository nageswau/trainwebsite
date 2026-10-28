import ReportLibraryPage from "@/components/ReportLibraryPage";
import { RECRUITER_NAV } from "@/lib/navigation";
import { RECRUITER_ROLE_LABEL } from "@/lib/recruiter";

// nehn-016 (DEC-SCOPE-309): a recruiter's report library -- students completing soon and the student placement report; the API keeps
// every row to the students who opted in to the placement pool.
export default function RecruiterReportLibraryPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  return (
    <ReportLibraryPage roles={["placement_team"]} nav={RECRUITER_NAV} roleLabel={RECRUITER_ROLE_LABEL} loginHref="/it/login"
      basePath="/recruiter/report-library" searchParams={searchParams} />
  );
}
