import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import RequirementApprovalQueue from "@/components/RequirementApprovalQueue";
import { serverApi } from "@/lib/api";
import { PORTAL_NAV, SUPER_ADMIN_NAV } from "@/lib/navigation";
import { type ApprovalRow, type ApprovalSettings, APPROVALS_URL } from "@/lib/recruiterRequirements";
import type { User } from "@/lib/types";

// hrc-007 (DEC-SCOPE-380 A9): the HR Manager's vacancy approval queue. The API decides who reads it (a `jobs.approve` holder; anyone
// else 403, shown as the access card).
export default async function HrManagerApprovalsPage() {
  let user: User;
  let page: { items: ApprovalRow[]; total: number };
  let settings: ApprovalSettings;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
    [page, settings] = await Promise.all([
      serverApi<{ items: ApprovalRow[]; total: number }>(`${APPROVALS_URL}?limit=50`),
      serverApi<ApprovalSettings>(`${APPROVALS_URL}/settings`),
    ]);
  } catch (e) {
    return accessUnavailable(e, "/it/login");
  }
  const superAdmin = user.role === "super_admin";
  return (
    <PortalShell nav={superAdmin ? SUPER_ADMIN_NAV : PORTAL_NAV["it/hr-manager"]} roleLabel={superAdmin ? "Super Administrator" : "HR Manager"} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Recruitment</div>
            <h2>Vacancy approvals</h2>
            <p className="muted">Job requirements waiting for approval before they open to candidates. Approving opens one; rejecting returns it to draft with your reason.</p>
          </div>
        </div>
        <RequirementApprovalQueue rows={page.items} total={page.total} settings={settings} />
      </div>
    </PortalShell>
  );
}
