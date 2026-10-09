"use client";
import { useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import RecruiterInterviewItem from "@/components/RecruiterInterviewItem";
import { interviewsUrl, isInterviewListPage, istDay, isView, LIST_LIMIT, type InterviewListPage, type InterviewView, type RecInterview, VIEW_TABS } from "@/lib/recruiterInterviews";
import { pageOffset } from "@/lib/telecaller";
import { getPage } from "@/lib/telecallerCatalogue";

const EMPTY: Record<InterviewView, string> = {
  upcoming: "No upcoming interviews.", awaiting_update: "No interviews are waiting for an update.", on_hold: "No interviews on hold.",
  closed: "No closed interviews yet.",
};

/** Upcoming reads as a calendar: one heading per IST day, the interviews of that day in time order. */
function byDay(items: RecInterview[]): [string, RecInterview[]][] {
  const days = new Map<string, RecInterview[]>();
  for (const item of items) {
    const day = istDay(item.scheduled_at);
    days.set(day, [...(days.get(day) ?? []), item]);
  }
  return [...days];
}

/** rec-020 (spec §4; IV12): the caller's interviews -- Upcoming (soonest first, by day), Awaiting update (the time has passed, or
 *  completed without a decision), On hold and Closed. The tab and page live in the URL, so refresh keeps the place. The API scopes the
 *  rows and decides every action. */
export default function RecruiterInterviewsPanel() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const raw = params.get("view");
  const view: InterviewView = isView(raw) ? raw : "upcoming";
  const offset = pageOffset(params.get("offset") ?? undefined);
  const requestUrl = interviewsUrl(view, offset);
  const [data, setData] = useState<InterviewListPage | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const [notice, setNotice] = useState<string | null>(null);
  const reload = () => setVersion((n) => n + 1);

  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    getPage<RecInterview>(requestUrl, controller.signal)
      .then((body) => {
        if (!isInterviewListPage(body)) throw new Error("Interviews without counts");
        setData(body);
      })
      .catch(() => controller.signal.aborted || setFailed(true));
    return () => controller.abort();
  }, [requestUrl, version]);

  function go(nextView: InterviewView, nextOffset = 0) {
    const next = new URLSearchParams();
    if (nextView !== "upcoming") next.set("view", nextView);
    if (nextOffset > 0) next.set("offset", String(nextOffset));
    setNotice(null);
    router.push(next.size ? `${pathname}?${next}` : pathname, { scroll: false });
  }

  const item = (i: RecInterview) => <RecruiterInterviewItem key={i.id} interview={i} card onChanged={(_, text) => { setNotice(text); reload(); }} />;
  return (
    <div className="action-card" aria-busy={data === null && !failed}>
      <nav aria-label="Interview lists" style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
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
        {notice && <p className="form-message" style={{ margin: "8px 0 0" }}>{notice}</p>}
      </div>
      {failed ? (
        <div style={{ marginTop: 12 }}>
          <p className="form-error" role="alert">Unable to load interviews.</p>
          <button type="button" className="btn secondary small" onClick={reload}>Retry</button>
        </div>
      ) : data === null ? (
        <p className="muted" role="status" style={{ marginTop: 12 }}>Loading interviews…</p>
      ) : data.items.length === 0 ? (
        <p className="muted" style={{ marginTop: 12 }}>{EMPTY[view]}</p>
      ) : (
        <>
          {view === "upcoming" ? (
            byDay(data.items).map(([day, items]) => (
              <section key={day} aria-label={day} style={{ marginTop: 12 }}>
                <h3 style={{ margin: "0 0 6px", fontSize: 15 }}>{day}</h3>
                <ul aria-label={`Interviews on ${day}`} style={{ padding: 0, margin: 0, display: "grid", gap: 8 }}>{items.map(item)}</ul>
              </section>
            ))
          ) : (
            <ul aria-label="Interviews" style={{ padding: 0, margin: "12px 0 0", display: "grid", gap: 8 }}>{data.items.map(item)}</ul>
          )}
          {data.total > LIST_LIMIT && (
            <nav aria-label="Interview pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
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
