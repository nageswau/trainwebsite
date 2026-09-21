import AdminSchoolTransferPanel from "@/components/AdminSchoolTransferPanel";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { PORTAL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

function AccessUnavailable({ message }: { message: string }) {
  return (
    <div className="section">
      <div className="container card">
        <h1>Access unavailable</h1>
        <p>{message}</p>
        <a className="btn" href="/overseas/login">Return to login</a>
      </div>
    </div>
  );
}

// ENH-005: the admin's transfer queue as its own page. It used to be the portal's generic section, whose read-only table (raw UUIDs, ISO
// timestamps, capped at 200 rows, counted differently from the queue) sat above the queue and pushed the approve/reject controls below the
// fold (browser QA N3). A static route wins over `[section]`, so the nav entry is unchanged. Admin-only, like the API (every route under
// /overseas-admin/school-transfer-requests answers 403 to any other role): the role is checked here first so nobody else is shown a screen
// that can only fail. The unauthenticated redirect to sign-in is the middleware's, as for every other /overseas page.
const ADMIN_ROLES = ["overseas_admin", "super_admin"];

export default async function AdminSchoolTransfersPage() {
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return <AccessUnavailable message={e instanceof Error ? e.message : "Unable to load this workspace"} />;
  }
  if (!ADMIN_ROLES.includes(user.role)) return <AccessUnavailable message="Overseas Administrator role required" />;
  return (
    <PortalShell nav={PORTAL_NAV["overseas/admin"]} roleLabel="Overseas Administrator" userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Workspace</div>
            <h2>School Transfers</h2>
            <p className="muted">Student transfer requests from School Coordinators. Approve or reject pending ones; approving moves the student in one step.</p>
          </div>
        </div>
      </div>
      <div className="portal-content action-center">
        <div className="action-grid">
          <AdminSchoolTransferPanel />
        </div>
      </div>
    </PortalShell>
  );
}
