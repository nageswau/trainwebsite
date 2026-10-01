"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { activityLabel, STAFF_URL, type StaffActivityItem, type StaffMember } from "@/lib/agentStaff";
import { isPage, type Page } from "@/lib/apiErrors";
import { formatDate } from "@/lib/formatDate";

export const ACTIVITY_PAGE_SIZE = 10;
const UNABLE = "Unable to load activity.";

class Refused extends Error {}

// AGN-021 (DEC-SCOPE-045 A1-A4): a staff member's student-journey work, shown inside their row on the Team page. Read on every
// open / page / Refresh (no cache), so a new action shows on the next load. Only the newest request may update the screen.
export default function AgentStaffActivity({ member, onClose }: { member: StaffMember; onClose: () => void }) {
  const [data, setData] = useState<Page<StaffActivityItem> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [offset, setOffset] = useState(0);
  const latest = useRef(0);
  const headingId = `staff-activity-${member.id}`;

  const load = useCallback(
    (at: number) => {
      const request = ++latest.current;
      setLoading(true);
      setError(null);
      fetch(`${STAFF_URL}/${member.id}/activity?limit=${ACTIVITY_PAGE_SIZE}&offset=${at}`)
        .then(async (response) => {
          const body: unknown = await response.json().catch(() => null);
          if (!response.ok) {
            const detail = (body as { detail?: unknown } | null)?.detail;
            throw new Refused(response.status < 500 && typeof detail === "string" ? detail : UNABLE);
          }
          if (!isPage<StaffActivityItem>(body)) throw new Refused(UNABLE);
          if (request === latest.current) setData(body);
        })
        .catch((failure: unknown) => {
          if (request === latest.current) setError(failure instanceof Refused ? failure.message : UNABLE);
        })
        .finally(() => {
          if (request === latest.current) setLoading(false);
        });
    },
    [member.id],
  );

  useEffect(() => {
    load(offset);
  }, [load, offset]);

  return (
    <section aria-labelledby={headingId} style={{ marginTop: 8 }} onKeyDown={(event) => event.key === "Escape" && onClose()}>
      <h4 id={headingId} style={{ margin: "0 0 4px" }}>Activity</h4>
      {error ? (
        <>
          <p className="form-error" role="alert">{error}</p>
          <button type="button" className="btn secondary small" onClick={() => load(offset)}>Try again</button>
        </>
      ) : data === null ? (
        <p className="muted" role="status">Loading activity…</p>
      ) : data.items.length === 0 ? (
        <p className="muted">No activity yet.</p>
      ) : (
        <ol aria-label={`Activity of ${member.code}`} aria-busy={loading} style={{ paddingLeft: 18, margin: "4px 0" }}>
          {data.items.map((item) => (
            <li key={item.id} style={{ fontSize: 13, marginBottom: 4, overflowWrap: "anywhere" }}>
              <strong>{activityLabel(item.action)}</strong> · {item.subject}
              {item.fields && item.fields.length > 0 ? ` — ${item.fields.map((f) => f.replaceAll("_", " ")).join(", ")}` : ""}{" "}
              <span className="muted"><time dateTime={item.at}>{formatDate(item.at, true)}</time></span>
            </li>
          ))}
        </ol>
      )}
      {data && !error && data.total > ACTIVITY_PAGE_SIZE && (
        <nav aria-label="Activity pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, margin: "4px 0" }}>
          <span className="muted" style={{ fontSize: 13 }}>Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}</span>
          <button type="button" className="btn secondary small" aria-label="Previous page" disabled={loading || offset === 0} onClick={() => setOffset(Math.max(0, offset - ACTIVITY_PAGE_SIZE))}>Previous</button>
          <button type="button" className="btn secondary small" aria-label="Next page" disabled={loading || offset + ACTIVITY_PAGE_SIZE >= data.total} onClick={() => setOffset(offset + ACTIVITY_PAGE_SIZE)}>Next</button>
        </nav>
      )}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 4 }}>
        <button type="button" className="btn secondary small" onClick={() => load(offset)}>Refresh</button>
        <button type="button" className="btn secondary small" aria-label="Close activity" autoFocus onClick={onClose}>Close</button>
      </div>
    </section>
  );
}
