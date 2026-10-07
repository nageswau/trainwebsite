import TelecallerReportsPage from "@/components/TelecallerReportsPage";
import { TELECALLER_MANAGER_NAV } from "@/lib/navigation";

// tel-024 (T24): a manager's reports cover their direct reports' leads (super_admin: everyone).
export default function TelecallerManagerReportsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  return (
    <TelecallerReportsPage roles={["telecaller_manager", "super_admin"]} nav={TELECALLER_MANAGER_NAV} roleLabel="Telecaller Manager"
      loginHref="/admin/login" basePath="/telecaller/manager/reports" searchParams={searchParams} />
  );
}
