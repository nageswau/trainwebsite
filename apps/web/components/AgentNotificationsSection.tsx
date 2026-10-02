import SchoolNotificationList, { type NotificationItem } from "./SchoolNotificationList";
import SectionUnavailable from "./SectionUnavailable";
import type { User } from "@/lib/types";

// AGN-017 (DEC-SCOPE-059 N8, spec §9): the agency Notifications page -- the signed-in member's own notices (assignments, document
// requests and rejections, status changes, new tasks, deadline reminders). PortalPage fetches the list beside the page payload and the
// unread count; `items` is null when that list failed (a 401 never reaches here: PortalPage shows the access-unavailable card).
const EMPTY = "No notifications yet. You'll be told here about assignments, document requests, status changes, new tasks and upcoming deadlines.";
const WINDOW = 100; // GET /workflows/notifications returns the newest 100

export default function AgentNotificationsSection({ user, items }: { user: User; items: NotificationItem[] | null }) {
  const member = user.role === "agent";
  return (
    <div className="portal-content">
      <div className="portal-title">
        <div>
          <div className="eyebrow">Workspace</div>
          <h1>Notifications</h1>
          <p className="muted">
            {member
              ? "Assignments, document requests, status changes, new tasks and deadline reminders for your students."
              : "Agency notifications go to the agency's own Masters and Staff."}
          </p>
        </div>
      </div>
      {member &&
        (items === null ? (
          <SectionUnavailable title="Notifications" />
        ) : (
          <div className="card">
            <SchoolNotificationList notifications={items} emptyText={EMPTY} localTime readBeforeOpen />
            {items.length >= WINDOW && <p className="muted">Showing your latest {WINDOW} notifications.</p>}
          </div>
        ))}
    </div>
  );
}
