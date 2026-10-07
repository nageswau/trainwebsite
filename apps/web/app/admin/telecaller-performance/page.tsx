import TelecallerPerformancePage from "@/components/TelecallerPerformancePage";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";

// tel-023 (PF1): super_admin compares every telecaller.
export default function AdminTelecallerPerformancePage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  return <TelecallerPerformancePage roles={["super_admin"]} nav={SUPER_ADMIN_NAV} roleLabel="Super Administrator" loginHref="/admin/login"
    base="/admin/telecaller-performance" searchParams={searchParams} adminNav />;
}
