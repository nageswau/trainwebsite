import type { ReactNode } from "react";

import PortalShell from "@/components/PortalShell";
import { MANAGEMENT_ROLE_LABEL, managementNavFor, type ManagementMe } from "@/lib/management";

// mgmt-004: the frame every ledger page shares -- the management sidebar for the caller's tiers and the page title. Only the finance
// tier (partner, accountant) gets this far; the API refuses everyone else before a page renders.
export default function LedgerShell({ me, title, intro, actions, children }: { me: ManagementMe; title: string; intro?: ReactNode; actions?: ReactNode; children: ReactNode }) {
  return (
    <PortalShell nav={managementNavFor(me.tiers)} roleLabel={MANAGEMENT_ROLE_LABEL[me.role] ?? me.role} userName={me.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">EduSphere management · Ledger</div>
            <h2>{title}</h2>
            {intro && <p className="muted">{intro}</p>}
          </div>
          {actions && <div className="actions">{actions}</div>}
        </div>
        {children}
      </div>
    </PortalShell>
  );
}
