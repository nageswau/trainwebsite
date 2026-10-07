import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import SchoolNotificationList, { type NotificationItem } from "@/components/SchoolNotificationList";
import { serverApi } from "@/lib/api";
import { TELECALLER_SIGN_IN } from "@/lib/navigation";
import { teamRoleLabel, type TelecallerMe } from "@/lib/telecaller";
import { telecallerNav } from "@/lib/telecallerNav";

// tel-020 (EVID-019 §20, T14): the telecaller's alerts -- the shared feed and list the BDM page uses; opening an unread notice marks it
// read before it navigates, so the sidebar badge is already right on the next page.
export default async function TelecallerNotificationsPage() {
  const nav = telecallerNav();
  let me: TelecallerMe, notifications: NotificationItem[];
  try {
    [me, notifications] = await Promise.all([
      serverApi<TelecallerMe>("/api/v1/telecaller/me"),
      serverApi<NotificationItem[]>("/api/v1/workflows/notifications"),
    ]);
  } catch (e) {
    return accessUnavailable(e, TELECALLER_SIGN_IN);
  }
  return (
    <PortalShell nav={await nav} roleLabel={teamRoleLabel(me.telecaller_profile.team)} userName={me.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Notifications</div>
            <h2>Your notifications</h2>
          </div>
        </div>
        <div className="card">
          <SchoolNotificationList notifications={notifications} readBeforeOpen
            emptyText="No notifications yet. New leads, follow-ups, appointments, returned leads and waiting leads appear here." />
        </div>
      </div>
    </PortalShell>
  );
}
