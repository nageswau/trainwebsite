import AdminTestimonialsPage from "@/components/AdminTestimonialsPage";
import { PORTAL_NAV } from "@/lib/navigation";

// PUB-022: overseas testimonials for the Overseas Admin (and a Super Admin who opens the division page).
export default function OverseasAdminTestimonialsPage() {
  return <AdminTestimonialsPage division="overseas" roles={["overseas_admin", "super_admin"]} nav={PORTAL_NAV["overseas/admin"]} roleLabel="Overseas Administrator" loginHref="/overseas/login" />;
}
