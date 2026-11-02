"use client";

import { type FormEvent, useCallback, useEffect, useId, useState } from "react";

import { sendJson, sendRequest } from "@/lib/apiErrors";
import { addDays, byDay, dayLabel, mondayOf, type Occurrence, slotsUrl, TIMETABLE_API, type TimetableFeed, timeRange, todayIst } from "@/lib/timetable";

/** itc-020 (DEC-SCOPE-342): one week of classes, grouped by day, for every IT role. The API scopes what each role sees (a student never
 *  sees a cancelled class; a counselor gets no join link). When the API says `can_edit`, a future class can be cancelled with a reason.
 *  `batchId` narrows the week to one batch; `refreshKey` reloads it after the admin edits the timetable. */
export default function TimetableCalendar({ batchId, refreshKey = 0 }: { batchId?: string; refreshKey?: number }) {
  const today = todayIst();
  const [week, setWeek] = useState(() => mondayOf(today));
  const [feed, setFeed] = useState<TimetableFeed | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [reload, setReload] = useState(0);
  const id = useId();

  const load = useCallback(async (signal: { cancelled: boolean }) => {
    setLoading(true);
    setError("");
    const params = new URLSearchParams({ from: week, to: addDays(week, 6), ...(batchId ? { batch_id: batchId } : {}) });
    const outcome = await sendRequest(`${TIMETABLE_API}?${params}`, { method: "GET" });
    if (signal.cancelled) return;
    setLoading(false);
    const data = outcome.ok ? (outcome.data as TimetableFeed) : null;
    // browser QA-03: a server failure gets our own words; a refusal (403/404/422) keeps the API's.
    if (!data || !Array.isArray(data.items)) return setError(outcome.ok || (outcome.status ?? 0) >= 500 ? "Unable to load the timetable." : outcome.message);
    setFeed(data);
  }, [week, batchId]);

  useEffect(() => {
    const signal = { cancelled: false };
    void load(signal);
    return () => {
      signal.cancelled = true;
    };
  }, [load, refreshKey, reload]);

  const days = feed ? byDay(feed.items) : [];
  const heading = `Week of ${dayLabel(week)}`;
  return (
    <section aria-labelledby={`${id}-week`} className="card" style={{ display: "grid", gap: 12 }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}>
        <h3 id={`${id}-week`} style={{ margin: 0, fontSize: 18 }}>{heading}</h3>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }} role="group" aria-label="Choose a week">
          <button type="button" className="btn secondary small" onClick={() => setWeek(addDays(week, -7))}>Previous week</button>
          <button type="button" className="btn secondary small" onClick={() => setWeek(mondayOf(today))} disabled={week === mondayOf(today)}>This week</button>
          <button type="button" className="btn secondary small" onClick={() => setWeek(addDays(week, 7))}>Next week</button>
        </div>
      </div>
      <p className="muted" style={{ margin: 0, fontSize: 13 }}>Times are in India time (IST).</p>
      <div aria-live="polite" aria-busy={loading}>
        {loading && !feed && <p className="muted">Loading classes…</p>}
        {error && (
          <div role="alert" style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
            <p className="form-error" style={{ margin: 0 }}>{error}</p>
            <button type="button" className="btn secondary small" onClick={() => setReload((n) => n + 1)}>Try again</button>
          </div>
        )}
        {!error && feed && !days.length && <p className="muted">{loading ? "Loading classes…" : "No classes this week."}</p>}
        {!error && days.map(({ date, items }) => (
          <div key={date} style={{ marginTop: 12 }}>
            <h4 style={{ margin: "0 0 6px", fontSize: 15 }}>
              {dayLabel(date)}
              {date === today && <span className="badge" style={{ marginLeft: 8 }}>Today</span>}
            </h4>
            <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 8 }}>
              {items.map((item) => (
                <ClassRow key={item.id} item={item} cancellable={!!feed?.can_edit && item.kind === "class" && item.status === "scheduled" && date >= today}
                  onCancelled={() => setReload((n) => n + 1)} />
              ))}
            </ul>
          </div>
        ))}
      </div>
    </section>
  );
}

function ClassRow({ item, cancellable, onCancelled }: { item: Occurrence; cancellable: boolean; onCancelled: () => void }) {
  const cancelled = item.status === "cancelled";
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const id = useId();

  async function cancel(event: FormEvent) {
    event.preventDefault();
    if (reason.trim().length < 3) return setError("Give a reason of at least 3 characters.");
    setBusy(true);
    setError("");
    const outcome = await sendJson(`${slotsUrl(item.batch_id)}/${item.slot_id}/cancellations`, "POST", { occurs_on: item.date, reason: reason.trim() });
    setBusy(false);
    if (!outcome.ok) return setError(outcome.message);
    setOpen(false);
    onCancelled();
  }

  const title = item.topic || item.program;
  return (
    <li className="action-card" style={{ display: "grid", gap: 4, opacity: cancelled ? 0.75 : 1 }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline", justifyContent: "space-between" }}>
        <strong style={{ textDecoration: cancelled ? "line-through" : undefined }}>{timeRange(item)}</strong>
        <span className="muted" style={{ fontSize: 13 }}>{item.batch} · {item.program}</span>
      </div>
      <div style={{ overflowWrap: "anywhere" }}>{title}{item.kind === "live_session" && <span className="muted"> (live session)</span>}</div>
      {cancelled ? (
        <p className="form-error" style={{ margin: 0, fontSize: 13 }}>Cancelled{item.cancel_reason ? `: ${item.cancel_reason}` : ""}</p>
      ) : (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", fontSize: 14 }}>
          {item.mode === "offline" ? <span>In person · {item.room}</span> : <span>Online{item.room ? ` · ${item.room}` : ""}</span>}
          {item.meeting_url && (
            <a className="btn small" href={item.meeting_url} target="_blank" rel="noopener noreferrer" aria-label={`Join ${title} on ${dayLabel(item.date)}`}>Join class</a>
          )}
          {cancellable && !open && (
            <button type="button" className="btn secondary small" aria-label={`Cancel ${title} on ${dayLabel(item.date)}`} onClick={() => setOpen(true)}>Cancel class</button>
          )}
        </div>
      )}
      {open && (
        <form onSubmit={cancel} noValidate style={{ display: "grid", gap: 6 }}>
          <div className="field" style={{ margin: 0 }}>
            <label htmlFor={`${id}-reason`}>Reason for cancelling (students are notified)</label>
            <textarea id={`${id}-reason`} rows={2} maxLength={500} value={reason} disabled={busy} autoFocus onChange={(e) => setReason(e.target.value)} />
          </div>
          {error && <p className="form-error" role="alert" style={{ margin: 0, fontSize: 13 }}>{error}</p>}
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            <button type="submit" className="btn small" disabled={busy}>{busy ? "Cancelling…" : "Confirm cancellation"}</button>
            <button type="button" className="btn secondary small" disabled={busy} onClick={() => { setOpen(false); setError(""); setReason(""); }}>Keep class</button>
          </div>
        </form>
      )}
    </li>
  );
}
