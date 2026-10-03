"use client";

import { useState } from "react";

import FormMessage from "@/components/FormMessage";
import { teamTripUrl, type Trip } from "@/lib/bdmTravel";
import { refocus } from "@/lib/focus";
import { jsonInit, useTripWrite } from "@/lib/useTripWrite";

const REJECT_ID = "trip-reject";

// bdm-010: approve, or reject with a required reason (Q-05). Shown only when the API says this caller may decide (T2/T3);
// the API checks again under a lock. The reason opens inline and takes focus; Escape backs out and returns focus to Reject.
export default function TripDecision({ trip }: { trip: Trip }) {
  const { busy, message, run } = useTripWrite();
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const [invalid, setInvalid] = useState(false);
  if (!trip.can_decide && !message) return null;

  const url = (verb: string) => `${teamTripUrl(trip.id)}/${verb}`;
  const close = () => {
    setRejecting(false);
    setInvalid(false);
    refocus(REJECT_ID);
  };
  async function reject(e: React.FormEvent) {
    e.preventDefault();
    if (!reason.trim()) return setInvalid(true);
    const outcome = await run(url("reject"), jsonInit("POST", { reason: reason.trim() }), "Trip not approved; the BDM has been told why.");
    if (outcome.ok) setRejecting(false);
  }

  return (
    <div>
      {trip.can_decide && !rejecting && (
        <div className="actions">
          <button type="button" className="btn" disabled={busy} onClick={() => run(url("approve"), { method: "POST" }, "Trip approved; the BDM has been told.")}>
            {busy ? "Saving…" : "Approve"}
          </button>
          <button id={REJECT_ID} type="button" className="btn secondary" disabled={busy} onClick={() => setRejecting(true)}>Reject</button>
        </div>
      )}
      {rejecting && (
        <form className="form form-warning" onSubmit={reject} onKeyDown={(e) => { if (e.key === "Escape" && !busy) close(); }} noValidate>
          <div className="field">
            <label htmlFor="trip-reject-reason">Reason for rejecting</label>
            <textarea id="trip-reject-reason" autoFocus rows={3} maxLength={1000} value={reason} onChange={(e) => setReason(e.target.value)}
              aria-invalid={invalid ? true : undefined} aria-describedby={invalid ? "trip-reject-reason-error" : undefined} />
            {invalid && <p className="form-error" id="trip-reject-reason-error">Reason is required</p>}
          </div>
          <div className="actions">
            <button type="submit" className="btn" disabled={busy}>{busy ? "Saving…" : "Confirm reject"}</button>
            <button type="button" className="btn secondary" disabled={busy} onClick={close}>Cancel</button>
          </div>
        </form>
      )}
      {message && <FormMessage message={message} style={{ marginTop: 12 }} />}
    </div>
  );
}
