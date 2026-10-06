import { Suspense } from "react";

import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import AdminTelecallerPanel from "@/components/AdminTelecallerPanel";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { SUPER_ADMIN_NAV, type NavItem } from "@/lib/navigation";
import type { User } from "@/lib/types";

// tel-001: the one body behind /admin/telecallers, /it/admin/telecallers and /overseas/admin/telecallers (a static route wins over
// [module]/[section]). The role check only spares other roles a screen that can only fail; the API enforces who manages which team.
export default async function AdminTelecallerPage({ roles, nav, roleLabel, loginHref }: { roles: string[]; nav: NavItem[]; roleLabel: string; loginHref: string }) {
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
            <h2>Telecallers</h2>
            <p className="muted">Create telecallers, set their reporting manager and keep their profiles current. Each new telecaller gets an emailed set-password link. Telecaller Managers are created from Users.</p>
          </div>
        </div>
      </div>
      <div className="portal-content action-center">
        <div className="action-grid">
          <Suspense fallback={<p className="muted" role="status">Loading telecallers…</p>}>
            <AdminTelecallerPanel role={user.role} />
          </Suspense>
        </div>
      </div>
    </PortalShell>
  );
}
