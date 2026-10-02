import AdminBdmPage from "@/components/AdminBdmPage";
import { PORTAL_NAV } from "@/lib/navigation";

// bdm-001: Overseas admins manage Agent and School BDMs (D10).
export default function OverseasAdminBdmsPage() {
  return <AdminBdmPage roles={["overseas_admin", "super_admin"]} nav={PORTAL_NAV["overseas/admin"]} roleLabel="Overseas Administrator" loginHref="/overseas/login" />;
}
