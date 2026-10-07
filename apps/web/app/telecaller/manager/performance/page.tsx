import TelecallerPerformancePage from "@/components/TelecallerPerformancePage";
import { TELECALLER_MANAGER_NAV } from "@/lib/navigation";

// tel-023 (§16): a manager compares their direct reports; super_admin every telecaller.
export default function TelecallerManagerPerformancePage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  return <TelecallerPerformancePage roles={["telecaller_manager", "super_admin"]} nav={TELECALLER_MANAGER_NAV} roleLabel="Telecaller Manager"
    loginHref="/admin/login" base="/telecaller/manager/performance" searchParams={searchParams} />;
}
