import AdminChecklistTemplatesPanel from "@/components/AdminChecklistTemplatesPanel";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { PORTAL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";
import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";

// ccrm-018 (DEC-SCOPE-248): document checklist templates, kept by the Overseas Admin (Super Admin passes the API's role check too).
// The unauthenticated redirect to sign-in is the middleware's, as for every other /overseas page.
const ADMIN_ROLES = ["overseas_admin", "super_admin"];

export default async function AdminChecklistsPage() {
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
            <h2>Document checklists</h2>
            <p className="muted">
              The documents an application needs, by country and optionally university, course level and intake. Counselors work from the most specific matching
              template.
            </p>
          </div>
        </div>
      </div>
      <div className="portal-content action-center">
        <div className="action-grid">
          <AdminChecklistTemplatesPanel />
        </div>
      </div>
    </PortalShell>
  );
}
