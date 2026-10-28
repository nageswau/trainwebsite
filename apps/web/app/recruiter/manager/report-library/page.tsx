import ReportLibraryPage from "@/components/ReportLibraryPage";
import { RECRUITER_MANAGER_NAV } from "@/lib/navigation";
import { PLACEMENT_MANAGER_LABEL } from "@/lib/recruiter";

// nehn-016 (DEC-SCOPE-312): a placement manager's report library -- the same placement reports as their recruiters (opted-in students).
export default function PlacementManagerReportLibraryPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  return (
    <ReportLibraryPage roles={["placement_manager"]} nav={RECRUITER_MANAGER_NAV} roleLabel={PLACEMENT_MANAGER_LABEL} loginHref="/admin/login"
      basePath="/recruiter/manager/report-library" searchParams={searchParams} />
  );
}
