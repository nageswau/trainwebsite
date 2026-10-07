import TelecallerReportsPage from "@/components/TelecallerReportsPage";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";

// tel-024 (T24): the Super Admin's telecaller reports (both teams).
export default function SuperAdminTelecallerReportsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  return (
    <TelecallerReportsPage roles={["super_admin"]} nav={SUPER_ADMIN_NAV} roleLabel="Super Administrator" loginHref="/admin/login"
      basePath="/admin/telecaller-reports" searchParams={searchParams} />
  );
}
