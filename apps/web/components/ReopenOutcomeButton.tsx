"use client";

import { FormEvent, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { sendJson } from "@/lib/apiErrors";

// `closed` false: nothing to reopen -- only a confirmation from an earlier reopen still shows.
type Props = { applicationId: string; action: "Resume" | "Reopen"; closed?: boolean; onDone?: (message: string) => void };

// ccrm-015 (DEC-SCOPE-244): clear an application's outcome with a reason -- "Resume" (on hold / deferred: counselor or Admin) or
// "Reopen" (a closed application: the Overseas Admin's table). The server decides who may.
export default function ReopenOutcomeButton({ applicationId, action, closed = true, onDone }: Props) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);
  const inFlight = useRef(false);
  const fieldId = `reopen-reason-${applicationId}`;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (inFlight.current || !reason.trim()) return;
    inFlight.current = true;
    setBusy(true);
    const result = await sendJson(`/api/v1/workflows/overseas/applications/${applicationId}/outcome/reopen`, "POST", { reason: reason.trim() });
    inFlight.current = false;
    setBusy(false);
    if (!result.ok) return setMessage({ text: result.message, failed: true });
    const text = action === "Resume" ? "Application resumed." : "Application reopened.";
    setOpen(false);
    setReason("");
    if (onDone) onDone(text); // the card shows it
    else setMessage({ text, failed: false });
    router.refresh();
  }

  return (
    <div>
      {open ? (
        <form className="form" onSubmit={submit} aria-label={`${action} application`} onKeyDown={(event) => event.key === "Escape" && !busy && setOpen(false)}>
          <div className="field">
            <label htmlFor={fieldId}>Reason</label>
            <textarea id={fieldId} value={reason} required maxLength={2000} onChange={(event) => setReason(event.target.value)} autoFocus />
          </div>
          <div className="actions">
            <button className="btn small" disabled={busy || !reason.trim()}>{busy ? "Saving…" : action}</button>
            <button type="button" className="btn ghost small" disabled={busy} onClick={() => setOpen(false)}>Cancel</button>
          </div>
        </form>
      ) : (
        closed && <button type="button" className="btn small secondary" onClick={() => (setOpen(true), setMessage(null))}>{action}</button>
      )}
      {message && <p className={message.failed ? "form-error" : "form-message"} role={message.failed ? "alert" : "status"}>{message.text}</p>}
    </div>
  );
}
