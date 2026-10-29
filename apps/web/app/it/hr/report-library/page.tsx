import ReportLibraryPage from "@/components/ReportLibraryPage";
import { PORTAL_NAV } from "@/lib/navigation";

// nehn-017 (DEC-SCOPE-310): HR's report library -- the hr-* reports, every row in the HR population (the API decides).
export default function HrReportLibraryPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  return (
    <ReportLibraryPage roles={["hr_team"]} nav={PORTAL_NAV["it/hr"]} roleLabel="HR Team" loginHref="/it/login"
      basePath="/it/hr/report-library" searchParams={searchParams} />
  );
}
