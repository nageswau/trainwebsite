import Link from "next/link";

import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import BdmTargetsEditor from "@/components/BdmTargetsEditor";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { BDM_TYPE_LABEL } from "@/lib/bdm";
import { bdmManagerNav } from "@/lib/bdmNav";
import { LINK_STYLE } from "@/lib/bdmOrganizations";
import { chosenMonth, currentMonth, MANAGER_TARGETS_PATH, monthLabel, type TargetSheet, teamTargetUrl } from "@/lib/bdmTargets";
import { isUuid } from "@/lib/bdmTravel";
import type { User } from "@/lib/types";

// bdm-016 (spec §6): one team BDM's month -- target, achieved and achievement % per KPI of their type, editable when the month is.
export default async function ManagerMemberTargetsPage({ params, searchParams }: { params: Promise<{ bdmId: string }>; searchParams: Promise<{ month?: string }> }) {
  const nav = bdmManagerNav();
  const { bdmId } = await params;
  const { month, note } = chosenMonth((await searchParams).month, currentMonth());
  let user: User, sheet: TargetSheet;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
    if (user.role !== "bdm_manager" && user.role !== "super_admin") return accessDenied(user, "This page is for BDM managers.");
    if (!isUuid(bdmId)) return accessDenied(user, "BDM not found"); // QA16-01: the API's 422 for a malformed id is not a sentence
    sheet = await serverApi<TargetSheet>(teamTargetUrl(bdmId, month));
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  return (
    <PortalShell nav={await nav} roleLabel={user.role === "super_admin" ? "Super Admin" : "BDM Manager"} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Targets</div>
            <h2>{sheet.bdm.full_name} — {monthLabel(sheet.month)}</h2>
            <p className="muted">{BDM_TYPE_LABEL[sheet.bdm_type]} BDM · <Link href={`${MANAGER_TARGETS_PATH}?month=${sheet.month}`} style={LINK_STYLE}>All team targets</Link></p>
            {note && <p className="muted">{note}</p>}
            {!sheet.editable && <p className="muted">{sheet.month_status === "past" ? "Past months are read-only." : "These targets can't be changed."}</p>}
          </div>
        </div>
        <BdmTargetsEditor key={`${sheet.bdm.id}-${sheet.month}`} initial={sheet} />
      </div>
    </PortalShell>
  );
}
