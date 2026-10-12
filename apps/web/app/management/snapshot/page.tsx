import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import ManagementSnapshot from "@/components/ManagementSnapshot";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { MANAGEMENT_HOME, MANAGEMENT_ROLE_LABEL, managementNavFor, type ManagementMe, type ManagementSnapshot as Snapshot } from "@/lib/management";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";

// mgmt-003 (MS18): the business snapshot for the operational tier. The API refuses everyone else (the accountant's 403 included),
// and that refusal is shown as the access card.
export default async function ManagementSnapshotPage() {
  let me: ManagementMe;
  let snapshot: Snapshot;
  try {
    [me, snapshot] = await Promise.all([serverApi<ManagementMe>("/api/v1/management/me"), serverApi<Snapshot>("/api/v1/management/snapshot")]);
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  return (
    <PortalShell nav={me.role === "super_admin" ? SUPER_ADMIN_NAV : managementNavFor(me.tiers)} roleLabel={MANAGEMENT_ROLE_LABEL[me.role] ?? me.role} userName={me.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">
              <Link href={MANAGEMENT_HOME}>Command Center</Link>
            </div>
            <h2>Business snapshot</h2>
          </div>
        </div>
        <ManagementSnapshot snapshot={snapshot} />
      </div>
    </PortalShell>
  );
}
