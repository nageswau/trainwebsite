import AdminAgentDepositsPanel from "@/components/AdminAgentDepositsPanel";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { PORTAL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";
import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";

// AGN-011 (DEC-SCOPE-057 §4.7): deposits agencies paid through EduSphere Razorpay, for Overseas Admin to record remittance and refunds.
// Readable by Overseas and Super Admins like the API; only an Overseas Admin records (D5), so `canAct` follows the role. The
// unauthenticated redirect to sign-in is the middleware's, as for every other /overseas page.
const ADMIN_ROLES = ["overseas_admin", "super_admin"];

export default async function AdminAgentDepositsPage() {
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
            <h2>Agent deposits</h2>
            <p className="muted">
              University deposits agencies paid through EduSphere. Record when finance remits a deposit to the university, or a refund made by hand.
            </p>
          </div>
        </div>
      </div>
      <div className="portal-content action-center">
        <div className="action-grid">
          <AdminAgentDepositsPanel canAct={user.role === "overseas_admin"} />
        </div>
      </div>
    </PortalShell>
  );
}
