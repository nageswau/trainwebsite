"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { SESSION_EXPIRED, SIGN_IN_PATH } from "@/lib/activityFeedback";
import { stageLabel } from "@/lib/agentApplications";
import { kindLabel, timelineUrl, type TimelineItem } from "@/lib/agentJourney";
import { isPage, type Page } from "@/lib/apiErrors";
import { formatDate, viewerTimeZone } from "@/lib/formatDate";

const PAGE_SIZE = 20;
const UNABLE = "Unable to load history.";

type Failure = { text: string; expired: boolean };

class LoadFailed extends Error {
  constructor(text: string, readonly expired = false) {
    super(text);
  }
}

function summary(item: TimelineItem): string {
  const parts = [kindLabel(item.kind), item.application?.university, item.document?.type].filter(Boolean);
  if (item.from_status && item.to_status) parts.push(`${stageLabel(item.from_status)} → ${stageLabel(item.to_status)}`);
  return parts.join(" · ");
}

// AGN-015 (DEC-SCOPE-060 §3, §7): the student's complete history, newest first -- the AGN-021 activity pattern. Hidden until asked
// for, so opening a student costs one request (the journey), not two. Read on every open / page / Refresh (no cache); only the
// newest request may update the screen.
export default function AgentStudentTimeline({ studentId }: { studentId: string }) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<Page<TimelineItem> | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [loading, setLoading] = useState(false);
  const [offset, setOffset] = useState(0);
  const latest = useRef(0);
  const panelId = `history-${studentId}`;

  const load = useCallback(
    (at: number) => {
      const request = ++latest.current;
      setLoading(true);
      setFailure(null);
      fetch(timelineUrl(studentId, PAGE_SIZE, at))
        .then(async (response) => {
          if (response.status === 401) throw new LoadFailed(SESSION_EXPIRED, true);
          const body: unknown = await response.json().catch(() => null);
          if (!response.ok || !isPage<TimelineItem>(body)) throw new LoadFailed(UNABLE);
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
    [studentId],
  );

  useEffect(() => {
    if (open) load(offset);
  }, [open, load, offset]);

  return (
    <div style={{ marginTop: 16 }}>
      <button type="button" className="btn secondary small" aria-expanded={open} aria-controls={panelId} onClick={() => setOpen(!open)}>
        {open ? "Hide history" : "Show history"}
      </button>
      {open && (
        <div id={panelId} style={{ marginTop: 8 }}>
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
            <p className="muted" role="status">Loading history…</p>
          ) : data.items.length === 0 ? (
            <p className="muted">No history yet.</p>
          ) : (
            <>
              {loading && <p className="muted" role="status" style={{ fontSize: 13, margin: "0 0 4px" }}>Updating history…</p>}
              <ol aria-label="Student history" aria-busy={loading} style={{ paddingLeft: 18, margin: "4px 0", opacity: loading ? 0.6 : 1 }}>
                {data.items.map((item) => (
                  <li key={item.id} style={{ fontSize: 13, marginBottom: 6, overflowWrap: "anywhere" }}>
                    <strong>{summary(item)}</strong>
                    {item.fields && item.fields.length > 0 ? ` — ${item.fields.map((f) => f.replaceAll("_", " ")).join(", ")}` : ""}
                    {` · ${item.actor} `}
                    <span className="muted"><time dateTime={item.at}>{formatDate(item.at, true, viewerTimeZone())}</time></span>
                    {item.notes && <span className="history-note" style={{ display: "block" }}>{item.notes}</span>}
                  </li>
                ))}
              </ol>
            </>
          )}
          {data && !failure && data.total > PAGE_SIZE && (
            <nav aria-label="History pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, margin: "4px 0" }}>
              <span className="muted" style={{ fontSize: 13 }}>Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}</span>
              <button type="button" className="btn secondary small" aria-label="Previous page" disabled={loading || offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Previous</button>
              <button type="button" className="btn secondary small" aria-label="Next page" disabled={loading || offset + PAGE_SIZE >= data.total} onClick={() => setOffset(offset + PAGE_SIZE)}>Next</button>
            </nav>
          )}
          {data && !failure && <button type="button" className="btn secondary small" onClick={() => load(offset)}>Refresh</button>}
        </div>
      )}
    </div>
  );
}
