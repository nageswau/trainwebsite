import ReportLibraryPage from "@/components/ReportLibraryPage";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";

// nehn-009 (DEC-SCOPE-303): the Super Admin's report library (every report, every row).
export default function SuperAdminReportLibraryPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  return (
    <ReportLibraryPage roles={["super_admin"]} nav={SUPER_ADMIN_NAV} roleLabel="Super Administrator" loginHref="/admin/login"
      basePath="/admin/report-library" searchParams={searchParams} />
  );
}
