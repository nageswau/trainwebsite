import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import SchoolNotificationList, { type NotificationItem } from "@/components/SchoolNotificationList";
import { serverApi } from "@/lib/api";
import { bdmManagerNav } from "@/lib/bdmNav";
import type { User } from "@/lib/types";

// bdm-010 (QA10-01): the BDM manager's own in-app notices -- "Travel approval needed" when a BDM submits a trip. Opening a notice
// marks it read and goes to the approvals queue.
export default async function ManagerNotificationsPage() {
  const nav = bdmManagerNav(); // the unread badge, read alongside the page's own data (never rejects)
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  if (user.role !== "bdm_manager") return accessDenied(user, "BDM manager role required");
  let notifications: NotificationItem[];
  try {
    notifications = await serverApi<NotificationItem[]>("/api/v1/workflows/notifications");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  return (
    <PortalShell nav={await nav} roleLabel="BDM Manager" userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Notifications</div>
            <h2>Your notifications</h2>
          </div>
        </div>
        <div className="card">
          <SchoolNotificationList notifications={notifications} readBeforeOpen
            emptyText="No notifications yet. You will be told here when one of your BDMs submits a trip for approval." />
        </div>
      </div>
    </PortalShell>
  );
}
