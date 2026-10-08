"use client";
import { useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import RecruiterMeetingItem from "@/components/RecruiterMeetingItem";
import { isMeetingListPage, isView, LIST_LIMIT, meetingsUrl, type MeetingListPage, type MeetingView, type RecMeeting, VIEW_TABS } from "@/lib/recruiterMeetings";
import { pageOffset } from "@/lib/telecaller";
import { getPage } from "@/lib/telecallerCatalogue";

const EMPTY: Record<MeetingView, string> = {
  upcoming: "No upcoming meetings.", awaiting_outcome: "No meetings are waiting for an outcome.", completed: "No completed meetings yet.",
  cancelled: "No cancelled meetings.",
};

/** rec-028 (spec §4; MT10): the caller's meetings -- Upcoming (soonest first), Awaiting outcome (started, no outcome yet), Completed and
 *  Cancelled. The tab and page live in the URL, so refresh keeps the place. The API scopes the rows and decides every action. */
export default function RecruiterMeetingsPanel() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const raw = params.get("view");
  const view: MeetingView = isView(raw) ? raw : "upcoming";
  const offset = pageOffset(params.get("offset") ?? undefined);
  const requestUrl = meetingsUrl(view, offset);
  const [data, setData] = useState<MeetingListPage | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const [notice, setNotice] = useState<{ text: string; failed: boolean } | null>(null);
  const reload = () => setVersion((n) => n + 1);

  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    getPage<RecMeeting>(requestUrl, controller.signal)
      .then((body) => {
        if (!isMeetingListPage(body)) throw new Error("Meetings without counts");
        setData(body);
      })
      .catch(() => controller.signal.aborted || setFailed(true));
    return () => controller.abort();
  }, [requestUrl, version]);

  function go(nextView: MeetingView, nextOffset = 0) {
    const next = new URLSearchParams();
    if (nextView !== "upcoming") next.set("view", nextView);
    if (nextOffset > 0) next.set("offset", String(nextOffset));
    setNotice(null);
    router.push(next.size ? `${pathname}?${next}` : pathname, { scroll: false });
  }

  return (
    <div className="action-card" aria-busy={data === null && !failed}>
      <nav aria-label="Meeting lists" style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {VIEW_TABS.map(([key, label]) => {
          const n = data?.counts[key];
          return (
            <button key={key} type="button" aria-current={view === key ? "page" : undefined} className={`btn small${view === key ? "" : " secondary"}`} onClick={() => go(key)}>
              {label}{n === undefined ? "" : ` (${n})`}
            </button>
          );
        })}
      </nav>
      <div role="status" aria-live="polite">
        {notice && <p className={notice.failed ? "form-error" : "form-message"} style={{ margin: "8px 0 0" }}>{notice.text}</p>}
      </div>
      {failed ? (
        <div style={{ marginTop: 12 }}>
          <p className="form-error" role="alert">Unable to load meetings.</p>
          <button type="button" className="btn secondary small" onClick={reload}>Retry</button>
        </div>
      ) : data === null ? (
        <p className="muted" role="status" style={{ marginTop: 12 }}>Loading meetings…</p>
      ) : data.items.length === 0 ? (
        <p className="muted" style={{ marginTop: 12 }}>{EMPTY[view]}</p>
      ) : (
        <>
          <ul aria-label="Meetings" style={{ padding: 0, margin: "12px 0 0", display: "grid", gap: 8 }}>
            {data.items.map((m) => (
              <RecruiterMeetingItem key={m.id} meeting={m} card onChanged={(_, text) => { setNotice({ text, failed: false }); reload(); }}
                onRefused={(text) => { setNotice({ text, failed: true }); reload(); }} />
            ))}
          </ul>
          {data.total > LIST_LIMIT && (
            <nav aria-label="Meeting pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
              <span className="muted" style={{ fontSize: 13 }}>Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}</span>
              <button type="button" className="btn secondary small" aria-label="Previous page" disabled={offset === 0} onClick={() => go(view, Math.max(0, offset - LIST_LIMIT))}>Previous</button>
              <button type="button" className="btn secondary small" aria-label="Next page" disabled={data.offset + data.items.length >= data.total} onClick={() => go(view, offset + LIST_LIMIT)}>Next</button>
            </nav>
          )}
        </>
      )}
    </div>
  );
}
