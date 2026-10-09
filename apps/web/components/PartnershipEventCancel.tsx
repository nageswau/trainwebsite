"use client";
import { useRouter } from "next/navigation";
import { type FormEvent, useRef, useState } from "react";

import FormMessage, { type FormMessageState } from "@/components/FormMessage";
import { sendJson } from "@/lib/apiErrors";
import { fieldErrors } from "@/lib/bdmPipeline";
import { EVENT_LIMITS, eventUrl, type PartnershipEvent } from "@/lib/partnershipCalendar";

// upc-011 (CL6): cancel a scheduled event with a reason (it then leaves the calendar). Shown only when the API's `permissions` allow it;
// the API decides again under a lock. Escape backs out. A success re-reads the page; until the re-read event arrives (a new `updated_at`)
// the button stays hidden, so a quick second click can't hit a stale state (upc-010 QA-I1).
const SAVE_FAILED = "The change could not be saved. Try again.";

export default function PartnershipEventCancel({ event: e }: { event: PartnershipEvent }) {
  const router = useRouter();
  const sending = useRef(false);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<FormMessageState | null>(null);
  const [staleAt, setStaleAt] = useState<string | null>(null);
  if (!e.permissions.can_cancel && !message) return null;

  async function confirm(event: FormEvent) {
    event.preventDefault();
    if (sending.current) return;
    if (!reason.trim()) return setError("A reason is required");
    sending.current = true;
    setBusy(true);
    setMessage(null);
    const result = await sendJson(eventUrl(e.id, "cancel"), "POST", { reason: reason.trim() });
    sending.current = false;
    setBusy(false);
    if (result.ok) {
      setOpen(false);
      setStaleAt(e.updated_at);
      setMessage({ text: "Event cancelled.", failed: false });
      router.refresh();
      return;
    }
    const mapped = result.status === 422 ? fieldErrors(result.detail) : {};
    setError(mapped.reason ?? null);
    setMessage({ text: mapped.reason ? "Check the highlighted field." : result.status !== undefined && result.detail === undefined ? SAVE_FAILED : result.message, failed: true });
  }

  return (
    <div>
      {!open && staleAt !== e.updated_at && e.permissions.can_cancel && (
        <div className="actions">
          <button type="button" className="btn ghost" onClick={() => { setOpen(true); setReason(""); setError(null); setMessage(null); }}>Cancel event</button>
        </div>
      )}
      {open && (
        <form className="form form-warning" onSubmit={confirm} noValidate aria-label="Cancel the event" onKeyDown={(k) => { if (k.key === "Escape" && !busy) setOpen(false); }}>
          <div className="field">
            <label htmlFor="event-reason">Why is the event cancelled?</label>
            <textarea id="event-reason" autoFocus rows={3} maxLength={EVENT_LIMITS.reason} value={reason} onChange={(x) => setReason(x.target.value)}
              {...(error ? { "aria-invalid": true as const, "aria-describedby": "event-reason-error" } : {})} />
            {error && <p className="form-error" id="event-reason-error">{error}</p>}
          </div>
          <div className="actions">
            <button type="submit" className="btn" disabled={busy}>{busy ? "Saving…" : "Confirm cancel"}</button>
            <button type="button" className="btn secondary" disabled={busy} onClick={() => setOpen(false)}>Back</button>
          </div>
        </form>
      )}
      {message && <FormMessage message={message} style={{ marginTop: 12 }} />}
    </div>
  );
}
