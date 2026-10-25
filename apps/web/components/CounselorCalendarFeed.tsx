"use client";

import { useRef, useState } from "react";

import { sendRequest } from "@/lib/apiErrors";
import { CALENDAR_FEED_API, REGENERATE_PROMPT, REVOKE_PROMPT, type CalendarFeedStatus } from "@/lib/counselorCalendar";
import { formatDate } from "@/lib/formatDate";

// ccrm-038 (CA4): create, copy, regenerate or turn off the counselor's calendar feed. The link is shown once, right after it is made;
// a regenerate or turn-off asks first because every subscribed calendar stops updating.
export default function CounselorCalendarFeed({ initial }: { initial: CalendarFeedStatus }) {
  const [feed, setFeed] = useState(initial);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const sending = useRef(false); // one request per double click
  const linkRef = useRef<HTMLInputElement>(null);

  async function run(method: "POST" | "DELETE", prompt?: string) {
    if (sending.current || (prompt && !window.confirm(prompt))) return;
    sending.current = true;
    setBusy(true);
    setError(null);
    setNotice(null);
    const outcome = await sendRequest(CALENDAR_FEED_API, { method, credentials: "include" });
    sending.current = false;
    setBusy(false);
    if (!outcome.ok) return setError(outcome.message);
    if (method === "DELETE") {
      setFeed({ active: false, created_at: null, url: null });
      return setNotice("The calendar feed is off. The old link no longer works.");
    }
    setFeed(outcome.data as CalendarFeedStatus);
    setNotice("Your calendar link is ready. Copy it now: for your security it is shown only once.");
    requestAnimationFrame(() => linkRef.current?.select());
  }

  async function copy() {
    if (!feed.url) return;
    try {
      await navigator.clipboard.writeText(feed.url);
      setNotice("Link copied. Paste it into your calendar app's “subscribe to calendar” option.");
    } catch {
      linkRef.current?.select();
      setNotice("Copy the selected link by hand (Ctrl+C or long-press).");
    }
  }

  return (
    <section className="action-card" aria-labelledby="calendar-feed-heading" style={{ display: "grid", gap: 12, maxWidth: 720 }}>
      <h3 id="calendar-feed-heading" style={{ margin: 0 }}>Calendar feed</h3>
      <p className="muted" style={{ margin: 0 }}>
        Subscribe to this private link in Google Calendar, Outlook or Apple Calendar to see your counselling appointments and your students&apos; visa
        appointments. It is read-only: changes made in your calendar app do not come back to EduSphere.
      </p>
      <p style={{ margin: 0 }}>
        <strong>Status:</strong> {feed.active ? `On (link created ${formatDate(feed.created_at!)})` : "Off"}
      </p>
      {feed.url && (
        <div className="field">
          <label htmlFor="calendar-feed-url">Your calendar link</label>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <input id="calendar-feed-url" ref={linkRef} readOnly value={feed.url} style={{ flex: "1 1 260px", minWidth: 0 }} onFocus={(e) => e.currentTarget.select()} />
            <button type="button" className="btn secondary" onClick={copy}>Copy link</button>
          </div>
          <p className="muted" style={{ fontSize: 13, margin: "6px 0 0" }}>Anyone with this link can see these appointments. Don&apos;t share it.</p>
        </div>
      )}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {feed.active ? (
          <>
            <button type="button" className="btn secondary" onClick={() => run("POST", REGENERATE_PROMPT)} disabled={busy}>Create a new link</button>
            <button type="button" className="btn secondary" onClick={() => run("DELETE", REVOKE_PROMPT)} disabled={busy}>Turn off feed</button>
          </>
        ) : (
          <button type="button" className="btn" onClick={() => run("POST")} disabled={busy}>Create calendar link</button>
        )}
      </div>
      <p role="status" aria-live="polite" style={{ margin: 0 }}>{notice}</p>
      {error && <p className="form-error" role="alert" style={{ margin: 0 }}>{error}</p>}
    </section>
  );
}
