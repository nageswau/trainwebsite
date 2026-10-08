import AdminPartnershipPage from "@/components/AdminPartnershipPage";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";

// upc-001: the Super Admin's Partnership managers page (heads are created from Users).
export default function SuperAdminPartnershipManagersPage() {
  return <AdminPartnershipPage roles={["super_admin"]} nav={SUPER_ADMIN_NAV} roleLabel="Super Administrator" loginHref="/admin/login" />;
}
