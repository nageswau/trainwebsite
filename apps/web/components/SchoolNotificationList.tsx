import { formatDate } from "@/lib/formatDate";

// The signed-in user's own in-app notifications, as the Parent page already shows them (same table, same "new" badge in text, same Open
// link). ENH-005 uses it for the School Coordinator: they are told when a transfer they filed is decided and when a student joins their
// school, and until this existed no coordinator screen could show those notices. The Parent page is deliberately left as it was.
export type NotificationItem = { id: string; title: string; body: string; read: boolean; action_url: string | null; created_at: string };

export default function SchoolNotificationList({ notifications, emptyText }: { notifications: NotificationItem[]; emptyText: string }) {
  if (notifications.length === 0) return <p className="muted">{emptyText}</p>;
  return (
    <div className="table-wrap">
      <table className="table">
        <thead><tr><th>When</th><th>Notification</th><th></th></tr></thead>
        <tbody>
          {notifications.map((n) => (
            <tr key={n.id}>
              <td>{formatDate(n.created_at, true)}</td>
              <td><strong>{n.title}</strong>{!n.read && <> <span className="badge">new</span></>}<br />{n.body}</td>
              <td>{n.action_url && <a className="btn secondary small" href={n.action_url}>Open</a>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
