"use client";
import { useRouter } from "next/navigation";
import { type FormEvent, useRef, useState } from "react";

import FormMessage, { type FormMessageState } from "@/components/FormMessage";
import { sendJson } from "@/lib/apiErrors";
import { indiaToday, type Visit, type VisitPermissions, visitUrl } from "@/lib/visits";

// upc-010 (§8, VS3-VS5): a visit's commands. Only the actions the API's `permissions` allow are shown; the API decides again under a
// lock. Reject, Complete and Close open an inline form (Reject and an early Close need a reason, Complete the follow-up date -- AC3);
// Escape backs out. Every success re-reads the page.
type Simple = { action: string; flag: keyof VisitPermissions; label: string; done: string; secondary?: boolean };
const SIMPLE: Simple[] = [
  { action: "submit", flag: "can_submit", label: "Submit for approval", done: "Submitted for approval." },
  { action: "approve", flag: "can_decide", label: "Approve", done: "Visit approved; the manager has been told." },
  { action: "book", flag: "can_book", label: "Mark travel booked", done: "Travel marked as booked." },
  { action: "follow-up", flag: "can_follow_up", label: "Start follow-up", done: "Follow-up started." },
];
type Prompt = "reject" | "complete" | "close";
const SAVE_FAILED = "The change could not be saved. Try again.";
const EARLY = new Set(["planned", "approved", "travel_booked"]);

export default function VisitActions({ visit: v }: { visit: Visit }) {
  const router = useRouter();
  const sending = useRef(false);
  const [busy, setBusy] = useState(false);
  const [prompt, setPrompt] = useState<Prompt | null>(null);
  const [value, setValue] = useState("");
  const [invalid, setInvalid] = useState(false);
  const [message, setMessage] = useState<FormMessageState | null>(null);
  const p = v.permissions;
  const simple = SIMPLE.filter((a) => p[a.flag]);
  if (!simple.length && !p.can_decide && !p.can_complete && !p.can_close && !message) return null;
  const earlyClose = EARLY.has(v.status);

  async function post(action: string, body: Record<string, string> | undefined, done: string) {
    if (sending.current) return;
    sending.current = true;
    setBusy(true);
    setMessage(null);
    const outcome = await sendJson(visitUrl(v.id, action), "POST", body ?? {});
    sending.current = false;
    setBusy(false);
    if (outcome.ok) {
      setPrompt(null);
      setValue("");
      setMessage({ text: done, failed: false });
      router.refresh();
      return;
    }
    // A response without a readable detail (e.g. a 500) gets a plain sentence; a dropped request keeps NOT_COMPLETED.
    setMessage({ text: outcome.status !== undefined && outcome.detail === undefined ? SAVE_FAILED : outcome.message, failed: true });
  }
  const open = (next: Prompt) => {
    setPrompt(next);
    setValue("");
    setInvalid(false);
    setMessage(null);
  };
  function confirm(event: FormEvent) {
    event.preventDefault();
    const text = value.trim();
    const needed = prompt === "reject" || prompt === "complete" || earlyClose;
    if (needed && !text) return setInvalid(true);
    if (prompt === "reject") void post("reject", { reason: text }, "Visit returned; the manager has been told why.");
    else if (prompt === "complete") void post("complete", { follow_up_date: text }, "Visit completed. The follow-up date is set.");
    else void post("close", text ? { reason: text } : undefined, "Visit closed.");
  }

  const promptText = {
    reject: { label: "Reason for returning the visit", error: "A reason is required", confirm: "Confirm reject" },
    complete: { label: "Follow-up date", error: "Choose the follow-up date", confirm: "Confirm completed" },
    close: earlyClose
      ? { label: "Why is the visit closed without taking place?", error: "A reason is required", confirm: "Confirm close" }
      : { label: "Closing note (optional)", error: "", confirm: "Confirm close" },
  };
  const current = prompt && promptText[prompt];

  return (
    <div>
      {!prompt && (
        <div className="actions">
          {simple.map((a) => (
            <button key={a.action} type="button" className="btn" disabled={busy} onClick={() => void post(a.action, undefined, a.done)}>{a.label}</button>
          ))}
          {p.can_decide && <button type="button" className="btn secondary" disabled={busy} onClick={() => open("reject")}>Reject</button>}
          {p.can_complete && <button type="button" className="btn" disabled={busy} onClick={() => open("complete")}>Mark visit completed</button>}
          {p.can_close && <button type="button" className="btn ghost" disabled={busy} onClick={() => open("close")}>Close visit</button>}
        </div>
      )}
      {prompt && current && (
        <form className="form form-warning" onSubmit={confirm} noValidate onKeyDown={(e) => { if (e.key === "Escape" && !busy) setPrompt(null); }}>
          <div className="field">
            <label htmlFor="visit-prompt">{current.label}</label>
            {prompt === "complete" ? (
              <input id="visit-prompt" type="date" autoFocus min={indiaToday()} value={value} onChange={(e) => setValue(e.target.value)}
                aria-invalid={invalid || undefined} aria-describedby={invalid ? "visit-prompt-error" : undefined} />
            ) : (
              <textarea id="visit-prompt" autoFocus rows={3} maxLength={1000} value={value} onChange={(e) => setValue(e.target.value)}
                aria-invalid={invalid || undefined} aria-describedby={invalid ? "visit-prompt-error" : undefined} />
            )}
            {invalid && <p className="form-error" id="visit-prompt-error">{current.error}</p>}
          </div>
          <div className="actions">
            <button type="submit" className="btn" disabled={busy}>{busy ? "Saving…" : current.confirm}</button>
            <button type="button" className="btn secondary" disabled={busy} onClick={() => setPrompt(null)}>Cancel</button>
          </div>
        </form>
      )}
      {message && <FormMessage message={message} style={{ marginTop: 12 }} />}
    </div>
  );
}
