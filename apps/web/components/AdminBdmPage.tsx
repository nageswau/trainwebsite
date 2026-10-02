import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import AdminBdmPanel from "@/components/AdminBdmPanel";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import type { NavItem } from "@/lib/navigation";
import type { User } from "@/lib/types";

// bdm-001: the one body behind /admin/bdms, /it/admin/bdms and /overseas/admin/bdms (a static route wins over [module]/[section]).
// The role check only spares other roles a screen that can only fail; the API enforces who manages which type (D10).
export default async function AdminBdmPage({ roles, nav, roleLabel }: { roles: string[]; nav: NavItem[]; roleLabel: string }) {
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e);
  }
  if (!roles.includes(user.role)) return accessDenied(user, `${roleLabel} role required`);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Workspace</div>
            <h2>BDMs</h2>
            <p className="muted">Create Business Development Managers, set their reporting manager and keep their profiles current. Each new BDM gets an emailed set-password link.</p>
          </div>
        </div>
      </div>
      <div className="portal-content action-center">
        <div className="action-grid">
          <AdminBdmPanel role={user.role} />
        </div>
      </div>
    </PortalShell>
  );
}
