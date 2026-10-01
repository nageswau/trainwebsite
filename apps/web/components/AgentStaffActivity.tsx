"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { SESSION_EXPIRED, SIGN_IN_PATH } from "@/lib/activityFeedback";
import { activityLabel, STAFF_URL, type StaffActivityItem, type StaffMember } from "@/lib/agentStaff";
import { isPage, type Page } from "@/lib/apiErrors";
import { formatDate, viewerTimeZone } from "@/lib/formatDate";

const ACTIVITY_PAGE_SIZE = 10;
const UNABLE = "Unable to load activity.";

// Why the list could not be shown. Browser QA-03: an expired session (401) is not retryable -- it offers sign-in instead (the
// app's LoadFailureAlert convention).
type Failure = { text: string; expired: boolean };

class LoadFailed extends Error {
  constructor(text: string, readonly expired = false) {
    super(text);
  }
}

// AGN-021 (DEC-SCOPE-046 A1-A4): a staff member's student-journey work, shown inside their row on the Team page. Read on every
// open / page / Refresh (no cache), so a new action shows on the next load. Only the newest request may update the screen.
export default function AgentStaffActivity({ member, onClose }: { member: StaffMember; onClose: () => void }) {
  const [data, setData] = useState<Page<StaffActivityItem> | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [loading, setLoading] = useState(true);
  const [offset, setOffset] = useState(0);
  const latest = useRef(0);
  const heading = useRef<HTMLHeadingElement>(null);
  const headingId = `staff-activity-${member.id}`;

  // Browser QA-04: start keyboard and screen-reader users at the top of the view (the heading), not on its last button, so Tab
  // goes on to the list's controls and Escape still closes it.
  useEffect(() => heading.current?.focus(), []);

  const load = useCallback(
    (at: number) => {
      const request = ++latest.current;
      setLoading(true);
      setFailure(null);
      fetch(`${STAFF_URL}/${member.id}/activity?limit=${ACTIVITY_PAGE_SIZE}&offset=${at}`)
        .then(async (response) => {
          if (response.status === 401) throw new LoadFailed(SESSION_EXPIRED, true);
          const body: unknown = await response.json().catch(() => null);
          if (!response.ok) {
            const detail = (body as { detail?: unknown } | null)?.detail;
            throw new LoadFailed(response.status < 500 && typeof detail === "string" ? detail : UNABLE);
          }
          if (!isPage<StaffActivityItem>(body)) throw new LoadFailed(UNABLE);
          if (request === latest.current) setData(body);
        })
        .catch((caught: unknown) => {
          if (request !== latest.current) return;
          // A dropped connection (TypeError) or anything unexpected reads as the generic message.
          setFailure(caught instanceof LoadFailed ? { text: caught.message, expired: caught.expired } : { text: UNABLE, expired: false });
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
      <h4 id={headingId} ref={heading} tabIndex={-1} style={{ margin: "0 0 4px" }}>Activity</h4>
      {failure ? (
        failure.expired ? (
          <p className="form-error" role="alert">{failure.text} <Link href={SIGN_IN_PATH}>Sign in again</Link></p>
        ) : (
          <>
            <p className="form-error" role="alert">{failure.text}</p>
            <button type="button" className="btn secondary small" onClick={() => load(offset)}>Try again</button>
          </>
        )
      ) : data === null ? (
        <p className="muted" role="status">Loading activity…</p>
      ) : data.items.length === 0 ? (
        <p className="muted">No activity yet.</p>
      ) : (
        <>
          {/* Browser QA-02: a visible cue (not only aria-busy) while a newer page or a Refresh loads over the current one. */}
          {loading && <p className="muted" role="status" style={{ fontSize: 13, margin: "0 0 4px" }}>Updating activity…</p>}
          <ol aria-label={`Activity of ${member.code}`} aria-busy={loading} style={{ paddingLeft: 18, margin: "4px 0", opacity: loading ? 0.6 : 1 }}>
            {data.items.map((item) => (
              <li key={item.id} style={{ fontSize: 13, marginBottom: 4, overflowWrap: "anywhere" }}>
                <strong>{activityLabel(item.action)}</strong> · {item.subject}
                {item.fields && item.fields.length > 0 ? ` — ${item.fields.map((f) => f.replaceAll("_", " ")).join(", ")}` : ""}{" "}
                <span className="muted"><time dateTime={item.at}>{formatDate(item.at, true, viewerTimeZone())}</time></span>
              </li>
            ))}
          </ol>
        </>
      )}
      {data && !failure && data.total > ACTIVITY_PAGE_SIZE && (
        <nav aria-label="Activity pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, margin: "4px 0" }}>
          <span className="muted" style={{ fontSize: 13 }}>Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}</span>
          <button type="button" className="btn secondary small" aria-label="Previous page" disabled={loading || offset === 0} onClick={() => setOffset(Math.max(0, offset - ACTIVITY_PAGE_SIZE))}>Previous</button>
          <button type="button" className="btn secondary small" aria-label="Next page" disabled={loading || offset + ACTIVITY_PAGE_SIZE >= data.total} onClick={() => setOffset(offset + ACTIVITY_PAGE_SIZE)}>Next</button>
        </nav>
      )}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 4 }}>
        {/* Browser QA-01: an error state has one retry action (Try again above); an expired session has none (QA-03). */}
        {!failure && <button type="button" className="btn secondary small" onClick={() => load(offset)}>Refresh</button>}
        <button type="button" className="btn secondary small" aria-label="Close activity" onClick={onClose}>Close</button>
      </div>
    </section>
  );
}
