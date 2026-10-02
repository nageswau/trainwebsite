import { Suspense } from "react";

import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import AdminBdmPanel from "@/components/AdminBdmPanel";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { SUPER_ADMIN_NAV, type NavItem } from "@/lib/navigation";
import type { User } from "@/lib/types";

// bdm-001: the one body behind /admin/bdms, /it/admin/bdms and /overseas/admin/bdms (a static route wins over [module]/[section]).
// The role check only spares other roles a screen that can only fail; the API enforces who manages which type (D10).
// `loginHref`: this page's own sign-in, so a signed-out visitor is not sent to the Overseas one (review deferred minor).
export default async function AdminBdmPage({ roles, nav, roleLabel, loginHref }: { roles: string[]; nav: NavItem[]; roleLabel: string; loginHref: string }) {
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, loginHref);
  }
  if (!roles.includes(user.role)) return accessDenied(user, `${roleLabel} role required`);
  // QA-12: a Super Admin who opens a division's BDM page is still labelled (and navigated) as the Super Admin.
  const superAdmin = user.role === "super_admin";
  return (
    <PortalShell nav={superAdmin ? SUPER_ADMIN_NAV : nav} roleLabel={superAdmin ? "Super Administrator" : roleLabel} userName={user.full_name}>
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
          {/* AdminBdmPanel reads its page and search from the URL (QA-13). */}
          <Suspense fallback={<p className="muted" role="status">Loading BDMs…</p>}>
            <AdminBdmPanel role={user.role} />
          </Suspense>
        </div>
      </div>
    </PortalShell>
  );
}
