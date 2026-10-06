import { Suspense } from "react";

import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { TELECALLER_MANAGER_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

// tel-002: the shell behind /telecaller/manager/products and /campaigns. Managers and super_admin edit the catalogue; the role check only
// spares other roles a screen that can only fail -- the API enforces who may write.
export default async function TelecallerCataloguePage({ title, intro, eyebrow = "Settings", children }: { title: string; intro: string; eyebrow?: string; children: React.ReactNode }) {
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  if (!["telecaller_manager", "super_admin"].includes(user.role)) return accessDenied(user, "Telecaller manager role required");
  return (
    <PortalShell nav={TELECALLER_MANAGER_NAV} roleLabel={user.role === "super_admin" ? "Super Administrator" : "Telecaller Manager"} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">{eyebrow}</div>
            <h2>{title}</h2>
            <p className="muted">{intro}</p>
          </div>
        </div>
      </div>
      <div className="portal-content action-center">
        <div className="action-grid"><Suspense fallback={<p className="muted" role="status">Loading…</p>}>{children}</Suspense></div>
      </div>
    </PortalShell>
  );
}
