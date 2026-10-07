import PortalLoading from "@/components/PortalLoading";
import { BDM_MANAGER_NAV } from "@/lib/navigation";

export default function Loading() {
  return <PortalLoading nav={BDM_MANAGER_NAV} label="master view" />;
}
