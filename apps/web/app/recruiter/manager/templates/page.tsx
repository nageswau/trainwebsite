import { Suspense } from "react";

import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import RecruiterTemplateLibrary from "@/components/RecruiterTemplateLibrary";
import { serverApi } from "@/lib/api";
import { RECRUITER_MANAGER_NAV, SUPER_ADMIN_NAV } from "@/lib/navigation";
import { PLACEMENT_MANAGER_LABEL } from "@/lib/recruiter";
import type { User } from "@/lib/types";

// rec-026 (EVID-018 §19, MS3) + pob-023 (DEC-SCOPE-408): the Team Lead's view of the governed library -- approve drafts, edit, archive. Recruiters pick templates in the composers on a
// company or candidate page; this screen is the manager's (and super_admin's). The API enforces who may read and write.
export default async function RecruiterManagerTemplatesPage() {
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  if (!["placement_manager", "super_admin"].includes(user.role)) return accessDenied(user, "Placement manager role required");
  const superAdmin = user.role === "super_admin";
  return (
    <PortalShell nav={superAdmin ? SUPER_ADMIN_NAV : RECRUITER_MANAGER_NAV} roleLabel={superAdmin ? "Super Administrator" : PLACEMENT_MANAGER_LABEL} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Recruiter CRM</div>
            <h2>Message templates</h2>
            <p className="muted">Email, LinkedIn, WhatsApp and calling templates the team starts from. Approve recruiters' drafts to share them; edits keep every version. Archive a template to hide it — it is never deleted.</p>
          </div>
        </div>
        <Suspense fallback={<p className="muted" role="status">Loading templates…</p>}>
          <RecruiterTemplateLibrary approver />
        </Suspense>
      </div>
    </PortalShell>
  );
}
