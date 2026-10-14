import AdminTestimonialsPage from "@/components/AdminTestimonialsPage";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";

// PUB-022: the Super Admin's testimonials (both divisions) and the site rating badge.
export default function SuperAdminTestimonialsPage() {
  return <AdminTestimonialsPage division={null} roles={["super_admin"]} nav={SUPER_ADMIN_NAV} roleLabel="Super Administrator" loginHref="/admin/login" />;
}
