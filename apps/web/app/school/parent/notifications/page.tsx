import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { formatSchoolDateTime } from "@/lib/formatDate";
import { SCHOOL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";
import { accessUnavailable } from "@/components/AccessUnavailable";

type NotificationItem = { id: string; title: string; body: string; read: boolean; action_url: string | null; created_at: string };

// SCH-007: the Parent's full notification feed -- assessment assigned / report ready,
// counselling or guidance recorded, session scheduled, result published (NOT-001 in-app
// channel; the email copy goes out alongside each row). Own rows only: the feed endpoint
// is keyed on the signed-in user, never a client-supplied id.
export default async function SchoolParentNotificationsPage() {
  let user: User;
  let notifications: NotificationItem[];
  try {
    [user, notifications] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi<NotificationItem[]>("/api/v1/workflows/notifications")]);
  } catch (e) {
    return accessUnavailable(e);
  }
  return (
    <PortalShell nav={SCHOOL_NAV.parent} roleLabel="Parent" userName={user.full_name}>
      <div className="portal-content">
        <h1>Notifications</h1>
        <div className="card">
          {notifications.length === 0 ? (
            <p className="muted">No notifications yet. You will be notified here when an assessment, counselling session, workshop, or result is recorded for your child.</p>
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>When</th><th>Notification</th><th></th></tr></thead>
                <tbody>
                  {notifications.map((n) => (
                    <tr key={n.id}>
                      <td>{formatSchoolDateTime(n.created_at)}</td>
                      <td><strong>{n.title}</strong>{!n.read && <> <span className="badge">new</span></>}<br />{n.body}</td>
                      <td>{n.action_url && <a className="btn secondary small" href={n.action_url}>Open</a>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </PortalShell>
  );
}
