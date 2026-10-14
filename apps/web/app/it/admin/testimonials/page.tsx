import AdminTestimonialsPage from "@/components/AdminTestimonialsPage";
import { PORTAL_NAV } from "@/lib/navigation";

// PUB-022: IT testimonials for the IT Admin (and a Super Admin who opens the division page).
export default function ItAdminTestimonialsPage() {
  return <AdminTestimonialsPage division="it" roles={["it_admin", "super_admin"]} nav={PORTAL_NAV["it/admin"]} roleLabel="IT Administrator" loginHref="/it/login" />;
}
