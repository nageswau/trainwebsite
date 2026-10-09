"use client";
import { useRouter } from "next/navigation";
import { type FormEvent, useRef, useState } from "react";

import FormMessage, { type FormMessageState } from "@/components/FormMessage";
import { sendJson } from "@/lib/apiErrors";
import { fieldErrors } from "@/lib/bdmPipeline";
import { LIMITS, type Meeting, meetingUrl } from "@/lib/meetings";
import { indiaToday } from "@/lib/visits";

// upc-009 (MG9-MG12): a scheduled meeting's commands. Only what the API's `permissions` allow is shown; the API decides again under a
// lock. Record outcome opens an inline form (notes / discussion points / decisions, the next action with its due date -- a follow-up, AC2
// -- and the next meeting date, Q-12); Cancel asks for a reason. Escape backs out. Every success re-reads the page; until the re-read
// meeting arrives (a new `updated_at`) the old actions stay hidden, so a quick second click can't hit a stale state (upc-010 QA-I1).
type Prompt = "complete" | "cancel";
const OUTCOME = ["notes", "discussion_points", "decisions", "next_action", "next_action_due_on", "next_meeting_date"] as const;
type Outcome = Record<(typeof OUTCOME)[number], string>;
const EMPTY: Outcome = { notes: "", discussion_points: "", decisions: "", next_action: "", next_action_due_on: "", next_meeting_date: "" };
const LABELS: Record<keyof Outcome, string> = {
  notes: "Notes", discussion_points: "Discussion points", decisions: "Decisions", next_action: "Next action",
  next_action_due_on: "Next action due date", next_meeting_date: "Next meeting date",
};
const SAVE_FAILED = "The change could not be saved. Try again.";

export default function MeetingActions({ meeting: m }: { meeting: Meeting }) {
  const router = useRouter();
  const sending = useRef(false);
  const [busy, setBusy] = useState(false);
  const [prompt, setPrompt] = useState<Prompt | null>(null);
  const [outcome, setOutcome] = useState<Outcome>(EMPTY);
  const [reason, setReason] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<FormMessageState | null>(null);
  const [staleAt, setStaleAt] = useState<string | null>(null);
  const p = m.permissions;
  if (!p.can_complete && !p.can_cancel && !message) return null;
  const stale = staleAt === m.updated_at;

  const open = (next: Prompt) => {
    setPrompt(next);
    setOutcome(EMPTY);
    setReason("");
    setErrors({});
    setMessage(null);
  };

  async function post(action: Prompt, body: Record<string, string>, done: string) {
    if (sending.current) return;
    sending.current = true;
    setBusy(true);
    setMessage(null);
    const result = await sendJson(meetingUrl(m.id, action), "POST", body);
    sending.current = false;
    setBusy(false);
    if (result.ok) {
      setPrompt(null);
      setStaleAt(m.updated_at);
      setMessage({ text: done, failed: false });
      router.refresh();
      return;
    }
    const mapped = result.status === 422 ? fieldErrors(result.detail) : {};
    setErrors(mapped);
    // A 422 on a field is shown there; a response without a readable detail (e.g. a 500) gets a plain sentence.
    const text = Object.keys(mapped).some((k) => k in LABELS || k === "reason") ? "Check the highlighted fields."
      : result.status !== undefined && result.detail === undefined ? SAVE_FAILED : result.message;
    setMessage({ text, failed: true });
  }

  function confirm(event: FormEvent) {
    event.preventDefault();
    if (prompt === "cancel") {
      if (!reason.trim()) return setErrors({ reason: "A reason is required" });
      return void post("cancel", { reason: reason.trim() }, "Meeting cancelled.");
    }
    const values = Object.fromEntries(OUTCOME.map((k) => [k, outcome[k].trim()])) as Outcome;
    const missing: Record<string, string> = {};
    if (!values.notes && !values.discussion_points && !values.decisions) missing.notes = "Record notes, discussion points or decisions";
    if (values.next_action && !values.next_action_due_on) missing.next_action_due_on = "Choose when the next action is due";
    if (values.next_action_due_on && !values.next_action) missing.next_action = "Describe the next action";
    setErrors(missing);
    if (Object.keys(missing).length) return;
    void post("complete", Object.fromEntries(Object.entries(values).filter(([, v]) => v)), "Outcome recorded.");
  }

  const a11y = (name: string) => (errors[name] ? { "aria-invalid": true as const, "aria-describedby": `meeting-${name}-error` } : {});
  const errorText = (name: string) => errors[name] && <p className="form-error" id={`meeting-${name}-error`}>{errors[name]}</p>;
  const outcomeField = (name: keyof Outcome) => {
    const set = (value: string) => setOutcome((o) => ({ ...o, [name]: value }));
    const dated = name === "next_action_due_on" || name === "next_meeting_date";
    return (
      <div className="field" key={name}>
        <label htmlFor={`meeting-${name}`}>{LABELS[name]}</label>
        {dated ? (
          <input id={`meeting-${name}`} type="date" min={indiaToday()} value={outcome[name]} onChange={(e) => set(e.target.value)} {...a11y(name)} />
        ) : name === "next_action" ? (
          <input id={`meeting-${name}`} maxLength={LIMITS.next_action} value={outcome[name]} placeholder="Becomes a follow-up task" onChange={(e) => set(e.target.value)} {...a11y(name)} />
        ) : (
          <textarea id={`meeting-${name}`} rows={3} maxLength={LIMITS[name]} value={outcome[name]} onChange={(e) => set(e.target.value)} {...a11y(name)} />
        )}
        {errorText(name)}
      </div>
    );
  };

  return (
    <div>
      {!prompt && !stale && (
        <>
          <div className="actions">
            {p.can_complete && <button type="button" className="btn" disabled={busy} onClick={() => open("complete")}>Record outcome</button>}
            {p.can_cancel && <button type="button" className="btn ghost" disabled={busy} onClick={() => open("cancel")}>Cancel meeting</button>}
          </div>
          {p.can_cancel && !p.can_complete && <p className="muted" style={{ margin: "8px 0 0" }}>You can record the outcome once the meeting has started.</p>}
        </>
      )}
      {prompt && (
        <form className="form form-warning" onSubmit={confirm} noValidate aria-label={prompt === "complete" ? "Record the meeting outcome" : "Cancel the meeting"}
          onKeyDown={(e) => { if (e.key === "Escape" && !busy) setPrompt(null); }}>
          {prompt === "complete" ? (
            <>
              <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))" }}>
                {outcomeField("notes")}
                {outcomeField("discussion_points")}
                {outcomeField("decisions")}
              </div>
              <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))" }}>
                {outcomeField("next_action")}
                {outcomeField("next_action_due_on")}
                {outcomeField("next_meeting_date")}
              </div>
              <p className="muted" style={{ margin: 0, fontSize: 13 }}>The next action and the next meeting date each become a follow-up for the responsible employee.</p>
            </>
          ) : (
            <div className="field">
              <label htmlFor="meeting-reason">Why is the meeting cancelled?</label>
              <textarea id="meeting-reason" autoFocus rows={3} maxLength={LIMITS.reason} value={reason} onChange={(e) => setReason(e.target.value)} {...a11y("reason")} />
              {errorText("reason")}
            </div>
          )}
          <div className="actions">
            <button type="submit" className="btn" disabled={busy}>{busy ? "Saving…" : prompt === "complete" ? "Save outcome" : "Confirm cancel"}</button>
            <button type="button" className="btn secondary" disabled={busy} onClick={() => setPrompt(null)}>Back</button>
          </div>
        </form>
      )}
      {message && <FormMessage message={message} style={{ marginTop: 12 }} />}
    </div>
  );
}
