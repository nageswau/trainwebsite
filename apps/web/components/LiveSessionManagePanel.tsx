"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import LocalTime from "@/components/LocalTime";
import type { LiveSessionInfo } from "@/lib/types";

// nehn-029 (docs/superpowers/specs/2026-10-26-nehn-029-live-class-reschedule-cancel-design.md): the trainer reschedules or cancels a
// live class that has not started. Times are edited in the batch's own zone (the API reads a zone-less value the same way, as on
// create), so a trainer abroad still moves the class in the batch's local time. Google Meet/Zoho events are not changed by EduSphere:
// the API's warning tells the trainer to update the provider by hand.

const API = "/api/v1/communications/it/live-sessions";
type Mode = { id: string; action: "reschedule" | "cancel" } | null;
type Result = { warning?: string | null; attendance_records?: number; detail?: unknown };

function zoneOf(session: LiveSessionInfo) {
  return session.timezone || "Asia/Kolkata";
}

/** An instant as a datetime-local value in `zone` ("YYYY-MM-DDTHH:mm"). */
export function toZoneInput(iso: string | null, zone: string): string {
  if (!iso) return "";
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-CA", { timeZone: zone, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" })
      .formatToParts(new Date(iso))
      .map(part => [part.type, part.value]),
  );
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
}

function errorText(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map(item => item?.msg || "Invalid input").join("; ");
  return "The change could not be saved.";
}

export default function LiveSessionManagePanel() {
  const router = useRouter();
  const [sessions, setSessions] = useState<LiveSessionInfo[] | null>(null);
  const [loadError, setLoadError] = useState("");
  const [mode, setMode] = useState<Mode>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);
  const feedbackRef = useRef<HTMLDivElement>(null);

  async function load() {
    try {
      const response = await fetch(API);
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(errorText(data.detail));
      setSessions(data);
      setLoadError("");
    } catch (error) {
      setSessions([]);
      setLoadError(error instanceof Error ? error.message : "Unable to load live sessions");
    }
  }

  useEffect(() => { void load(); }, []);
  useEffect(() => { if (message) feedbackRef.current?.focus(); }, [message]);

  async function send(event: FormEvent<HTMLFormElement>, path: string, method: "PATCH" | "POST", body: Record<string, unknown>, done: (result: Result) => string) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      const response = await fetch(path, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const data: Result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(errorText(data.detail));
      setMode(null);
      setMessage({ text: done(data), failed: false });
      await load();
      router.refresh();
    } catch (error) {
      setMessage({ text: error instanceof Error ? error.message : "The change could not be saved.", failed: true });
    } finally {
      setBusy(false);
    }
  }

  function reschedule(event: FormEvent<HTMLFormElement>, session: LiveSessionInfo) {
    const form = new FormData(event.currentTarget);
    const zone = zoneOf(session);
    const now = { title: session.title, starts_at: toZoneInput(session.starts_at, zone), ends_at: toZoneInput(session.ends_at, zone), meeting_url: session.meeting_url || "" };
    const changed = Object.fromEntries(Object.entries(now).flatMap(([key, before]) => {
      const value = String(form.get(key) ?? "").trim();
      return value && value !== before ? [[key, value]] : [];
    }));
    if (!Object.keys(changed).length) {
      event.preventDefault();
      setMessage({ text: "Nothing was changed.", failed: true });
      return;
    }
    void send(event, `${API}/${session.id}`, "PATCH", changed, result => ["Live class updated. Enrolled learners have been notified.", result.warning].filter(Boolean).join(" "));
  }

  function cancel(event: FormEvent<HTMLFormElement>, session: LiveSessionInfo) {
    const reason = String(new FormData(event.currentTarget).get("reason") ?? "").trim();
    if (reason.length < 3) {
      event.preventDefault();
      setMessage({ text: "Enter a reason of at least 3 characters.", failed: true });
      return;
    }
    void send(event, `${API}/${session.id}/cancel`, "POST", { reason }, result => [
      "Live class cancelled. Enrolled learners have been notified.",
      result.attendance_records ? `Attendance already marked for ${result.attendance_records} learner(s) on that date is kept.` : "",
      result.warning,
    ].filter(Boolean).join(" "));
  }

  const nowMs = Date.now();
  const upcoming = (sessions || []).filter(s => s.status !== "cancelled" && new Date(s.starts_at).getTime() > nowMs).sort((a, b) => a.starts_at.localeCompare(b.starts_at));
  const cancelled = (sessions || []).filter(s => s.status === "cancelled");

  return (
    <div className="action-card">
      <h3>Reschedule or cancel a live class</h3>
      <p className="muted">Only classes that have not started can be changed. Learners are notified in the app and by email.</p>
      {message && (
        <div ref={feedbackRef} tabIndex={-1} className={message.failed ? "form-error" : "form-message"} role={message.failed ? "alert" : "status"} aria-live={message.failed ? "assertive" : "polite"}>
          {message.text}
        </div>
      )}
      {sessions === null && <p className="muted">Loading live sessions…</p>}
      {loadError && <p className="form-error" role="alert">{loadError}</p>}
      {sessions !== null && !loadError && !upcoming.length && <p className="muted">No upcoming live class can be changed.</p>}
      {upcoming.map(session => {
        const zone = zoneOf(session);
        const open = mode?.id === session.id ? mode.action : null;
        const titleId = `manage-${session.id}`;
        return (
          <section className="card" key={session.id} aria-labelledby={titleId} style={{ marginTop: 12 }}>
            <span className="badge">{session.batch}</span>
            <h4 id={titleId} style={{ marginTop: 8 }}>{session.title}</h4>
            <p className="muted" style={{ fontSize: 13 }}><LocalTime value={session.starts_at} time label /></p>
            <div className="actions">
              <button type="button" className="btn small secondary" aria-expanded={open === "reschedule"} disabled={busy} onClick={() => { setMessage(null); setMode(open === "reschedule" ? null : { id: session.id, action: "reschedule" }); }}>Reschedule</button>
              <button type="button" className="btn small ghost" aria-expanded={open === "cancel"} disabled={busy} onClick={() => { setMessage(null); setMode(open === "cancel" ? null : { id: session.id, action: "cancel" }); }}>Cancel class</button>
            </div>
            {open === "reschedule" && (
              <form className="form" aria-label={`Reschedule ${session.title}`} onSubmit={event => reschedule(event, session)} style={{ marginTop: 12 }}>
                <div className="field"><label htmlFor={`${titleId}-title`}>Session title</label><input id={`${titleId}-title`} name="title" defaultValue={session.title} minLength={2} maxLength={180} required /></div>
                <div className="field"><label htmlFor={`${titleId}-start`}>Starts ({zone})</label><input id={`${titleId}-start`} name="starts_at" type="datetime-local" defaultValue={toZoneInput(session.starts_at, zone)} required /></div>
                <div className="field"><label htmlFor={`${titleId}-end`}>Ends ({zone})</label><input id={`${titleId}-end`} name="ends_at" type="datetime-local" defaultValue={toZoneInput(session.ends_at, zone)} required /></div>
                <div className="field"><label htmlFor={`${titleId}-url`}>Meeting link</label><input id={`${titleId}-url`} name="meeting_url" type="url" defaultValue={session.meeting_url || ""} maxLength={500} /></div>
                <div className="actions">
                  <button className="btn small" disabled={busy}>{busy ? "Saving…" : "Save changes"}</button>
                  <button type="button" className="btn small ghost" onClick={() => setMode(null)}>Close</button>
                </div>
              </form>
            )}
            {open === "cancel" && (
              <form className="form" aria-label={`Cancel ${session.title}`} onSubmit={event => cancel(event, session)} style={{ marginTop: 12 }}>
                <div className="field full"><label htmlFor={`${titleId}-reason`}>Reason learners will see</label><textarea id={`${titleId}-reason`} name="reason" minLength={3} maxLength={500} required /></div>
                <div className="actions">
                  <button className="btn small" disabled={busy}>{busy ? "Cancelling…" : "Confirm cancellation"}</button>
                  <button type="button" className="btn small ghost" onClick={() => setMode(null)}>Keep class</button>
                </div>
              </form>
            )}
          </section>
        );
      })}
      {cancelled.length > 0 && (
        <>
          <h4 style={{ marginTop: 20 }}>Cancelled classes</h4>
          <ul>
            {cancelled.map(session => (
              <li key={session.id} style={{ fontSize: 13 }}>
                <span className="status error">Cancelled</span> {session.title} · {session.batch} · <LocalTime value={session.starts_at} time label /> — {session.cancel_reason || "No reason given"}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
