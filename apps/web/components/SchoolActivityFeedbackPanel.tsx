"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import ActivityFeedbackDetails from "@/components/ActivityFeedbackDetails";
import ActivityFeedbackForm from "@/components/ActivityFeedbackForm";
import LoadFailureAlert from "@/components/LoadFailureAlert";
import UnsentFeedbackNote from "@/components/UnsentFeedbackNote";
import {
  type ActivityFeedback,
  activityTypeLabel,
  FEEDBACK_FILTERS,
  type FeedbackActivity,
  type FeedbackFilter,
  type LoadFailure,
  participationText,
  type UnsentText,
} from "@/lib/activityFeedback";
import { isPage, type Page } from "@/lib/apiErrors";
import { formatSchoolDateTime } from "@/lib/formatDate";

// ENH-018 (spec §7.1): a school's completed Edusphere activities and their feedback. The first page is server-rendered; the
// filter and "Load more" fetch on the client (the ENH-005 admin-queue pattern). The coordinator opens the form inline under a
// row; the principal (canSubmit=false) only reads. Status is always a text badge, never colour alone.
// Browser QA fixes: a new filter clears the previous rows at once, so a failure can never leave them under the new label
// (QA-018-06); a 401 asks the user to sign in rather than retry (QA-018-14); the filter is never disabled, so keyboard focus
// stays on it -- superseded requests are aborted instead (QA-018-05); "Load more" moves focus to the first new row (QA-018-04);
// `focusActivityId` (from the Activities page's per-row link) shows just that activity, form open if it awaits feedback (QA-018-09).
// The filter lives in the URL (`?status=`), so refresh, back/forward and shared links keep it (QA-018-07). A 409 refreshes only
// that row, in place, and keeps the coordinator's unsent text beside it to copy (QA-018-03).
const LIMIT = 25;
const EMPTY: Record<FeedbackFilter, string> = { all: "No completed Edusphere activities yet.", awaiting: "Nothing awaiting feedback.", submitted: "No feedback submitted yet." };
const ALL_PATH = "/school/coordinator/feedback";
const LIST_API = "/api/v1/school/activity-feedback";

type Props = { initial: Page<FeedbackActivity>; canSubmit: boolean; focusActivityId?: string; initialFilter?: FeedbackFilter };

export default function SchoolActivityFeedbackPanel({ initial, canSubmit, focusActivityId, initialFilter = "all" }: Props) {
  const focusRow = focusActivityId ? initial.items.find((row) => row.activity_id === focusActivityId) : undefined;
  const [focused, setFocused] = useState(Boolean(focusActivityId));
  const [filter, setFilter] = useState<FeedbackFilter>(initialFilter);
  const [unsent, setUnsent] = useState<Record<string, UnsentText>>({});
  const [items, setItems] = useState(initial.items);
  const [total, setTotal] = useState(initial.total);
  const [loading, setLoading] = useState<"first" | "more" | null>(null);
  const [failure, setFailure] = useState<LoadFailure>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(canSubmit && focusRow && !focusRow.feedback ? focusRow.activity_id : null);
  const [focusIndex, setFocusIndex] = useState<number | null>(null);
  const controller = useRef<AbortController | null>(null);
  const messageRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const triggers = useRef(new Map<string, HTMLButtonElement>());

  const load = useCallback(async (next: FeedbackFilter, offset: number, mode: "first" | "more") => {
    controller.current?.abort();
    const abort = (controller.current = new AbortController());
    setLoading(mode);
    setFailure(null);
    if (mode === "first") setItems([]);
    try {
      const response = await fetch(`${LIST_API}?status=${next}&limit=${LIMIT}&offset=${offset}`, { signal: abort.signal });
      const data = await response.json().catch(() => null);
      if (response.status === 401) return setFailure("expired");
      if (!response.ok || !isPage<FeedbackActivity>(data)) return setFailure("failed");
      setItems((prev) => (mode === "more" ? [...prev, ...data.items] : data.items));
      setTotal(data.total);
      if (mode === "more" && data.items.length > 0) setFocusIndex(offset);
    } catch (error) {
      if ((error as Error).name !== "AbortError") setFailure("failed");
    } finally {
      if (!abort.signal.aborted) setLoading(null);
    }
  }, []);

  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => {
    if (focusIndex === null) return;
    (listRef.current?.children[focusIndex] as HTMLElement | undefined)?.focus();
    setFocusIndex(null);
  }, [focusIndex, items]);

  function announce(text: string) {
    setMessage(text);
    requestAnimationFrame(() => messageRef.current?.focus());
  }
  function changeFilter(next: FeedbackFilter) {
    setFilter(next);
    setFocused(false);
    setMessage(null);
    setOpenId(null);
    window.history.replaceState(null, "", next === "all" ? window.location.pathname : `?status=${next}`);
    void load(next, 0, "first");
  }
  /** Re-read one activity after a 409 and swap it in where it is, so the coordinator keeps their place in the list. */
  async function refreshRow(activityId: string) {
    try {
      const response = await fetch(`${LIST_API}?status=all&limit=1&offset=0&activity_id=${activityId}`);
      const data = await response.json().catch(() => null);
      if (response.status === 401) return setFailure("expired");
      const fresh = response.ok && isPage<FeedbackActivity>(data) ? data.items[0] : undefined;
      if (!fresh) return void load(filter, 0, "first");
      setItems((prev) => prev.map((row) => (row.activity_id === activityId ? fresh : row)));
    } catch {
      void load(filter, 0, "first");
    }
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
  function onDuplicate(activity: FeedbackActivity, text: UnsentText) {
    setOpenId(null);
    setUnsent((prev) => ({ ...prev, [activity.activity_id]: text }));
    announce("Feedback had already been submitted for this activity; your text was not saved. You can copy it below.");
    void refreshRow(activity.activity_id);
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
            <select id="feedback-filter" className="select" value={filter} onChange={(e) => changeFilter(e.target.value as FeedbackFilter)}>
              {FEEDBACK_FILTERS.map(([value, text]) => <option key={value} value={value}>{text}</option>)}
            </select>
          </div>
          {focused && (
            <div>
              <Link className="btn secondary small" href={ALL_PATH}>Show all activities</Link>
            </div>
          )}
        </div>
        <div ref={messageRef} tabIndex={-1} role="status" aria-live="polite">{message && <div className="form-message">{message}</div>}</div>
        {failure && <LoadFailureAlert failure={failure} onRetry={() => void load(filter, 0, "first")} />}
        {loading === "first" ? (
          <div aria-busy="true">
            <p className="muted">Loading activity feedback…</p>
            <div className="skeleton-line" aria-hidden="true" />
          </div>
        ) : items.length === 0 && !failure ? (
          focused ? (
            <div className="empty">
              <h3>This activity is not open for feedback.</h3>
              <p>Feedback opens once a career seminar, career awareness session, parent orientation or campus visit has taken place.</p>
            </div>
          ) : (
            <div className="empty">
              <h3>{EMPTY[filter]}</h3>
              {filter === "all" && <p>Feedback opens after a career seminar, career awareness session, parent orientation or campus visit has taken place.</p>}
              {filter === "all" && canSubmit && <Link className="btn secondary small" href="/school/coordinator/activities">Go to Activities</Link>}
            </div>
          )
        ) : items.length > 0 ? (
          <>
            <p className="muted" aria-live="polite">{`Showing ${items.length} of ${total}`}</p>
            <ul ref={listRef} className="link-list" role="list" aria-label="Completed Edusphere activities">
              {items.map((row) => (
                <li key={row.activity_id} className="feedback-row" tabIndex={-1}>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "8px 16px", justifyContent: "space-between", alignItems: "center" }}>
                    <div className="who">
                      <strong>{row.title}</strong>
                      <span>
                        {activityTypeLabel(row.activity_type)} · {formatSchoolDateTime(row.scheduled_at, true)} ·{participationText(row.participation)}
                      </span>
                    </div>
                    <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
                      <span className={`badge ${row.feedback ? "badge-done" : "badge-pending"}`}>{row.feedback ? "Submitted" : "Awaiting feedback"}</span>
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
                    <details open={focused && row.activity_id === focusActivityId}>
                      <summary>View feedback</summary>
                      <ActivityFeedbackDetails feedback={row.feedback} zone="school" />
                    </details>
                  )}
                  {openId === row.activity_id && (
                    <ActivityFeedbackForm activity={row} onSubmitted={(feedback) => onSubmitted(row, feedback)} onDuplicate={(text) => onDuplicate(row, text)} onCancel={() => onCancel(row.activity_id)} />
                  )}
                  {unsent[row.activity_id] && (
                    <UnsentFeedbackNote
                      unsent={unsent[row.activity_id]}
                      onDismiss={() => setUnsent((prev) => Object.fromEntries(Object.entries(prev).filter(([id]) => id !== row.activity_id)))}
                    />
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
