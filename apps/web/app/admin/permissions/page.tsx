import Link from "next/link";

import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import PermissionMatrix, { type PermissionCatalogue } from "@/components/PermissionMatrix";
import PortalShell from "@/components/PortalShell";
import UserPermissionOverrides from "@/components/UserPermissionOverrides";
import { serverApi } from "@/lib/api";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

const LOGIN = "/admin/login";

// nehn-006 (DEC-SCOPE-295): the Super Admin's permission matrix over nehn-005's catalogue. Only super_admin may read or edit grants (P6),
// so anyone else gets the access card here before the catalogue is asked for; the API refuses them either way.
// nehn-007 (DEC-SCOPE-298): a "By user" tab for per-user overrides; the tab and the picked user live in the URL (refresh/back keep them).
export default async function AdminPermissionsPage({ searchParams }: { searchParams: Promise<{ tab?: string; user?: string }> }) {
  const { tab, user: picked } = await searchParams;
  const byUser = tab === "user";
  let user: User;
  let catalogue: PermissionCatalogue;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
    if (user.role !== "super_admin") return accessDenied(user, "Only a super admin can manage permissions");
    catalogue = await serverApi<PermissionCatalogue>("/api/v1/admin/permissions/catalogue");
  } catch (e) {
    return accessUnavailable(e, LOGIN);
  }
  return (
    <PortalShell nav={SUPER_ADMIN_NAV} roleLabel="Super Administrator" userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Administration</div>
            <h2>Permissions</h2>
            <p className="muted">Choose a role, then switch each page action on or off, or give one user an override. Changes apply on the next page load, and every saved change is recorded in the audit log.</p>
          </div>
        </div>
        <nav className="actions" aria-label="Permission views" style={{ marginBottom: 16 }}>
          <Link href="/admin/permissions" className={byUser ? "btn secondary small" : "btn small"} aria-current={byUser ? undefined : "page"}>By role</Link>
          <Link href="/admin/permissions?tab=user" className={byUser ? "btn small" : "btn secondary small"} aria-current={byUser ? "page" : undefined}>By user</Link>
        </nav>
        {byUser ? <UserPermissionOverrides catalogue={catalogue} userId={picked || null} /> : <PermissionMatrix catalogue={catalogue} />}
      </div>
    </PortalShell>
  );
}
