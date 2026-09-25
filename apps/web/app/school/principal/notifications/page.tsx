import PortalShell from "@/components/PortalShell";
import SchoolNotificationList, { type NotificationItem } from "@/components/SchoolNotificationList";
import { serverApi } from "@/lib/api";
import { SCHOOL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";
import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";

// ENH-023 (DEC-SCOPE-030 D9): the School Principal's own notifications -- their school's partnership tier changing. Same
// feed as the Coordinator page, keyed on the signed-in user, never a client-supplied id. Principal-only.
export default async function SchoolPrincipalNotificationsPage() {
  let user: User;
  let notifications: NotificationItem[];
  try {
    user = await serverApi<User>("/api/v1/auth/me");
    if (user.role !== "school_principal") return accessDenied(user, "School Principal role required");
    notifications = await serverApi<NotificationItem[]>("/api/v1/workflows/notifications");
  } catch (e) {
    return accessUnavailable(e);
  }
  return (
    <PortalShell nav={SCHOOL_NAV.principal} roleLabel="Principal" userName={user.full_name}>
      <div className="portal-content">
        <h1>Notifications</h1>
        <div className="card">
          <SchoolNotificationList notifications={notifications} emptyText="No notifications yet. You will be told here when your school's partnership changes." />
        </div>
      </div>
    </PortalShell>
  );
}
