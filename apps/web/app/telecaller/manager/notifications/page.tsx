import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import SchoolNotificationList, { type NotificationItem } from "@/components/SchoolNotificationList";
import { serverApi } from "@/lib/api";
import { telecallerManagerNav } from "@/lib/telecallerNav";
import type { User } from "@/lib/types";

// itc-009 (DEC-SCOPE-342): the telecaller manager's own in-app notices -- "Follow-up overdue" when a telecaller's follow-up passes the
// team's escalation hours. Opening a notice marks it read and goes to the lead. The bdm-010 manager page, for this role.
export default async function TelecallerManagerNotificationsPage() {
  const nav = telecallerManagerNav(); // the unread badge, read alongside the page's own data (never rejects)
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  if (user.role !== "telecaller_manager") return accessDenied(user, "Telecaller manager role required");
  let notifications: NotificationItem[];
  try {
    notifications = await serverApi<NotificationItem[]>("/api/v1/workflows/notifications");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  return (
    <PortalShell nav={await nav} roleLabel="Telecaller Manager" userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Notifications</div>
            <h2>Your notifications</h2>
          </div>
        </div>
        <div className="card">
          <SchoolNotificationList notifications={notifications} readBeforeOpen
            emptyText="No notifications yet. Overdue follow-ups escalated from your telecallers appear here." />
        </div>
      </div>
    </PortalShell>
  );
}
