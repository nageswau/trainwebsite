import AdminBdmPage from "@/components/AdminBdmPage";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";

// bdm-001: the Super Admin's BDM page (every type; also the only creator of BDM managers, via Users).
export default function SuperAdminBdmsPage() {
  return <AdminBdmPage roles={["super_admin"]} nav={SUPER_ADMIN_NAV} roleLabel="Super Administrator" />;
}
