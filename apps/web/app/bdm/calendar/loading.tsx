import PortalLoading from "@/components/PortalLoading";
import { BDM_NAV } from "@/lib/navigation";

export default function Loading() {
  return <PortalLoading nav={BDM_NAV} label="your calendar" />;
}
