import Link from "next/link";

import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import TargetsEditor from "@/components/TargetsEditor";
import { serverApi } from "@/lib/api";
import { LINK_STYLE } from "@/lib/bdmOrganizations";
import { chosenMonth, currentMonth, monthLabel } from "@/lib/bdmTargets";
import { isUuid } from "@/lib/bdmTravel";
import { type ManagerTargetSheet, managerTargetUrl, TARGET_READERS, TARGETS_PATH, TARGETS_URL } from "@/lib/partnershipTargets";
import type { User } from "@/lib/types";
import { shellFor } from "@/lib/universities";

// upc-021 (spec §5): one manager's month -- target, actual and achievement per §21 KPI, editable by their head (or super_admin) when the
// month is. The API scopes the manager (another head's manager, or another manager for a manager, is its 404 message).
export default async function PartnershipManagerTargetsPage({ params, searchParams }: { params: Promise<{ managerId: string }>; searchParams: Promise<{ month?: string }> }) {
  const { managerId } = await params;
  const { month, note } = chosenMonth((await searchParams).month, currentMonth());
  let user: User, sheet: ManagerTargetSheet;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
    if (!TARGET_READERS.has(user.role)) return accessDenied(user, "Partnership targets access required");
    if (!isUuid(managerId)) return accessDenied(user, "Partnership manager not found"); // the API's 422 for a malformed id is not a sentence
    sheet = await serverApi<ManagerTargetSheet>(managerTargetUrl(managerId, month));
  } catch (e) {
    return accessUnavailable(e, "/overseas/login");
  }
  const { nav, roleLabel } = shellFor(user.role);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Targets &amp; Forecast</div>
            <h2>{sheet.manager.full_name} — {monthLabel(sheet.month)}</h2>
            <p className="muted"><Link href={`${TARGETS_PATH}?month=${sheet.month}`} style={LINK_STYLE}>All team targets</Link></p>
            {note && <p className="muted">{note}</p>}
            {!sheet.editable && <p className="muted">{sheet.month_status === "past" ? "Past months are read-only." : "These targets can't be changed."}</p>}
          </div>
        </div>
        <TargetsEditor key={`${sheet.manager.id}-${sheet.month}`} initial={sheet} ownerId={sheet.manager.id} ownerField="manager_user_id" saveUrl={TARGETS_URL} />
      </div>
    </PortalShell>
  );
}
