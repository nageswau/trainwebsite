import TelecallerPerformancePage from "@/components/TelecallerPerformancePage";
import { PORTAL_NAV } from "@/lib/navigation";

// tel-023 (PF1): IT admins compare IT telecallers.
export default function ItAdminTelecallerPerformancePage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  return <TelecallerPerformancePage roles={["it_admin", "super_admin"]} nav={PORTAL_NAV["it/admin"]} roleLabel="IT Administrator" loginHref="/it/login"
    base="/it/admin/telecaller-performance" searchParams={searchParams} adminNav />;
}
