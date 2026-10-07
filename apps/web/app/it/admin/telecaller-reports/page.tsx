import TelecallerReportsPage from "@/components/TelecallerReportsPage";
import { PORTAL_NAV } from "@/lib/navigation";

// tel-024 (T24): a division admin's telecaller reports cover their own division.
export default function ItAdminTelecallerReportsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  return (
    <TelecallerReportsPage roles={["it_admin", "super_admin"]} nav={PORTAL_NAV["it/admin"]} roleLabel="IT Administrator" loginHref="/it/login"
      basePath="/it/admin/telecaller-reports" searchParams={searchParams} />
  );
}
