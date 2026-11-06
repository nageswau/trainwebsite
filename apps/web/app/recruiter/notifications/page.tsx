import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import SchoolNotificationList, { type NotificationItem } from "@/components/SchoolNotificationList";
import { serverApi } from "@/lib/api";
import { companyShell, RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import type { User } from "@/lib/types";

const WINDOW = 100; // GET /workflows/notifications returns the newest 100

// hrc-032 (DEC-SCOPE-412 N11): recruitment staff's own notices, with the shared list's Type filter. Until now they could only be read by email.
export default async function RecruiterNotificationsPage() {
  let user: User;
  let items: NotificationItem[];
  try {
    [user, items] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi<NotificationItem[]>("/api/v1/workflows/notifications")]);
  } catch (e) {
    return accessUnavailable(e, RECRUITER_SIGN_IN);
  }
  const { nav, roleLabel } = companyShell(user.role);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Recruitment</div>
            <h2>Notifications</h2>
            <p className="muted">New applications, vacancy changes, assignments and overdue interview feedback.</p>
          </div>
        </div>
        <div className="card">
          <SchoolNotificationList notifications={items} emptyText="No notifications yet. You'll be told here about new applications, vacancy changes, assignments and overdue feedback." localTime readBeforeOpen />
          {items.length >= WINDOW && <p className="muted">Showing your latest {WINDOW} notifications.</p>}
        </div>
      </div>
    </PortalShell>
  );
}
