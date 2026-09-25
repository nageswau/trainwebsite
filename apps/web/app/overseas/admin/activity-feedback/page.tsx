import AdminActivityFeedbackPanel from "@/components/AdminActivityFeedbackPanel";
import PortalShell from "@/components/PortalShell";
import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import { serverApi } from "@/lib/api";
import { PORTAL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

// ENH-018 (D2): Edusphere management reads every school's activity feedback. A static route, so it wins over `[section]`;
// admin-only like the API, so nobody else is shown a screen that can only fail (ENH-005's school-transfers page pattern).
const ADMIN_ROLES = ["overseas_admin", "super_admin"];

export default async function AdminActivityFeedbackPage() {
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e);
  }
  if (!ADMIN_ROLES.includes(user.role)) return accessDenied(user, "Overseas Administrator role required");
  return (
    <PortalShell nav={PORTAL_NAV["overseas/admin"]} roleLabel="Overseas Administrator" userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Workspace</div>
            <h2>Activity Feedback</h2>
            <p className="muted">Feedback School Coordinators recorded after each Edusphere activity, across every partner school.</p>
          </div>
        </div>
        <AdminActivityFeedbackPanel />
      </div>
    </PortalShell>
  );
}
