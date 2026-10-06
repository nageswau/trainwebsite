import AdminTelecallerPage from "@/components/AdminTelecallerPage";
import { PORTAL_NAV } from "@/lib/navigation";

// tel-001: Overseas admins manage Overseas telecallers.
export default function OverseasAdminTelecallersPage() {
  return <AdminTelecallerPage roles={["overseas_admin", "super_admin"]} nav={PORTAL_NAV["overseas/admin"]} roleLabel="Overseas Administrator" loginHref="/overseas/login" />;
}
