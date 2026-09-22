import PortalShell from "@/components/PortalShell";
import SchoolNotificationList, { type NotificationItem } from "@/components/SchoolNotificationList";
import { ApiError, serverApi } from "@/lib/api";
import { SCHOOL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";
import { accessUnavailable } from "@/components/AccessUnavailable";

// ENH-005: the School Coordinator's own notifications -- a transfer request they filed was decided, or a student has joined their school.
// The feed endpoint is keyed on the signed-in user, never a client-supplied id. Coordinator-only, like the rest of this section.
export default async function SchoolCoordinatorNotificationsPage() {
  let user: User;
  let notifications: NotificationItem[];
  try {
    user = await serverApi<User>("/api/v1/auth/me");
    if (user.role !== "school_coordinator") return accessUnavailable(new ApiError("School Coordinator role required", 403));
    notifications = await serverApi<NotificationItem[]>("/api/v1/workflows/notifications");
  } catch (e) {
    return accessUnavailable(e);
  }
  return (
    <PortalShell nav={SCHOOL_NAV.coordinator} roleLabel="School Coordinator" userName={user.full_name}>
      <div className="portal-content">
        <h1>Notifications</h1>
        <div className="card">
          <SchoolNotificationList notifications={notifications} emptyText="No notifications yet. You will be told here when a transfer request is decided, or a student joins your school." />
        </div>
      </div>
    </PortalShell>
  );
}
