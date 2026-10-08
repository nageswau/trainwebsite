import { redirect } from "next/navigation";
import { Suspense } from "react";

import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import RecruiterSkillsPanel from "@/components/RecruiterSkillsPanel";
import { serverApi } from "@/lib/api";
import { RECRUITER_MANAGER_NAV, RECRUITER_NAV, SUPER_ADMIN_NAV } from "@/lib/navigation";
import { PLACEMENT_MANAGER_LABEL, RECRUITER_ROLE_LABEL } from "@/lib/recruiter";
import type { User } from "@/lib/types";

const WRITERS = ["placement_manager", "super_admin"];

// rec-006 (S2, S3): the shell behind /recruiter/manager/skills (managers and super_admin edit) and /recruiter/skills (recruiters read).
// A writer who opens the read-only page goes to the editable one. The role checks only spare other roles a screen that can only fail
// -- the API enforces who may read and write.
export default async function RecruiterSkillsPage({ edit }: { edit: boolean }) {
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, edit ? "/admin/login" : "/it/login");
  }
  const writer = WRITERS.includes(user.role);
  if (!edit && writer) redirect("/recruiter/manager/skills");
  if (edit ? !writer : user.role !== "placement_team") return accessDenied(user, edit ? "Placement manager role required" : "Recruiter role required");
  const superAdmin = user.role === "super_admin";
  const nav = superAdmin ? SUPER_ADMIN_NAV : edit ? RECRUITER_MANAGER_NAV : RECRUITER_NAV;
  const roleLabel = superAdmin ? "Super Administrator" : edit ? PLACEMENT_MANAGER_LABEL : RECRUITER_ROLE_LABEL;
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Skills Master</div>
            <h2>Skills</h2>
            <p className="muted">
              {edit
                ? "The skills recruiters search and tag candidates with. Add aliases so other spellings (J2EE, ReactJS) find the right skill. Deactivate a skill to hide it — it is never deleted."
                : "Every skill recruiters search and tag candidates with, with its other spellings. Ask your placement manager to add or change a skill."}
            </p>
          </div>
        </div>
      </div>
      <div className="portal-content action-center">
        <div className="action-grid"><Suspense fallback={<p className="muted" role="status">Loading…</p>}><RecruiterSkillsPanel canEdit={edit} /></Suspense></div>
      </div>
    </PortalShell>
  );
}
