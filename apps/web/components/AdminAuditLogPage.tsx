import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import AdminAuditLog from "@/components/AdminAuditLog";
import PortalShell from "@/components/PortalShell";
import WorkflowPanel from "@/components/WorkflowPanel";
import { ApiError, serverApi } from "@/lib/api";
import { auditFilterError, auditFilters, auditUrl, type AuditRow } from "@/lib/auditLog";
import type { NavItem } from "@/lib/navigation";
import type { User } from "@/lib/types";

const UNAVAILABLE = "The audit log is unavailable right now. Please try again.";
// A FastAPI validation 422 (e.g. an over-long filter from a hand-edited address) has no worded detail; a worded one is shown as is.
const REFUSED = "These filters could not be applied. Check them and try again.";

// nehn-042 (DEC-SCOPE-289 A7): the one body behind /admin/security-logs (Super Admin, every division, plus the Export panel) and the
// division admins' /it/admin/audit-log and /overseas/admin/audit-log (a static route wins over [module]/[section]). The role check only
// spares other roles a screen that can only fail; the API scopes a division admin to their own division in SQL (A3).
export default async function AdminAuditLogPage({ base, role, nav, roleLabel, loginHref, searchParams }: {
  base: string; role: "super_admin" | "it_admin" | "overseas_admin"; nav: NavItem[]; roleLabel: string; loginHref: string;
  searchParams: Record<string, string | string[] | undefined>;
}) {
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, loginHref);
  }
  if (user.role !== role) return accessDenied(user, `${roleLabel} role required`);
  const filters = auditFilters(searchParams);
  let rows: AuditRow[] | null = null;
  let error = auditFilterError(filters);
  if (!error) {
    try {
      rows = await serverApi<AuditRow[]>(auditUrl(filters));
    } catch (e) {
      if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return accessUnavailable(e, loginHref);
      error = e instanceof ApiError && e.status === 422 ? (e.message.startsWith("[object") ? REFUSED : e.message) : UNAVAILABLE;
    }
  }
  const superAdmin = role === "super_admin";
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Security</div>
            <h2>{superAdmin ? "Security & Audit Logs" : "Audit Log"}</h2>
            <p className="muted">
              Who did what, newest first. {superAdmin ? "Every division." : "Actions by your division's users and the system."} Pick an entity
              reference to see that record&apos;s whole history, or a name to see everything that person did. Times are India time (IST).
            </p>
          </div>
        </div>
        <AdminAuditLog base={base} rows={rows} error={error} filters={filters} showDivision={superAdmin} />
      </div>
      {superAdmin && <WorkflowPanel user={user} section="security-logs" />}
    </PortalShell>
  );
}
