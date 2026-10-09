import { Suspense } from "react";

import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import PartnershipTasksPanel from "@/components/PartnershipTasksPanel";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { TASK_READERS } from "@/lib/partnershipTasks";
import type { User } from "@/lib/types";
import { shellFor } from "@/lib/universities";

// upc-020 (§19/§20): every partnership follow-up and task, in the §20 bands. The panel reads the list itself (filters in the URL); the
// API is the gate, and a role that cannot read tasks (TK8) is refused here before the panel asks.
export default async function PartnershipTasksPage() {
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, "/overseas/login");
  }
  if (!TASK_READERS.has(user.role)) return accessDenied(user, "Partnership tasks access required");
  const { nav, roleLabel } = shellFor(user.role);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Follow-ups &amp; Tasks</div>
            <h2>Follow-ups &amp; tasks</h2>
            <p className="muted">Every university&apos;s next actions. Some are added automatically when a university changes stage or a visit is completed.</p>
          </div>
        </div>
        <section className="action-card wide">
          <Suspense fallback={<p className="muted" role="status">Loading follow-ups…</p>}>
            <PartnershipTasksPanel role={user.role} />
          </Suspense>
        </section>
      </div>
    </PortalShell>
  );
}
