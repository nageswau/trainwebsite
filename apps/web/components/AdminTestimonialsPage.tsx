import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import RatingBadgeForm from "@/components/RatingBadgeForm";
import TestimonialManager from "@/components/TestimonialManager";
import { serverApi } from "@/lib/api";
import { SUPER_ADMIN_NAV, type NavItem } from "@/lib/navigation";
import type { Division } from "@/lib/testimonials";
import type { User } from "@/lib/types";

// PUB-022 (DEC-SCOPE-210): the one body behind /admin/testimonials (both divisions + the rating badge) and the division admins'
// /it/admin/testimonials and /overseas/admin/testimonials (a static route wins over [module]/[section]). The role check only
// spares other roles a screen that can only fail; the API enforces the division (SP2) and the Super-Admin-only badge (SP5).
export default async function AdminTestimonialsPage({ division, roles, nav, roleLabel, loginHref }: { division: Division | null; roles: string[]; nav: NavItem[]; roleLabel: string; loginHref: string }) {
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, loginHref);
  }
  if (!roles.includes(user.role)) return accessDenied(user, `${roleLabel} role required`);
  const superAdmin = user.role === "super_admin";
  const divisions: Division[] = division ? [division] : ["it", "overseas"];
  return (
    <PortalShell nav={superAdmin ? SUPER_ADMIN_NAV : nav} roleLabel={superAdmin ? "Super Administrator" : roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Website</div>
            <h2>Testimonials</h2>
            <p className="muted">Real student stories for the public homepage. A testimonial is shown only after you record the person&apos;s consent and publish it.</p>
          </div>
        </div>
      </div>
      <div className="portal-content action-center">
        <div className="action-grid">
          {superAdmin && division === null && <RatingBadgeForm />}
          <TestimonialManager divisions={divisions} />
        </div>
      </div>
    </PortalShell>
  );
}
