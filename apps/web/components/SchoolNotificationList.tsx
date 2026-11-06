"use client";

import { useId, useState } from "react";

import LocalTime from "./LocalTime";
import { formatDate, SCHOOL_TIME_ZONE } from "@/lib/formatDate";

// The signed-in user's own in-app notifications, as the Parent page already shows them (same table, same "new" badge in text, same Open
// link). ENH-005 uses it for the School Coordinator: they are told when a transfer they filed is decided and when a student joins their
// school, and until this existed no coordinator screen could show those notices. The Parent page is deliberately left as it was.
// It is a list, not a table (AC-24: the new screens render no table), in the same `.link-list` rows the transfers screen uses, so it also
// stacks on a phone without a scroll container.
// itc-002 (DEC-SCOPE-336): a catalogued notice also names its event type and the record it is about (null on older notices).
export type NotificationItem = {
  id: string; title: string; body: string; read: boolean; action_url: string | null; created_at: string;
  event_type?: string | null; entity_type?: string | null; entity_id?: string | null;
};

const READ_WAIT_MS = 1500;

function markRead(id: string, keepalive: boolean): Promise<unknown> {
  return fetch(`/api/v1/workflows/notifications/${id}/read`, { method: "PATCH", keepalive }).catch(() => undefined);
}

// AGN-017: `localTime` -- the agency page shows each time in the viewer's zone (LocalTime, hydration-safe); school pages keep the school zone.
// `readBeforeOpen` (QA17-01) -- a plain click on an unread notice waits for its read (at most READ_WAIT_MS, failure or not) before
// navigating, so the next page's unread badge already counts it; a modified click (new tab, new window) is left to the browser.
export default function SchoolNotificationList({
  notifications,
  emptyText,
  localTime = false,
  readBeforeOpen = false,
  typeByTitle = false,
}: {
  notifications: NotificationItem[];
  emptyText: string;
  localTime?: boolean;
  readBeforeOpen?: boolean;
  typeByTitle?: boolean; // hrc-031 (DEC-SCOPE-412 P8): an untyped notice's fixed title is its type, so the portals' recruitment notices filter too
}) {
  const filterId = useId();
  const [type, setType] = useState("");
  if (notifications.length === 0) return <p className="muted">{emptyText}</p>;
  // itc-002: the Type filter appears only once a typed notice is present; a type's title is fixed by the catalogue, so it names the option.
  const types = new Map<string, string>();
  const typeOf = (n: NotificationItem) => n.event_type ?? (typeByTitle ? n.title : null);
  for (const n of notifications) {
    const key = typeOf(n);
    if (key && !types.has(key)) types.set(key, n.title);
  }
  const shown = type ? notifications.filter((n) => typeOf(n) === type) : notifications;
  return (
    <>
    {types.size > 0 && (
      <form className="form filter-bar" aria-label="Filter notifications" onSubmit={(event) => event.preventDefault()} style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "end", marginBottom: 12 }}>
        <div className="field">
          <label htmlFor={filterId}>Type</label>
          <select id={filterId} value={type} onChange={(event) => setType(event.target.value)}>
            <option value="">All</option>
            {[...types].sort((a, b) => a[1].localeCompare(b[1])).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
          </select>
        </div>
        {type && <p className="muted" role="status">Showing {shown.length} of {notifications.length}</p>}
      </form>
    )}
    <ul className="link-list" role="list" aria-label="Notifications">
      {shown.map((n) => (
        <li key={n.id}>
          <div className="who">
            <strong>{n.title}{!n.read && <> <span className="badge">new</span></>}</strong>
            <span id={`notice-${n.id}-body`}>{n.body}</span>
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
                aria-describedby={`notice-${n.id}-body`} // QA17-03: notices sharing a title stay distinguishable
                onClick={(e) => {
                  if (n.read) return;
                  const plain = e.button === 0 && !(e.metaKey || e.ctrlKey || e.shiftKey || e.altKey);
                  if (!readBeforeOpen || !plain) {
                    void markRead(n.id, true);
                    return;
                  }
                  e.preventDefault();
                  const href = n.action_url as string;
                  void Promise.race([markRead(n.id, false), new Promise((resolve) => setTimeout(resolve, READ_WAIT_MS))]).then(() => window.location.assign(href));
                }}
              >
                Open
              </a>
            </div>
          )}
        </li>
      ))}
    </ul>
    </>
  );
}
