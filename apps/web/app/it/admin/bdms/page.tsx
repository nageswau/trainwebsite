import AdminBdmPage from "@/components/AdminBdmPage";
import { PORTAL_NAV } from "@/lib/navigation";

// bdm-001: IT admins manage College BDMs (D10).
export default function ItAdminBdmsPage() {
  return <AdminBdmPage roles={["it_admin", "super_admin"]} nav={PORTAL_NAV["it/admin"]} roleLabel="IT Administrator" loginHref="/it/login" />;
}
