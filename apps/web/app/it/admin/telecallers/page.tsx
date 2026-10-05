import AdminTelecallerPage from "@/components/AdminTelecallerPage";
import { PORTAL_NAV } from "@/lib/navigation";

// tel-001 (AC2): IT admins manage IT telecallers.
export default function ItAdminTelecallersPage() {
  return <AdminTelecallerPage roles={["it_admin", "super_admin"]} nav={PORTAL_NAV["it/admin"]} roleLabel="IT Administrator" loginHref="/it/login" />;
}
