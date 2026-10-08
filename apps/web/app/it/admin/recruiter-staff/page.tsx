import AdminRecruiterPage from "@/components/AdminRecruiterPage";
import { PORTAL_NAV } from "@/lib/navigation";

// rec-001 (R2): IT admins manage recruiters (an IT role).
export default function ItAdminRecruiterStaffPage() {
  return <AdminRecruiterPage nav={PORTAL_NAV["it/admin"]} roleLabel="IT Administrator" loginHref="/it/login" />;
}
