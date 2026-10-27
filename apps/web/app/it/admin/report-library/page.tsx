import ReportLibraryPage from "@/components/ReportLibraryPage";
import { PORTAL_NAV } from "@/lib/navigation";

// nehn-009 (DEC-SCOPE-303): the IT admin's report library.
export default function ItAdminReportLibraryPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  return (
    <ReportLibraryPage roles={["it_admin", "super_admin"]} nav={PORTAL_NAV["it/admin"]} roleLabel="IT Administrator" loginHref="/it/login"
      basePath="/it/admin/report-library" searchParams={searchParams} />
  );
}
