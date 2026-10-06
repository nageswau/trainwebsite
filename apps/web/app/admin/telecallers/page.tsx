import AdminTelecallerPage from "@/components/AdminTelecallerPage";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";

// tel-001: the Super Admin's Telecallers page (both teams; managers are created from Users).
export default function SuperAdminTelecallersPage() {
  return <AdminTelecallerPage roles={["super_admin"]} nav={SUPER_ADMIN_NAV} roleLabel="Super Administrator" loginHref="/admin/login" />;
}
