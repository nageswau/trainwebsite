import { Suspense } from "react";

import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import AdminPartnershipPanel from "@/components/AdminPartnershipPanel";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { SUPER_ADMIN_NAV, type NavItem } from "@/lib/navigation";
import type { User } from "@/lib/types";

// upc-001: the one body behind /admin/partnership-managers and /overseas/admin/partnership-managers (a static route wins over
// [module]/[section]). The role check only spares other roles a screen that can only fail; the API enforces who manages managers (PU7).
export default async function AdminPartnershipPage({ roles, nav, roleLabel, loginHref }: { roles: string[]; nav: NavItem[]; roleLabel: string; loginHref: string }) {
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, loginHref);
  }
  if (!roles.includes(user.role)) return accessDenied(user, `${roleLabel} role required`);
  const superAdmin = user.role === "super_admin";
  return (
    <PortalShell nav={superAdmin ? SUPER_ADMIN_NAV : nav} roleLabel={superAdmin ? "Super Administrator" : roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Workspace</div>
            <h2>Partnership managers</h2>
            <p className="muted">Create University Partnership managers, set their reporting head and keep their profiles current. Each new manager gets an emailed set-password link. Partnership Heads are created by a Super Admin from Users.</p>
          </div>
        </div>
      </div>
      <div className="portal-content action-center">
        <div className="action-grid">
          <Suspense fallback={<p className="muted" role="status">Loading partnership managers…</p>}>
            <AdminPartnershipPanel />
          </Suspense>
        </div>
      </div>
    </PortalShell>
  );
}
