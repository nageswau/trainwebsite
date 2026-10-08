import AdminRecruiterPage from "@/components/AdminRecruiterPage";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";

// rec-001: the Super Admin's Recruiter Staff page (placement managers are created from Users).
export default function SuperAdminRecruiterStaffPage() {
  return <AdminRecruiterPage nav={SUPER_ADMIN_NAV} roleLabel="Super Administrator" loginHref="/admin/login" />;
}
