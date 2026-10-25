import { Suspense } from "react";

import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import RecruiterTemplatesPanel from "@/components/RecruiterTemplatesPanel";
import { serverApi } from "@/lib/api";
import { COUNSELOR_LIBRARY } from "@/lib/counselorMessages";
import { PORTAL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

// ccrm-037 (DEC-SCOPE-271, MT1): the Overseas Admin's WhatsApp and email templates for counselors -- rec-026's panel with this library.
// Counselors pick them on a student's Activities tab; the API enforces who may read and write. Super Admin passes too.
const ADMIN_ROLES = ["overseas_admin", "super_admin"];

export default async function CounselorTemplatesPage() {
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, "/overseas/login");
  }
  if (!ADMIN_ROLES.includes(user.role)) return accessDenied(user, "Overseas Administrator role required");
  return (
    <PortalShell nav={PORTAL_NAV["overseas/admin"]} roleLabel="Overseas Administrator" userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Workspace</div>
            <h2>Message templates</h2>
            <p className="muted">
              WhatsApp and email messages counselors start from when they write to a student, such as an offer update or a deadline reminder.
              They can edit the text before sending. Use placeholders for the student&apos;s and the application&apos;s details. Deactivate a
              template to hide it — it is never deleted.
            </p>
          </div>
        </div>
        <Suspense fallback={<p className="muted" role="status">Loading templates…</p>}>
          <RecruiterTemplatesPanel library={COUNSELOR_LIBRARY} />
        </Suspense>
      </div>
    </PortalShell>
  );
}
