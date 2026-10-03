import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import SchoolNotificationList, { type NotificationItem } from "@/components/SchoolNotificationList";
import { serverApi } from "@/lib/api";
import { BDM_TYPE_LABEL, type BdmMe } from "@/lib/bdm";
import { bdmNav } from "@/lib/bdmNav";
import { BDM_SIGN_IN } from "@/lib/navigation";

// bdm-010 (QA10-01): the BDM's own in-app notices -- a trip approved or not approved. Same feed and list as the other portals; opening
// an unread notice marks it read before it navigates, so the sidebar badge is already right on the next page (AGN-017 QA17-01).
export default async function BdmNotificationsPage() {
  const nav = bdmNav(); // the unread badge, read alongside the page's own data (never rejects)
  let me: BdmMe, notifications: NotificationItem[];
  try {
    [me, notifications] = await Promise.all([
      serverApi<BdmMe>("/api/v1/bdm/me"),
      serverApi<NotificationItem[]>("/api/v1/workflows/notifications"),
    ]);
  } catch (e) {
    return accessUnavailable(e, BDM_SIGN_IN);
  }
  return (
    <PortalShell nav={await nav} roleLabel={`${BDM_TYPE_LABEL[me.bdm_profile.bdm_type]} BDM`} userName={me.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Notifications</div>
            <h2>Your notifications</h2>
          </div>
        </div>
        <div className="card">
          <SchoolNotificationList notifications={notifications} readBeforeOpen
            emptyText="No notifications yet. You will be told here when your manager approves a trip or sends it back." />
        </div>
      </div>
    </PortalShell>
  );
}
