"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import ActivityFeedbackDetails from "@/components/ActivityFeedbackDetails";
import ActivityFeedbackForm from "@/components/ActivityFeedbackForm";
import { type ActivityFeedback, activityTypeLabel, FEEDBACK_FILTERS, type FeedbackActivity, type FeedbackFilter, participationText } from "@/lib/activityFeedback";
import { isPage, type Page } from "@/lib/apiErrors";
import { formatDate } from "@/lib/formatDate";

// ENH-018 (spec §7.1): a school's completed Edusphere activities and their feedback. The first page is server-rendered; the
// filter and "Load more" fetch on the client (the ENH-005 admin-queue pattern). The coordinator opens the form inline under a
// row; the principal (canSubmit=false) only reads. Status is always a text badge, never colour alone.
const LIMIT = 25;
const EMPTY: Record<FeedbackFilter, string> = { all: "No completed Edusphere activities yet.", awaiting: "Nothing awaiting feedback.", submitted: "No feedback submitted yet." };

export default function SchoolActivityFeedbackPanel({ initial, canSubmit }: { initial: Page<FeedbackActivity>; canSubmit: boolean }) {
  const [filter, setFilter] = useState<FeedbackFilter>("all");
  const [items, setItems] = useState(initial.items);
  const [total, setTotal] = useState(initial.total);
  const [loading, setLoading] = useState<"first" | "more" | null>(null);
  const [failed, setFailed] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);
  const messageRef = useRef<HTMLDivElement>(null);
  const alertRef = useRef<HTMLDivElement>(null);
  const triggers = useRef(new Map<string, HTMLButtonElement>());

  const load = useCallback(async (next: FeedbackFilter, offset: number, mode: "first" | "more") => {
    controller.current?.abort();
    const abort = (controller.current = new AbortController());
    setLoading(mode);
    try {
      const response = await fetch(`/api/v1/school/activity-feedback?status=${next}&limit=${LIMIT}&offset=${offset}`, { signal: abort.signal });
      const data = await response.json().catch(() => null);
      if (!response.ok || !isPage<FeedbackActivity>(data)) return setFailed(true);
      setFailed(false);
      setItems((prev) => (mode === "more" ? [...prev, ...data.items] : data.items));
      setTotal(data.total);
    } catch (error) {
      if ((error as Error).name !== "AbortError") setFailed(true);
    } finally {
      if (!abort.signal.aborted) setLoading(null);
    }
  }, []);

  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => {
    if (failed) alertRef.current?.focus();
  }, [failed]);

  function announce(text: string) {
    setMessage(text);
    requestAnimationFrame(() => messageRef.current?.focus());
  }
  function changeFilter(next: FeedbackFilter) {
    setFilter(next);
    setMessage(null);
    setOpenId(null);
    void load(next, 0, "first");
  }
  function onSubmitted(activity: FeedbackActivity, feedback: ActivityFeedback) {
    setOpenId(null);
    if (filter === "awaiting") {
      setItems((prev) => prev.filter((row) => row.activity_id !== activity.activity_id));
      setTotal((t) => Math.max(0, t - 1));
    } else {
      setItems((prev) => prev.map((row) => (row.activity_id === activity.activity_id ? { ...row, feedback } : row)));
    }
    announce(`Feedback saved for ${activity.title}.`);
  }
  function onDuplicate() {
    setOpenId(null);
    announce("Feedback had already been submitted for this activity; showing what was saved.");
    void load(filter, 0, "first");
  }
  function onCancel(activityId: string) {
    setOpenId(null);
    requestAnimationFrame(() => triggers.current.get(activityId)?.focus());
  }

  return (
    <div className="portal-content">
      <div className="card">
        <div className="portal-title">
          <div>
            <h2>Activity feedback</h2>
            <p className="muted">{canSubmit ? "Rate each completed Edusphere activity once. Edusphere uses it to improve the next session." : "Feedback your coordinator recorded after each Edusphere activity."}</p>
          </div>
        </div>
        <div className="table-controls">
          <div>
            <label htmlFor="feedback-filter">Show</label>
            <select id="feedback-filter" className="select" value={filter} disabled={loading !== null} onChange={(e) => changeFilter(e.target.value as FeedbackFilter)}>
              {FEEDBACK_FILTERS.map(([value, text]) => <option key={value} value={value}>{text}</option>)}
            </select>
          </div>
        </div>
        <div ref={messageRef} tabIndex={-1} role="status" aria-live="polite">{message && <div className="form-message">{message}</div>}</div>
        {failed && (
          <div ref={alertRef} tabIndex={-1} className="form-error" role="alert">
            <p style={{ margin: 0 }}>Could not load activity feedback.</p>
            <button type="button" className="btn small secondary" style={{ marginTop: 8 }} onClick={() => void load(filter, 0, "first")}>Try again</button>
          </div>
        )}
        {loading === "first" ? (
          <div aria-busy="true">
            <p className="muted">Loading activity feedback…</p>
            <div className="skeleton-line" aria-hidden="true" />
          </div>
        ) : items.length === 0 && !failed ? (
          <div className="empty">
            <h3>{EMPTY[filter]}</h3>
            {filter === "all" && <p>Feedback opens after a career seminar, career awareness session, parent orientation or campus visit has taken place.</p>}
            {filter === "all" && canSubmit && <Link className="btn secondary small" href="/school/coordinator/activities">Go to Activities</Link>}
          </div>
        ) : items.length > 0 ? (
          <>
            <p className="muted" aria-live="polite">{`Showing ${items.length} of ${total}`}</p>
            <ul className="link-list" role="list" aria-label="Completed Edusphere activities">
              {items.map((row) => (
                <li key={row.activity_id} className="feedback-row">
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "8px 16px", justifyContent: "space-between", alignItems: "center" }}>
                    <div className="who">
                      <strong>{row.title}</strong>
                      <span>{`${activityTypeLabel(row.activity_type)} · ${formatDate(row.scheduled_at, true)} · ${participationText(row.participation)}`}</span>
                    </div>
                    <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
                      <span className="badge">{row.feedback ? "Submitted" : "Awaiting feedback"}</span>
                      {canSubmit && !row.feedback && openId !== row.activity_id && (
                        <button
                          type="button"
                          className="btn small"
                          aria-label={`Give feedback for ${row.title}`}
                          ref={(el) => void (el ? triggers.current.set(row.activity_id, el) : triggers.current.delete(row.activity_id))}
                          onClick={() => {
                            setMessage(null);
                            setOpenId(row.activity_id);
                          }}
                        >
                          Give feedback
                        </button>
                      )}
                    </div>
                  </div>
                  {row.feedback && (
                    <details>
                      <summary>View feedback</summary>
                      <ActivityFeedbackDetails feedback={row.feedback} />
                    </details>
                  )}
                  {openId === row.activity_id && (
                    <ActivityFeedbackForm activity={row} onSubmitted={(feedback) => onSubmitted(row, feedback)} onDuplicate={onDuplicate} onCancel={() => onCancel(row.activity_id)} />
                  )}
                </li>
              ))}
            </ul>
            {items.length < total && (
              <button type="button" className="btn secondary small" disabled={loading !== null} onClick={() => void load(filter, items.length, "more")}>{loading === "more" ? "Loading…" : "Load more"}</button>
            )}
          </>
        ) : null}
      </div>
    </div>
  );
}
