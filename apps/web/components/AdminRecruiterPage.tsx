import { Suspense } from "react";

import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import AdminRecruiterPanel from "@/components/AdminRecruiterPanel";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { SUPER_ADMIN_NAV, type NavItem } from "@/lib/navigation";
import type { User } from "@/lib/types";

// rec-001: the one body behind /admin/recruiter-staff and /it/admin/recruiter-staff (a static route wins over [module]/[section]).
// The role check only spares other roles a screen that can only fail; the API enforces it (super_admin, it_admin).
export default async function AdminRecruiterPage({ nav, roleLabel, loginHref }: { nav: NavItem[]; roleLabel: string; loginHref: string }) {
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, loginHref);
  }
  if (!["super_admin", "it_admin"].includes(user.role)) return accessDenied(user, "Super Admin or IT Administrator role required");
  const superAdmin = user.role === "super_admin";
  return (
    <PortalShell nav={superAdmin ? SUPER_ADMIN_NAV : nav} roleLabel={superAdmin ? "Super Administrator" : roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Workspace</div>
            <h2>Recruiter Staff</h2>
            <p className="muted">Create recruiters, set their Employee ID and reporting placement manager, and keep their profiles current. Each new recruiter gets an emailed set-password link. Recruiters marked “No manager” predate this page — use Edit to set one. Placement Managers are created by a Super Admin from Users.</p>
          </div>
        </div>
      </div>
      <div className="portal-content action-center">
        <div className="action-grid">
          <Suspense fallback={<p className="muted" role="status">Loading recruiters…</p>}>
            <AdminRecruiterPanel />
          </Suspense>
        </div>
      </div>
    </PortalShell>
  );
}
