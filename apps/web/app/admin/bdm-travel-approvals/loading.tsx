import PortalLoading from "@/components/PortalLoading";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";

export default function Loading() {
  return <PortalLoading nav={SUPER_ADMIN_NAV} label="trips waiting on an inactive manager" />;
}
