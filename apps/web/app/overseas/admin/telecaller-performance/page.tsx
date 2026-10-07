import TelecallerPerformancePage from "@/components/TelecallerPerformancePage";
import { PORTAL_NAV } from "@/lib/navigation";

// tel-023 (PF1): Overseas admins compare Overseas telecallers.
export default function OverseasAdminTelecallerPerformancePage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  return <TelecallerPerformancePage roles={["overseas_admin", "super_admin"]} nav={PORTAL_NAV["overseas/admin"]} roleLabel="Overseas Administrator"
    loginHref="/overseas/login" base="/overseas/admin/telecaller-performance" searchParams={searchParams} adminNav />;
}
