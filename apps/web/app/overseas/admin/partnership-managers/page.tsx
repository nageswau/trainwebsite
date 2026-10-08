import AdminPartnershipPage from "@/components/AdminPartnershipPage";
import { PORTAL_NAV } from "@/lib/navigation";

// upc-001 (PU7): Overseas admins manage partnership managers (an Overseas role).
export default function OverseasAdminPartnershipManagersPage() {
  return <AdminPartnershipPage roles={["overseas_admin", "super_admin"]} nav={PORTAL_NAV["overseas/admin"]} roleLabel="Overseas Administrator" loginHref="/overseas/login" />;
}
