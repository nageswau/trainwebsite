import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import PermissionMatrix, { type PermissionCatalogue } from "@/components/PermissionMatrix";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

const LOGIN = "/admin/login";

// nehn-006 (DEC-SCOPE-295): the Super Admin's permission matrix over nehn-005's catalogue. Only super_admin may read or edit grants (P6),
// so anyone else gets the access card here before the catalogue is asked for; the API refuses them either way.
export default async function AdminPermissionsPage() {
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
            <p className="muted">Choose a role, then switch each page action on or off. Changes apply on the role&apos;s next page load, and every saved change is recorded in the audit log.</p>
          </div>
        </div>
        <PermissionMatrix catalogue={catalogue} />
      </div>
    </PortalShell>
  );
}
