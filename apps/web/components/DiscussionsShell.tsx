import Link from "next/link";
import type { ReactNode } from "react";

import PortalShell from "@/components/PortalShell";
import { MANAGEMENT_HOME, MANAGEMENT_ROLE_LABEL, managementNavFor, type ManagementMe } from "@/lib/management";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";

// mgmt-027: the frame every discussions page shares. Only the operational tier (partner, super_admin) gets this far; the super admin
// keeps their own sidebar, as on the business snapshot (mgmt-003).
export default function DiscussionsShell({ me, title, intro, actions, children }: { me: ManagementMe; title: string; intro?: ReactNode; actions?: ReactNode; children: ReactNode }) {
  return (
    <PortalShell nav={me.role === "super_admin" ? SUPER_ADMIN_NAV : managementNavFor(me.tiers)} roleLabel={MANAGEMENT_ROLE_LABEL[me.role] ?? me.role} userName={me.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow"><Link href={MANAGEMENT_HOME}>Command Center</Link> · Discussions &amp; decisions</div>
            <h2 style={{ overflowWrap: "anywhere" }}>{title}</h2>
            {intro && <p className="muted">{intro}</p>}
          </div>
          {actions && <div className="actions">{actions}</div>}
        </div>
        {children}
      </div>
    </PortalShell>
  );
}
