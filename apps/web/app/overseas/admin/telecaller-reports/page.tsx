import TelecallerReportsPage from "@/components/TelecallerReportsPage";
import { PORTAL_NAV } from "@/lib/navigation";

// tel-024 (T24): a division admin's telecaller reports cover their own division.
export default function OverseasAdminTelecallerReportsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  return (
    <TelecallerReportsPage roles={["overseas_admin", "super_admin"]} nav={PORTAL_NAV["overseas/admin"]} roleLabel="Overseas Administrator"
      loginHref="/overseas/login" basePath="/overseas/admin/telecaller-reports" searchParams={searchParams} />
  );
}
