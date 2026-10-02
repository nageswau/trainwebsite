"use client";

import LocalTime from "./LocalTime";
import { formatDate, SCHOOL_TIME_ZONE } from "@/lib/formatDate";

// The signed-in user's own in-app notifications, as the Parent page already shows them (same table, same "new" badge in text, same Open
// link). ENH-005 uses it for the School Coordinator: they are told when a transfer they filed is decided and when a student joins their
// school, and until this existed no coordinator screen could show those notices. The Parent page is deliberately left as it was.
// It is a list, not a table (AC-24: the new screens render no table), in the same `.link-list` rows the transfers screen uses, so it also
// stacks on a phone without a scroll container.
export type NotificationItem = { id: string; title: string; body: string; read: boolean; action_url: string | null; created_at: string };

// AGN-017: `localTime` -- the agency page shows each time in the viewer's zone (LocalTime, hydration-safe); school pages keep the school zone.
export default function SchoolNotificationList({ notifications, emptyText, localTime = false }: { notifications: NotificationItem[]; emptyText: string; localTime?: boolean }) {
  if (notifications.length === 0) return <p className="muted">{emptyText}</p>;
  return (
    <ul className="link-list" role="list" aria-label="Notifications">
      {notifications.map((n) => (
        <li key={n.id}>
          <div className="who">
            <strong>{n.title}{!n.read && <> <span className="badge">new</span></>}</strong>
            <span>{n.body}</span>
            <span className="muted">{localTime ? <LocalTime value={n.created_at} time /> : formatDate(n.created_at, true, SCHOOL_TIME_ZONE)}</span>
          </div>
          {n.action_url && (
            <div className="meta">
              {/* QA-023-06: named after the notice so links are distinguishable, and opening an unread notice marks it read.
                  keepalive lets the request finish while the browser follows the link; a failure never blocks navigation. */}
              <a
                className="btn secondary small"
                href={n.action_url}
                aria-label={`Open: ${n.title}`}
                onClick={() => {
                  if (!n.read) void fetch(`/api/v1/workflows/notifications/${n.id}/read`, { method: "PATCH", keepalive: true }).catch(() => undefined);
                }}
              >
                Open
              </a>
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}
